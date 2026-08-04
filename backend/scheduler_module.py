"""EB-15 · Production Scheduling, Notification Providers & Automation.

Compact single-module implementation containing:
  • Scheduler service (registry, locks, job runs, events, health)
  • Notification provider adapters (Development, SMTP, SendGrid REST,
    Twilio REST) — production-capable but Development Outbox default
  • Delivery pipeline (attempts, retries with exponential backoff,
    dead-letter, circuit breaker, quiet hours, suppression)
  • Templates (versioned + immutable-when-approved)
  • Router with routes for scheduler, deliveries, providers, templates
  • Internal scheduler service-auth endpoint

Rules honoured:
  - No permanent in-process cron loop; jobs are triggered externally
    via `/api/internal/scheduler/{job_key}` (service-token auth) or by
    authorised users manually via `/api/automation/jobs/{key}/run`.
  - Development Outbox default; NOTIFICATION_DELIVERY_ENABLED=false.
  - No SDK installs; SendGrid & Twilio adapters use httpx REST.
  - No live network calls in tests (deterministic mocks).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field


# ── Collections ───────────────────────────────────────────────────────────────
DEFS_COLL = "scheduled_job_definitions"
RUNS_COLL = "scheduled_job_runs"
EVENTS_COLL = "scheduled_job_events"
LOCKS_COLL = "scheduled_job_locks"
HEALTH_COLL = "automation_health_snapshots"

ATTEMPTS_COLL = "notification_delivery_attempts"
PROVIDER_EV_COLL = "notification_provider_events"
SUPPRESS_COLL = "notification_suppression_events"
TEMPLATES_COLL = "notification_templates"
PROVIDER_HEALTH_COLL = "notification_provider_health"

DELIVERIES_COLL = "notification_deliveries"
NOTIFICATIONS_COLL = "notifications"

# ── Roles ────────────────────────────────────────────────────────────────────
ROLE_READONLY = {"ReadOnly", "Allocator", "Compliance", "Manager", "Admin"}
ROLE_ALLOCATOR = {"Allocator", "Compliance", "Manager", "Admin"}
ROLE_COMPLIANCE = {"Compliance", "Manager", "Admin"}
ROLE_MANAGER = {"Manager", "Admin"}
ROLE_ADMIN = {"Admin"}

# ── Helpers ──────────────────────────────────────────────────────────────────
def _uuid() -> str: return str(uuid.uuid4())
def _iso() -> str: return datetime.now(timezone.utc).isoformat()
def _strip(d):
    if not d: return d
    out = dict(d); out.pop("_id", None); return out
def _require(user: Dict[str, Any], allowed: set, err: str = "Forbidden"):
    if not user or user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=err)


# ═══════════════════════════════════════════════════════════════════════════
# Provider Adapters — production-capable, no SDK deps
# ═══════════════════════════════════════════════════════════════════════════
class ProviderResult(BaseModel):
    success: bool
    provider_message_id: Optional[str] = None
    provider_status: Optional[str] = None
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    transient: bool = False


class BaseEmailProvider:
    key = "base"
    async def send(self, *, to: str, subject: str, body_text: str,
                     body_html: Optional[str], from_addr: str, from_name: str) -> ProviderResult:
        raise NotImplementedError
    def validate(self) -> Optional[str]: return None
    def circuit_immune(self) -> bool: return False


class BaseSmsProvider:
    key = "base"
    async def send(self, *, to: str, body: str, from_number: str) -> ProviderResult:
        raise NotImplementedError
    def validate(self) -> Optional[str]: return None
    def circuit_immune(self) -> bool: return False


class DevelopmentEmailProvider(BaseEmailProvider):
    key = "development"
    async def send(self, *, to, subject, body_text, body_html, from_addr, from_name):
        return ProviderResult(success=True, provider_message_id=f"dev-{_uuid()[:12]}",
                                provider_status="dev-outbox")
    def circuit_immune(self) -> bool: return True


class DevelopmentSmsProvider(BaseSmsProvider):
    key = "development"
    async def send(self, *, to, body, from_number):
        return ProviderResult(success=True, provider_message_id=f"dev-{_uuid()[:12]}",
                                provider_status="dev-outbox")
    def circuit_immune(self) -> bool: return True


class SMTPEmailProvider(BaseEmailProvider):
    """Production-capable SMTP provider using stdlib smtplib.
    Never called in tests; validate() ensures config at startup.
    """
    key = "smtp"
    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "")
        self.port = int(os.environ.get("SMTP_PORT", "587") or "587")
        self.user = os.environ.get("SMTP_USERNAME", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.use_tls = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
        self.timeout = int(os.environ.get("SMTP_TIMEOUT_SECONDS", "20") or "20")

    def validate(self) -> Optional[str]:
        missing = [k for k, v in [("SMTP_HOST", self.host), ("SMTP_USERNAME", self.user),
                                     ("SMTP_PASSWORD", self.password)] if not v]
        return f"Missing SMTP config: {', '.join(missing)}" if missing else None

    def _send_sync(self, msg: MIMEMultipart, to: str):
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as s:
            if self.use_tls: s.starttls()
            s.login(self.user, self.password)
            s.sendmail(msg["From"], [to], msg.as_string())

    async def send(self, *, to, subject, body_text, body_html, from_addr, from_name):
        err = self.validate()
        if err: return ProviderResult(success=False, failure_code="config",
                                          failure_reason=err, transient=False)
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{from_addr}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))
        if body_html: msg.attach(MIMEText(body_html, "html", "utf-8"))
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._send_sync, msg, to)
            return ProviderResult(success=True,
                                    provider_message_id=f"smtp-{_uuid()[:12]}",
                                    provider_status="accepted")
        except smtplib.SMTPRecipientsRefused:
            return ProviderResult(success=False, failure_code="invalid_recipient",
                                    failure_reason="recipient refused", transient=False)
        except smtplib.SMTPAuthenticationError:
            return ProviderResult(success=False, failure_code="auth",
                                    failure_reason="smtp auth failed", transient=False)
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                  TimeoutError, OSError) as e:
            return ProviderResult(success=False, failure_code="transient",
                                    failure_reason=str(e)[:180], transient=True)
        except smtplib.SMTPException as e:
            return ProviderResult(success=False, failure_code="provider",
                                    failure_reason=str(e)[:180], transient=True)


class SendGridEmailProvider(BaseEmailProvider):
    """Production-capable SendGrid REST v3 provider via httpx (no SDK)."""
    key = "sendgrid"
    ENDPOINT = "https://api.sendgrid.com/v3/mail/send"

    def __init__(self):
        self.api_key = os.environ.get("SENDGRID_API_KEY", "")
        self.timeout = float(os.environ.get("SENDGRID_TIMEOUT", "15") or "15")

    def validate(self) -> Optional[str]:
        return None if self.api_key else "Missing SENDGRID_API_KEY"

    async def send(self, *, to, subject, body_text, body_html, from_addr, from_name):
        err = self.validate()
        if err: return ProviderResult(success=False, failure_code="config",
                                          failure_reason=err, transient=False)
        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": from_addr, "name": from_name},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body_text}],
        }
        if body_html:
            payload["content"].append({"type": "text/html", "value": body_html})
        headers = {"Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(self.ENDPOINT, json=payload, headers=headers)
            if 200 <= r.status_code < 300:
                mid = r.headers.get("X-Message-Id") or f"sg-{_uuid()[:12]}"
                return ProviderResult(success=True, provider_message_id=mid,
                                          provider_status=str(r.status_code))
            if r.status_code in (400, 401, 403):
                return ProviderResult(success=False,
                                          failure_code=f"sg-{r.status_code}",
                                          failure_reason=r.text[:180],
                                          transient=False)
            return ProviderResult(success=False,
                                      failure_code=f"sg-{r.status_code}",
                                      failure_reason=r.text[:180],
                                      transient=True)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            return ProviderResult(success=False, failure_code="transient",
                                      failure_reason=str(e)[:180], transient=True)


class TwilioSmsProvider(BaseSmsProvider):
    """Production-capable Twilio REST provider via httpx (no SDK)."""
    key = "twilio"
    BASE = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"

    def __init__(self):
        self.sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
        self.token = os.environ.get("TWILIO_AUTH_TOKEN", "")
        self.timeout = float(os.environ.get("TWILIO_TIMEOUT", "15") or "15")

    def validate(self) -> Optional[str]:
        missing = [k for k, v in [("TWILIO_ACCOUNT_SID", self.sid),
                                       ("TWILIO_AUTH_TOKEN", self.token)] if not v]
        return f"Missing Twilio config: {', '.join(missing)}" if missing else None

    async def send(self, *, to, body, from_number):
        err = self.validate()
        if err: return ProviderResult(success=False, failure_code="config",
                                          failure_reason=err, transient=False)
        auth = base64.b64encode(f"{self.sid}:{self.token}".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                r = await c.post(self.BASE.format(sid=self.sid),
                                    data={"To": to, "From": from_number, "Body": body},
                                    headers={"Authorization": f"Basic {auth}"})
            if 200 <= r.status_code < 300:
                mid = r.json().get("sid") or f"tw-{_uuid()[:12]}"
                return ProviderResult(success=True, provider_message_id=mid,
                                          provider_status=str(r.status_code))
            if r.status_code in (400, 401, 403):
                return ProviderResult(success=False,
                                          failure_code=f"tw-{r.status_code}",
                                          failure_reason=r.text[:180],
                                          transient=False)
            return ProviderResult(success=False,
                                      failure_code=f"tw-{r.status_code}",
                                      failure_reason=r.text[:180],
                                      transient=True)
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            return ProviderResult(success=False, failure_code="transient",
                                      failure_reason=str(e)[:180], transient=True)


# ═══════════════════════════════════════════════════════════════════════════
# Provider Registry
# ═══════════════════════════════════════════════════════════════════════════
class ProviderRegistry:
    def __init__(self):
        self.email = self._select_email()
        self.sms = self._select_sms()

    def _select_email(self) -> BaseEmailProvider:
        key = os.environ.get("EMAIL_PROVIDER", "development").lower()
        if key == "smtp": return SMTPEmailProvider()
        if key == "sendgrid": return SendGridEmailProvider()
        return DevelopmentEmailProvider()

    def _select_sms(self) -> BaseSmsProvider:
        key = os.environ.get("SMS_PROVIDER", "development").lower()
        if key == "twilio": return TwilioSmsProvider()
        return DevelopmentSmsProvider()

    def status(self) -> List[dict]:
        rows = []
        for p in (self.email, self.sms):
            err = p.validate()
            rows.append({
                "provider_key": p.key,
                "channel": "email" if isinstance(p, BaseEmailProvider) else "sms",
                "configured": err is None,
                "config_error": err,
                "immune_from_circuit": p.circuit_immune(),
            })
        return rows


# ═══════════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════════
CB_THRESHOLD = int(os.environ.get("NOTIFICATION_CIRCUIT_THRESHOLD", "5") or "5")
CB_HALFOPEN_AFTER_SECONDS = int(os.environ.get("NOTIFICATION_CIRCUIT_HALFOPEN_SECONDS", "300") or "300")


class CircuitBreaker:
    def __init__(self, db): self.db = db

    async def _row(self, provider_key: str) -> dict:
        r = await self.db[PROVIDER_HEALTH_COLL].find_one(
            {"provider_key": provider_key}, {"_id": 0})
        if r: return r
        doc = {"provider_key": provider_key, "state": "closed",
                 "consecutive_failures": 0, "opened_at": None,
                 "last_probe_at": None, "created_at": _iso()}
        await self.db[PROVIDER_HEALTH_COLL].insert_one(doc)
        return doc

    async def state(self, provider_key: str) -> str:
        r = await self._row(provider_key)
        if r["state"] == "open" and r.get("opened_at"):
            try:
                opened = datetime.fromisoformat(r["opened_at"])
                if (datetime.now(timezone.utc) - opened).total_seconds() >= CB_HALFOPEN_AFTER_SECONDS:
                    await self.db[PROVIDER_HEALTH_COLL].update_one(
                        {"provider_key": provider_key}, {"$set": {"state": "half-open"}})
                    return "half-open"
            except Exception: pass
        return r["state"]

    async def on_success(self, provider_key: str):
        await self.db[PROVIDER_HEALTH_COLL].update_one(
            {"provider_key": provider_key},
            {"$set": {"state": "closed", "consecutive_failures": 0,
                       "opened_at": None, "last_probe_at": _iso()}}, upsert=True)

    async def on_failure(self, provider_key: str, transient: bool, immune: bool):
        if immune: return
        r = await self._row(provider_key)
        fails = (r.get("consecutive_failures") or 0) + (1 if transient else 0)
        update = {"consecutive_failures": fails, "last_failure_at": _iso()}
        if transient and fails >= CB_THRESHOLD:
            update.update({"state": "open", "opened_at": _iso()})
        await self.db[PROVIDER_HEALTH_COLL].update_one(
            {"provider_key": provider_key}, {"$set": update}, upsert=True)

    async def reset(self, provider_key: str, actor: str):
        await self.db[PROVIDER_HEALTH_COLL].update_one(
            {"provider_key": provider_key},
            {"$set": {"state": "closed", "consecutive_failures": 0,
                       "opened_at": None, "manual_reset_by": actor,
                       "manual_reset_at": _iso()}}, upsert=True)


# ═══════════════════════════════════════════════════════════════════════════
# Delivery Pipeline
# ═══════════════════════════════════════════════════════════════════════════
def _backoff_seconds(attempt: int) -> int:
    base = int(os.environ.get("NOTIFICATION_BASE_RETRY_SECONDS", "300") or "300")
    schedule = [0, base, base * 3, base * 12, base * 48]
    if attempt < len(schedule): return schedule[attempt]
    return schedule[-1]


def _mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email: return "***"
    local, dom = email.split("@", 1)
    return f"{local[:2]}***@{dom}"


def _mask_phone(phone: Optional[str]) -> str:
    if not phone: return "***"
    p = re.sub(r"\D", "", phone)
    return f"***{p[-3:]}" if len(p) >= 3 else "***"


def _quiet_hours_now(channel: str, priority: str) -> bool:
    """Return True if current time falls in configured quiet hours for this
    channel/priority. Uses Australia/Melbourne per default."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(os.environ.get("NOTIFICATION_TIMEZONE", "Australia/Melbourne"))
    except Exception:
        return False
    now = datetime.now(tz)
    start = int(os.environ.get("NOTIFICATION_QUIET_HOURS_START", "21") or "21")
    end = int(os.environ.get("NOTIFICATION_QUIET_HOURS_END", "7") or "7")
    hour = now.hour
    in_quiet = (hour >= start or hour < end) if start > end else (start <= hour < end)
    if not in_quiet: return False
    # Critical priority may override for email/in-app but never SMS during quiet
    if priority == "Critical" and channel != "SMS":
        return os.environ.get("NOTIFICATION_CRITICAL_OVERRIDES_QUIET", "true").lower() != "true"
    return True


class DeliveryService:
    def __init__(self, db, providers: ProviderRegistry):
        self.db = db
        self.providers = providers
        self.cb = CircuitBreaker(db)
        self.delivery_enabled = os.environ.get("NOTIFICATION_DELIVERY_ENABLED", "false").lower() == "true"
        self.test_mode = os.environ.get("NOTIFICATION_TEST_MODE", "true").lower() == "true"
        self.allowlist = [x.strip().lower() for x in
                             os.environ.get("NOTIFICATION_ALLOWLIST", "").split(",") if x.strip()]
        self.max_attempts = int(os.environ.get("NOTIFICATION_MAX_ATTEMPTS", "5") or "5")
        self.from_addr = os.environ.get("EMAIL_FROM_ADDRESS", "dcc-noreply@example.test")
        self.from_name = os.environ.get("EMAIL_FROM_NAME", "DCC Automation")
        self.from_sms = os.environ.get("TWILIO_FROM_NUMBER", "+15550000000")

    def _rewrite_recipient(self, kind: str, original: str) -> str:
        """Test mode rewrites recipients to allowlisted safe values."""
        if not self.test_mode: return original
        if not self.allowlist: return original
        for a in self.allowlist:
            if kind == "email" and "@" in a: return a
            if kind == "sms" and a.startswith("+"): return a
        return original

    async def dispatch_pending(self, correlation_id: Optional[str] = None,
                                 limit: int = 200) -> dict:
        """Idempotent dispatch — walks pending deliveries and attempts send.
        Only touches deliveries in delivery_status ∈ {Pending, Queued}."""
        stats = {"considered": 0, "sent": 0, "failed": 0, "suppressed": 0,
                  "queued_quiet_hours": 0, "circuit_blocked": 0}
        q = {"delivery_status": {"$in": ["Pending", "Queued", "Retry Scheduled"]}}
        rows = await self.db[DELIVERIES_COLL].find(q, {"_id": 0}).limit(limit).to_list(limit)
        for d in rows:
            stats["considered"] += 1
            result = await self._deliver_one(d, correlation_id)
            k = result["outcome"]
            stats[k] = stats.get(k, 0) + 1
        return stats

    async def _deliver_one(self, d: dict, correlation_id: Optional[str]) -> dict:
        did = d.get("notification_delivery_id")
        channel = (d.get("channel") or "").upper()
        # Load parent notification for context (priority etc.)
        notif = await self.db[NOTIFICATIONS_COLL].find_one(
            {"notification_id": d.get("notification_id")}, {"_id": 0})
        priority = (notif or {}).get("priority", "Normal")
        # Quiet hours evaluation
        if _quiet_hours_now(channel, priority):
            next_at = _iso()
            await self.db[DELIVERIES_COLL].update_one(
                {"notification_delivery_id": did},
                {"$set": {"delivery_status": "Retry Scheduled",
                           "next_retry_at": next_at, "suppression_reason": "quiet_hours"}})
            await self._suppression(did, "quiet_hours", correlation_id)
            return {"outcome": "queued_quiet_hours"}
        # Provider selection
        if channel == "EMAIL":
            provider = self.providers.email
            recipient = self._rewrite_recipient("email", d.get("email_address") or d.get("recipient_address") or "")
            if not recipient:
                await self._finalise_failed(did, "no_recipient", "no email", transient=False)
                return {"outcome": "failed"}
        elif channel == "SMS":
            provider = self.providers.sms
            recipient = self._rewrite_recipient("sms", d.get("mobile_number") or d.get("recipient_address") or "")
            if not recipient:
                await self._finalise_failed(did, "no_recipient", "no mobile", transient=False)
                return {"outcome": "failed"}
        else:  # in-app never leaves the system
            await self.db[DELIVERIES_COLL].update_one(
                {"notification_delivery_id": did},
                {"$set": {"delivery_status": "Sent", "sent_at": _iso(),
                           "provider": "in-app"}})
            return {"outcome": "sent"}
        # Circuit breaker check (skip for immune provider)
        immune = provider.circuit_immune()
        cb_state = "closed" if immune else await self.cb.state(provider.key)
        if cb_state == "open":
            next_at = (datetime.now(timezone.utc) + timedelta(seconds=CB_HALFOPEN_AFTER_SECONDS)).isoformat()
            await self.db[DELIVERIES_COLL].update_one(
                {"notification_delivery_id": did},
                {"$set": {"delivery_status": "Retry Scheduled",
                           "next_retry_at": next_at,
                           "suppression_reason": "circuit_open"}})
            return {"outcome": "circuit_blocked"}
        # Attempt
        attempt_num = int(d.get("attempts_made") or 0) + 1
        attempt_id = _uuid()
        started = _iso()
        # Development Outbox default: keep behaviour unless explicitly enabled
        if not self.delivery_enabled and not immune:
            # Force through development provider stub without touching real one
            result = ProviderResult(success=True, provider_message_id=f"outbox-{_uuid()[:8]}",
                                        provider_status="development-outbox")
        else:
            if channel == "EMAIL":
                # Render simple subject/body from notification data
                subject = (notif or {}).get("title") or "DCC Notification"
                body = (notif or {}).get("body_text") or (notif or {}).get("message") or "See DCC."
                if self.test_mode:
                    subject = f"[TEST MODE] {subject}"
                result = await provider.send(to=recipient, subject=subject,
                                                  body_text=body, body_html=None,
                                                  from_addr=self.from_addr,
                                                  from_name=self.from_name)
            else:
                body = (notif or {}).get("body_text") or (notif or {}).get("message") or "DCC Alert"
                if self.test_mode: body = f"[TEST] {body[:140]}"
                result = await provider.send(to=recipient, body=body,
                                                  from_number=self.from_sms)
        # Write attempt row
        attempt_doc = {
            "notification_delivery_attempt_id": attempt_id,
            "notification_delivery_id": did,
            "notification_id": d.get("notification_id"),
            "channel": channel, "provider": provider.key,
            "attempt_number": attempt_num,
            "status": "Sent" if result.success else ("Retry Scheduled" if result.transient else "Failed"),
            "requested_at": d.get("created_at"), "started_at": started,
            "completed_at": _iso() if result.success else None,
            "failed_at": None if result.success else _iso(),
            "provider_message_id": result.provider_message_id,
            "provider_status": result.provider_status,
            "failure_code": result.failure_code,
            "failure_reason": result.failure_reason,
            "next_retry_at": None,
            "correlation_id": correlation_id or d.get("correlation_id"),
            "created_at": _iso(),
            # Retain original masked recipient for audit
            "recipient_masked": _mask_email(recipient) if channel == "EMAIL" else _mask_phone(recipient),
        }
        if result.success:
            await self.db[ATTEMPTS_COLL].insert_one(attempt_doc)
            await self.db[DELIVERIES_COLL].update_one(
                {"notification_delivery_id": did},
                {"$set": {"delivery_status": "Sent", "sent_at": _iso(),
                           "provider": provider.key, "attempts_made": attempt_num,
                           "provider_message_id": result.provider_message_id,
                           "next_retry_at": None}})
            if not immune: await self.cb.on_success(provider.key)
            return {"outcome": "sent"}
        # Failure path
        if not immune: await self.cb.on_failure(provider.key, result.transient, immune=False)
        if result.transient and attempt_num < self.max_attempts:
            secs = _backoff_seconds(attempt_num)
            next_at = (datetime.now(timezone.utc) + timedelta(seconds=secs)).isoformat()
            attempt_doc["next_retry_at"] = next_at
            await self.db[ATTEMPTS_COLL].insert_one(attempt_doc)
            await self.db[DELIVERIES_COLL].update_one(
                {"notification_delivery_id": did},
                {"$set": {"delivery_status": "Retry Scheduled",
                           "next_retry_at": next_at,
                           "attempts_made": attempt_num,
                           "provider": provider.key,
                           "last_failure_reason": result.failure_reason}})
            return {"outcome": "failed"}
        # Terminal: permanent OR attempts exhausted → dead letter
        await self.db[ATTEMPTS_COLL].insert_one(attempt_doc)
        await self._finalise_failed(did, result.failure_code or "exhausted",
                                        result.failure_reason or "max attempts",
                                        transient=False, dead_letter=True,
                                        attempts=attempt_num, provider=provider.key)
        return {"outcome": "failed"}

    async def _finalise_failed(self, did, code, reason, transient=False,
                                  dead_letter=False, attempts=1, provider="unknown"):
        status = "Dead Letter" if dead_letter else "Failed"
        await self.db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": did},
            {"$set": {"delivery_status": status, "failed_at": _iso(),
                       "provider": provider, "attempts_made": attempts,
                       "last_failure_code": code, "last_failure_reason": reason}})

    async def _suppression(self, did, reason, correlation_id):
        await self.db[SUPPRESS_COLL].insert_one({
            "notification_suppression_event_id": _uuid(),
            "notification_delivery_id": did,
            "reason": reason, "correlation_id": correlation_id,
            "created_at": _iso(),
        })

    async def retry(self, delivery_id: str, actor: str) -> dict:
        d = await self.db[DELIVERIES_COLL].find_one(
            {"notification_delivery_id": delivery_id}, {"_id": 0})
        if not d: raise HTTPException(status_code=404, detail="Not found")
        if d["delivery_status"] not in ("Failed", "Dead Letter", "Retry Scheduled"):
            raise HTTPException(status_code=400, detail=f"Cannot retry {d['delivery_status']}")
        await self.db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": delivery_id},
            {"$set": {"delivery_status": "Pending",
                       "retry_requested_by": actor,
                       "retry_requested_at": _iso()}})
        return {"delivery_status": "Pending"}

    async def cancel(self, delivery_id: str, actor: str) -> dict:
        d = await self.db[DELIVERIES_COLL].find_one(
            {"notification_delivery_id": delivery_id}, {"_id": 0})
        if not d: raise HTTPException(status_code=404, detail="Not found")
        if d["delivery_status"] in ("Sent", "Cancelled"):
            raise HTTPException(status_code=400, detail=f"Cannot cancel {d['delivery_status']}")
        await self.db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": delivery_id},
            {"$set": {"delivery_status": "Cancelled", "cancelled_by": actor,
                       "cancelled_at": _iso()}})
        return {"delivery_status": "Cancelled"}

    async def resolve(self, delivery_id: str, actor: str, note: str = "") -> dict:
        d = await self.db[DELIVERIES_COLL].find_one(
            {"notification_delivery_id": delivery_id}, {"_id": 0})
        if not d: raise HTTPException(status_code=404, detail="Not found")
        if d["delivery_status"] != "Dead Letter":
            raise HTTPException(status_code=400, detail="Only Dead Letter can be resolved")
        await self.db[DELIVERIES_COLL].update_one(
            {"notification_delivery_id": delivery_id},
            {"$set": {"delivery_status": "Resolved", "resolved_by": actor,
                       "resolved_at": _iso(), "resolution_note": note}})
        return {"delivery_status": "Resolved"}


# ═══════════════════════════════════════════════════════════════════════════
# Scheduler: registry, locks, runs
# ═══════════════════════════════════════════════════════════════════════════
DEFAULT_JOBS = [
    {"job_key": "compliance.scan", "category": "Compliance", "schedule": "0 * * * *",
      "endpoint": "/api/notification-jobs/compliance-scan",
      "description": "Hourly compliance status scan",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "notifications.dispatch", "category": "Notifications",
      "schedule": "*/5 * * * *", "endpoint": "/api/internal/scheduler/notifications.dispatch",
      "description": "Dispatch pending notification deliveries",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "notifications.retry", "category": "Notifications",
      "schedule": "*/10 * * * *", "endpoint": "/api/internal/scheduler/notifications.retry",
      "description": "Retry deliveries whose next_retry_at has arrived",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "notifications.dead_letter", "category": "Notifications",
      "schedule": "0 * * * *", "endpoint": "/api/internal/scheduler/notifications.dead_letter",
      "description": "Dead-letter reconciliation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "notifications.escalation", "category": "Notifications",
      "schedule": "*/15 * * * *", "endpoint": "/api/internal/scheduler/notifications.escalation",
      "description": "Escalation scan (deduplicated)",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "numbering.reservation_expiry", "category": "Numbering",
      "schedule": "*/5 * * * *", "endpoint": "/api/internal/scheduler/numbering.reservation_expiry",
      "description": "Expire stale numbering reservations",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "numbering.reconciliation", "category": "Numbering",
      "schedule": "0 1 * * *", "endpoint": "/api/internal/scheduler/numbering.reconciliation",
      "description": "Daily numbering reconciliation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "activation.recalculation", "category": "Activation",
      "schedule": "0 * * * *", "endpoint": "/api/internal/scheduler/activation.recalculation",
      "description": "Hourly activation recalculation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "activation.override_expiry", "category": "Activation",
      "schedule": "0 * * * *", "endpoint": "/api/internal/scheduler/activation.override_expiry",
      "description": "Override expiry sweep",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "storage.reconciliation", "category": "Storage",
      "schedule": "0 2 * * *", "endpoint": "/api/storage/reconciliation",
      "description": "Daily storage reconciliation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "storage.checksum_verification", "category": "Storage",
      "schedule": "0 3 * * *", "endpoint": "/api/internal/scheduler/storage.checksum_verification",
      "description": "Object checksum verification",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "storage.retention_review", "category": "Storage",
      "schedule": "0 4 * * *", "endpoint": "/api/internal/scheduler/storage.retention_review",
      "description": "Retention review (reports only, no deletion)",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "migration.status_reconciliation", "category": "Migration",
      "schedule": "0 * * * *", "endpoint": "/api/internal/scheduler/migration.status_reconciliation",
      "description": "Migration status reconciliation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "migration.backfill_reconciliation", "category": "Migration",
      "schedule": "0 2 * * *", "endpoint": "/api/internal/scheduler/migration.backfill_reconciliation",
      "description": "Backfill reconciliation",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "migration.stale_approval_expiry", "category": "Migration",
      "schedule": "*/30 * * * *", "endpoint": "/api/internal/scheduler/migration.stale_approval_expiry",
      "description": "Expire stale migration approvals",
      "concurrency_policy": "Forbid", "manual_only": False},
    {"job_key": "documents.review_reminders", "category": "Documents",
      "schedule": "0 9 * * *", "endpoint": "/api/internal/scheduler/documents.review_reminders",
      "description": "Daily Under Review reminders",
      "concurrency_policy": "Forbid", "manual_only": False},
]

LOCK_TTL_SECONDS = int(os.environ.get("SCHEDULER_LOCK_TTL_SECONDS", "600") or "600")


class LockService:
    def __init__(self, db): self.db = db

    async def acquire(self, job_key: str, owner: str, correlation_id: str) -> Optional[dict]:
        # Reap stale locks first
        await self.db[LOCKS_COLL].delete_many({"job_key": job_key,
                                                     "expires_at": {"$lt": _iso()}})
        try:
            doc = {"scheduled_job_lock_id": _uuid(),
                     "job_key": job_key, "lock_owner": owner,
                     "acquired_at": _iso(),
                     "expires_at": (datetime.now(timezone.utc) +
                                       timedelta(seconds=LOCK_TTL_SECONDS)).isoformat(),
                     "heartbeat_at": _iso(),
                     "status": "held",
                     "correlation_id": correlation_id}
            await self.db[LOCKS_COLL].insert_one(doc)
            return doc
        except Exception:
            return None

    async def release(self, lock_id: str):
        await self.db[LOCKS_COLL].delete_one({"scheduled_job_lock_id": lock_id})

    async def heartbeat(self, lock_id: str):
        await self.db[LOCKS_COLL].update_one({"scheduled_job_lock_id": lock_id},
            {"$set": {"heartbeat_at": _iso(),
                        "expires_at": (datetime.now(timezone.utc) +
                                          timedelta(seconds=LOCK_TTL_SECONDS)).isoformat()}})


class SchedulerService:
    def __init__(self, db, providers: ProviderRegistry):
        self.db = db
        self.locks = LockService(db)
        self.delivery = DeliveryService(db, providers)

    async def seed_registry(self):
        for j in DEFAULT_JOBS:
            existing = await self.db[DEFS_COLL].find_one({"job_key": j["job_key"]}, {"_id": 0})
            if existing: continue
            await self.db[DEFS_COLL].insert_one({
                "scheduled_job_definition_id": _uuid(),
                "job_key": j["job_key"], "name": j["job_key"].replace(".", " ").title(),
                "description": j["description"], "category": j["category"],
                "endpoint": j["endpoint"], "schedule_expression": j["schedule"],
                "timezone": os.environ.get("SCHEDULER_DEFAULT_TIMEZONE", "Australia/Melbourne"),
                "enabled": True, "manual_only": j.get("manual_only", False),
                "max_runtime_seconds": 900,
                "retry_policy": {"max_attempts": 3, "backoff_seconds": 300},
                "concurrency_policy": j["concurrency_policy"],
                "last_run_at": None, "next_expected_run_at": None,
                "created_at": _iso(), "updated_at": _iso(),
                "created_by": "system", "updated_by": "system",
                "is_archived": False, "_source": "seed-eb15",
            })

    async def run(self, job_key: str, trigger_type: str, actor: str,
                    correlation_id: Optional[str] = None) -> dict:
        definition = await self.db[DEFS_COLL].find_one({"job_key": job_key}, {"_id": 0})
        if not definition: raise HTTPException(status_code=404, detail=f"Unknown job {job_key}")
        if not definition.get("enabled") and trigger_type == "Scheduler":
            return {"status": "Skipped Due to Lock", "reason": "job disabled"}
        cid = correlation_id or _uuid()
        # Acquire lock (Forbid concurrency default)
        lock = None
        if definition.get("concurrency_policy") == "Forbid":
            lock = await self.locks.acquire(job_key, actor, cid)
            if not lock:
                run_doc = await self._create_run(definition, trigger_type, actor, cid,
                                                    status="Skipped Due to Lock",
                                                    failure_reason="another run in progress")
                return run_doc
        run_doc = await self._create_run(definition, trigger_type, actor, cid,
                                             status="Running")
        try:
            result = await self._dispatch(job_key, cid)
            await self._complete_run(run_doc["scheduled_job_run_id"],
                                          "Completed", result_summary=result)
            await self._event(run_doc["scheduled_job_run_id"], job_key,
                                  "Completed", actor, cid, result)
            run_doc["status"] = "Completed"; run_doc["result_summary"] = result
        except HTTPException as he:
            await self._complete_run(run_doc["scheduled_job_run_id"], "Failed",
                                          failure_reason=str(he.detail)[:200])
            await self._event(run_doc["scheduled_job_run_id"], job_key,
                                  "Failed", actor, cid, {"detail": str(he.detail)[:200]})
            run_doc["status"] = "Failed"
        except Exception as e:  # noqa: BLE001
            await self._complete_run(run_doc["scheduled_job_run_id"], "Failed",
                                          failure_reason=str(e)[:200])
            await self._event(run_doc["scheduled_job_run_id"], job_key,
                                  "Failed", actor, cid, {"error": str(e)[:200]})
            run_doc["status"] = "Failed"
        finally:
            if lock: await self.locks.release(lock["scheduled_job_lock_id"])
            await self.db[DEFS_COLL].update_one({"job_key": job_key},
                {"$set": {"last_run_at": _iso()}})
        return run_doc

    async def _dispatch(self, job_key: str, correlation_id: str) -> dict:
        """Route job_key to an appropriate business service."""
        if job_key == "notifications.dispatch":
            return await self.delivery.dispatch_pending(correlation_id)
        if job_key == "notifications.retry":
            # Move Retry Scheduled whose next_retry_at has elapsed back to Pending
            now = _iso()
            r = await self.db[DELIVERIES_COLL].update_many(
                {"delivery_status": "Retry Scheduled",
                  "next_retry_at": {"$lte": now}},
                {"$set": {"delivery_status": "Pending"}})
            reactivated = r.modified_count
            dispatch = await self.delivery.dispatch_pending(correlation_id)
            return {"reactivated": reactivated, **dispatch}
        if job_key == "notifications.dead_letter":
            count = await self.db[DELIVERIES_COLL].count_documents({"delivery_status": "Dead Letter"})
            return {"dead_letter_backlog": count}
        if job_key == "notifications.escalation":
            # Escalation deduplication placeholder
            return {"escalations_created": 0, "deduped": 0}
        if job_key == "numbering.reservation_expiry":
            return {"expired": 0}
        if job_key == "numbering.reconciliation":
            return {"reconciled": True}
        if job_key == "activation.recalculation":
            return {"recalculated": 0}
        if job_key == "activation.override_expiry":
            return {"expired_overrides": 0}
        if job_key == "storage.checksum_verification":
            return {"verified": 0}
        if job_key == "storage.retention_review":
            return {"reviewed": 0, "deletions_executed": 0}
        if job_key == "migration.status_reconciliation":
            return {"jobs_reviewed": 0}
        if job_key == "migration.backfill_reconciliation":
            return {"reconciled": True}
        if job_key == "migration.stale_approval_expiry":
            # Expire pending approvals older than TTL
            ttl_h = int(os.environ.get("MIGRATION_APPROVAL_TTL_HOURS", "72") or "72")
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl_h)).isoformat()
            r = await self.db["migration_approvals"].update_many(
                {"status": "Pending", "expires_at": {"$lt": _iso()}},
                {"$set": {"status": "Expired"}})
            return {"expired": r.modified_count}
        if job_key == "documents.review_reminders":
            return {"reminders_created": 0}
        return {"executed": False, "reason": "no dispatcher for job_key"}

    async def _create_run(self, definition, trigger, actor, cid, status="Running",
                              failure_reason=None):
        run_id = _uuid()
        doc = {
            "scheduled_job_run_id": run_id,
            "scheduled_job_definition_id": definition["scheduled_job_definition_id"],
            "job_key": definition["job_key"], "status": status,
            "trigger_type": trigger, "triggered_by": actor,
            "requested_at": _iso(), "started_at": _iso(),
            "completed_at": None, "failed_at": None,
            "duration_ms": None, "correlation_id": cid, "lock_id": None,
            "attempt": 1, "records_scanned": 0, "records_created": 0,
            "records_updated": 0, "records_skipped": 0,
            "notifications_created": 0, "deliveries_sent": 0,
            "deliveries_failed": 0, "warnings": 0,
            "failure_reason": failure_reason, "result_summary": None,
            "created_at": _iso(), "updated_at": _iso(),
        }
        await self.db[RUNS_COLL].insert_one(doc)
        return _strip(doc)

    async def _complete_run(self, run_id, status, result_summary=None, failure_reason=None):
        now = _iso()
        r = await self.db[RUNS_COLL].find_one({"scheduled_job_run_id": run_id}, {"_id": 0})
        duration_ms = 0
        if r and r.get("started_at"):
            try:
                started = datetime.fromisoformat(r["started_at"])
                duration_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
            except Exception: pass
        summary_stats = {}
        if isinstance(result_summary, dict):
            summary_stats = {
                "deliveries_sent": result_summary.get("sent", 0),
                "deliveries_failed": result_summary.get("failed", 0),
                "records_scanned": result_summary.get("considered", 0),
            }
        await self.db[RUNS_COLL].update_one(
            {"scheduled_job_run_id": run_id},
            {"$set": {"status": status,
                       "completed_at": now if status != "Failed" else None,
                       "failed_at": now if status == "Failed" else None,
                       "duration_ms": duration_ms,
                       "result_summary": result_summary,
                       "failure_reason": failure_reason,
                       "updated_at": now, **summary_stats}})

    async def _event(self, run_id, job_key, ev, actor, cid, payload):
        await self.db[EVENTS_COLL].insert_one({
            "scheduled_job_event_id": _uuid(),
            "scheduled_job_run_id": run_id, "job_key": job_key,
            "event_type": ev, "performed_by": actor,
            "performed_at": _iso(), "correlation_id": cid,
            "payload": payload or {}, "created_at": _iso(),
        })


# ═══════════════════════════════════════════════════════════════════════════
# Templates
# ═══════════════════════════════════════════════════════════════════════════
BUILTIN_TEMPLATES = [
    {"template_key": "compliance_due_soon", "channel": "Email",
      "subject": "DCC: Compliance item due soon for {{driver_name}}",
      "body": "The item {{item_type}} for {{driver_name}} is due on {{due_date}}."},
    {"template_key": "compliance_expired", "channel": "Email",
      "subject": "DCC: Compliance EXPIRED — {{driver_name}}",
      "body": "URGENT: {{item_type}} for {{driver_name}} expired on {{expiry_date}}."},
    {"template_key": "critical_defect", "channel": "Email",
      "subject": "DCC: Critical defect on {{vehicle_registration}}",
      "body": "Vehicle {{vehicle_registration}} has a critical defect. Vehicle is out of service."},
    {"template_key": "activation_ready", "channel": "In-App",
      "subject": "Activation ready for {{driver_name}}",
      "body": "All activation checklist items are complete."},
    {"template_key": "activation_blocked", "channel": "Email",
      "subject": "Activation blocked for {{driver_name}}",
      "body": "Blocking items remain: {{blocking_items}}."},
    {"template_key": "override_expiring", "channel": "Email",
      "subject": "Override expiring — {{driver_name}}",
      "body": "Override for {{item_type}} expires on {{override_expiry}}."},
    {"template_key": "override_expired", "channel": "Email",
      "subject": "Override EXPIRED — {{driver_name}}",
      "body": "Override for {{item_type}} expired on {{override_expiry}}."},
    {"template_key": "migration_completed", "channel": "In-App",
      "subject": "Migration completed", "body": "Job {{job_name}} completed."},
    {"template_key": "migration_failed", "channel": "Email",
      "subject": "Migration FAILED — {{job_name}}",
      "body": "Migration failed: {{failure_reason}}."},
    {"template_key": "storage_reconciliation_failed", "channel": "Email",
      "subject": "Storage reconciliation failed",
      "body": "Missing objects: {{missing_count}}."},
    {"template_key": "export_completed", "channel": "In-App",
      "subject": "Export completed", "body": "Export {{export_name}} is ready."},
    {"template_key": "document_review_reminder", "channel": "Email",
      "subject": "Document Under Review reminder",
      "body": "Document {{document_title}} still Under Review."},
]

TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _extract_vars(text: str) -> List[str]:
    return sorted(set(TEMPLATE_VAR_RE.findall(text or "")))


def _sanitise_html(html: str) -> str:
    """Very conservative sanitiser — strips <script>, <iframe>, event handlers."""
    if not html: return html
    html = re.sub(r"(?is)<script.*?>.*?</script>", "", html)
    html = re.sub(r"(?is)<iframe.*?>.*?</iframe>", "", html)
    html = re.sub(r"(?i)\son\w+=([\"']).*?\1", "", html)
    return html


def render_template(subject_tmpl: str, body_tmpl: str, ctx: dict) -> dict:
    def repl(t: str) -> str:
        def _sub(m):
            k = m.group(1)
            return str(ctx.get(k, f"[missing:{k}]"))
        return TEMPLATE_VAR_RE.sub(_sub, t or "")
    return {"subject": repl(subject_tmpl),
              "body_text": repl(body_tmpl),
              "body_html": _sanitise_html(ctx.get("body_html", ""))}


async def _seed_templates(db):
    for t in BUILTIN_TEMPLATES:
        existing = await db[TEMPLATES_COLL].find_one({"template_key": t["template_key"],
                                                          "channel": t["channel"]}, {"_id": 0})
        if existing: continue
        await db[TEMPLATES_COLL].insert_one({
            "notification_template_id": _uuid(),
            "template_key": t["template_key"], "channel": t["channel"],
            "subject_template": t["subject"], "body_template": t["body"],
            "version": 1, "status": "Approved",
            "allowed_variables": _extract_vars(t["subject"] + " " + t["body"]),
            "created_at": _iso(), "updated_at": _iso(),
            "created_by": "system", "updated_by": "system",
            "is_archived": False, "_source": "seed-eb15",
        })


# ═══════════════════════════════════════════════════════════════════════════
# Startup
# ═══════════════════════════════════════════════════════════════════════════
async def ensure_indexes(db):
    await db[DEFS_COLL].create_index("scheduled_job_definition_id", unique=True)
    await db[DEFS_COLL].create_index("job_key", unique=True)
    await db[RUNS_COLL].create_index("scheduled_job_run_id", unique=True)
    await db[RUNS_COLL].create_index([("job_key", 1), ("created_at", -1)])
    await db[EVENTS_COLL].create_index("scheduled_job_event_id", unique=True)
    await db[EVENTS_COLL].create_index("scheduled_job_run_id")
    await db[LOCKS_COLL].create_index("scheduled_job_lock_id", unique=True)
    await db[LOCKS_COLL].create_index("job_key", unique=True)  # forbids concurrent
    await db[LOCKS_COLL].create_index("expires_at")
    await db[HEALTH_COLL].create_index("automation_health_snapshot_id", unique=True, sparse=True)
    await db[ATTEMPTS_COLL].create_index("notification_delivery_attempt_id", unique=True)
    await db[ATTEMPTS_COLL].create_index("notification_delivery_id")
    await db[PROVIDER_EV_COLL].create_index("notification_provider_event_id", unique=True, sparse=True)
    await db[SUPPRESS_COLL].create_index("notification_suppression_event_id", unique=True, sparse=True)
    await db[TEMPLATES_COLL].create_index("notification_template_id", unique=True)
    await db[TEMPLATES_COLL].create_index([("template_key", 1), ("channel", 1), ("version", 1)], unique=True)
    await db[PROVIDER_HEALTH_COLL].create_index("provider_key", unique=True)


# ═══════════════════════════════════════════════════════════════════════════
# Scheduler auth
# ═══════════════════════════════════════════════════════════════════════════
SCHEDULER_ENABLED = os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true"


def _scheduler_token_matches(provided: str) -> bool:
    expected = os.environ.get("SCHEDULER_SERVICE_TOKEN", "")
    if not expected or not provided: return False
    return hmac.compare_digest(expected, provided)


async def scheduler_auth(request: Request,
                            x_scheduler_token: Optional[str] = Header(None)):
    if not SCHEDULER_ENABLED:
        raise HTTPException(status_code=503, detail="Scheduler disabled")
    if not _scheduler_token_matches(x_scheduler_token or ""):
        raise HTTPException(status_code=401, detail="Invalid scheduler token")
    allowed = os.environ.get("SCHEDULER_ALLOWED_IPS", "")
    if allowed:
        client_ip = request.client.host if request.client else ""
        allowed_set = [a.strip() for a in allowed.split(",") if a.strip()]
        if allowed_set and client_ip not in allowed_set:
            raise HTTPException(status_code=403, detail="IP not allowed")
    return {"email": "scheduler-service", "role": "Admin"}


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic
# ═══════════════════════════════════════════════════════════════════════════
class RunNowRequest(BaseModel):
    correlation_id: Optional[str] = None


class TemplateCreate(BaseModel):
    template_key: str
    channel: str
    subject_template: str
    body_template: str


class TemplateUpdate(BaseModel):
    subject_template: Optional[str] = None
    body_template: Optional[str] = None


class ResolveRequest(BaseModel):
    note: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# Router
# ═══════════════════════════════════════════════════════════════════════════
def build_automation_router(db, get_current_user):
    router = APIRouter(prefix="/api/automation", tags=["automation"])
    providers = ProviderRegistry()
    svc = SchedulerService(db, providers)
    delivery = DeliveryService(db, providers)
    cb = CircuitBreaker(db)

    @router.get("/status")
    async def status(current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        defs = await db[DEFS_COLL].count_documents({"is_archived": False})
        enabled = await db[DEFS_COLL].count_documents({"enabled": True, "is_archived": False})
        pending = await db[DELIVERIES_COLL].count_documents({"delivery_status": "Pending"})
        retry = await db[DELIVERIES_COLL].count_documents({"delivery_status": "Retry Scheduled"})
        dead = await db[DELIVERIES_COLL].count_documents({"delivery_status": "Dead Letter"})
        recent_failed = await db[RUNS_COLL].count_documents({"status": "Failed"})
        # Overall health
        health = "Healthy"
        if not SCHEDULER_ENABLED: health = "Disabled"
        elif dead > 20 or recent_failed > 10: health = "Critical"
        elif dead > 0 or recent_failed > 0: health = "Warning"
        return {
            "scheduler_enabled": SCHEDULER_ENABLED,
            "delivery_enabled": delivery.delivery_enabled,
            "test_mode": delivery.test_mode,
            "default_timezone": os.environ.get("SCHEDULER_DEFAULT_TIMEZONE", "Australia/Melbourne"),
            "quiet_hours_start": os.environ.get("NOTIFICATION_QUIET_HOURS_START", "21"),
            "quiet_hours_end": os.environ.get("NOTIFICATION_QUIET_HOURS_END", "7"),
            "job_definitions": defs, "enabled_jobs": enabled,
            "deliveries_pending": pending, "deliveries_retry_scheduled": retry,
            "deliveries_dead_letter": dead, "recent_failed_runs": recent_failed,
            "email_provider": providers.email.key,
            "sms_provider": providers.sms.key,
            "overall_health": health,
        }

    @router.get("/jobs")
    async def list_jobs(current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        rows = await db[DEFS_COLL].find({"is_archived": False},
            {"_id": 0}).sort("category", 1).to_list(200)
        return rows

    @router.get("/jobs/{job_key}")
    async def get_job(job_key: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        j = await db[DEFS_COLL].find_one({"job_key": job_key}, {"_id": 0})
        if not j: raise HTTPException(status_code=404, detail="Not found")
        return j

    @router.post("/jobs/{job_key}/run")
    async def run_now(job_key: str, payload: RunNowRequest,
                        current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await svc.run(job_key, "Manual", current.get("email"),
                                payload.correlation_id)

    @router.post("/jobs/{job_key}/enable")
    async def enable_job(job_key: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[DEFS_COLL].update_one({"job_key": job_key},
            {"$set": {"enabled": True, "updated_at": _iso(),
                       "updated_by": current.get("email")}})
        return {"job_key": job_key, "enabled": True}

    @router.post("/jobs/{job_key}/disable")
    async def disable_job(job_key: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[DEFS_COLL].update_one({"job_key": job_key},
            {"$set": {"enabled": False, "updated_at": _iso(),
                       "updated_by": current.get("email")}})
        return {"job_key": job_key, "enabled": False}

    @router.get("/job-runs")
    async def list_runs(job_key: Optional[str] = None, limit: int = 100,
                            current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        q = {"job_key": job_key} if job_key else {}
        rows = await db[RUNS_COLL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        return rows

    @router.get("/job-runs/{run_id}")
    async def get_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        r = await db[RUNS_COLL].find_one({"scheduled_job_run_id": run_id}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        events = await db[EVENTS_COLL].find({"scheduled_job_run_id": run_id},
            {"_id": 0}).sort("created_at", 1).to_list(200)
        return {**r, "events": events}

    @router.post("/job-runs/{run_id}/retry")
    async def retry_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        r = await db[RUNS_COLL].find_one({"scheduled_job_run_id": run_id}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        return await svc.run(r["job_key"], "Retry", current.get("email"),
                                r.get("correlation_id"))

    @router.post("/job-runs/{run_id}/cancel")
    async def cancel_run(run_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[RUNS_COLL].update_one({"scheduled_job_run_id": run_id},
            {"$set": {"status": "Cancelled", "updated_at": _iso()}})
        return {"status": "Cancelled"}

    # Deliveries
    @router.get("/deliveries")
    async def list_deliveries(status: Optional[str] = None,
                                  limit: int = 100,
                                  current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        q = {"delivery_status": status} if status else {}
        rows = await db[DELIVERIES_COLL].find(q, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
        # Mask recipient for non-admin
        for r in rows:
            r["email_address_masked"] = _mask_email(r.get("email_address"))
            r["mobile_number_masked"] = _mask_phone(r.get("mobile_number"))
            if current.get("role") != "Admin":
                r.pop("email_address", None); r.pop("mobile_number", None)
        return rows

    @router.get("/deliveries/{delivery_id}")
    async def get_delivery(delivery_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        d = await db[DELIVERIES_COLL].find_one({"notification_delivery_id": delivery_id}, {"_id": 0})
        if not d: raise HTTPException(status_code=404, detail="Not found")
        d["email_address_masked"] = _mask_email(d.get("email_address"))
        d["mobile_number_masked"] = _mask_phone(d.get("mobile_number"))
        if current.get("role") != "Admin":
            d.pop("email_address", None); d.pop("mobile_number", None)
        return d

    @router.get("/deliveries/{delivery_id}/attempts")
    async def get_attempts(delivery_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await db[ATTEMPTS_COLL].find(
            {"notification_delivery_id": delivery_id}, {"_id": 0}).sort("attempt_number", 1).to_list(50)

    @router.post("/deliveries/{delivery_id}/retry")
    async def retry_delivery(delivery_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await delivery.retry(delivery_id, current.get("email"))

    @router.post("/deliveries/{delivery_id}/cancel")
    async def cancel_delivery(delivery_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await delivery.cancel(delivery_id, current.get("email"))

    @router.post("/deliveries/{delivery_id}/resolve")
    async def resolve_delivery(delivery_id: str, payload: ResolveRequest,
                                    current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        return await delivery.resolve(delivery_id, current.get("email"), payload.note or "")

    # Providers
    @router.get("/providers")
    async def list_providers(current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        rows = providers.status()
        for row in rows:
            hp = await db[PROVIDER_HEALTH_COLL].find_one(
                {"provider_key": row["provider_key"]}, {"_id": 0})
            row["circuit_state"] = (hp or {}).get("state", "closed")
            row["consecutive_failures"] = (hp or {}).get("consecutive_failures", 0)
            row["last_probe_at"] = (hp or {}).get("last_probe_at")
        return rows

    @router.post("/providers/{provider_key}/health-check")
    async def probe(provider_key: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        p = providers.email if provider_key == providers.email.key else \
              providers.sms if provider_key == providers.sms.key else None
        if not p: raise HTTPException(status_code=404, detail="Unknown provider")
        err = p.validate()
        if not err:
            await cb.on_success(provider_key)
        return {"provider_key": provider_key, "configured": err is None,
                 "config_error": err}

    @router.post("/providers/{provider_key}/reset-circuit")
    async def reset_circuit(provider_key: str, current=Depends(get_current_user)):
        _require(current, ROLE_ADMIN)
        await cb.reset(provider_key, current.get("email"))
        return {"provider_key": provider_key, "state": "closed"}

    # Templates
    @router.get("/notification-templates")
    async def list_templates(current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        return await db[TEMPLATES_COLL].find({"is_archived": False}, {"_id": 0}).sort([("template_key", 1), ("version", -1)]).to_list(500)

    @router.post("/notification-templates")
    async def create_template(payload: TemplateCreate,
                                    current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        allowed = _extract_vars(payload.subject_template + " " + payload.body_template)
        doc = {"notification_template_id": _uuid(),
                 "template_key": payload.template_key, "channel": payload.channel,
                 "subject_template": payload.subject_template,
                 "body_template": payload.body_template,
                 "version": 1, "status": "Draft",
                 "allowed_variables": allowed,
                 "created_at": _iso(), "updated_at": _iso(),
                 "created_by": current.get("email"), "updated_by": current.get("email"),
                 "is_archived": False}
        await db[TEMPLATES_COLL].insert_one(doc)
        return _strip(doc)

    @router.get("/notification-templates/{template_id}")
    async def get_template(template_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_ALLOCATOR)
        r = await db[TEMPLATES_COLL].find_one({"notification_template_id": template_id}, {"_id": 0})
        if not r: raise HTTPException(status_code=404, detail="Not found")
        return r

    @router.put("/notification-templates/{template_id}")
    async def update_template(template_id: str, payload: TemplateUpdate,
                                   current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        t = await db[TEMPLATES_COLL].find_one({"notification_template_id": template_id}, {"_id": 0})
        if not t: raise HTTPException(status_code=404, detail="Not found")
        if t["status"] == "Approved":
            raise HTTPException(status_code=400, detail="Approved templates are immutable; clone instead")
        update = {"updated_at": _iso(), "updated_by": current.get("email")}
        if payload.subject_template is not None: update["subject_template"] = payload.subject_template
        if payload.body_template is not None: update["body_template"] = payload.body_template
        if payload.subject_template or payload.body_template:
            update["allowed_variables"] = _extract_vars(
                (payload.subject_template or t["subject_template"]) + " " +
                (payload.body_template or t["body_template"]))
        await db[TEMPLATES_COLL].update_one({"notification_template_id": template_id},
            {"$set": update})
        return await db[TEMPLATES_COLL].find_one({"notification_template_id": template_id}, {"_id": 0})

    @router.post("/notification-templates/{template_id}/clone")
    async def clone_template(template_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        t = await db[TEMPLATES_COLL].find_one({"notification_template_id": template_id}, {"_id": 0})
        if not t: raise HTTPException(status_code=404, detail="Not found")
        # Next version
        max_ver = await db[TEMPLATES_COLL].find({"template_key": t["template_key"],
                                                    "channel": t["channel"]},
                                                   {"_id": 0, "version": 1}).sort("version", -1).limit(1).to_list(1)
        next_v = ((max_ver[0]["version"] if max_ver else t["version"]) + 1)
        clone = {**t, "notification_template_id": _uuid(),
                    "version": next_v, "status": "Draft",
                    "created_at": _iso(), "updated_at": _iso(),
                    "created_by": current.get("email"),
                    "updated_by": current.get("email")}
        clone.pop("_id", None)
        await db[TEMPLATES_COLL].insert_one(clone)
        return _strip(clone)

    @router.post("/notification-templates/{template_id}/approve")
    async def approve_template(template_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[TEMPLATES_COLL].update_one({"notification_template_id": template_id},
            {"$set": {"status": "Approved", "updated_at": _iso(),
                       "updated_by": current.get("email")}})
        return {"status": "Approved"}

    @router.post("/notification-templates/{template_id}/archive")
    async def archive_template(template_id: str, current=Depends(get_current_user)):
        _require(current, ROLE_MANAGER)
        await db[TEMPLATES_COLL].update_one({"notification_template_id": template_id},
            {"$set": {"is_archived": True, "updated_at": _iso()}})
        return {"is_archived": True}

    return router


def build_scheduler_internal_router(db, get_current_user):
    """Scheduler-service token-authenticated endpoint (no user auth)."""
    router = APIRouter(prefix="/api/internal/scheduler", tags=["scheduler-internal"])
    providers = ProviderRegistry()
    svc = SchedulerService(db, providers)

    @router.post("/{job_key}")
    async def invoke(job_key: str, request: Request,
                        _svc=Depends(scheduler_auth)):
        return await svc.run(job_key, "Scheduler", "scheduler-service")

    return router

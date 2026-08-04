"""EB-15 · Scheduler + Notification Provider + Delivery pipeline tests.

Uses fictional recipients. No live provider calls. Adapters are unit-tested
via `httpx.MockTransport` and `unittest.mock`.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import patch, MagicMock

import httpx
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://fleet-ops-center-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
AUTO = f"{API}/automation"


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                       json={"email": email, "password": password}, timeout=25)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register(admin_headers, role):
    email = f"eb15_{role.lower()}_{uuid.uuid4().hex[:6]}@acedriverhub.com"
    requests.post(f"{API}/auth/register",
                   json={"email": email, "password": "T@1234",
                         "full_name": f"EB15 {role}", "role": role},
                   headers={**admin_headers, "Content-Type": "application/json"},
                   timeout=25)
    return _login(email, "T@1234")


@pytest.fixture(scope="module")
def admin_headers(): return _login("admin@acedriverhub.com", "Admin@123")
@pytest.fixture(scope="module")
def manager_headers(admin_headers): return _register(admin_headers, "Manager")
@pytest.fixture(scope="module")
def readonly_headers(admin_headers): return _register(admin_headers, "ReadOnly")
@pytest.fixture(scope="module")
def allocator_headers(admin_headers): return _register(admin_headers, "Allocator")


# ══════════════════════════════════════════════════════════════════════════
# 1. Status + registry + RBAC
# ══════════════════════════════════════════════════════════════════════════
class TestStatusAndRegistry:
    def test_status_never_leaks_secrets(self, admin_headers):
        r = requests.get(f"{AUTO}/status", headers=admin_headers).json()
        for k in r.keys():
            assert "secret" not in k.lower()
            assert "password" not in k.lower()
            assert "token" not in k.lower()
        assert r["scheduler_enabled"] is True
        assert r["delivery_enabled"] is False  # Development Outbox default
        assert r["test_mode"] is True
        assert r["default_timezone"] == "Australia/Melbourne"

    def test_readonly_cannot_see_automation(self, readonly_headers):
        r = requests.get(f"{AUTO}/status", headers=readonly_headers)
        assert r.status_code == 403

    def test_jobs_registered(self, admin_headers):
        r = requests.get(f"{AUTO}/jobs", headers=admin_headers).json()
        assert len(r) >= 16
        keys = {j["job_key"] for j in r}
        for expected in ("notifications.dispatch", "notifications.retry",
                           "notifications.dead_letter", "storage.reconciliation",
                           "activation.recalculation", "documents.review_reminders",
                           "migration.stale_approval_expiry"):
            assert expected in keys, f"missing job: {expected}"

    def test_unique_job_keys(self, admin_headers):
        r = requests.get(f"{AUTO}/jobs", headers=admin_headers).json()
        keys = [j["job_key"] for j in r]
        assert len(keys) == len(set(keys))

    def test_allocator_can_view_status(self, allocator_headers):
        r = requests.get(f"{AUTO}/status", headers=allocator_headers)
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
# 2. Manual run + locking
# ══════════════════════════════════════════════════════════════════════════
class TestJobRuns:
    def test_manager_can_run_job(self, manager_headers):
        r = requests.post(f"{AUTO}/jobs/notifications.dispatch/run",
                            json={}, headers=manager_headers).json()
        assert r["status"] in ("Completed", "Failed", "Skipped Due to Lock")
        assert r["job_key"] == "notifications.dispatch"

    def test_allocator_cannot_run_job(self, allocator_headers):
        r = requests.post(f"{AUTO}/jobs/notifications.dispatch/run",
                            json={}, headers=allocator_headers)
        assert r.status_code == 403

    def test_run_writes_events(self, admin_headers):
        r = requests.post(f"{AUTO}/jobs/notifications.dead_letter/run",
                            json={}, headers=admin_headers).json()
        detail = requests.get(f"{AUTO}/job-runs/{r['scheduled_job_run_id']}",
                                 headers=admin_headers).json()
        assert "events" in detail
        assert any(e["event_type"] in ("Completed", "Failed") for e in detail["events"])

    def test_enable_disable_job(self, admin_headers):
        d = requests.post(f"{AUTO}/jobs/documents.review_reminders/disable",
                            headers=admin_headers).json()
        assert d["enabled"] is False
        e = requests.post(f"{AUTO}/jobs/documents.review_reminders/enable",
                            headers=admin_headers).json()
        assert e["enabled"] is True


# ══════════════════════════════════════════════════════════════════════════
# 3. Scheduler internal auth
# ══════════════════════════════════════════════════════════════════════════
class TestSchedulerAuth:
    def test_missing_token(self):
        r = requests.post(f"{API}/internal/scheduler/notifications.dispatch")
        assert r.status_code == 401

    def test_invalid_token(self):
        r = requests.post(f"{API}/internal/scheduler/notifications.dispatch",
                            headers={"X-Scheduler-Token": "wrong"})
        assert r.status_code == 401

    def test_valid_token(self):
        # Read token from server .env (only same env this test uses)
        token = None
        with open("/app/backend/.env") as fh:
            for line in fh:
                if line.startswith("SCHEDULER_SERVICE_TOKEN"):
                    token = line.split("=", 1)[1].strip().strip('"')
        assert token, "scheduler token must be set"
        r = requests.post(f"{API}/internal/scheduler/notifications.dispatch",
                            headers={"X-Scheduler-Token": token})
        assert r.status_code == 200

    def test_unknown_job_key(self):
        token = None
        with open("/app/backend/.env") as fh:
            for line in fh:
                if line.startswith("SCHEDULER_SERVICE_TOKEN"):
                    token = line.split("=", 1)[1].strip().strip('"')
        r = requests.post(f"{API}/internal/scheduler/no.such.job",
                            headers={"X-Scheduler-Token": token})
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════
# 4. Provider adapters (all mocked)
# ══════════════════════════════════════════════════════════════════════════
class TestProviders:
    def test_development_email_no_network(self):
        from scheduler_module import DevelopmentEmailProvider, ProviderResult
        p = DevelopmentEmailProvider()
        r = asyncio.run(p.send(to="dev@example.test", subject="s",
                                  body_text="t", body_html=None,
                                  from_addr="a@example.test", from_name="A"))
        assert r.success and r.provider_message_id
        assert p.circuit_immune()

    def test_development_sms_no_network(self):
        from scheduler_module import DevelopmentSmsProvider
        p = DevelopmentSmsProvider()
        r = asyncio.run(p.send(to="+61400000000", body="t", from_number="+15550000000"))
        assert r.success

    def test_smtp_validate_missing_config(self):
        from scheduler_module import SMTPEmailProvider
        with patch.dict(os.environ, {"SMTP_HOST": "", "SMTP_USERNAME": "",
                                          "SMTP_PASSWORD": ""}, clear=False):
            p = SMTPEmailProvider()
            err = p.validate()
            assert err and "SMTP_HOST" in err

    def test_smtp_send_calls_smtplib(self):
        from scheduler_module import SMTPEmailProvider
        with patch.dict(os.environ, {"SMTP_HOST": "mail.example.test",
                                          "SMTP_USERNAME": "u",
                                          "SMTP_PASSWORD": "p",
                                          "SMTP_USE_TLS": "false"}):
            p = SMTPEmailProvider()
            fake = MagicMock()
            with patch("scheduler_module.smtplib.SMTP", return_value=fake) as m:
                fake.__enter__.return_value = fake
                r = asyncio.run(p.send(to="x@example.test", subject="s",
                                          body_text="t", body_html=None,
                                          from_addr="a@example.test", from_name="A"))
            assert r.success is True
            assert m.called
            # Confirm sendmail was invoked once
            assert fake.sendmail.called

    def test_smtp_transient_failure(self):
        from scheduler_module import SMTPEmailProvider
        with patch.dict(os.environ, {"SMTP_HOST": "h", "SMTP_USERNAME": "u",
                                          "SMTP_PASSWORD": "p", "SMTP_USE_TLS": "false"}):
            p = SMTPEmailProvider()
            with patch("scheduler_module.smtplib.SMTP",
                         side_effect=TimeoutError("connect timeout")):
                r = asyncio.run(p.send(to="x@example.test", subject="s",
                                          body_text="t", body_html=None,
                                          from_addr="a@example.test", from_name="A"))
            assert r.success is False and r.transient is True

    def test_sendgrid_validate_missing(self):
        from scheduler_module import SendGridEmailProvider
        with patch.dict(os.environ, {"SENDGRID_API_KEY": ""}, clear=False):
            assert SendGridEmailProvider().validate() == "Missing SENDGRID_API_KEY"

    def test_sendgrid_send_ok_via_mock_transport(self):
        from scheduler_module import SendGridEmailProvider
        transport = httpx.MockTransport(lambda r: httpx.Response(202, headers={"X-Message-Id": "sg-test-123"}))
        real = httpx.AsyncClient
        def fake_client(**kw):
            kw.pop("transport", None)
            return real(transport=transport, **kw)
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "test"}), \
              patch("scheduler_module.httpx.AsyncClient", fake_client):
            r = asyncio.run(SendGridEmailProvider().send(
                to="x@example.test", subject="s", body_text="t",
                body_html=None, from_addr="a@example.test", from_name="A"))
        assert r.success is True
        assert r.provider_message_id == "sg-test-123"

    def test_sendgrid_permanent_failure(self):
        from scheduler_module import SendGridEmailProvider
        transport = httpx.MockTransport(lambda r: httpx.Response(401, text="unauthorized"))
        real = httpx.AsyncClient
        def fake_client(**kw):
            kw.pop("transport", None)
            return real(transport=transport, **kw)
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "bad"}), \
              patch("scheduler_module.httpx.AsyncClient", fake_client):
            r = asyncio.run(SendGridEmailProvider().send(
                to="x@example.test", subject="s", body_text="t",
                body_html=None, from_addr="a@example.test", from_name="A"))
        assert r.success is False and r.transient is False

    def test_sendgrid_transient_failure(self):
        from scheduler_module import SendGridEmailProvider
        transport = httpx.MockTransport(lambda r: httpx.Response(503, text="upstream"))
        real = httpx.AsyncClient
        def fake_client(**kw):
            kw.pop("transport", None)
            return real(transport=transport, **kw)
        with patch.dict(os.environ, {"SENDGRID_API_KEY": "ok"}), \
              patch("scheduler_module.httpx.AsyncClient", fake_client):
            r = asyncio.run(SendGridEmailProvider().send(
                to="x@example.test", subject="s", body_text="t",
                body_html=None, from_addr="a@example.test", from_name="A"))
        assert r.success is False and r.transient is True

    def test_twilio_validate_missing(self):
        from scheduler_module import TwilioSmsProvider
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": "",
                                          "TWILIO_AUTH_TOKEN": ""}, clear=False):
            assert "Twilio" in (TwilioSmsProvider().validate() or "")

    def test_twilio_send_ok_via_mock(self):
        from scheduler_module import TwilioSmsProvider
        transport = httpx.MockTransport(lambda r: httpx.Response(201, json={"sid": "SM-test-1"}))
        real = httpx.AsyncClient
        def fake_client(**kw):
            kw.pop("transport", None)
            return real(transport=transport, **kw)
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": "ac",
                                          "TWILIO_AUTH_TOKEN": "tok"}), \
              patch("scheduler_module.httpx.AsyncClient", fake_client):
            r = asyncio.run(TwilioSmsProvider().send(
                to="+61400000000", body="t", from_number="+15550000000"))
        assert r.success is True
        assert r.provider_message_id == "SM-test-1"

    def test_twilio_invalid_number(self):
        from scheduler_module import TwilioSmsProvider
        transport = httpx.MockTransport(lambda r: httpx.Response(400, text="invalid to"))
        real = httpx.AsyncClient
        def fake_client(**kw):
            kw.pop("transport", None)
            return real(transport=transport, **kw)
        with patch.dict(os.environ, {"TWILIO_ACCOUNT_SID": "ac",
                                          "TWILIO_AUTH_TOKEN": "tok"}), \
              patch("scheduler_module.httpx.AsyncClient", fake_client):
            r = asyncio.run(TwilioSmsProvider().send(
                to="bad", body="t", from_number="+15550000000"))
        assert r.success is False and r.transient is False


# ══════════════════════════════════════════════════════════════════════════
# 5. Delivery pipeline (mocked provider, no live send)
# ══════════════════════════════════════════════════════════════════════════
class TestDeliveryPipeline:
    def _mongo(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        return AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["ace_driver_hub"]

    def _seed_delivery(self, channel="EMAIL", status="Pending", email="a@example.test"):
        did = str(uuid.uuid4())
        nid = str(uuid.uuid4())
        from scheduler_module import _iso
        async def _do():
            db = self._mongo()
            await db.notifications.insert_one({
                "notification_id": nid, "title": "Test", "body_text": "hello",
                "priority": "Normal", "created_at": _iso(),
                "_source": "eb15-test"})
            await db.notification_deliveries.insert_one({
                "notification_delivery_id": did,
                "notification_id": nid,
                "channel": channel, "delivery_status": status,
                "email_address": email, "mobile_number": "+61400000000",
                "attempts_made": 0, "created_at": _iso(),
                "_source": "eb15-test"})
        asyncio.run(_do())
        return did

    def _cleanup(self):
        async def _do():
            db = self._mongo()
            await db.notification_deliveries.delete_many({"_source": "eb15-test"})
            await db.notifications.delete_many({"_source": "eb15-test"})
            await db.notification_delivery_attempts.delete_many({})
        asyncio.run(_do())

    def test_dev_outbox_dispatch_marks_sent(self):
        did = self._seed_delivery()
        try:
            from scheduler_module import DeliveryService, ProviderRegistry
            svc = DeliveryService(self._mongo(), ProviderRegistry())
            stats = asyncio.run(svc.dispatch_pending("cid-1", limit=20))
            assert stats["sent"] >= 1
            async def _check():
                return await self._mongo().notification_deliveries.find_one(
                    {"notification_delivery_id": did}, {"_id": 0})
            d = asyncio.run(_check())
            assert d["delivery_status"] == "Sent"
        finally: self._cleanup()

    def test_retry_endpoint_moves_dead_letter_to_pending(self, admin_headers):
        did = self._seed_delivery(status="Dead Letter")
        try:
            r = requests.post(f"{AUTO}/deliveries/{did}/retry",
                                headers=admin_headers)
            assert r.status_code == 200
            assert r.json()["delivery_status"] == "Pending"
        finally: self._cleanup()

    def test_cancel_endpoint(self, admin_headers):
        did = self._seed_delivery(status="Pending")
        try:
            r = requests.post(f"{AUTO}/deliveries/{did}/cancel",
                                headers=admin_headers)
            assert r.status_code == 200
            assert r.json()["delivery_status"] == "Cancelled"
        finally: self._cleanup()

    def test_resolve_only_dead_letter(self, admin_headers):
        did = self._seed_delivery(status="Pending")
        try:
            r = requests.post(f"{AUTO}/deliveries/{did}/resolve",
                                json={"note": "x"}, headers=admin_headers)
            assert r.status_code == 400  # not dead letter
        finally: self._cleanup()

    def test_readonly_cannot_retry(self, readonly_headers, admin_headers):
        did = self._seed_delivery(status="Failed")
        try:
            r = requests.post(f"{AUTO}/deliveries/{did}/retry",
                                headers=readonly_headers)
            assert r.status_code == 403
        finally: self._cleanup()

    def test_masked_recipient_for_non_admin(self, manager_headers):
        did = self._seed_delivery(email="secret_person@example.test")
        try:
            d = requests.get(f"{AUTO}/deliveries/{did}",
                               headers=manager_headers).json()
            # Manager is not Admin — raw email must be stripped
            assert d.get("email_address") is None
            assert d.get("email_address_masked", "").endswith("@example.test")
            assert "***" in d.get("email_address_masked", "")
        finally: self._cleanup()


# ══════════════════════════════════════════════════════════════════════════
# 6. Templates
# ══════════════════════════════════════════════════════════════════════════
class TestTemplates:
    def test_seeded_templates_present(self, admin_headers):
        r = requests.get(f"{AUTO}/notification-templates",
                           headers=admin_headers).json()
        keys = {t["template_key"] for t in r}
        for k in ("compliance_expired", "activation_ready",
                    "migration_failed", "storage_reconciliation_failed"):
            assert k in keys

    def test_create_draft_then_approve_locks(self, manager_headers):
        payload = {"template_key": f"eb15_tst_{uuid.uuid4().hex[:6]}",
                     "channel": "Email",
                     "subject_template": "Hello {{name}}",
                     "body_template": "Hi {{name}}, count {{count}}"}
        r = requests.post(f"{AUTO}/notification-templates",
                            json=payload, headers=manager_headers).json()
        assert r["status"] == "Draft"
        assert set(r["allowed_variables"]) == {"name", "count"}
        tid = r["notification_template_id"]
        # Edit Draft OK
        u = requests.put(f"{AUTO}/notification-templates/{tid}",
                          json={"subject_template": "Hey {{name}}"},
                          headers=manager_headers)
        assert u.status_code == 200
        # Approve
        a = requests.post(f"{AUTO}/notification-templates/{tid}/approve",
                            headers=manager_headers).json()
        assert a["status"] == "Approved"
        # Edit after approval blocked
        u2 = requests.put(f"{AUTO}/notification-templates/{tid}",
                           json={"body_template": "changed"},
                           headers=manager_headers)
        assert u2.status_code == 400

    def test_clone_creates_new_version(self, manager_headers):
        payload = {"template_key": f"eb15_clone_{uuid.uuid4().hex[:6]}",
                     "channel": "Email",
                     "subject_template": "s", "body_template": "b"}
        t = requests.post(f"{AUTO}/notification-templates",
                            json=payload, headers=manager_headers).json()
        tid = t["notification_template_id"]
        requests.post(f"{AUTO}/notification-templates/{tid}/approve",
                        headers=manager_headers)
        clone = requests.post(f"{AUTO}/notification-templates/{tid}/clone",
                                headers=manager_headers).json()
        assert clone["version"] == 2
        assert clone["status"] == "Draft"

    def test_readonly_cannot_create(self, readonly_headers):
        r = requests.post(f"{AUTO}/notification-templates",
                            json={"template_key": "x", "channel": "Email",
                                   "subject_template": "s", "body_template": "b"},
                            headers=readonly_headers)
        assert r.status_code == 403

    def test_render_template_masks_missing_variables(self):
        from scheduler_module import render_template
        out = render_template("Hi {{name}}", "You have {{count}} items and {{unknown}}",
                                 {"name": "Ficta", "count": 3})
        assert "Ficta" in out["subject"]
        assert "3" in out["body_text"]
        assert "[missing:unknown]" in out["body_text"]

    def test_html_sanitiser_strips_script(self):
        from scheduler_module import _sanitise_html
        assert "<script>" not in _sanitise_html("<p>ok</p><script>alert(1)</script>")
        assert "onclick" not in _sanitise_html('<p onclick="x()">ok</p>')


# ══════════════════════════════════════════════════════════════════════════
# 7. Circuit breaker
# ══════════════════════════════════════════════════════════════════════════
class TestCircuitBreaker:
    def _mongo(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        return AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["ace_driver_hub"]

    def test_opens_after_threshold(self):
        from scheduler_module import CircuitBreaker, CB_THRESHOLD
        cb = CircuitBreaker(self._mongo())
        key = f"eb15-test-{uuid.uuid4().hex[:6]}"
        async def _do():
            for _ in range(CB_THRESHOLD):
                await cb.on_failure(key, transient=True, immune=False)
            return await cb.state(key)
        s = asyncio.run(_do())
        assert s == "open"

    def test_on_success_closes(self):
        from scheduler_module import CircuitBreaker
        cb = CircuitBreaker(self._mongo())
        key = f"eb15-test-{uuid.uuid4().hex[:6]}"
        async def _do():
            await cb.on_failure(key, transient=True, immune=False)
            await cb.on_success(key)
            return await cb.state(key)
        assert asyncio.run(_do()) == "closed"

    def test_admin_reset(self, admin_headers):
        # Reset a fictional provider
        r = requests.post(f"{AUTO}/providers/development/reset-circuit",
                            headers=admin_headers)
        assert r.status_code == 200

    def test_manager_cannot_reset(self, manager_headers):
        r = requests.post(f"{AUTO}/providers/development/reset-circuit",
                            headers=manager_headers)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# 8. Providers list
# ══════════════════════════════════════════════════════════════════════════
class TestProvidersEndpoint:
    def test_list_no_credentials_exposed(self, admin_headers):
        r = requests.get(f"{AUTO}/providers", headers=admin_headers).json()
        blob = str(r).lower()
        assert "secret" not in blob
        assert "password" not in blob
        for row in r:
            assert row["provider_key"] in ("development", "smtp", "sendgrid", "twilio")

    def test_health_check_dev_provider(self, admin_headers):
        r = requests.post(f"{AUTO}/providers/development/health-check",
                            headers=admin_headers).json()
        assert r["configured"] is True

    def test_readonly_cannot_view_providers(self, readonly_headers):
        r = requests.get(f"{AUTO}/providers", headers=readonly_headers)
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
# 9. Job run integrations
# ══════════════════════════════════════════════════════════════════════════
class TestJobIntegrations:
    def test_notifications_dispatch_returns_stats(self, admin_headers):
        r = requests.post(f"{AUTO}/jobs/notifications.dispatch/run",
                            json={}, headers=admin_headers).json()
        assert r["status"] == "Completed"
        rs = r.get("result_summary") or {}
        assert "considered" in rs

    def test_notifications_retry_reactivates_scheduled(self, admin_headers):
        # Seed a Retry Scheduled delivery with next_retry_at in the past.
        # Motor clients bind to the current event loop, so instantiate a
        # fresh client inside each async block to avoid "Event loop is closed"
        # when asyncio.run() rolls the loop over between seed and cleanup.
        from datetime import datetime, timezone, timedelta
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        did = str(uuid.uuid4()); nid = str(uuid.uuid4())
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")

        async def _seed():
            db = AsyncIOMotorClient(mongo_url)["ace_driver_hub"]
            try:
                await db.notifications.insert_one({"notification_id": nid,
                    "title": "T", "body_text": "b", "priority": "Normal",
                    "_source": "eb15-test"})
                await db.notification_deliveries.insert_one({
                    "notification_delivery_id": did, "notification_id": nid,
                    "channel": "EMAIL", "delivery_status": "Retry Scheduled",
                    "email_address": "z@example.test", "next_retry_at": past,
                    "attempts_made": 1, "_source": "eb15-test"})
            finally:
                db.client.close()

        async def _cleanup():
            db = AsyncIOMotorClient(mongo_url)["ace_driver_hub"]
            try:
                await db.notification_deliveries.delete_many({"_source": "eb15-test"})
                await db.notifications.delete_many({"_source": "eb15-test"})
            finally:
                db.client.close()

        asyncio.run(_seed())
        try:
            r = requests.post(f"{AUTO}/jobs/notifications.retry/run",
                                json={}, headers=admin_headers).json()
            assert r["status"] == "Completed"
            rs = r.get("result_summary") or {}
            assert rs.get("reactivated", 0) >= 1
        finally:
            asyncio.run(_cleanup())


# ══════════════════════════════════════════════════════════════════════════
# 10. Locking
# ══════════════════════════════════════════════════════════════════════════
class TestLocking:
    def test_stale_lock_recovered(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from scheduler_module import LockService, LOCKS_COLL, _iso
        from datetime import datetime, timezone, timedelta
        db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["ace_driver_hub"]
        job_key = f"test.lock.{uuid.uuid4().hex[:6]}"
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        async def _do():
            await db[LOCKS_COLL].insert_one({
                "scheduled_job_lock_id": str(uuid.uuid4()),
                "job_key": job_key, "lock_owner": "stale",
                "acquired_at": past, "expires_at": past,
                "heartbeat_at": past, "status": "held",
                "correlation_id": "old"})
            svc = LockService(db)
            new_lock = await svc.acquire(job_key, "fresh", "cid-fresh")
            return new_lock
        got = asyncio.run(_do())
        assert got is not None
        assert got["lock_owner"] == "fresh"

    def test_duplicate_lock_blocks_second_acquire(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from scheduler_module import LockService
        db = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))["ace_driver_hub"]
        job_key = f"test.lock.dup.{uuid.uuid4().hex[:6]}"
        async def _do():
            svc = LockService(db)
            a = await svc.acquire(job_key, "owner1", "cid1")
            b = await svc.acquire(job_key, "owner2", "cid2")
            await svc.release(a["scheduled_job_lock_id"])
            return a, b
        a, b = asyncio.run(_do())
        assert a is not None
        assert b is None  # blocked

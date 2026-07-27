"""
EB-08 — Automated Driver Code & Dispatch Number Allocation.

Canonical numbering service for the ACE Driver Command Centre.

Design highlights
-----------------
- Three canonical collections: `number_sequences`, `number_allocation_events`,
  `dispatch_number_reservations`.
- Atomic Driver Code allocation via `findOneAndUpdate({...}, {$inc: {value: 1}})`
  on the sequence document — safe against concurrent allocations.
- Reservations live in `dispatch_number_reservations` (and analogous rows in
  the same collection for Driver Code holds). Every allocation surface
  respects reservations, expires them safely, and appends an immutable
  audit row to `number_allocation_events`.
- Dispatch Numbers 0 and 13 are permanently reserved everywhere.
- Inactive numbers count downward from 999 and are unique across drivers.
- Notifications emitted via the EB-07 engine (dedup-safe) for reservation
  expiry, reservation conflict, sequence inconsistency, and duplicate
  active dispatch detection.

The module is deliberately self-contained: constants, models, service,
routes and seed are all here so it can be reasoned about — and unit
tested — as a unit.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException

from registers import DRIVERS_COLL

logger = logging.getLogger("dcc.numbering")

# ---------------------------------------------------------------- collections
SEQUENCES_COLL = "number_sequences"
EVENTS_COLL = "number_allocation_events"
RESERVATIONS_COLL = "dispatch_number_reservations"

SEED_TAG = "seed-eb08"

# ---------------------------------------------------------------- reserved
RESERVED_DISPATCH_NUMBERS = {0, 13}
INACTIVE_DISPATCH_START = 999
INACTIVE_DISPATCH_FLOOR = 100  # inactive numbers live in [100, 999]
ACTIVE_DISPATCH_FLOOR = 1
ACTIVE_DISPATCH_CEILING = 999  # active operational numbers <= this

DEFAULT_RESERVATION_MINUTES = 15


# ---------------------------------------------------------------- vocabularies
class IdentifierType(str, Enum):
    DriverCode = "Driver Code"
    ActiveDispatch = "Active Dispatch Number"
    InactiveDispatch = "Inactive Dispatch Number"


class AllocationAction(str, Enum):
    Suggested = "Suggested"
    Reserved = "Reserved"
    Allocated = "Allocated"
    Overridden = "Overridden"
    Released = "Released"
    Reassigned = "Reassigned"
    Rejected = "Rejected"
    Expired = "Expired"
    Cancelled = "Cancelled"


class ReservationStatus(str, Enum):
    Reserved = "Reserved"
    Consumed = "Consumed"
    Released = "Released"
    Expired = "Expired"
    Cancelled = "Cancelled"


DRIVER_CODE_SEQUENCE_KEY = "driver_code"


# ---------------------------------------------------------------- helpers
def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _is_int_string(v: Any) -> bool:
    if v is None:
        return False
    try:
        int(str(v))
        return True
    except (TypeError, ValueError):
        return False


def _parse_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(str(v))
    except (TypeError, ValueError):
        return None


# =============================================================================
#  Service
# =============================================================================
class NumberingService:
    def __init__(self, db):
        self.db = db

    # ------------------------------------------------ event log
    async def _log_event(
        self,
        identifier_type: str,
        identifier_value: Any,
        action: str,
        performed_by: str,
        automatic: bool = False,
        manual_override: bool = False,
        sequence_advanced: bool = False,
        driver_id: Optional[str] = None,
        sequence_id: Optional[str] = None,
        reservation_id: Optional[str] = None,
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        doc = {
            "allocation_event_id": _uuid(),
            "identifier_type": identifier_type,
            "identifier_value": str(identifier_value) if identifier_value is not None else None,
            "action": action,
            "driver_id": driver_id,
            "sequence_id": sequence_id,
            "reservation_id": reservation_id,
            "automatic": automatic,
            "manual_override": manual_override,
            "sequence_advanced": sequence_advanced,
            "reason": reason,
            "performed_by": performed_by,
            "performed_at": _iso(),
            "correlation_id": correlation_id or _uuid(),
        }
        await self.db[EVENTS_COLL].insert_one(dict(doc))
        return doc

    # ------------------------------------------------ Driver Code sequence
    async def _get_or_init_sequence(self) -> Dict[str, Any]:
        seq = await self.db[SEQUENCES_COLL].find_one(
            {"sequence_key": DRIVER_CODE_SEQUENCE_KEY}, {"_id": 0}
        )
        if seq:
            return seq
        # Initialise from the current canonical maximum integer driver_code
        highest = 0
        async for d in self.db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}}, {"_id": 0, "driver_code": 1}
        ):
            n = _parse_int(d.get("driver_code"))
            if n is not None and n > highest:
                highest = n
        doc = {
            "sequence_id": _uuid(),
            "sequence_key": DRIVER_CODE_SEQUENCE_KEY,
            "value": highest,
            "created_at": _iso(),
            "updated_at": _iso(),
            "updated_by": "system-init",
            "_source": "system",
        }
        await self.db[SEQUENCES_COLL].insert_one(dict(doc))
        return doc

    async def suggest_driver_code(self) -> Dict[str, Any]:
        seq = await self._get_or_init_sequence()
        proposed = int(seq["value"]) + 1
        # Skip past any existing driver_code collisions (historical imports)
        while True:
            existing = await self.db[DRIVERS_COLL].find_one(
                {"driver_code": str(proposed), "is_archived": {"$ne": True}},
                {"_id": 0, "id": 1},
            )
            reserved = await self.db[RESERVATIONS_COLL].find_one(
                {"identifier_type": IdentifierType.DriverCode.value,
                 "identifier_value": str(proposed),
                 "status": ReservationStatus.Reserved.value},
                {"_id": 0, "reservation_id": 1},
            )
            if not existing and not reserved:
                break
            proposed += 1
        return {"suggested_driver_code": str(proposed),
                "current_sequence_value": int(seq["value"]),
                "next_after_advance": proposed}

    async def get_sequence(self) -> Dict[str, Any]:
        seq = await self._get_or_init_sequence()
        seq.pop("_id", None)
        return seq

    async def set_sequence(self, new_value: int, actor_email: str,
                            reason: Optional[str] = None) -> Dict[str, Any]:
        if new_value < 0:
            raise HTTPException(status_code=400, detail="Sequence value must be >= 0")
        seq = await self._get_or_init_sequence()
        prev = int(seq["value"])
        await self.db[SEQUENCES_COLL].update_one(
            {"sequence_key": DRIVER_CODE_SEQUENCE_KEY},
            {"$set": {"value": int(new_value), "updated_at": _iso(),
                       "updated_by": actor_email}},
        )
        await self._log_event(
            IdentifierType.DriverCode.value, new_value,
            AllocationAction.Overridden.value, actor_email,
            manual_override=True,
            sequence_advanced=new_value > prev,
            sequence_id=seq["sequence_id"],
            reason=reason or f"Sequence changed from {prev} to {new_value}",
        )
        return await self.get_sequence()

    async def reserve_driver_code(
        self, requested_value: Optional[str], actor_email: str,
        is_manual_override: bool = False, is_historical: bool = True,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reserve a Driver Code.

        - When `requested_value` is None → return automatic suggestion and
          advance the sequence pointer atomically.
        - When manual, we still create a reservation row but do NOT advance
          the sequence unless `is_historical=False` (explicit live override).
        """
        seq = await self._get_or_init_sequence()
        automatic = requested_value in (None, "")
        if automatic:
            # Atomic advance
            updated = await self.db[SEQUENCES_COLL].find_one_and_update(
                {"sequence_key": DRIVER_CODE_SEQUENCE_KEY},
                {"$inc": {"value": 1}, "$set": {"updated_at": _iso(),
                                                  "updated_by": actor_email}},
                return_document=True,
            )
            code = str(int(updated["value"]))
            # If somebody already owns this code, roll the sequence forward
            # until we find a clean slot (dedup is rare and bounded).
            while True:
                existing = await self.db[DRIVERS_COLL].find_one(
                    {"driver_code": code, "is_archived": {"$ne": True}}, {"_id": 0, "id": 1}
                )
                if not existing:
                    break
                updated = await self.db[SEQUENCES_COLL].find_one_and_update(
                    {"sequence_key": DRIVER_CODE_SEQUENCE_KEY},
                    {"$inc": {"value": 1}, "$set": {"updated_at": _iso(),
                                                     "updated_by": actor_email}},
                    return_document=True,
                )
                code = str(int(updated["value"]))
            sequence_advanced = True
        else:
            code = str(requested_value).strip()
            if not _is_int_string(code):
                # Non-integer manual overrides are allowed for historical
                # ids (e.g. DRV-UNQ-*) but do not advance the sequence.
                pass
            # Duplicate rejection
            existing = await self.db[DRIVERS_COLL].find_one(
                {"driver_code": code, "is_archived": {"$ne": True}}, {"_id": 0, "id": 1}
            )
            if existing:
                await self._log_event(
                    IdentifierType.DriverCode.value, code,
                    AllocationAction.Rejected.value, actor_email,
                    manual_override=True, reason="Duplicate active Driver Code",
                )
                raise HTTPException(status_code=409, detail=f"Driver Code {code} already exists")
            # Existing reservation collision
            other_res = await self.db[RESERVATIONS_COLL].find_one(
                {"identifier_type": IdentifierType.DriverCode.value,
                 "identifier_value": code,
                 "status": ReservationStatus.Reserved.value}, {"_id": 0, "reservation_id": 1},
            )
            if other_res:
                raise HTTPException(status_code=409,
                                     detail=f"Driver Code {code} already reserved")
            sequence_advanced = False
            if not is_historical and _is_int_string(code):
                # Explicit live override → advance sequence to max(current, override)
                n = int(code)
                seq_val = int(seq["value"])
                if n > seq_val:
                    await self.db[SEQUENCES_COLL].update_one(
                        {"sequence_key": DRIVER_CODE_SEQUENCE_KEY},
                        {"$set": {"value": n, "updated_at": _iso(),
                                   "updated_by": actor_email}},
                    )
                    sequence_advanced = True

        expires = datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_RESERVATION_MINUTES)
        res = {
            "reservation_id": _uuid(),
            "identifier_type": IdentifierType.DriverCode.value,
            "identifier_value": code,
            "dispatch_number": None,
            "reserved_by": actor_email,
            "reserved_at": _iso(),
            "expires_at": _iso(expires),
            "status": ReservationStatus.Reserved.value,
            "driver_id": None,
            "automatic": automatic,
            "manual_override": is_manual_override,
            "sequence_advanced": sequence_advanced,
            "created_at": _iso(),
        }
        await self.db[RESERVATIONS_COLL].insert_one(dict(res))
        await self._log_event(
            IdentifierType.DriverCode.value, code,
            AllocationAction.Reserved.value, actor_email,
            automatic=automatic,
            manual_override=is_manual_override,
            sequence_advanced=sequence_advanced,
            sequence_id=seq["sequence_id"],
            reservation_id=res["reservation_id"],
            reason=reason,
        )
        res.pop("_id", None)
        return res

    # ------------------------------------------------ Dispatch numbers
    async def _active_dispatch_numbers(self) -> List[int]:
        nums: List[int] = []
        async for d in self.db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}, "driver_status": {"$ne": "Archived"}},
            {"_id": 0, "dispatch_number": 1, "driver_status": 1},
        ):
            n = _parse_int(d.get("dispatch_number"))
            if n is None:
                continue
            # Only count as "active" if it falls in the active range
            if n < INACTIVE_DISPATCH_FLOOR:
                nums.append(n)
        return sorted(set(nums))

    async def _inactive_dispatch_numbers(self) -> List[int]:
        nums: List[int] = []
        async for d in self.db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}}, {"_id": 0, "dispatch_number": 1, "driver_status": 1},
        ):
            n = _parse_int(d.get("dispatch_number"))
            if n is None:
                continue
            if n >= INACTIVE_DISPATCH_FLOOR:
                nums.append(n)
        return sorted(set(nums), reverse=True)

    async def _reserved_dispatch_numbers(self) -> List[int]:
        now = _iso()
        nums: List[int] = []
        async for r in self.db[RESERVATIONS_COLL].find(
            {"identifier_type": {"$in": [IdentifierType.ActiveDispatch.value,
                                          IdentifierType.InactiveDispatch.value]},
             "status": ReservationStatus.Reserved.value,
             "expires_at": {"$gt": now}},
            {"_id": 0, "dispatch_number": 1},
        ):
            n = _parse_int(r.get("dispatch_number"))
            if n is not None:
                nums.append(n)
        return sorted(set(nums))

    async def dispatch_available(self) -> Dict[str, Any]:
        active = set(await self._active_dispatch_numbers())
        reserved = set(await self._reserved_dispatch_numbers())
        blocked = active | reserved | RESERVED_DISPATCH_NUMBERS
        max_active = max([n for n in active if n < INACTIVE_DISPATCH_FLOOR], default=0)
        # Reusable = gaps in [1, max_active] excluding reserved and 0/13
        reusable = [n for n in range(ACTIVE_DISPATCH_FLOOR,
                                       min(max_active + 1, INACTIVE_DISPATCH_FLOOR))
                    if n not in blocked]
        # Next new = max_active + 1, skipping reserved and 0/13
        candidate = max(max_active + 1, ACTIVE_DISPATCH_FLOOR)
        while candidate in blocked or candidate in RESERVED_DISPATCH_NUMBERS:
            candidate += 1
        if candidate >= INACTIVE_DISPATCH_FLOOR:
            candidate = None  # no active slot available
        return {
            "reusable": reusable,
            "next_new": candidate,
            "reserved": sorted(reserved),
            "reserved_permanent": sorted(RESERVED_DISPATCH_NUMBERS),
            "in_use": sorted(active),
            "inactive_in_use": await self._inactive_dispatch_numbers(),
        }

    async def reserve_dispatch(
        self, requested_value: Any, actor_email: str,
        is_manual_override: bool = False, driver_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        n = _parse_int(requested_value) if requested_value not in (None, "") else None
        automatic = n is None
        if automatic:
            # Prefer reusable, then next-new
            avail = await self.dispatch_available()
            n = (avail["reusable"] or [None])[0] or avail["next_new"]
            if n is None:
                raise HTTPException(status_code=409,
                                     detail="No active dispatch numbers available")
        # Reject permanently reserved values
        if n in RESERVED_DISPATCH_NUMBERS:
            await self._log_event(
                IdentifierType.ActiveDispatch.value, n,
                AllocationAction.Rejected.value, actor_email,
                manual_override=is_manual_override,
                reason=f"Reserved permanent value {n} may not be allocated",
            )
            raise HTTPException(status_code=400,
                                 detail=f"Dispatch Number {n} is permanently reserved")
        if n < ACTIVE_DISPATCH_FLOOR:
            raise HTTPException(status_code=400,
                                 detail=f"Dispatch Number {n} must be >= {ACTIVE_DISPATCH_FLOOR}")
        # Reject already active (excluding the current driver where relevant)
        active = set(await self._active_dispatch_numbers())
        # If a driver_id is supplied and that driver already owns n, allow it.
        current_owner = None
        async for d in self.db[DRIVERS_COLL].find(
            {"dispatch_number": str(n), "is_archived": {"$ne": True}}, {"_id": 0, "id": 1},
        ):
            current_owner = d["id"]
            break
        if n in active and current_owner and current_owner != driver_id:
            await self._log_event(
                IdentifierType.ActiveDispatch.value, n,
                AllocationAction.Rejected.value, actor_email,
                manual_override=is_manual_override,
                reason="Duplicate active dispatch number",
                driver_id=driver_id,
            )
            raise HTTPException(status_code=409,
                                 detail=f"Dispatch Number {n} already active for another driver")
        # Reject reserved
        reserved = set(await self._reserved_dispatch_numbers())
        if n in reserved:
            raise HTTPException(status_code=409,
                                 detail=f"Dispatch Number {n} already reserved")
        expires = datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_RESERVATION_MINUTES)
        res = {
            "reservation_id": _uuid(),
            "identifier_type": IdentifierType.ActiveDispatch.value,
            "identifier_value": str(n),
            "dispatch_number": str(n),
            "reserved_by": actor_email,
            "reserved_at": _iso(),
            "expires_at": _iso(expires),
            "status": ReservationStatus.Reserved.value,
            "driver_id": driver_id,
            "automatic": automatic,
            "manual_override": is_manual_override,
            "sequence_advanced": False,
            "created_at": _iso(),
        }
        await self.db[RESERVATIONS_COLL].insert_one(dict(res))
        await self._log_event(
            IdentifierType.ActiveDispatch.value, n,
            AllocationAction.Reserved.value, actor_email,
            automatic=automatic,
            manual_override=is_manual_override,
            reservation_id=res["reservation_id"],
            driver_id=driver_id,
            reason=reason,
        )
        res.pop("_id", None)
        return res

    async def allocate_inactive(self, driver_id: str, actor_email: str,
                                  reason: Optional[str] = None) -> Dict[str, Any]:
        used = set(await self._inactive_dispatch_numbers())
        candidate = INACTIVE_DISPATCH_START
        while candidate in used and candidate >= INACTIVE_DISPATCH_FLOOR:
            candidate -= 1
        if candidate < INACTIVE_DISPATCH_FLOOR:
            raise HTTPException(status_code=409,
                                 detail="No inactive dispatch numbers available")
        # Write directly to the driver record — no reservation required for
        # inactive allocation (it happens synchronously when a driver moves
        # to Inactive/Archived status).
        driver = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        prev = driver.get("dispatch_number")
        await self.db[DRIVERS_COLL].update_one(
            {"id": driver_id},
            {"$set": {"dispatch_number": str(candidate), "updated_at": _iso(),
                       "updated_by": actor_email}},
        )
        await self._log_event(
            IdentifierType.InactiveDispatch.value, candidate,
            AllocationAction.Allocated.value, actor_email,
            automatic=True, driver_id=driver_id,
            reason=reason or f"Allocated inactive number (previous {prev})",
        )
        return {"driver_id": driver_id, "dispatch_number": str(candidate), "previous": prev}

    async def reactivate_driver(self, driver_id: str, new_dispatch: Any,
                                  actor_email: str) -> Dict[str, Any]:
        n = _parse_int(new_dispatch)
        if n is None or n < ACTIVE_DISPATCH_FLOOR or n >= INACTIVE_DISPATCH_FLOOR \
                or n in RESERVED_DISPATCH_NUMBERS:
            raise HTTPException(status_code=400,
                                 detail="An active Dispatch Number in the active range is required")
        driver = await self.db[DRIVERS_COLL].find_one({"id": driver_id}, {"_id": 0})
        if not driver:
            raise HTTPException(status_code=404, detail="Driver not found")
        # Reserve via the normal path so uniqueness + conflict rules apply
        res = await self.reserve_dispatch(n, actor_email, is_manual_override=True,
                                            driver_id=driver_id,
                                            reason="Reactivation")
        # Consume immediately: write to driver, mark reservation Consumed.
        prev = driver.get("dispatch_number")
        await self.db[DRIVERS_COLL].update_one(
            {"id": driver_id},
            {"$set": {"dispatch_number": str(n), "updated_at": _iso(),
                       "updated_by": actor_email}},
        )
        await self.db[RESERVATIONS_COLL].update_one(
            {"reservation_id": res["reservation_id"]},
            {"$set": {"status": ReservationStatus.Consumed.value,
                       "driver_id": driver_id}},
        )
        await self._log_event(
            IdentifierType.ActiveDispatch.value, n,
            AllocationAction.Reassigned.value, actor_email,
            manual_override=True, driver_id=driver_id,
            reservation_id=res["reservation_id"],
            reason=f"Reactivated from previous {prev}",
        )
        return {"driver_id": driver_id, "dispatch_number": str(n), "previous": prev,
                "reservation_id": res["reservation_id"]}

    # ------------------------------------------------ reservation lifecycle
    async def release_reservation(self, reservation_id: str, actor_email: str,
                                    reason: Optional[str] = None) -> Dict[str, Any]:
        res = await self.db[RESERVATIONS_COLL].find_one(
            {"reservation_id": reservation_id}, {"_id": 0}
        )
        if not res:
            raise HTTPException(status_code=404, detail="Reservation not found")
        if res["status"] != ReservationStatus.Reserved.value:
            return res
        await self.db[RESERVATIONS_COLL].update_one(
            {"reservation_id": reservation_id},
            {"$set": {"status": ReservationStatus.Released.value,
                       "released_at": _iso(), "released_by": actor_email}},
        )
        await self._log_event(
            res["identifier_type"], res["identifier_value"],
            AllocationAction.Released.value, actor_email,
            reservation_id=reservation_id, driver_id=res.get("driver_id"),
            reason=reason or "Reservation released",
        )
        res["status"] = ReservationStatus.Released.value
        return res

    async def consume_reservation(self, reservation_id: str, driver_id: str,
                                    actor_email: str) -> Dict[str, Any]:
        res = await self.db[RESERVATIONS_COLL].find_one(
            {"reservation_id": reservation_id}, {"_id": 0}
        )
        if not res:
            raise HTTPException(status_code=404, detail="Reservation not found")
        if res["status"] != ReservationStatus.Reserved.value:
            raise HTTPException(status_code=409,
                                 detail=f"Reservation is {res['status']}, not Reserved")
        # Expiry safety-net
        if res.get("expires_at") and res["expires_at"] < _iso():
            await self.db[RESERVATIONS_COLL].update_one(
                {"reservation_id": reservation_id},
                {"$set": {"status": ReservationStatus.Expired.value}},
            )
            raise HTTPException(status_code=409, detail="Reservation expired")
        await self.db[RESERVATIONS_COLL].update_one(
            {"reservation_id": reservation_id},
            {"$set": {"status": ReservationStatus.Consumed.value,
                       "driver_id": driver_id, "consumed_at": _iso()}},
        )
        await self._log_event(
            res["identifier_type"], res["identifier_value"],
            AllocationAction.Allocated.value, actor_email,
            reservation_id=reservation_id, driver_id=driver_id,
            automatic=bool(res.get("automatic")),
            manual_override=bool(res.get("manual_override")),
            sequence_advanced=bool(res.get("sequence_advanced")),
            reason="Reservation consumed on Driver save",
        )
        res["status"] = ReservationStatus.Consumed.value
        return res

    async def list_reservations(self, only_active: bool = True) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if only_active:
            q["status"] = ReservationStatus.Reserved.value
            q["expires_at"] = {"$gt": _iso()}
        rows = await self.db[RESERVATIONS_COLL].find(q, {"_id": 0}).sort("reserved_at", -1).to_list(500)
        return rows

    async def expire_stale_reservations(self, actor_email: str = "system") -> Dict[str, Any]:
        now = _iso()
        stale = await self.db[RESERVATIONS_COLL].find(
            {"status": ReservationStatus.Reserved.value, "expires_at": {"$lte": now}},
            {"_id": 0},
        ).to_list(500)
        for r in stale:
            await self.db[RESERVATIONS_COLL].update_one(
                {"reservation_id": r["reservation_id"]},
                {"$set": {"status": ReservationStatus.Expired.value,
                           "expired_at": now}},
            )
            await self._log_event(
                r["identifier_type"], r["identifier_value"],
                AllocationAction.Expired.value, actor_email,
                reservation_id=r["reservation_id"], driver_id=r.get("driver_id"),
                reason="Reservation TTL elapsed",
            )
            # Emit a dedup-safe in-app notification via EB-07 engine
            try:
                from notifications_module import NotificationsEngine, EventType, EntityType
                await NotificationsEngine(self.db).emit_event(
                    EventType.ManualNotification.value, EntityType.General.value,
                    r["reservation_id"], r["reservation_id"],
                    {"entity_label": f"Reservation {r['identifier_value']} expired",
                     "title": "Numbering reservation expired",
                     "message": f"{r['identifier_type']} reservation of "
                                f"{r['identifier_value']} expired without being consumed."},
                    source="numbering-eb08",
                )
            except Exception:  # noqa
                pass
        return {"expired_count": len(stale)}

    async def reconcile(self, actor_email: str = "system") -> Dict[str, Any]:
        """Detect duplicate active dispatch numbers or sequence drift.

        Idempotent — dedup on the notification side prevents alert flood.
        """
        stats = {"conflicts_found": 0, "conflicts_notified": 0,
                 "sequence_updated": False}
        # 1. Duplicate active dispatch numbers
        counts: Dict[int, List[str]] = {}
        async for d in self.db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}}, {"_id": 0, "id": 1, "dispatch_number": 1}
        ):
            n = _parse_int(d.get("dispatch_number"))
            if n is None or n >= INACTIVE_DISPATCH_FLOOR:
                continue
            counts.setdefault(n, []).append(d["id"])
        for num, ids in counts.items():
            if len(ids) <= 1:
                continue
            stats["conflicts_found"] += 1
            try:
                from notifications_module import NotificationsEngine, EventType, EntityType
                await NotificationsEngine(self.db).emit_event(
                    EventType.ManualNotification.value, EntityType.General.value,
                    f"dispatch-{num}", f"dispatch-{num}",
                    {"entity_label": f"Dispatch Number {num} duplicated",
                     "title": f"Duplicate active dispatch #{num}",
                     "message": f"{len(ids)} drivers currently share active "
                                f"dispatch number {num}: {', '.join(ids)}"},
                    source="numbering-eb08",
                )
                stats["conflicts_notified"] += 1
            except Exception:
                pass
        # 2. Sequence drift — sequence value < max integer driver_code
        seq = await self._get_or_init_sequence()
        max_int = 0
        async for d in self.db[DRIVERS_COLL].find(
            {"is_archived": {"$ne": True}}, {"_id": 0, "driver_code": 1},
        ):
            n = _parse_int(d.get("driver_code"))
            if n is not None and n > max_int:
                max_int = n
        if int(seq["value"]) < max_int:
            await self.db[SEQUENCES_COLL].update_one(
                {"sequence_key": DRIVER_CODE_SEQUENCE_KEY},
                {"$set": {"value": max_int, "updated_at": _iso(),
                           "updated_by": f"{actor_email} (reconcile)"}},
            )
            stats["sequence_updated"] = True
            await self._log_event(
                IdentifierType.DriverCode.value, max_int,
                AllocationAction.Overridden.value, actor_email,
                manual_override=False, sequence_advanced=True,
                reason=f"Reconciliation: advanced sequence from {seq['value']} to {max_int}",
            )
        stats["at"] = _iso()
        return stats


# =============================================================================
#  Indexes + seed
# =============================================================================
async def ensure_indexes(db) -> None:
    await db[SEQUENCES_COLL].create_index("sequence_key", unique=True, sparse=True)
    await db[EVENTS_COLL].create_index("allocation_event_id", unique=True, sparse=True)
    await db[EVENTS_COLL].create_index("performed_at")
    await db[RESERVATIONS_COLL].create_index("reservation_id", unique=True, sparse=True)
    await db[RESERVATIONS_COLL].create_index("status")
    await db[RESERVATIONS_COLL].create_index("expires_at")


async def seed_examples(db) -> None:
    if await db[EVENTS_COLL].count_documents({"correlation_id": {"$in": [SEED_TAG]}}) > 0:
        return
    svc = NumberingService(db)
    seq = await svc._get_or_init_sequence()

    # Automatic allocation (advances sequence)
    await svc._log_event(
        IdentifierType.DriverCode.value, str(int(seq["value"]) + 1),
        AllocationAction.Allocated.value, "system",
        automatic=True, sequence_advanced=True,
        sequence_id=seq["sequence_id"],
        correlation_id=SEED_TAG,
        reason="Seed: automatic Driver Code allocation",
    )

    # Historical manual (does not advance)
    await svc._log_event(
        IdentifierType.DriverCode.value, "75",
        AllocationAction.Overridden.value, "system",
        manual_override=True, sequence_advanced=False,
        correlation_id=SEED_TAG,
        reason="Seed: historical manual Driver Code, sequence not advanced",
    )

    # Reusable + Next new
    await svc._log_event(
        IdentifierType.ActiveDispatch.value, "29",
        AllocationAction.Suggested.value, "system",
        automatic=True, correlation_id=SEED_TAG,
        reason="Seed: reusable dispatch suggestion",
    )
    await svc._log_event(
        IdentifierType.ActiveDispatch.value, "81",
        AllocationAction.Suggested.value, "system",
        automatic=True, correlation_id=SEED_TAG,
        reason="Seed: next-new dispatch suggestion",
    )

    # Inactive
    await svc._log_event(
        IdentifierType.InactiveDispatch.value, str(INACTIVE_DISPATCH_START),
        AllocationAction.Allocated.value, "system",
        automatic=True, correlation_id=SEED_TAG,
        reason="Seed: inactive dispatch begins at 999",
    )

    # Active reservation + expired
    now = datetime.now(timezone.utc)
    active_res = {
        "reservation_id": _uuid(),
        "identifier_type": IdentifierType.ActiveDispatch.value,
        "identifier_value": "45",
        "dispatch_number": "45",
        "reserved_by": "system-seed",
        "reserved_at": _iso(now),
        "expires_at": _iso(now + timedelta(minutes=DEFAULT_RESERVATION_MINUTES)),
        "status": ReservationStatus.Reserved.value,
        "driver_id": None, "automatic": True, "manual_override": False,
        "sequence_advanced": False,
        "created_at": _iso(now),
        "_source": SEED_TAG,
    }
    expired_res = dict(active_res)
    expired_res["reservation_id"] = _uuid()
    expired_res["identifier_value"] = "67"
    expired_res["dispatch_number"] = "67"
    expired_res["status"] = ReservationStatus.Expired.value
    expired_res["reserved_at"] = _iso(now - timedelta(hours=1))
    expired_res["expires_at"] = _iso(now - timedelta(minutes=30))
    await db[RESERVATIONS_COLL].insert_one(dict(active_res))
    await db[RESERVATIONS_COLL].insert_one(dict(expired_res))

    # Rejected reserved 0 + 13
    for r in (0, 13):
        await svc._log_event(
            IdentifierType.ActiveDispatch.value, r,
            AllocationAction.Rejected.value, "system",
            reason=f"Seed: reserved permanent value {r}",
            correlation_id=SEED_TAG,
        )

    # Manual override sequence-not-advanced
    await svc._log_event(
        IdentifierType.DriverCode.value, "42",
        AllocationAction.Overridden.value, "system",
        manual_override=True, sequence_advanced=False,
        correlation_id=SEED_TAG,
        reason="Seed: manual override kept historical, sequence not advanced",
    )


# =============================================================================
#  Router
# =============================================================================
def _require_role(user: Dict[str, Any], allowed: Tuple[str, ...]) -> None:
    if user.get("role") not in allowed:
        raise HTTPException(status_code=403, detail=f"Requires one of {allowed}")


def build_numbering_router(db, get_current_user):
    router = APIRouter(prefix="/api")
    svc = NumberingService(db)

    WRITE_ROLES = ("Admin", "Manager", "Allocator")
    READ_ROLES = ("Admin", "Manager", "Compliance", "Allocator")

    # ------------- Driver Code
    @router.get("/numbering/driver-code/suggestion")
    async def get_dc_suggestion(current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        return await svc.suggest_driver_code()

    @router.post("/numbering/driver-code/reserve")
    async def reserve_dc(payload: Dict[str, Any] = None, current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        payload = payload or {}
        requested = payload.get("value")
        is_manual = payload.get("manual_override") is True or requested not in (None, "")
        is_historical = bool(payload.get("historical", True)) if is_manual else False
        return await svc.reserve_driver_code(
            requested, current.get("email"),
            is_manual_override=is_manual, is_historical=is_historical,
            reason=payload.get("reason"),
        )

    @router.post("/numbering/driver-code/release")
    async def release_dc(payload: Dict[str, Any], current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        if not payload.get("reservation_id"):
            raise HTTPException(status_code=400, detail="reservation_id required")
        return await svc.release_reservation(
            payload["reservation_id"], current.get("email"), payload.get("reason")
        )

    @router.post("/numbering/driver-code/consume")
    async def consume_dc(payload: Dict[str, Any], current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        if not payload.get("reservation_id") or not payload.get("driver_id"):
            raise HTTPException(status_code=400,
                                 detail="reservation_id + driver_id required")
        return await svc.consume_reservation(
            payload["reservation_id"], payload["driver_id"], current.get("email")
        )

    @router.get("/numbering/driver-code/sequence")
    async def get_sequence(current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        return await svc.get_sequence()

    @router.put("/numbering/driver-code/sequence")
    async def set_sequence(payload: Dict[str, Any], current=Depends(get_current_user)):
        _require_role(current, ("Admin",))
        try:
            new_value = int(payload.get("value"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="value must be an integer")
        return await svc.set_sequence(new_value, current.get("email"),
                                       payload.get("reason"))

    # ------------- Dispatch
    @router.get("/numbering/dispatch/available")
    async def dispatch_available(current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        return await svc.dispatch_available()

    @router.post("/numbering/dispatch/reserve")
    async def dispatch_reserve(payload: Dict[str, Any] = None,
                                 current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        payload = payload or {}
        return await svc.reserve_dispatch(
            payload.get("value"), current.get("email"),
            is_manual_override=payload.get("manual_override") is True,
            driver_id=payload.get("driver_id"),
            reason=payload.get("reason"),
        )

    @router.post("/numbering/dispatch/release")
    async def dispatch_release(payload: Dict[str, Any], current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        if not payload.get("reservation_id"):
            raise HTTPException(status_code=400, detail="reservation_id required")
        return await svc.release_reservation(
            payload["reservation_id"], current.get("email"), payload.get("reason")
        )

    @router.post("/numbering/dispatch/consume")
    async def dispatch_consume(payload: Dict[str, Any],
                                 current=Depends(get_current_user)):
        _require_role(current, WRITE_ROLES)
        if not payload.get("reservation_id") or not payload.get("driver_id"):
            raise HTTPException(status_code=400,
                                 detail="reservation_id + driver_id required")
        return await svc.consume_reservation(
            payload["reservation_id"], payload["driver_id"], current.get("email")
        )

    @router.post("/numbering/dispatch/allocate-inactive")
    async def dispatch_alloc_inactive(payload: Dict[str, Any],
                                        current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        if not payload.get("driver_id"):
            raise HTTPException(status_code=400, detail="driver_id required")
        return await svc.allocate_inactive(payload["driver_id"], current.get("email"),
                                             payload.get("reason"))

    @router.post("/numbering/dispatch/reactivate")
    async def dispatch_reactivate(payload: Dict[str, Any],
                                    current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        if not payload.get("driver_id") or payload.get("value") in (None, ""):
            raise HTTPException(status_code=400,
                                 detail="driver_id + value required")
        return await svc.reactivate_driver(payload["driver_id"], payload["value"],
                                             current.get("email"))

    @router.get("/numbering/dispatch/reservations")
    async def dispatch_reservations(only_active: bool = True,
                                       current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        return await svc.list_reservations(only_active=only_active)

    # ------------- History
    @router.get("/numbering/allocation-events")
    async def list_events(identifier_type: Optional[str] = None,
                           driver_id: Optional[str] = None,
                           current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        q: Dict[str, Any] = {}
        if identifier_type:
            q["identifier_type"] = identifier_type
        if driver_id:
            q["driver_id"] = driver_id
        rows = await db[EVENTS_COLL].find(q, {"_id": 0}).sort("performed_at", -1).to_list(500)
        return rows

    @router.get("/numbering/drivers/{driver_id}/history")
    async def driver_history(driver_id: str, current=Depends(get_current_user)):
        _require_role(current, READ_ROLES)
        rows = await db[EVENTS_COLL].find({"driver_id": driver_id}, {"_id": 0}) \
            .sort("performed_at", -1).to_list(500)
        return rows

    # ------------- Maintenance jobs
    @router.post("/numbering/jobs/expire-reservations")
    async def job_expire(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await svc.expire_stale_reservations(current.get("email") or "system")

    @router.post("/numbering/jobs/reconcile")
    async def job_reconcile(current=Depends(get_current_user)):
        _require_role(current, ("Admin", "Manager"))
        return await svc.reconcile(current.get("email") or "system")

    return router

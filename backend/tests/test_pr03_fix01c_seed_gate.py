"""PR-03-FIX-01C · Production seed-safety gate.

Locks in that the four authorised demo/sample/seed startup hooks are
skipped when `APP_ENV=production` and preserved when `APP_ENV` is
anything else (dev / preview / test / staging).

Gated hooks:
    * seed_sample_data()        (server.py:519 on_startup call site)
    * backfill_driver_ids()     (server.py:519 on_startup call site)
    * seed_registers(db)        (server.py:519 on_startup call site)
    * seed_relationships(db)    (server.py:519 on_startup call site)

Unchanged (deliberately out of scope — must NOT be gated):
    * create_index / ensure_indexes  (schema-only)
    * seed_admin                     (admin bootstrap, canonical to all envs)
    * migrate_existing_drivers       (canonical-field migration)
    * reconcile_vehicle_lifecycle    (EB-R02C owner-locked remap)
    * startup_reconciliation         (relationships reconciliation)
    * seed_compliance / seed_documents / notif_seed_* / num_seed /
      seed_eb09 / seed_default_template / exp_seed / mp_seed_rules /
      _seed_companies / st_seed_policies / _seed_templates    (not in
      PR-03-FIX-01C scope — behaviour preserved exactly).
"""
from __future__ import annotations

from pathlib import Path
import re
import ast
import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock

SERVER = Path("/app/backend/server.py")


def _read(): return SERVER.read_text(encoding="utf-8")


# ─── Structural tests · gate present at exact call sites ───────────────
class TestGateStructure:
    def test_production_guard_variable_defined_in_on_startup(self):
        src = _read()
        on_startup_match = re.search(
            r"async def on_startup\(\):(.*?)(?=\n@app\.on_event|\nasync def [A-Za-z_])",
            src, re.DOTALL,
        )
        assert on_startup_match, "on_startup block must be locatable"
        body = on_startup_match.group(1)
        assert '_is_production = os.environ.get("APP_ENV", "").lower() == "production"' in body, \
            "A single production-detector binding must exist inside on_startup"

    def test_seed_sample_data_gated(self):
        src = _read()
        # Guarded block must contain seed_sample_data call.
        assert re.search(
            r"if not _is_production:\s*\n\s+await seed_sample_data\(\)",
            src,
        ), "seed_sample_data must be inside an `if not _is_production:` guard"

    def test_backfill_driver_ids_gated(self):
        src = _read()
        assert re.search(
            r"if not _is_production:\s*\n\s+await seed_sample_data\(\)\s*\n\s+await backfill_driver_ids\(\)",
            src,
        ), "backfill_driver_ids must be inside the same `if not _is_production:` guard as seed_sample_data"

    def test_seed_registers_gated(self):
        src = _read()
        assert re.search(
            r"if not _is_production:\s*\n\s+await seed_registers\(db\)",
            src,
        ), "seed_registers must be inside an `if not _is_production:` guard"

    def test_seed_relationships_gated(self):
        src = _read()
        assert re.search(
            r"if not _is_production:\s*\n\s+await seed_relationships\(db\)",
            src,
        ), "seed_relationships must be inside an `if not _is_production:` guard"

    def test_no_bare_calls_to_gated_hooks_in_on_startup(self):
        src = _read()
        on_startup = re.search(
            r"async def on_startup\(\):(.*?)(?=\n@app\.on_event|\nasync def [A-Za-z_])",
            src, re.DOTALL,
        ).group(1)
        # For each gated hook, the only `await` call site must be inside
        # a guarded block. Simple proof: there is no bare line matching
        # `^    await seed_sample_data()` at base indent (4 spaces).
        for sym in ("seed_sample_data()", "backfill_driver_ids()",
                    "seed_registers(db)", "seed_relationships(db)"):
            bare = re.search(rf"^    await {re.escape(sym)}\s*$", on_startup, re.MULTILINE)
            assert bare is None, f"{sym} must not have a bare un-gated call site"


# ─── Non-regression · unrelated startup work NOT gated ─────────────────
class TestNonRegressionOtherHooks:
    def test_seed_admin_still_unconditional(self):
        src = _read()
        on_startup = re.search(
            r"async def on_startup\(\):(.*?)(?=\n@app\.on_event|\nasync def [A-Za-z_])",
            src, re.DOTALL,
        ).group(1)
        assert re.search(r"^    await seed_admin\(\)\s*$", on_startup, re.MULTILINE), \
            "seed_admin must remain unconditional — canonical to every environment"

    def test_migrate_and_reconcile_still_unconditional(self):
        src = _read()
        on_startup = re.search(
            r"async def on_startup\(\):(.*?)(?=\n@app\.on_event|\nasync def [A-Za-z_])",
            src, re.DOTALL,
        ).group(1)
        assert re.search(r"^    await migrate_existing_drivers\(db\)", on_startup, re.MULTILINE)
        assert re.search(r"^    await reconcile_vehicle_lifecycle\(db\)", on_startup, re.MULTILINE)
        assert re.search(r"^    await startup_reconciliation\(db\)", on_startup, re.MULTILINE)

    def test_out_of_scope_seed_hooks_not_gated(self):
        """Only four hooks are authorised to be gated. Prove the gate did
        not creep onto seed_compliance / seed_documents / seed_eb09 /
        _seed_companies / seed_default_template / exp_seed / etc."""
        src = _read()
        on_startup = re.search(
            r"async def on_startup\(\):(.*?)(?=\n@app\.on_event|\nasync def [A-Za-z_])",
            src, re.DOTALL,
        ).group(1)
        for sym in [
            "seed_compliance(db)", "seed_documents(db)", "notif_seed_rules(db)",
            "notif_seed_examples(db)", "num_seed(db)", "seed_eb09(db)",
            "seed_default_template(db)", "exp_seed(db)", "mp_seed_rules(db)",
            "_seed_companies(db)", "st_seed_policies(db)",
        ]:
            # These must still appear at base indent (4 spaces) — un-gated.
            # (If one were accidentally gated the match below would fail.)
            assert re.search(rf"^    await {re.escape(sym)}\s*$", on_startup, re.MULTILINE), \
                f"{sym} must remain un-gated and un-indented beyond base — scope creep"


# ─── Behavioural tests · gate actually prevents the four writes ────────
# We call on_startup() directly with APP_ENV in two settings and assert
# which AsyncMocks were invoked. The database layer is mocked to a stub
# so we don't need Mongo for this test.

class _StubColl:
    def __init__(self):
        self.create_index = AsyncMock()
        self.count_documents = AsyncMock(return_value=1)   # non-empty to pass sample-data guard
        self.find = AsyncMock()
        self.find_one = AsyncMock(return_value=None)
        self.insert_one = AsyncMock()
        self.insert_many = AsyncMock()
        self.update_one = AsyncMock()
        self.update_many = AsyncMock(return_value=types.SimpleNamespace(modified_count=0))

class _StubDB:
    def __init__(self):
        self._colls = {}
        self.users = _StubColl()
    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _StubColl()
        return self._colls[name]


def _run_on_startup_with_app_env(monkeypatch, app_env_value):
    """Call server.on_startup() with APP_ENV set, capturing which of the
    four gated hooks were invoked. Returns a dict with four booleans."""
    sys.path.insert(0, "/app/backend")
    import server as srv

    stub_db = _StubDB()
    monkeypatch.setattr(srv, "db", stub_db, raising=True)
    monkeypatch.setenv("APP_ENV", app_env_value)

    called = {
        "seed_sample_data": False,
        "backfill_driver_ids": False,
        "seed_registers": False,
        "seed_relationships": False,
    }

    async def _mk_tracker(key):
        async def _t(*args, **kwargs):
            called[key] = True
        return _t

    # Patch gated-scope functions on the server module (and the registers
    # / relationships modules the inline imports pull from).
    monkeypatch.setattr(srv, "seed_sample_data", AsyncMock(side_effect=lambda: called.__setitem__("seed_sample_data", True)))
    monkeypatch.setattr(srv, "backfill_driver_ids", AsyncMock(side_effect=lambda: called.__setitem__("backfill_driver_ids", True)))
    monkeypatch.setattr(srv, "seed_admin", AsyncMock())
    # MODULE_COLLECTIONS iteration — provide a safe empty-ish set so the
    # loop runs but doesn't fault.
    monkeypatch.setattr(srv, "MODULE_COLLECTIONS", {"drivers": "drivers"}, raising=False)

    # Patch inline-import targets: registers.seed_registers,
    # relationships.seed_relationships. Everything else inside on_startup
    # (migrate_existing_drivers, reconcile_vehicle_lifecycle, ensure_indexes,
    # startup_reconciliation, seed_compliance, …) is patched to no-op
    # AsyncMock so we only measure the four gated hooks.
    import registers as reg_mod
    import relationships as rel_mod
    monkeypatch.setattr(reg_mod, "seed_registers",
                        AsyncMock(side_effect=lambda db: called.__setitem__("seed_registers", True)))
    monkeypatch.setattr(reg_mod, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(reg_mod, "migrate_existing_drivers", AsyncMock())
    monkeypatch.setattr(reg_mod, "reconcile_vehicle_lifecycle", AsyncMock())
    monkeypatch.setattr(rel_mod, "seed_relationships",
                        AsyncMock(side_effect=lambda db: called.__setitem__("seed_relationships", True)))
    monkeypatch.setattr(rel_mod, "ensure_indexes", AsyncMock())
    monkeypatch.setattr(rel_mod, "startup_reconciliation", AsyncMock())

    # Stub out all downstream module seeds so on_startup can walk through
    # without any real database side-effects.
    import compliance_records as cr; monkeypatch.setattr(cr, "ensure_indexes", AsyncMock()); monkeypatch.setattr(cr, "seed_compliance", AsyncMock()); monkeypatch.setattr(cr, "startup_reconciliation", AsyncMock())
    import documents_module as dm; monkeypatch.setattr(dm, "ensure_indexes", AsyncMock()); monkeypatch.setattr(dm, "seed_documents", AsyncMock())
    import imports_module as im; monkeypatch.setattr(im, "ensure_indexes", AsyncMock())
    import notifications_module as nm; monkeypatch.setattr(nm, "ensure_indexes", AsyncMock()); monkeypatch.setattr(nm, "seed_rules", AsyncMock()); monkeypatch.setattr(nm, "seed_examples", AsyncMock())
    import numbering_module as num; monkeypatch.setattr(num, "ensure_indexes", AsyncMock()); monkeypatch.setattr(num, "seed_examples", AsyncMock())
    import driver_profile_module as dpm; monkeypatch.setattr(dpm, "ensure_indexes", AsyncMock()); monkeypatch.setattr(dpm, "seed_eb09", AsyncMock())
    import activation_module as am; monkeypatch.setattr(am, "ensure_indexes", AsyncMock()); monkeypatch.setattr(am, "seed_default_template", AsyncMock())
    import driver_export_module as dem; monkeypatch.setattr(dem, "ensure_indexes", AsyncMock()); monkeypatch.setattr(dem, "seed_dev_examples", AsyncMock())
    import migration_prep_module as mpm; monkeypatch.setattr(mpm, "ensure_indexes", AsyncMock()); monkeypatch.setattr(mpm, "seed_transform_rules", AsyncMock())
    import company_module as cm; monkeypatch.setattr(cm, "seed_company_registry", AsyncMock())
    import storage_module as sm; monkeypatch.setattr(sm, "ensure_indexes", AsyncMock()); monkeypatch.setattr(sm, "seed_retention_policies", AsyncMock())
    import migration_commit_module as mcm; monkeypatch.setattr(mcm, "ensure_indexes", AsyncMock())
    import scheduler_module as sched
    monkeypatch.setattr(sched, "ensure_indexes", AsyncMock())
    # scheduler service bits are instantiated with no await on startup; patch _seed_templates to no-op
    monkeypatch.setattr(sched, "_seed_templates", AsyncMock(), raising=False)

    asyncio.get_event_loop().run_until_complete(srv.on_startup())
    return called


class TestGateBehaviourProductionBlocked:
    def test_production_blocks_all_four_hooks(self, monkeypatch):
        called = _run_on_startup_with_app_env(monkeypatch, "production")
        assert called["seed_sample_data"] is False
        assert called["backfill_driver_ids"] is False
        assert called["seed_registers"] is False
        assert called["seed_relationships"] is False

    def test_production_case_insensitive(self, monkeypatch):
        called = _run_on_startup_with_app_env(monkeypatch, "Production")
        assert all(v is False for v in called.values()), \
            "`Production` (any case) must still trip the gate"


class TestGateBehaviourNonProductionAllowed:
    def test_dev_runs_all_four_hooks(self, monkeypatch):
        called = _run_on_startup_with_app_env(monkeypatch, "dev")
        assert called["seed_sample_data"] is True
        assert called["backfill_driver_ids"] is True
        assert called["seed_registers"] is True
        assert called["seed_relationships"] is True

    def test_preview_runs_all_four_hooks(self, monkeypatch):
        called = _run_on_startup_with_app_env(monkeypatch, "preview")
        assert all(v is True for v in called.values())

    def test_staging_runs_all_four_hooks(self, monkeypatch):
        called = _run_on_startup_with_app_env(monkeypatch, "staging")
        assert all(v is True for v in called.values())

    def test_unset_app_env_runs_all_four_hooks(self, monkeypatch):
        # Empty string / unset → default dev behaviour is preserved
        called = _run_on_startup_with_app_env(monkeypatch, "")
        assert all(v is True for v in called.values())

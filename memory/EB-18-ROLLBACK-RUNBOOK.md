# EB-18 Rollback Runbook (18 ordered steps)
Declare · Disable providers · Disable webhooks · Disable scheduler · Suppress notifications · Stop migration · Capture failure evidence · Restore application · Data rollback (approved) · Storage rollback · Reconcile · Integrity recheck · Security recheck · Recovery recheck · Verify auth · Verify ops · Record incident · Determine retry/abandon.
Rollback is *simulated* in EB-18 framework (state transition only). Real Production rollback requires explicit approval outside EB-18.

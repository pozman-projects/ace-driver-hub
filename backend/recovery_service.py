"""EB-17b · Recovery service facade (re-export)."""
from recovery_module import (  # noqa: F401
    RecoveryService, DOMAINS, DOMAIN_COLLECTIONS, SCHEMA_VERSION,
    DEFAULT_CONFIG, ensure_indexes, build_recovery_router,
)

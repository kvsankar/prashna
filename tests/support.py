"""Values shared by the API, UI, and ops test trees."""
from __future__ import annotations

# Tests run the server with PRASHNA_SETUP_TOKEN set to this value (see
# tests/conftest.py), so first-admin setup is deterministic (UC-A-01).
SETUP_TOKEN = "test-setup-token"

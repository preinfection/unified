"""Suite-wide guards.

No test may reach the network. The update check and the changelog fetch
go through app.services.updates, which refuses to make a request while
NETWORK_ENABLED is False; tests that exercise them inject a fake fetch.
"""
from __future__ import annotations

import pytest

from app.services import updates


@pytest.fixture(autouse=True, scope="session")
def _no_network():
    updates.NETWORK_ENABLED = False
    yield
    updates.NETWORK_ENABLED = True

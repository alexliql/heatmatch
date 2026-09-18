"""Test-suite guarantees.

The ingest tests must run without network access. Rather than trusting
that every test remembers to stub its source, this blocks HTTP at the transport
layer: a test that forgets fails loudly here instead of silently downloading
tens of megabytes on a CI runner.
"""

import pytest
import requests


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("test attempted a network request; stub the source or use a fixture")

    monkeypatch.setattr(requests.sessions.Session, "request", blocked)

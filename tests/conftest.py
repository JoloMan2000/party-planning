"""Gemeinsame pytest-Fixtures für die party_engine Testsuite.

Lädt den ECHTEN Katalog aus ``catalog/*.json`` (kein Mocking, siehe
AUFGABE §43) genau einmal pro Testsession.
"""

from __future__ import annotations

import pytest

from party_engine.catalog import load_catalog
from party_engine.domain import PartyConfig


@pytest.fixture(scope="session")
def catalog():
    return load_catalog()


@pytest.fixture()
def config():
    return PartyConfig()

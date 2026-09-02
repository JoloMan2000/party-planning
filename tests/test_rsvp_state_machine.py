"""Pytest-Unit-Tests für ``accounts.rsvp_state_machine`` (Account-basierter
Pivot, Phase 1). Ergänzt den ausführbaren ``__main__``-Selbsttest im Modul
selbst um eine parametrisierte pytest-Variante für die Testsuite."""

from __future__ import annotations

import pytest

from accounts.domain import RsvpStatus
from accounts.rsvp_state_machine import can_expire, can_guest_transition, can_host_revoke

FREE_STATES = (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED)
TERMINAL_STATES = (RsvpStatus.REVOKED, RsvpStatus.EXPIRED)
NON_TERMINAL_STATES = (RsvpStatus.PENDING, RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED)


@pytest.mark.parametrize("target", [RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED])
def test_pending_kann_zu_allen_drei_zielzustaenden(target):
    assert can_guest_transition(RsvpStatus.PENDING, target) is True


@pytest.mark.parametrize("target", [RsvpStatus.REVOKED, RsvpStatus.EXPIRED])
def test_pending_kann_nicht_zu_terminalen_zustaenden(target):
    assert can_guest_transition(RsvpStatus.PENDING, target) is False


@pytest.mark.parametrize("source", FREE_STATES)
@pytest.mark.parametrize("target", FREE_STATES)
def test_frei_zwischen_accepted_tentative_declined(source, target):
    if source == target:
        pytest.skip("Selbst-Transition nicht relevant")
    assert can_guest_transition(source, target) is True


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
@pytest.mark.parametrize("target", list(RsvpStatus))
def test_terminal_zustand_erlaubt_keine_ausgehende_transition(terminal, target):
    assert can_guest_transition(terminal, target) is False


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
@pytest.mark.parametrize("source", list(RsvpStatus))
def test_terminal_zustand_ist_nicht_per_guest_erreichbar(terminal, source):
    assert can_guest_transition(source, terminal) is False


@pytest.mark.parametrize("state", NON_TERMINAL_STATES)
def test_host_kann_aus_nicht_terminalem_zustand_revoken(state):
    assert can_host_revoke(state) is True


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_host_kann_nicht_aus_terminalem_zustand_revoken(state):
    assert can_host_revoke(state) is False


@pytest.mark.parametrize("state", NON_TERMINAL_STATES)
def test_expire_erlaubt_aus_nicht_terminalem_zustand(state):
    assert can_expire(state) is True


@pytest.mark.parametrize("state", TERMINAL_STATES)
def test_expire_nicht_erlaubt_aus_terminalem_zustand(state):
    assert can_expire(state) is False

"""Pytest-Unit-Tests für ``social.friend_request_state_machine``
(Social-Graph-Phase-1). Ergänzt den ausführbaren ``__main__``-Selbsttest im
Modul selbst um eine parametrisierte pytest-Variante für die Testsuite."""

from __future__ import annotations

import pytest

from social.domain import FriendRequestStatus
from social.friend_request_state_machine import can_expire, can_receiver_respond, can_sender_cancel

TERMINAL_STATES = (
    FriendRequestStatus.ACCEPTED,
    FriendRequestStatus.DECLINED,
    FriendRequestStatus.CANCELLED,
    FriendRequestStatus.EXPIRED,
)


def test_pending_erlaubt_empfaenger_antwort():
    assert can_receiver_respond(FriendRequestStatus.PENDING) is True


def test_pending_erlaubt_sender_cancel():
    assert can_sender_cancel(FriendRequestStatus.PENDING) is True


def test_pending_erlaubt_expire():
    assert can_expire(FriendRequestStatus.PENDING) is True


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
def test_terminal_zustand_erlaubt_keine_empfaenger_antwort(terminal):
    assert can_receiver_respond(terminal) is False


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
def test_terminal_zustand_erlaubt_kein_sender_cancel(terminal):
    assert can_sender_cancel(terminal) is False


@pytest.mark.parametrize("terminal", TERMINAL_STATES)
def test_terminal_zustand_erlaubt_kein_expire(terminal):
    assert can_expire(terminal) is False


def test_alle_vier_terminalzustaende_sind_abgedeckt():
    assert set(TERMINAL_STATES) == {
        FriendRequestStatus.ACCEPTED,
        FriendRequestStatus.DECLINED,
        FriendRequestStatus.CANCELLED,
        FriendRequestStatus.EXPIRED,
    }

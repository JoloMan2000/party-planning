"""Kontrollierte FriendRequest-State-Machine (AUFGABE-Spec §15) - mirrort
strukturell ``accounts/rsvp_state_machine.py``: separate, unabhängig
testbare Funktionen pro Akteur statt einer überladenen Funktion, da die
Akteure (Empfänger, Sender, System) unterschiedliche Berechtigungen haben.

Anders als RSVP (drei UNTERSCHIEDLICH geformte Transitions-Mengen zwischen
mehreren nicht-terminalen Zuständen) reduzieren sich hier alle drei
Funktionen auf "current == PENDING", weil ``FriendRequestStatus`` genau
EINEN nicht-terminalen Zustand kennt (siehe ``social/domain.py``-Doku) -
das ist beabsichtigt, kein Kopierfehler, und wird von den Tests explizit
pro terminalem Zustand geprüft."""

from __future__ import annotations

from social.domain import FriendRequestStatus

_TERMINAL = {
    FriendRequestStatus.ACCEPTED,
    FriendRequestStatus.DECLINED,
    FriendRequestStatus.CANCELLED,
    FriendRequestStatus.EXPIRED,
}


def can_receiver_respond(current: FriendRequestStatus) -> bool:
    """PENDING -> ACCEPTED oder DECLINED, ausschließlich durch den
    Empfänger der Anfrage."""
    return current == FriendRequestStatus.PENDING


def can_sender_cancel(current: FriendRequestStatus) -> bool:
    """PENDING -> CANCELLED, ausschließlich durch den ursprünglichen
    Sender der Anfrage."""
    return current == FriendRequestStatus.PENDING


def can_expire(current: FriendRequestStatus) -> bool:
    """System-/Hintergrund-Transition (Anfrage zu lange offen). Phase 1
    definiert nur die Regel, kein Scheduled Job ruft sie auf - identische
    Deferral-Entscheidung wie ``accounts/rsvp_state_machine.py::can_expire``."""
    return current == FriendRequestStatus.PENDING


if __name__ == "__main__":
    assert can_receiver_respond(FriendRequestStatus.PENDING) is True
    assert can_sender_cancel(FriendRequestStatus.PENDING) is True
    assert can_expire(FriendRequestStatus.PENDING) is True

    for terminal in _TERMINAL:
        assert can_receiver_respond(terminal) is False
        assert can_sender_cancel(terminal) is False
        assert can_expire(terminal) is False

    assert _TERMINAL == {
        FriendRequestStatus.ACCEPTED,
        FriendRequestStatus.DECLINED,
        FriendRequestStatus.CANCELLED,
        FriendRequestStatus.EXPIRED,
    }

    print("social/friend_request_state_machine.py sanity check OK.")

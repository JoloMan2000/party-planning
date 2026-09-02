"""Kontrollierte RSVP-State-Machine (AUFGABE-Spec §9) - kein beliebiges
String-Setzen. Drei separate, unabhängig testbare Funktionen statt einer
überladenen Funktion, da die drei Transitions-Arten (Gast-Selbstbedienung,
Host-Revoke, System-Expiry) unterschiedliche Berechtigungs-Akteure haben.
"""

from __future__ import annotations

from accounts.domain import RsvpStatus

_GUEST_TRANSITIONS: dict[RsvpStatus, set[RsvpStatus]] = {
    RsvpStatus.PENDING: {RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED},
    RsvpStatus.ACCEPTED: {RsvpStatus.TENTATIVE, RsvpStatus.DECLINED},
    RsvpStatus.TENTATIVE: {RsvpStatus.ACCEPTED, RsvpStatus.DECLINED},
    RsvpStatus.DECLINED: {RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE},
    RsvpStatus.REVOKED: set(),
    RsvpStatus.EXPIRED: set(),
}

_TERMINAL = {RsvpStatus.REVOKED, RsvpStatus.EXPIRED}


def can_guest_transition(current: RsvpStatus, new: RsvpStatus) -> bool:
    """PENDING -> ACCEPTED|TENTATIVE|DECLINED, danach frei zwischen
    ACCEPTED/TENTATIVE/DECLINED wechselbar. Der Gast kann NIE selbst in/aus
    REVOKED oder EXPIRED wechseln."""
    return new in _GUEST_TRANSITIONS.get(current, set())


def can_host_revoke(current: RsvpStatus) -> bool:
    """Host-Aktion: aus jedem nicht-terminalen Status -> REVOKED erlaubt."""
    return current not in _TERMINAL


def can_expire(current: RsvpStatus) -> bool:
    """System-/Hintergrund-Transition (Party vorbei): aus jedem nicht-
    terminalen Status -> EXPIRED erlaubt. Phase 1 definiert nur die Regel,
    kein Scheduled Job ruft sie auf (siehe Plan, Deferral-Liste)."""
    return current not in _TERMINAL


if __name__ == "__main__":
    # PENDING -> alle drei Zielzustände erlaubt.
    assert can_guest_transition(RsvpStatus.PENDING, RsvpStatus.ACCEPTED) is True
    assert can_guest_transition(RsvpStatus.PENDING, RsvpStatus.TENTATIVE) is True
    assert can_guest_transition(RsvpStatus.PENDING, RsvpStatus.DECLINED) is True
    assert can_guest_transition(RsvpStatus.PENDING, RsvpStatus.REVOKED) is False
    assert can_guest_transition(RsvpStatus.PENDING, RsvpStatus.EXPIRED) is False

    # Frei zwischen ACCEPTED/TENTATIVE/DECLINED wechselbar.
    for a in (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED):
        for b in (RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED):
            if a == b:
                continue
            assert can_guest_transition(a, b) is True, f"{a} -> {b} sollte erlaubt sein"

    # Terminal-Zustände: keine Selbst-Transition raus, keine rein.
    for terminal in (RsvpStatus.REVOKED, RsvpStatus.EXPIRED):
        for target in RsvpStatus:
            assert can_guest_transition(terminal, target) is False
        for source in RsvpStatus:
            assert can_guest_transition(source, terminal) is False

    # Host-Revoke: aus jedem nicht-terminalen Status erlaubt, aus terminalen nicht.
    for s in (RsvpStatus.PENDING, RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED):
        assert can_host_revoke(s) is True
    for s in (RsvpStatus.REVOKED, RsvpStatus.EXPIRED):
        assert can_host_revoke(s) is False

    # Expire: gleiche Form wie Revoke.
    for s in (RsvpStatus.PENDING, RsvpStatus.ACCEPTED, RsvpStatus.TENTATIVE, RsvpStatus.DECLINED):
        assert can_expire(s) is True
    for s in (RsvpStatus.REVOKED, RsvpStatus.EXPIRED):
        assert can_expire(s) is False

    print("accounts/rsvp_state_machine.py sanity check OK.")

"""Framework-freie Domain-Modelle für den Social Graph (Social-Graph-Phase-1:
Friends-Fundament - Friend Requests, Friendship, Blocking).

Eigenes Top-Level-Package, analog zu ``geo/``/``party_context/``/
``music_engine/`` - Social ist eine eigene Domain, nicht in ``accounts/``,
``discover_storage.py`` o.ä. eingebettet (siehe AUFGABE-Spec: "Social Graph
Layer", nicht direkt in parties/discover/profile eingebaut). Keine Imports
aus ``accounts/`` hier - Domain-Module importieren sich in diesem Projekt
grundsätzlich nicht gegenseitig, nur die Storage-Schicht (``social/*.py``)
referenziert ``accounts.user_storage``/``accounts.domain`` für Cross-Checks.

``username`` selbst lebt bewusst NICHT hier, sondern auf
``accounts.domain.UserProfile`` (siehe dortige Doku) - Social-Graph-Phase-1
erweitert die existierende Profile-Schicht statt eine zweite parallele
Identitäts-/Profil-Struktur aufzubauen."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class FriendRequestStatus(str, Enum):
    """Anders als ``accounts.domain.RsvpStatus`` (freie Bewegung zwischen
    ACCEPTED/TENTATIVE/DECLINED) hat ein ``FriendRequest`` genau EINEN
    nicht-terminalen Zustand (PENDING) und vier sich gegenseitig
    ausschließende terminale Ausgänge - kein Wiedereintritt in PENDING,
    kein Wechsel zwischen terminalen Zuständen (siehe
    ``social/friend_request_state_machine.py``)."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class FriendRequest:
    """User-zu-User-Anfrage (AUFGABE-Spec §13-16) - bewusst KONTRASTIERT
    gegen ``accounts.domain.Invitation``: eine Invitation ist Host->Gast in
    eine konkrete ``Party`` (asymmetrisch, party-scoped, "Selbst einladen"
    kommt durch Konstruktion nicht vor). Ein ``FriendRequest`` ist
    user<->user, symmetrischer Ausgang (führt zu einer ``Friendship``), und
    braucht deshalb ECHTE Self-/Duplicate-/Cross-Merge-Behandlung (siehe
    ``social/friend_requests.py::create_friend_request``).

    ``version`` existiert für Defense-in-Depth, aber ANDERS als bei
    ``Invitation.version`` müssen Aufrufer von accept/decline/cancel KEINE
    ``expected_version`` mitgeben - das guarded
    ``UPDATE ... WHERE status = 'pending'`` übernimmt die
    Concurrency-Sicherheit (siehe state machine Moduldoku)."""

    id: str
    sender_id: str
    receiver_id: str
    status: FriendRequestStatus = FriendRequestStatus.PENDING
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: datetime | None = None


@dataclass
class Friendship:
    """Erste SYMMETRISCHE Beziehung in dieser Codebase (AUFGABE-Spec §17-19)
    - jedes bisherige UNIQUE-Paar (``invitations(party_id,
    invited_user_id)``, ``blocked_organizers(user_id, organizer_user_id)``)
    ist gerichtet. Invariante: ``user_a_id < user_b_id`` (lexikographisch)
    IMMER - wird ausschließlich in ``social/friendships.py::_canonical_pair``
    durchgesetzt, nie vom Aufrufer. Entsteht ausschließlich über den
    Accept-/Merge-Pfad in ``social/friend_requests.py`` - kein eigener
    manueller Anlage-Einstiegspunkt (Konvention wie
    ``UserProfile.birth_date``-Schutz: dokumentiert durchgesetzt, kein
    DB-Trigger)."""

    id: str
    user_a_id: str
    user_b_id: str
    source_friend_request_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserBlock:
    """Harter interpersönlicher Constraint (AUFGABE-Spec §31-33) - explizit
    kontrastiert gegen ``accounts.domain.BlockedOrganizer``
    (``accounts/domain.py``): ein Organizer-Block versteckt nur dessen
    veröffentlichte Parties (Content-Sichtbarkeits-Filter, gerichtet, keine
    Beziehungs-Nebenwirkungen). ``UserBlock`` dagegen (1) verhindert künftige
    Friend Requests in beide Richtungen, (2) verhindert künftige
    Friendship-Anlage, (3) storniert sofort jede pending ``FriendRequest``
    zwischen den beiden Usern und (4) beendet eine bestehende ``Friendship``
    (siehe ``social/blocks.py::block_user``). Gleiche
    ``UNIQUE(blocker_id, blocked_id)``-Idempotenz-Form wie
    ``BlockedOrganizer``, bewusst gerichtet - A blockiert B impliziert nicht,
    dass B A blockiert hat."""

    id: str
    blocker_id: str
    blocked_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

"""Domain-Modell für den Account-basierten Multi-Tenant-Pivot (Phase 1).

Framework-freie Dataclasses + Enums, mirroring die Konvention von
``party_engine``/``music_engine``/``party_context`` (keine FastAPI-/sqlite3-
Importe hier, nur reine Datenstrukturen).

WICHTIG: ``Party`` hier ist ein NEUES, eigenständiges Konzept (Multi-Tenant,
ein User kann mehrere Parties hosten/besuchen) - komplett getrennt von der
bestehenden Singleton-Party-Config (``party_engine.domain.PartyConfig`` /
``event_theme.party_settings``). Phase 1 verdrahtet diese beiden Welten
bewusst NICHT miteinander (siehe Plan, Abschnitt "Explicit deferral list").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class RsvpStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    TENTATIVE = "tentative"
    DECLINED = "declined"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PartyRole(str, Enum):
    HOST = "host"
    CO_HOST = "co_host"
    GUEST = "guest"


@dataclass
class User:
    """Öffentliches User-Modell (AUFGABE-Spec §4). Enthält bewusst KEIN
    ``password_hash``-Feld - Auth-Geheimnisse gehören nicht in dieses Modell
    und werden nie über diese Dataclass serialisiert."""

    id: str
    email: str
    display_name: str
    profile_image: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Party:
    """Multi-Tenant-Party (AUFGABE-Spec §26 PartyProfile, minimale Phase-1-
    Variante). NICHT dasselbe wie ``party_engine.domain.PartyConfig``."""

    id: str
    host_user_id: str
    name: str
    description: str = ""
    starts_at: datetime | None = None
    location: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PartyMembership:
    """Tatsächliche Beziehung User<->Party (AUFGABE-Spec §40) - bewusst
    getrennt von ``Invitation`` (der Einladung/RSVP-Anfrage)."""

    id: str
    party_id: str
    user_id: str
    role: PartyRole
    rsvp_status: RsvpStatus
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Invitation:
    """Einladung als echtes Domain-Objekt (AUFGABE-Spec §8), kein Notification."""

    id: str
    party_id: str
    host_user_id: str
    invited_user_id: str
    status: RsvpStatus = RsvpStatus.PENDING
    invitation_message: str = ""
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    viewed_at: datetime | None = None
    responded_at: datetime | None = None


@dataclass
class RsvpHistoryEntry:
    """Auditierbare Statusänderung (AUFGABE-Spec §42)."""

    id: str
    invitation_id: str
    party_id: str
    user_id: str  # die eingeladene Person, um die es in diesem Eintrag geht
    previous_status: RsvpStatus
    new_status: RsvpStatus
    changed_by_user_id: str  # eingeladene Person bei normalem RSVP, Host bei Revoke
    client_request_id: str | None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

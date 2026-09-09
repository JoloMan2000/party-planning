"""Domain-Modell für den ``Organizer`` (Social-Graph-Phase-4, "Organizer
Domain Foundation").

WICHTIG: Dies ist das ERSTE echte ``Organizer``-Entity in dieser Codebase.
Bisher gab es nur zwei informelle Verwendungen des Worts "Organizer", die
BEWUSST unangetastet bleiben und NICHTS mit dieser Dataclass zu tun haben:
- ``backend/app/routers/parties.py``: ein Party-Host wurde bislang informell
  als "Organizer" bezeichnet, verifiziert über das simple ``User.is_verified``-
  Flag (siehe ``accounts.user_storage.set_user_verified``). Dieses Flag wird
  durch Phase 4 funktional abgelöst (siehe ``is_user_verified_organizer_member``
  unten), aber NICHT entfernt (deprecated-in-place, siehe Plan).
- ``BlockedOrganizer`` (``accounts/domain.py``, Discover-Engine-Phase-1)
  blockt anhand des rohen ``organizer_user_id`` (= Party-Host-User-ID), nicht
  anhand einer ``Organizer.id``. Diese Verknüpfung explizit NICHT hergestellt
  in Phase 4 (siehe Plan, "Explicit deferral list").

``Organizer`` hier ist eine eigenständige Entität (z.B. ein Veranstalter-
Unternehmen), die mehrere User als Mitglieder mit unterschiedlichen Rollen
haben kann (``OrganizerMembership``) - analog zu ``Party``/``PartyMembership``
in ``accounts/domain.py``, aber ein komplett getrenntes Konzept: eine Party
gehört (noch) zu keinem ``Organizer`` (kein ``Party.organizer_id``-Feld,
bewusst deferred), Publish-Berechtigung hängt nur davon ab, ob der Host
IRGENDEIN Mitglied EINES verifizierten ``Organizer`` ist."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class OrganizerRole(str, Enum):
    """Rolle einer ``OrganizerMembership``. Phase 4 verdrahtet nur die
    Existenz aller fünf Werte (frei wählbar über ``POST
    .../members``) - eine feingranulare Rechte-Matrix pro Rolle (z.B. darf
    ``EDITOR`` X, aber nicht Y) ist noch nicht gebaut; aktuell ist nur
    ``OWNER`` (Mitglieder-Verwaltung) tatsächlich privilegiert."""

    OWNER = "owner"
    ADMIN = "admin"
    EVENT_MANAGER = "event_manager"
    EDITOR = "editor"
    VIEWER = "viewer"


class OrganizerVerificationStatus(str, Enum):
    """Voller 5-Werte-Lifecycle für spätere Erweiterung (z.B. ein echter
    Review-Antrags-Flow), aber Phase 4 verdrahtet nur den binären Übergang
    ``UNVERIFIED <-> VERIFIED`` über die Admin-Endpunkte (siehe
    ``backend/app/routers/admin_organizers.py``) - mirrors das Präzedenzfall-
    Muster von ``DiscoverNotInterestedReason`` (voll modelliert, teilweise
    verdrahtet). ``PENDING``/``SUSPENDED``/``REJECTED`` sind bewusst
    NICHT über die Verify-Endpunkte erreichbar, dienen aber schon jetzt als
    Beweis, dass ``is_user_verified_organizer_member`` NUR bei ``VERIFIED``
    greift (siehe Storage-Tests)."""

    UNVERIFIED = "unverified"
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


@dataclass
class Organizer:
    """Eigenständige Veranstalter-Entität (Social-Graph-Phase-4). Bewusst
    OHNE ``username`` - anders als ``UserProfile.username`` (Social-Graph-
    Phase-1) gibt es noch keinen Such-/Discoverability-Anwendungsfall für
    Organizer, der einen stabilen öffentlichen Identifier bräuchte."""

    id: str
    owner_user_id: str  # denormalisierte Bequemlichkeit; die eigentliche Quelle der Wahrheit ist die OWNER-Zeile in organizer_memberships. Wird in Phase 4 nie umgehängt (kein Ownership-Transfer-Endpoint).
    display_name: str
    organizer_type: str = ""  # freier String, kein geschlossener Katalog - mirrors PublicEvent.event_type
    verification_status: OrganizerVerificationStatus = OrganizerVerificationStatus.UNVERIFIED
    description: str = ""
    website_url: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class OrganizerMembership:
    """Tatsächliche Beziehung User<->Organizer - analog zu ``PartyMembership``,
    aber ein eigenständiges Konzept (kein User ist automatisch Mitglied eines
    Organizers, nur weil er Mitglied einer Party ist, die diesem Organizer
    gehören könnte - diese Verknüpfung existiert in Phase 4 noch gar nicht)."""

    id: str
    organizer_id: str
    user_id: str
    role: OrganizerRole
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

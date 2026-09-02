"""API-Tests: geschützte Routen ohne Token (Account-basierter Pivot, Phase 1).

Ersetzt die alte Admin-Passwort-Auth-Suite (``get_current_admin``/
``settings.admin_password`` existieren nicht mehr, Entscheidung #2 "clean
break") - deckt ab, dass jede neue geschützte Route (``/me/*``,
``/parties/*``, ``/invitations/*``) ohne Token mit 401 abgelehnt wird
(mirroring der alten ``ADMIN_ROUTES``-Parametrisierung). Signup/Login/
Refresh/Logout-Verhalten selbst steht in ``test_api_auth.py``.
"""

from __future__ import annotations

import pytest

AUTHED_ROUTES = [
    ("GET", "/api/v1/me", None),
    ("GET", "/api/v1/me/parties", None),
    ("GET", "/api/v1/me/invitations", None),
    ("POST", "/api/v1/parties", {"name": "Some Party"}),
    ("GET", "/api/v1/parties/some-party-id", None),
    ("PATCH", "/api/v1/parties/some-party-id", {"name": "Renamed"}),
    ("GET", "/api/v1/parties/some-party-id/guests", None),
    ("POST", "/api/v1/parties/some-party-id/invitations", {"invited_user_email": "someone@example.com"}),
    ("GET", "/api/v1/invitations/some-invitation-id", None),
    ("PUT", "/api/v1/invitations/some-invitation-id/rsvp", {"status": "accepted", "version": 1}),
]


@pytest.mark.parametrize("method,path,body", AUTHED_ROUTES)
def test_geschuetzte_route_ohne_token_gibt_401(api_client, method, path, body):
    resp = api_client.request(method, path, json=body)
    assert resp.status_code == 401


def test_geschuetzte_route_mit_gueltigem_token_ist_erlaubt(api_client, auth_headers_factory):
    headers, user, _refresh_token = auth_headers_factory()
    resp = api_client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == user["id"]

"""Distanz-/Radius-Berechnung der Geo Platform (Spec §46-47, §50).

Diese App ist 100% SQLite (bestätigt per Survey - keine PostgreSQL/PostGIS-
Abhängigkeit irgendwo im Repo), daher ersetzt dieses Modul die vom Spec
konzeptionell empfohlene räumliche DB-Extension durch eine pragmatische
Python/SQL-Lösung: ``bounding_box()`` liefert ein günstiges, indiziertes
SQL-Prefilter, ``haversine_km()`` ist die einzige Quelle für die tatsächliche
geodätische Distanz - ein Bounding-Box-Treffer allein ist NIEMALS die
endgültige Eligibility-Entscheidung (Spec §50 explizit)."""

from __future__ import annotations

import math

from geo.domain import GeoPoint

_EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    """Echte geodätische Distanz zwischen zwei Punkten in Kilometern -
    bewusst NICHT naive Grad-Differenz-Mathematik (Spec §46)."""
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def bounding_box(center: GeoPoint, radius_km: float) -> tuple[float, float, float, float]:
    """Liefert ``(lat_min, lat_max, lon_min, lon_max)`` - NUR ein günstiges
    SQL-Prefilter (nutzt den ``idx_party_locations_point``-Index), niemals
    die finale Eligibility-Entscheidung (dafür immer zusätzlich
    ``haversine_km`` gegen ``radius_km`` prüfen, Spec §50). Die
    Längengrad-Spanne wird an den Breitengrad angepasst (schmaler nahe den
    Polen), sonst wäre die Box bei hohen Breiten unnötig riesig."""
    lat_delta = radius_km / _EARTH_RADIUS_KM * (180 / math.pi)
    lat_min = center.latitude - lat_delta
    lat_max = center.latitude + lat_delta

    lon_scale = math.cos(math.radians(center.latitude))
    if lon_scale < 1e-6:
        # Pol-Nähe: Längengrad wird bedeutungslos, volle Spanne verwenden
        # statt einer Division durch (nahezu) Null.
        lon_min, lon_max = -180.0, 180.0
    else:
        lon_delta = radius_km / (_EARTH_RADIUS_KM * lon_scale) * (180 / math.pi)
        lon_min = center.longitude - lon_delta
        lon_max = center.longitude + lon_delta

    return lat_min, lat_max, lon_min, lon_max

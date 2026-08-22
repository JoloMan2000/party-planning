"""
Kalender-Export für Gäste
=========================

Erzeugt aus den admin-konfigurierten Party-Einstellungen (siehe
event_theme.py: 'party_date', 'party_start_time', 'party_duration_hours',
'party_location') einen Google-Calendar-"Add event"-Link sowie den Inhalt
einer .ics-Datei (iCalendar), die Gäste am Ende des Fragebogens nutzen
können, um die Party plattformübergreifend (iPhone/Apple Calendar, Google
Calendar, Android, Outlook, ...) in ihren eigenen Kalender einzutragen.

Beide Funktionen liefern None, falls der Admin noch kein Datum konfiguriert
hat (siehe render_party_settings_section in "Party Planning.py") - die
aufrufende Stelle blendet die "Zum Kalender hinzufügen"-Sektion dann
komplett aus, statt einen kaputten Link/leeren Termin anzuzeigen.

Dieses Modul ist bewusst Streamlit-frei (reine Datum/Zeit-Logik + String-
Bausteine), damit es leicht testbar/wiederverwendbar bleibt - siehe
Docstring-Konvention der übrigen Module in diesem Repo (z.B. event_theme.py).
"""

from __future__ import annotations

from datetime import date as ddate, datetime, time as dtime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

# Die App/Party ist auf Deutschland ausgerichtet (siehe DEFAULT_LANGUAGE="de"
# in translations.py) - für den Kalender-Export reicht daher eine feste
# Zeitzone, ohne eine volle VTIMEZONE-Definition mitliefern zu müssen.
_PARTY_TIMEZONE = ZoneInfo("Europe/Berlin")
_UTC = ZoneInfo("UTC")
_DEFAULT_START_TIME = dtime(19, 0)
_ICS_DATETIME_FORMAT = "%Y%m%dT%H%M%SZ"


def _resolve_start_end(settings: dict) -> tuple[datetime, datetime] | None:
    """Kombiniert 'party_date'/'party_start_time'/'party_duration_hours' aus
    den Party-Einstellungen zu einem lokalisierten (Europe/Berlin) Start-
    und End-Zeitpunkt. Liefert None, falls kein Datum gesetzt ist - dann ist
    der Kalender-Export für Gäste noch nicht verfügbar."""
    date_str = (settings.get("party_date") or "").strip()
    if not date_str:
        return None
    try:
        party_date = ddate.fromisoformat(date_str)
    except ValueError:
        return None

    time_str = (settings.get("party_start_time") or "").strip()
    try:
        start_time = dtime.fromisoformat(time_str) if time_str else _DEFAULT_START_TIME
    except ValueError:
        start_time = _DEFAULT_START_TIME

    try:
        duration_hours = float(settings.get("party_duration_hours") or 7.0)
    except (TypeError, ValueError):
        duration_hours = 7.0
    if duration_hours <= 0:
        duration_hours = 7.0

    start = datetime.combine(party_date, start_time, tzinfo=_PARTY_TIMEZONE)
    end = start + timedelta(hours=duration_hours)
    return start, end


def format_party_datetime(settings: dict) -> str | None:
    """Liefert eine kurze, sprachneutrale Anzeige von Datum/Uhrzeit/Ort der
    Party (z.B. '📅 05.09.2026 · 🕖 19:00 · 📍 Musterstraße 1'), gedacht zur
    Anzeige im Gäste-Fragebogen VOR dem Absenden (siehe "Party Planning.py":
    render_event_intro()/render_guest_form()) - nicht erst auf der
    Abschluss-Seite. Nutzt bewusst nur Icons statt übersetzter Text-Labels,
    damit sie ohne zusätzliche Übersetzungs-Keys in allen 16 Sprachen korrekt
    dargestellt wird. Liefert None, falls kein Datum konfiguriert ist."""
    resolved = _resolve_start_end(settings)
    if resolved is None:
        return None
    start, _end = resolved
    parts = [f"📅 {start.strftime('%d.%m.%Y')}", f"🕖 {start.strftime('%H:%M')}"]
    location = (settings.get("party_location") or "").strip()
    if location:
        parts.append(f"📍 {location}")
    return " · ".join(parts)


def has_scheduled_date(settings: dict) -> bool:
    """True, sobald der Admin ein gültiges Party-Datum konfiguriert hat -
    steuert, ob die Gast-UI die "Zum Kalender hinzufügen"-Sektion überhaupt
    anzeigt."""
    return _resolve_start_end(settings) is not None


def google_calendar_url(settings: dict, title: str) -> str | None:
    """Liefert eine Google-Calendar-"Add event"-URL für die Party, oder
    None, falls kein Datum konfiguriert ist."""
    resolved = _resolve_start_end(settings)
    if resolved is None:
        return None
    start, end = resolved
    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": (
            f"{start.astimezone(_UTC).strftime(_ICS_DATETIME_FORMAT)}/"
            f"{end.astimezone(_UTC).strftime(_ICS_DATETIME_FORMAT)}"
        ),
    }
    location = (settings.get("party_location") or "").strip()
    if location:
        params["location"] = location
    return f"https://www.google.com/calendar/render?{urlencode(params)}"


def _escape_ics_text(text: str) -> str:
    """Escaped Sonderzeichen gemäß RFC 5545 (iCalendar) für TEXT-Felder wie
    SUMMARY/LOCATION."""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def ics_content(settings: dict, title: str) -> str | None:
    """Liefert den vollständigen Inhalt einer .ics-Datei (iCalendar,
    RFC 5545) für die Party, geeignet zum Import in Apple Calendar, Outlook
    und Android-Kalender-Apps. Liefert None, falls kein Datum konfiguriert
    ist."""
    resolved = _resolve_start_end(settings)
    if resolved is None:
        return None
    start, end = resolved
    dtstamp = datetime.now(_UTC).strftime(_ICS_DATETIME_FORMAT)
    dtstart = start.astimezone(_UTC).strftime(_ICS_DATETIME_FORMAT)
    dtend = end.astimezone(_UTC).strftime(_ICS_DATETIME_FORMAT)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Party Planning//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:party-{dtstart}@party-planning.local",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART:{dtstart}",
        f"DTEND:{dtend}",
        f"SUMMARY:{_escape_ics_text(title)}",
    ]
    location = (settings.get("party_location") or "").strip()
    if location:
        lines.append(f"LOCATION:{_escape_ics_text(location)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"

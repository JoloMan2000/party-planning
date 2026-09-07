# 🌴 Summer Party Planung

Party-Planungs-App: Gäste beantworten Uhrzeit-, Getränke-, Essens- und
Songwünsche, der Host bekommt eine Auswertung inkl. Einkaufsliste und kann
aus den Songwünschen automatisch eine Spotify-Playlist erstellen lassen.

**Hinweis:** Die frühere Streamlit-Oberfläche (`"Party Planning.py"`) wurde
im Zuge des Account-basierten Multi-Tenant-Pivots retiriert. Unterstützte
Clients sind jetzt ausschließlich:

- **`backend/`** - FastAPI-Backend (User-Accounts, Partys, Einladungen,
  JWT-Auth, party-gescopte Admin-Endpunkte). Ausführen vom Repo-Root aus:

  ```bash
  pip install -r requirements.txt
  uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
  ```

- **`mobile/`** - Flutter-App (Gäste-Wizard + Admin-Dashboard), siehe
  `mobile/README.md`.

## Spotify-Playlist einrichten (optional)

Damit die automatische Spotify-Playlist-Erstellung im Admin-Bereich
funktioniert, brauchst du eine eigene Spotify-App:

1. Auf [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   einloggen und „Create app" wählen.
2. Client ID/Secret sowie eine passende Redirect-URI für den vom Backend
   verwendeten OAuth-Flow eintragen.
3. Die Zugangsdaten als Backend-Konfiguration (Umgebungsvariablen) hinterlegen.

## Zugriff

- **Gäste** nutzen die Flutter-App bzw. den anonymen Gast-Wizard-Endpunkt
  (`/api/v1/guest/{party_id}/...`) - kein Login nötig.
- **Host/Co-Host** loggen sich per Account (JWT) ein und verwalten ihre
  eigenen Partys über die party-gescopten Admin-Endpunkte
  (`/api/v1/parties/{party_id}/admin/...`).

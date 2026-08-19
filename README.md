# 🌴 Summer Party Planung

Linkbasierter Fragebogen für die Partyplanung (Streamlit). Gäste beantworten
in 4 Schritten Uhrzeit, Getränke-, Essens- und Songwünsche. Über einen
geheimen Admin-Link bekommst du eine Auswertung inkl. Einkaufsliste und
kannst aus den Songwünschen automatisch eine Spotify-Playlist erstellen
lassen.

## Lokal ausführen

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# admin_token in .streamlit/secrets.toml auf einen eigenen Wert setzen
streamlit run "Party Planning.py"
```

Admin-Ansicht lokal: `http://localhost:8501/?admin=<dein-admin-token>`

## Spotify-Playlist einrichten (optional)

Damit im Admin-Bereich der Button „🎵 Spotify-Playlist erstellen" funktioniert,
brauchst du eine eigene Spotify-App:

1. Auf [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   einloggen und „Create app" wählen.
2. Bei **Redirect URIs** exakt deinen Admin-Link eintragen, also
   `<deine-app-url>/?admin=<dein-admin-token>` (lokal z. B.
   `http://localhost:8501/?admin=<dein-admin-token>`).
3. In den App-Einstellungen `Client ID` und `Client Secret` kopieren.
4. In `.streamlit/secrets.toml` (bzw. im Cloud-Dashboard unter „Secrets")
   ergänzen:
   ```toml
   spotify_client_id = "deine-client-id"
   spotify_client_secret = "dein-client-secret"
   spotify_redirect_uri = "<deine-app-url>/?admin=<dein-admin-token>"
   ```
5. App neu starten, dann im Admin-Bereich auf „🔗 Mit Spotify verbinden"
   klicken und einmalig den Spotify-Login/-Consent bestätigen.

**Hinweis:** Die Verbindung (Refresh-Token) wird lokal in `.spotify_token.json`
gespeichert (gitignored). Wie bei `responses.db` ist dieser Speicher auf
Streamlit Community Cloud nicht dauerhaft garantiert – nach einem
Neustart/Redeploy musst du dich ggf. einmalig neu verbinden. Songs, die nicht
eindeutig auf Spotify gefunden werden, werden dir nach der Playlist-Erstellung
als Liste angezeigt.

## Deployment auf Streamlit Community Cloud

1. Repo auf GitHub pushen (siehe unten).
2. Auf [share.streamlit.io](https://share.streamlit.io) mit GitHub einloggen.
3. „New app" → dieses Repo auswählen → Main file: `Party Planning.py`.
4. Vor dem Deploy: unter **Advanced settings → Secrets** einfügen:
   ```toml
   admin_token = "dein-geheimer-wert"
   ```
5. Deploy klicken. Die App ist dann unter `https://<app-name>.streamlit.app`
   erreichbar.
6. Gäste-Link: die normale App-URL. Admin-Link: `https://<app-name>.streamlit.app/?admin=<dein-admin-token>`.

**Hinweis zur Datenspeicherung:** Die Antworten werden in einer lokalen
SQLite-Datei (`responses.db`) gespeichert. Auf Streamlit Community Cloud ist
der Dateispeicher **nicht dauerhaft garantiert** (kann bei Neustart/Redeploy
der App zurückgesetzt werden). Nutze daher regelmäßig den
„⬇️ Antworten als CSV sichern"-Button im Admin-Bereich als Backup, besonders
kurz bevor du die finale Einkaufsliste erstellst.

## Zugriff

- **Gäste** öffnen die normale App-URL – kein Login nötig.
- **Admin** (du) öffnet die URL mit `?admin=<admin_token>` Anhang. Diesen
  Link nicht weitergeben.
- Der Link selbst ist nicht öffentlich auffindbar, aber technisch für jeden
  erreichbar, der ihn kennt – gib den Gäste-Link daher nur direkt an deine
  Gäste weiter.

# 🌴 Summer Party Planung

Linkbasierter Fragebogen für die Partyplanung (Streamlit). Gäste beantworten
in 3 Schritten Uhrzeit, Getränke- und Essenswünsche. Über einen geheimen
Admin-Link bekommst du eine Auswertung inkl. Einkaufsliste.

## Lokal ausführen

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# admin_token in .streamlit/secrets.toml auf einen eigenen Wert setzen
streamlit run "Party Planning.py"
```

Admin-Ansicht lokal: `http://localhost:8501/?admin=<dein-admin-token>`

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

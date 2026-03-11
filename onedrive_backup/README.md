Onedrive Backup Machine

Minimal scaffold for a Home Assistant OS add-on that downloads backups from OneDrive to local disk.

Files of interest:
- `config.json`, `Dockerfile`, `start.sh`, `requirements.txt`, `main.py`, `static/`

Account linking flow:
- Open add-on Web UI and click `Vincular conta OneDrive`.
- Open the shown Microsoft URL and type the displayed device code.
- Wait for the UI status to change to authenticated.

OneDrive Backup Add-on for Home Assistant

Minimal scaffold for a Home Assistant OS add-on that uploads backups to OneDrive.

Files of interest:
- [config.json](config.json)
- [Dockerfile](Dockerfile)
- [start.sh](start.sh)
- [requirements.txt](requirements.txt)
- [main.py](main.py)
- [static/index.html](static/index.html)

Options
 - `secure_key`: (optional) Fernet key used to encrypt token cache on disk. Generate with:
	 ```bash
	 python - <<'PY'
	 from cryptography.fernet import Fernet
	 print(Fernet.generate_key().decode())
	 PY
	 ```
	 Paste the generated key into the add-on options as `secure_key`.

Run inside Home Assistant add-on build environment. Configure OAuth credentials in add-on options.

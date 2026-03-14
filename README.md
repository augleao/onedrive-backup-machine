
Onedrive Backup Machine

Bring your OneDrive files into Home Assistant with a backup workflow that is simple to configure, reliable to run, and easy to inspect when something goes wrong.

This add-on turns your Home Assistant host into a scheduled backup station for OneDrive. Link your Microsoft account, choose the files or folders you want to protect, and let the add-on create organized local backups automatically.

Why people will want to use it:
- Scheduled backups directly from OneDrive to local storage on Home Assistant OS.
- Full and incremental backup strategies for faster recurring syncs.
- Multiple backup tasks, each with its own source selection and schedule.
- Dedicated run folders so each backup is easy to identify by type and timestamp.
- Built-in diagnostics UI with job errors and application logs for troubleshooting.
- Clean web interface through Home Assistant ingress.

What the add-on does well:
- Keeps backup history readable with folders like `full_14_03_2026_10_49_00` and `incremental_14_03_2026_10_49_00`.
- Preserves an internal per-task mirror for efficient incremental comparisons.
- Exposes recent job results so users can see downloaded files, skipped files, and errors at a glance.
- Makes support easier by surfacing logs directly in the UI.

Typical flow:
1. Configure `client_id` in the add-on options.
2. Open the add-on Web UI and link your OneDrive account.
3. Create one or more backup tasks.
4. Select folders/files from OneDrive, choose full or incremental mode, and define the schedule.
5. Run backups on demand or let them execute automatically.

Project files:
- [config.json](config.json)
- [Dockerfile](Dockerfile)
- [start.sh](start.sh)
- [requirements.txt](requirements.txt)
- [main.py](main.py)
- [static/index.html](static/index.html)

This repository is intended to run as a Home Assistant add-on. OAuth and storage settings are configured through the add-on options.

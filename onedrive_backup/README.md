Onedrive Backup Machine

Protect the files that matter in OneDrive without depending on another cloud-to-cloud service. This add-on uses your Home Assistant host as a local backup machine, giving you more control, better visibility, and a much clearer recovery path.

Highlights:
- Connect a Microsoft account through a simple device login flow.
- Create multiple backup tasks for different folders and schedules.
- Choose between full and incremental backups.
- Save every backup job in its own clearly named folder.
- Inspect job failures from the UI with error details and live log access.

Why it stands out:
- It is built for users who want automation and traceability, not a black-box sync.
- Each execution is stored in a separate folder, making it easy to identify and validate backups.
- Error visibility is part of the product, with job diagnostics and log viewing directly in the interface.

Account linking flow:
1. Open the add-on Web UI and click `Link OneDrive Account`.
2. Open the Microsoft URL shown on screen.
3. Enter the device code displayed by the add-on.
4. Wait until the UI reports that the account is linked.

Backup storage layout:
- The configured `backup_path` stores one folder per backup run.
- Each run uses a readable folder name based on mode and execution time:
  - `full_DD_MM_YYYY_HH_MM_SS`
  - `incremental_DD_MM_YYYY_HH_MM_SS`
- For incremental processing, the add-on also maintains an internal mirror at `.latest/<task_name>`.

Files of interest:
- `config.json`
- `Dockerfile`
- `start.sh`
- `requirements.txt`
- `main.py`
- `static/`

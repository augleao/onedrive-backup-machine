Onedrive Backup Machine

Protect the files that matter in OneDrive with a backup experience designed for clarity, automation, and recovery confidence.

This add-on uses your Home Assistant host as a local backup machine for OneDrive content. Instead of treating backup like a hidden sync process, it gives you visible jobs, readable backup folders, scheduled execution, and direct access to logs when something breaks.

## Highlights

- Microsoft account linking with a simple device login flow.
- Multiple backup tasks for different folders and schedules.
- Full and incremental strategies.
- One dedicated folder per job run.
- Error diagnostics directly in the UI.
- Log access without leaving the add-on.

## Why Users Tend To Trust It

- Every execution is stored in its own folder.
- The backup history is human-readable.
- Failures are visible and inspectable.
- The interface is built for operation, not just setup.

## Typical User Flow

1. Open the add-on UI.
2. Configure the Microsoft application `client_id` if needed.
3. Click `Link OneDrive Account`.
4. Visit the Microsoft URL displayed by the add-on.
5. Enter the device code.
6. Return to the UI and create one or more backup tasks.
7. Select files or folders, choose mode and schedule, then save.

## Backup Storage Layout

The configured `backup_path` stores one folder per backup execution.

Folder examples:
- `full_DD_MM_YYYY_HH_MM_SS`
- `incremental_DD_MM_YYYY_HH_MM_SS`

This structure helps users quickly identify:
- what type of backup ran
- when it ran
- whether a run actually produced files

For incremental jobs, the add-on also maintains an internal mirror at `.latest/<task_name>` to compare changes efficiently between runs.

## Troubleshooting Flow

When a job reports errors:
1. Open `Recent Jobs`.
2. Click `Errors` on the failed or partially failed job.
3. Review the job error messages.
4. Inspect the application log shown in the diagnostics modal.

This makes it much easier to understand whether the issue is related to authentication, licensing, source access, or destination storage.

## Home Assistant Dashboard Entities

The repository includes a custom component that creates entities for dashboards:
- sensor.onedrive_backup_last_job_status
- sensor.onedrive_backup_last_job_errors
- sensor.onedrive_backup_last_job_downloaded
- sensor.onedrive_backup_last_job_skipped
- button.onedrive_backup_run_now
- task-specific run buttons for tasks found during startup

Service available for automations and scripts:
- onedrive_backup.run_task with optional task_id

configuration.yaml example:

		onedrive_backup:
			addon_url: http://127.0.0.1:8080
			scan_interval: 30

## Files Of Interest

- `config.json`
- `Dockerfile`
- `start.sh`
- `requirements.txt`
- `main.py`
- `static/`

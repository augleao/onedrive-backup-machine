
Onedrive Backup Machine

Back up the files that matter in OneDrive to your Home Assistant host with scheduling, visibility, and control.

Onedrive Backup Machine is a Home Assistant add-on built for people who do not want their file protection strategy to depend on another opaque cloud workflow. It lets you connect OneDrive, choose exactly what should be protected, schedule recurring jobs, and keep every run stored locally in a way that is easy to inspect and recover.

## Why Use It

Most sync tools optimize for convenience. Backups need something else: traceability, repeatability, and confidence that you can verify what happened.

This add-on focuses on that:
- Run backups from OneDrive directly into local storage on Home Assistant OS.
- Create multiple tasks for different folders, schedules, and strategies.
- Choose between full and incremental runs depending on how often your data changes.
- Keep each run in its own timestamped folder so you can recognize backups instantly.
- Inspect failures directly in the UI with job-level error details and application logs.

## Core Features

- OneDrive account linking through a device login flow.
- Full backup mode for complete snapshots.
- Incremental backup mode for faster recurring jobs.
- Multiple backup tasks with independent schedules.
- Manual execution for immediate runs.
- Recent jobs view with status, counts, and error summaries.
- Diagnostics modal for troubleshooting backup failures.
- Local backup storage under the path you configure in the add-on.

## How It Works

1. Configure your Microsoft application `client_id` in the add-on options.
2. Open the add-on UI from Home Assistant.
3. Link your OneDrive account using the device code flow.
4. Create a task and select the folders or files you want to protect.
5. Define whether the task should run as full or incremental.
6. Choose the schedule.
7. Let the add-on run automatically or trigger a job manually.

## Backup Layout

The configured `backup_path` stores one folder per execution, making backup history readable at a glance.

Examples:
- `full_14_03_2026_10_49_00`
- `incremental_14_03_2026_10_49_00`

This makes it much easier to:
- identify when a backup ran
- distinguish full and incremental executions
- verify whether a job produced output
- browse older backup runs without guessing

For incremental processing, the add-on also keeps an internal mirror under `.latest/<task_name>` so it can compare changes efficiently without exposing that implementation detail as the main backup view.

## Why It Feels Better Than A Basic Sync

- A sync can silently overwrite or mirror mistakes.
- A backup gives you a recoverable history.
- Separate run folders make validation much easier.
- Error and log visibility reduce the time spent guessing why a job failed.

The goal is not just moving files. The goal is making recovery trustworthy.

## Troubleshooting

If a job fails:
- Open `Recent Jobs` in the add-on UI.
- Click the `Errors` indicator for that job.
- Review the job error messages.
- Inspect the application log shown in the diagnostics panel.

Common causes include:
- missing or invalid Microsoft app configuration
- account not linked or expired token state
- missing OneDrive or SharePoint license in tenant-based accounts
- inaccessible destination path

## Dashboard Entities (Custom Component)

The custom component now exposes entities that can be added to Home Assistant dashboards:
- Sensors for latest job status, errors, downloaded count, and skipped count.
- A Run Now button entity.
- Per-task Run buttons created from the tasks currently available at startup.

It also registers a service:
- onedrive_backup.run_task with optional task_id.

Example configuration.yaml section:

		onedrive_backup:
			addon_url: http://127.0.0.1:8080
			scan_interval: 30

After restart, add the generated entities to your dashboard using standard cards.

## Good Fit For

- Home Assistant users who want local copies of important cloud files
- users who want scheduled backups instead of one-off exports
- people who need more visibility than a black-box sync tool provides
- self-hosters who prefer auditable backup history

## Repository Structure

- [config.json](config.json)
- [Dockerfile](Dockerfile)
- [start.sh](start.sh)
- [requirements.txt](requirements.txt)
- [main.py](main.py)
- [static/index.html](static/index.html)
- [onedrive_backup](onedrive_backup)
- [custom_components/onedrive_backup](custom_components/onedrive_backup)

## Status

The project is actively evolving. The current direction is focused on a stronger backup UX: better job visibility, clearer storage layout, and easier troubleshooting inside the add-on itself.

# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

## [0.2.1] - 2026-03-14
### Added
- Dynamic task run buttons in the custom component without Home Assistant restart.

## [0.3.22] - 2026-03-14
### Added
- Job cancellation support for running and queued backup jobs from the add-on UI.
- New API endpoint `POST /api/jobs/{job_id}/cancel`.
- Recent Jobs table now includes an `Actions` column with `Cancel` button when applicable.

## [0.2.0] - 2026-03-14
### Added
- Home Assistant custom component entities for dashboard usage:
	- Run Now button
	- Task-specific run buttons (from tasks loaded at startup)
	- Last job sensors (status, errors, downloaded, skipped)
- Service `onedrive_backup.run_task` with optional `task_id`.

## [0.1.2] - 2026-03-14
### Changed
- Bumped integration version to `0.1.2` for release/update tracking.
- Bumped add-on package version to `0.3.21` in add-on configs.

## [0.1.1] - 2026-03-13
### Added
- Keep a Changelog structure for future releases.
- Home Assistant custom component scaffold for HACS distribution.

### Changed
- Set integration version to `0.1.1`.

## [0.1.0] - 2026-03-13
### Added
- Initial release setup and repository publication.

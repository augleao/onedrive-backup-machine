"""Sensor entities for OneDrive Backup integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up OneDrive Backup sensors."""
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        return

    entities = [
        LastJobStatusSensor(coordinator),
        LastJobErrorsSensor(coordinator),
        LastJobDownloadedSensor(coordinator),
        LastJobSkippedSensor(coordinator),
    ]
    async_add_entities(entities)


class _BaseJobSensor(CoordinatorEntity, SensorEntity):
    """Common behavior for job-based sensors."""

    _attr_has_entity_name = True

    def _latest_job(self) -> dict:
        jobs = (self.coordinator.data or {}).get("jobs") or []
        return jobs[0] if jobs else {}

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class LastJobStatusSensor(_BaseJobSensor):
    """Expose latest backup job status."""

    _attr_name = "Last Job Status"
    _attr_unique_id = "onedrive_backup_last_job_status"
    _attr_icon = "mdi:cloud-check-outline"

    @property
    def native_value(self):
        job = self._latest_job()
        if not job:
            return "idle"
        return job.get("status") or "unknown"

    @property
    def extra_state_attributes(self):
        job = self._latest_job()
        summary = job.get("summary") or {}
        return {
            "task_name": job.get("task_name"),
            "task_id": job.get("task_id"),
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "mode": job.get("mode"),
            "downloaded": summary.get("downloaded", 0),
            "skipped": summary.get("skipped", 0),
            "errors": summary.get("errors", 0),
            "error_messages": summary.get("error_messages", []),
        }


class LastJobErrorsSensor(_BaseJobSensor):
    """Expose latest backup job error count."""

    _attr_name = "Last Job Errors"
    _attr_unique_id = "onedrive_backup_last_job_errors"
    _attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self):
        job = self._latest_job()
        summary = job.get("summary") or {}
        return int(summary.get("errors") or 0)


class LastJobDownloadedSensor(_BaseJobSensor):
    """Expose latest backup downloaded count."""

    _attr_name = "Last Job Downloaded"
    _attr_unique_id = "onedrive_backup_last_job_downloaded"
    _attr_icon = "mdi:download"

    @property
    def native_value(self):
        job = self._latest_job()
        summary = job.get("summary") or {}
        return int(summary.get("downloaded") or 0)


class LastJobSkippedSensor(_BaseJobSensor):
    """Expose latest backup skipped count."""

    _attr_name = "Last Job Skipped"
    _attr_unique_id = "onedrive_backup_last_job_skipped"
    _attr_icon = "mdi:skip-next"

    @property
    def native_value(self):
        job = self._latest_job()
        summary = job.get("summary") or {}
        return int(summary.get("skipped") or 0)

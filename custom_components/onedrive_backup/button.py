"""Button entities for OneDrive Backup integration."""
from __future__ import annotations

from homeassistant.core import callback
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up OneDrive Backup buttons."""
    coordinator = hass.data[DOMAIN].get("coordinator")
    if not coordinator:
        return

    task_buttons = hass.data[DOMAIN].setdefault("task_buttons", {})

    entities = [RunNowButton(coordinator)]

    tasks = (coordinator.data or {}).get("tasks") or []
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue
        if task_id in task_buttons:
            continue
        button = RunTaskButton(coordinator, task_id=task_id)
        task_buttons[task_id] = button
        entities.append(button)

    async_add_entities(entities)

    @callback
    def _sync_task_buttons() -> None:
        tasks_live = (coordinator.data or {}).get("tasks") or []
        new_buttons = []
        for task in tasks_live:
            task_id = task.get("id")
            if not task_id or task_id in task_buttons:
                continue
            button = RunTaskButton(coordinator, task_id=task_id)
            task_buttons[task_id] = button
            new_buttons.append(button)

        if new_buttons:
            async_add_entities(new_buttons)

    coordinator.async_add_listener(_sync_task_buttons)


class _BaseButton(CoordinatorEntity, ButtonEntity):
    """Base OneDrive backup button."""

    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data is not None


class RunNowButton(_BaseButton):
    """Run backup immediately using add-on default behavior."""

    _attr_name = "Run Now"
    _attr_unique_id = "onedrive_backup_run_now"
    _attr_icon = "mdi:play-circle-outline"

    async def async_press(self) -> None:
        await self.coordinator.async_run_now(task_id=None)
        await self.coordinator.async_request_refresh()


class RunTaskButton(_BaseButton):
    """Run a specific task immediately."""

    def __init__(self, coordinator, task_id: str) -> None:
        super().__init__(coordinator)
        self._task_id = task_id
        self._attr_unique_id = f"onedrive_backup_run_task_{task_id}"
        self._attr_icon = "mdi:play"

    def _task(self) -> dict | None:
        tasks = (self.coordinator.data or {}).get("tasks") or []
        for task in tasks:
            if task.get("id") == self._task_id:
                return task
        return None

    @property
    def name(self) -> str:
        task = self._task()
        task_name = (task or {}).get("name") or self._task_id
        return f"Run {task_name}"

    @property
    def available(self) -> bool:
        return super().available and self._task() is not None

    @property
    def extra_state_attributes(self):
        task = self._task()
        return {
            "task_id": self._task_id,
            "task_name": (task or {}).get("name"),
            "task_exists": task is not None,
        }

    async def async_press(self) -> None:
        await self.coordinator.async_run_now(task_id=self._task_id)
        await self.coordinator.async_request_refresh()

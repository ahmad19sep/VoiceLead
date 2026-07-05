from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .integrations import env_connected


@dataclass(frozen=True)
class CalendarResult:
    """Outcome of a calendar action.

    ``event_id`` is only ever populated by a real connected calendar client.
    A honest unavailable adapter must never invent an event id, so that the
    local system never claims a booking is on a real calendar when it is not.
    """

    success: bool
    provider: str
    action: str
    message: str
    event_id: str | None = None
    raw_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CalendarAdapter:
    key = "calendar"
    name = "Calendar"
    category = "scheduling"
    capabilities: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()

    def connected(self) -> bool:
        return False

    def production_ready(self) -> bool:
        return False

    def health(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "provider": self.name,
            "category": self.category,
            "connected": self.connected(),
            "production_ready": self.production_ready(),
            "capabilities": list(self.capabilities),
            "requirements": list(self.requirements),
        }

    def _unavailable(self, action: str) -> CalendarResult:
        return CalendarResult(
            False,
            self.name,
            action,
            f"{self.name} is not connected; booking left pending until a real calendar is configured.",
            raw_status="unavailable",
        )

    def create_event(self, booking: dict[str, Any]) -> CalendarResult:
        return self._unavailable("create_event")

    def cancel_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        return self._unavailable("cancel_event")

    def reschedule_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        return self._unavailable("reschedule_event")


class EnvCalendarAdapter(CalendarAdapter):
    env_keys: tuple[str, ...] = ()
    # Subclasses decide production readiness; without a working client the
    # adapter refuses to fabricate confirmed event ids.
    ready_requires_client = True

    def connected(self) -> bool:
        return env_connected(*self.env_keys) if self.env_keys else False

    def production_ready(self) -> bool:
        return self.connected() and not self.ready_requires_client

    def _not_ready(self, action: str) -> CalendarResult:
        if not self.connected():
            return self._unavailable(action)
        return CalendarResult(
            False,
            self.name,
            action,
            f"{self.name} credentials are present but the client is not ready "
            "(invalid service-account JSON or missing signing library); "
            "no confirmed event id is created and the booking stays pending.",
            raw_status="pending_client",
        )

    def create_event(self, booking: dict[str, Any]) -> CalendarResult:
        return self._not_ready("create_event")

    def cancel_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        return self._not_ready("cancel_event")

    def reschedule_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        return self._not_ready("reschedule_event")


class GoogleCalendarAdapter(EnvCalendarAdapter):
    key = "google_calendar"
    name = "Google Calendar"
    category = "scheduling"
    env_keys = ("GOOGLE_CALENDAR_ID", "GOOGLE_CALENDAR_CREDENTIALS")
    capabilities = ("create_event", "cancel_event", "reschedule_event", "confirmed_event_id")
    requirements = (
        "GOOGLE_CALENDAR_ID",
        "GOOGLE_CALENDAR_CREDENTIALS service-account JSON",
        "cryptography package for service-account signing",
    )

    def _client_ready(self) -> bool:
        from .google_calendar import client_ready

        return client_ready()[0]

    def production_ready(self) -> bool:
        return self.connected() and self._client_ready()

    def create_event(self, booking: dict[str, Any]) -> CalendarResult:
        if not self._client_ready():
            return self._not_ready("create_event")
        from .google_calendar import create_event

        try:
            event_id, message = create_event(booking)
        except Exception as error:
            return CalendarResult(False, self.name, "create_event", str(error), raw_status="error")
        if not event_id:
            return CalendarResult(False, self.name, "create_event", message, raw_status="needs_date")
        return CalendarResult(True, self.name, "create_event", message, event_id, "confirmed")

    def cancel_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        if not self._client_ready():
            return self._not_ready("cancel_event")
        from .google_calendar import cancel_event

        try:
            ok, message = cancel_event(event_id)
        except Exception as error:
            return CalendarResult(False, self.name, "cancel_event", str(error), event_id, "error")
        return CalendarResult(ok, self.name, "cancel_event", message, event_id, "cancelled" if ok else "error")

    def reschedule_event(self, booking: dict[str, Any], event_id: str | None) -> CalendarResult:
        if not self._client_ready():
            return self._not_ready("reschedule_event")
        from .google_calendar import reschedule_event

        try:
            new_event_id, message = reschedule_event(booking, event_id)
        except Exception as error:
            return CalendarResult(False, self.name, "reschedule_event", str(error), event_id, "error")
        if not new_event_id:
            return CalendarResult(False, self.name, "reschedule_event", message, raw_status="needs_date")
        return CalendarResult(True, self.name, "reschedule_event", message, new_event_id, "confirmed")


def calendar_registry() -> dict[str, CalendarAdapter]:
    adapters: list[CalendarAdapter] = [GoogleCalendarAdapter()]
    return {adapter.key: adapter for adapter in adapters}


def calendar_adapter(key: str | None = None) -> CalendarAdapter:
    registry = calendar_registry()
    return registry.get(key or "google_calendar", registry["google_calendar"])


def calendar_statuses() -> list[dict[str, Any]]:
    return [adapter.health() for adapter in calendar_registry().values()]

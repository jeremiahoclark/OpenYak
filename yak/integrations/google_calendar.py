"""Google Calendar API v3 integration with service-account auth (read-only)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger


class GoogleCalendarClient:
    """Async wrapper around Google Calendar API v3 using a service account."""

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

    def __init__(self, key_file: str, calendar_id: str, timezone: str = "UTC"):
        self.key_file = key_file
        self.calendar_id = calendar_id
        self.timezone = timezone
        self._service: Any = None

    def _get_service(self) -> Any:
        """Lazily build the Google Calendar API service (blocking)."""
        if self._service is None:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            creds = Credentials.from_service_account_file(
                self.key_file, scopes=self.SCOPES
            )
            self._service = build("calendar", "v3", credentials=creds)
        return self._service

    def _list_events_sync(
        self,
        max_results: int = 10,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        query: str | None = None,
    ) -> list[dict]:
        """Blocking call to events().list()."""
        service = self._get_service()
        kwargs: dict[str, Any] = {
            "calendarId": self.calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_min:
            kwargs["timeMin"] = time_min.isoformat()
        if time_max:
            kwargs["timeMax"] = time_max.isoformat()
        if query:
            kwargs["q"] = query
        result = service.events().list(**kwargs).execute()
        return result.get("items", [])

    async def list_events(
        self,
        max_results: int = 10,
        time_min: datetime | None = None,
        time_max: datetime | None = None,
        query: str | None = None,
    ) -> list[dict]:
        """List calendar events (async)."""
        return await asyncio.to_thread(
            self._list_events_sync, max_results, time_min, time_max, query
        )

    def _get_freebusy_sync(
        self, time_min: datetime, time_max: datetime
    ) -> list[dict]:
        """Blocking call to freebusy().query()."""
        service = self._get_service()
        body = {
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "items": [{"id": self.calendar_id}],
        }
        result = service.freebusy().query(body=body).execute()
        calendars = result.get("calendars", {})
        cal = calendars.get(self.calendar_id, {})
        return cal.get("busy", [])

    async def get_freebusy(
        self, time_min: datetime, time_max: datetime
    ) -> list[dict]:
        """Get free/busy slots (async)."""
        return await asyncio.to_thread(
            self._get_freebusy_sync, time_min, time_max
        )

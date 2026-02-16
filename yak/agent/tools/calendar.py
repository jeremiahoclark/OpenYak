"""Calendar tool for the agent (read-only Google Calendar access)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from yak.agent.tools.base import Tool

if TYPE_CHECKING:
    from yak.integrations.google_calendar import GoogleCalendarClient


class CalendarTool(Tool):
    """Query Google Calendar events and free/busy information."""

    name = "calendar"
    description = (
        "Read-only access to Google Calendar. "
        "Actions: list_events (upcoming events), freebusy (busy slots), "
        "search (find events by keyword)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_events", "freebusy", "search"],
                "description": "The calendar action to perform",
            },
            "query": {
                "type": "string",
                "description": "Search query (for search action)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of events to return (default 10)",
                "minimum": 1,
                "maximum": 50,
            },
            "days_ahead": {
                "type": "integer",
                "description": "Number of days ahead to look (default 1)",
                "minimum": 1,
                "maximum": 90,
            },
        },
        "required": ["action"],
    }

    def __init__(self, client: GoogleCalendarClient):
        self._client = client

    async def execute(
        self,
        action: str,
        query: str | None = None,
        max_results: int | None = None,
        days_ahead: int | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            now = datetime.now(timezone.utc)
            days = days_ahead or 1
            time_max = now + timedelta(days=days)
            n = max_results or 10

            if action == "list_events":
                return await self._list_events(now, time_max, n)
            elif action == "freebusy":
                return await self._freebusy(now, time_max)
            elif action == "search":
                if not query:
                    return "Error: 'query' is required for the search action"
                return await self._search(now, time_max, query, n)
            else:
                return f"Error: Unknown action '{action}'"
        except Exception as e:
            return f"Error: {e}"

    async def _list_events(
        self, time_min: datetime, time_max: datetime, max_results: int
    ) -> str:
        events = await self._client.list_events(
            max_results=max_results, time_min=time_min, time_max=time_max
        )
        if not events:
            return "No upcoming events found."
        return self._format_events(events)

    async def _freebusy(self, time_min: datetime, time_max: datetime) -> str:
        slots = await self._client.get_freebusy(time_min, time_max)
        if not slots:
            return f"You are free from {time_min:%Y-%m-%d %H:%M} to {time_max:%Y-%m-%d %H:%M}."
        lines = ["Busy slots:"]
        for slot in slots:
            start = slot.get("start", "?")
            end = slot.get("end", "?")
            lines.append(f"  {start} -- {end}")
        return "\n".join(lines)

    async def _search(
        self, time_min: datetime, time_max: datetime, query: str, max_results: int
    ) -> str:
        events = await self._client.list_events(
            max_results=max_results, time_min=time_min, time_max=time_max, query=query
        )
        if not events:
            return f"No events matching '{query}'."
        return self._format_events(events)

    @staticmethod
    def _format_events(events: list[dict]) -> str:
        lines: list[str] = []
        for i, ev in enumerate(events, 1):
            summary = ev.get("summary", "(no title)")
            start_raw = ev.get("start", {})
            start = start_raw.get("dateTime") or start_raw.get("date", "?")
            end_raw = ev.get("end", {})
            end = end_raw.get("dateTime") or end_raw.get("date", "")
            location = ev.get("location", "")

            line = f"{i}. {summary}\n   Start: {start}"
            if end:
                line += f"\n   End: {end}"
            if location:
                line += f"\n   Location: {location}"
            lines.append(line)
        return "\n".join(lines)

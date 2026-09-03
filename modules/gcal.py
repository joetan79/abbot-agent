"""Google Calendar integration for ABbot.
Setup: set GOOGLE_CALENDAR_CREDENTIALS in .env (path to credentials.json from Google Cloud Console).
Auth flow is done via the Telegram bot itself — bot sends auth URL, user pastes the code back."""

import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "data/gcal_credentials.json")
TOKEN_FILE = "data/gcal_token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Google Calendar's fixed per-event color palette (colorId -> name), as shown in the
# event color picker. "green" maps to Basil (10), the closer match to a plain "green"
# ask; "sage" (2) is the paler alternate green some people mean instead.
COLOR_NAME_TO_ID = {
    "lavender": "1", "purple": "3", "grape": "3",
    "sage": "2", "green": "10", "basil": "10",
    "flamingo": "4", "pink": "4",
    "banana": "5", "yellow": "5",
    "tangerine": "6", "orange": "6",
    "peacock": "7", "teal": "7", "cyan": "7",
    "graphite": "8", "gray": "8", "grey": "8",
    "blueberry": "9", "blue": "9",
    "tomato": "11", "red": "11",
}


def _resolve_color_id(color: str | None) -> str | None:
    if not color:
        return None
    return COLOR_NAME_TO_ID.get(color.strip().lower())


def is_available() -> bool:
    try:
        import googleapiclient  # noqa
        import google_auth_oauthlib  # noqa
        return True
    except ImportError:
        return False


def is_connected() -> bool:
    return Path(TOKEN_FILE).exists() and is_available()


def _get_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        except Exception as e:
            logger.error(f"[GCal] Token refresh failed: {e}")
            # Token revoked or expired — remove it so is_connected() returns False
            try:
                Path(TOKEN_FILE).unlink()
            except Exception:
                pass
            return None
    if not creds or not creds.valid:
        return None
    return build("calendar", "v3", credentials=creds)


FLOW_STATE_FILE = "data/gcal_flow_state.json"
_active_flow = None  # keep flow in memory to preserve code_verifier


def get_auth_url() -> str | None:
    """Returns the OAuth2 URL for the user to visit. Returns None if credentials file missing."""
    global _active_flow
    if not is_available():
        return None
    if not Path(CREDENTIALS_FILE).exists():
        return None
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            CREDENTIALS_FILE, scopes=SCOPES,
            redirect_uri="urn:ietf:wg:oauth:2.0:oob"
        )
        auth_url, _ = flow.authorization_url(prompt="consent")
        _active_flow = flow  # preserve so code_verifier survives until complete_auth
        return auth_url
    except Exception as e:
        logger.error(f"[GCal] Auth URL error: {e}")
        return None


def complete_auth(code: str) -> bool:
    """Exchange the auth code for a token and save it."""
    global _active_flow
    if not Path(CREDENTIALS_FILE).exists():
        return False
    try:
        from google_auth_oauthlib.flow import Flow

        # Use the in-memory flow (preserves code_verifier for PKCE)
        flow = _active_flow
        if flow is None:
            # Fallback: recreate without PKCE (works if auth URL was also generated without it)
            flow = Flow.from_client_secrets_file(
                CREDENTIALS_FILE, scopes=SCOPES,
                redirect_uri="urn:ietf:wg:oauth:2.0:oob"
            )

        flow.fetch_token(code=code)
        with open(TOKEN_FILE, "w") as f:
            f.write(flow.credentials.to_json())
        _active_flow = None
        logger.info("[GCal] Auth completed, token saved")
        return True
    except Exception as e:
        logger.error(f"[GCal] Auth completion failed: {e}")
        return False


def get_today_events() -> list:
    """Return today's calendar events as a list of dicts."""
    svc = _get_service()
    if not svc:
        return []
    try:
        now = datetime.utcnow()
        start = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        end = now.replace(hour=23, minute=59, second=59).isoformat() + "Z"
        result = svc.events().list(
            calendarId="primary", timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime"
        ).execute()
        events = []
        for e in result.get("items", []):
            start_dt = e["start"].get("dateTime", e["start"].get("date", ""))
            try:
                dt = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M")
            except Exception:
                time_str = start_dt
            events.append({"time": time_str, "title": e.get("summary", "(no title)"),
                           "location": e.get("location", "")})
        return events
    except Exception as e:
        logger.error(f"[GCal] get_today_events failed: {e}")
        return []


def get_week_events() -> list:
    """Return this week's events."""
    svc = _get_service()
    if not svc:
        return []
    try:
        now = datetime.utcnow()
        start = now.isoformat() + "Z"
        end = (now + timedelta(days=7)).isoformat() + "Z"
        result = svc.events().list(
            calendarId="primary", timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime", maxResults=20
        ).execute()
        events = []
        for e in result.get("items", []):
            start_dt = e["start"].get("dateTime", e["start"].get("date", ""))
            try:
                dt = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
                date_str = dt.strftime("%a %d %b %H:%M")
            except Exception:
                date_str = start_dt
            events.append({
                "datetime": date_str,
                "start_iso": start_dt,
                "title": e.get("summary", "(no title)"),
            })
        return events
    except Exception as e:
        logger.error(f"[GCal] get_week_events failed: {e}")
        return []


TZ = "Asia/Macau"
DAY_ABBR = {
    "monday": "MO", "tuesday": "TU", "wednesday": "WE",
    "thursday": "TH", "friday": "FR", "saturday": "SA", "sunday": "SU"
}


def add_event(title: str, start_dt: datetime, end_dt: datetime = None, description: str = "", color: str = None) -> bool:
    svc = _get_service()
    if not svc:
        return False
    try:
        if not end_dt:
            end_dt = start_dt + timedelta(hours=1)
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TZ},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TZ},
        }
        color_id = _resolve_color_id(color)
        if color_id:
            event["colorId"] = color_id
        svc.events().insert(calendarId="primary", body=event).execute()
        return True
    except Exception as e:
        logger.error(f"[GCal] add_event failed: {e}")
        return False


def add_recurring_event(
    title: str,
    start_date: "date",
    end_date: "date",
    days_of_week: list,
    start_time: tuple,
    end_time: tuple,
    description: str = "",
    color: str = None,
) -> int:
    """Add recurring events on specified days between start_date and end_date.
    start_time/end_time are (hour, minute) tuples.
    Returns count of events created, or -1 on error."""
    import pytz
    from datetime import date as _date
    svc = _get_service()
    if not svc:
        return -1
    try:
        tz = pytz.timezone(TZ)
        day_names = [d.lower() for d in days_of_week]
        day_nums = {"monday":0,"tuesday":1,"wednesday":2,"thursday":3,
                    "friday":4,"saturday":5,"sunday":6}
        target_days = [day_nums[d] for d in day_names if d in day_nums]

        # Build RRULE: weekly on specified days until end_date
        byday = ",".join(DAY_ABBR[d] for d in day_names if d in DAY_ABBR)
        until_str = end_date.strftime("%Y%m%dT235959Z")
        rrule = f"RRULE:FREQ=WEEKLY;BYDAY={byday};UNTIL={until_str}"

        # Find first occurrence on or after start_date
        cur = start_date
        while cur.weekday() not in target_days:
            cur = cur + timedelta(days=1)
            if cur > end_date:
                return 0

        sh, sm = start_time
        eh, em = end_time
        start_dt = tz.localize(datetime(cur.year, cur.month, cur.day, sh, sm, 0))
        end_dt = tz.localize(datetime(cur.year, cur.month, cur.day, eh, em, 0))

        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": TZ},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": TZ},
            "recurrence": [rrule],
        }
        color_id = _resolve_color_id(color)
        if color_id:
            event["colorId"] = color_id
        svc.events().insert(calendarId="primary", body=event).execute()
        # Count occurrences for confirmation message
        count = 0
        cur2 = cur
        while cur2 <= end_date:
            if cur2.weekday() in target_days:
                count += 1
            cur2 = cur2 + timedelta(days=1)
        return count
    except Exception as e:
        logger.error(f"[GCal] add_recurring_event failed: {e}")
        return -1


def find_events_by_title(title: str, days_ahead: int = 60) -> list:
    """Search upcoming events whose title contains the given string (case-insensitive)."""
    svc = _get_service()
    if not svc:
        return []
    try:
        now = datetime.utcnow()
        result = svc.events().list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=(now + timedelta(days=days_ahead)).isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        ).execute()
        matches = []
        title_lower = title.lower()
        for e in result.get("items", []):
            if title_lower in e.get("summary", "").lower():
                matches.append({
                    "id": e["id"],
                    "title": e.get("summary", ""),
                    "start": e["start"].get("dateTime", e["start"].get("date", "")),
                    "end": e["end"].get("dateTime", e["end"].get("date", "")),
                    "recurrence": e.get("recurrence", []),
                    "recurringEventId": e.get("recurringEventId"),
                })
        return matches
    except Exception as e:
        logger.error(f"[GCal] find_events_by_title failed: {e}")
        return []


def modify_event(event_id: str, updates: dict, all_recurring: bool = False) -> bool:
    """Patch an existing event. updates can have: title, start_time, end_time, start_date."""
    import pytz
    svc = _get_service()
    if not svc:
        return False
    try:
        event = svc.events().get(calendarId="primary", eventId=event_id).execute()
        tz = pytz.timezone(TZ)

        if "title" in updates:
            event["summary"] = updates["title"]

        if "start_time" in updates or "end_time" in updates or "start_date" in updates:
            start_str = event["start"].get("dateTime") or ""
            end_str = event["end"].get("dateTime") or ""
            is_all_day = not start_str
            if is_all_day:
                # All-day event: build datetime from date field
                start_date_str = event["start"].get("date", "")
                end_date_str = event["end"].get("date", "")
                logger.info(f"[GCal] Event is all-day: start.date={start_date_str}")
                try:
                    from datetime import date as _date
                    sd = datetime.strptime(start_date_str, "%Y-%m-%d")
                    ed = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else sd
                    start_dt = tz.localize(sd.replace(hour=0, minute=0, second=0))
                    end_dt = tz.localize(ed.replace(hour=1, minute=0, second=0))
                except Exception as parse_err:
                    logger.error(f"[GCal] modify_event: failed to parse all-day date: {parse_err}")
                    return False
            else:
                try:
                    start_dt = datetime.fromisoformat(start_str)
                    end_dt = datetime.fromisoformat(end_str)
                except Exception as parse_err:
                    logger.error(f"[GCal] modify_event: failed to parse dateTime '{start_str}': {parse_err}")
                    return False

            if "start_date" in updates:
                d = updates["start_date"]
                start_dt = start_dt.replace(year=d.year, month=d.month, day=d.day)
                end_dt = end_dt.replace(year=d.year, month=d.month, day=d.day)

            if "start_time" in updates:
                h, m = updates["start_time"]
                start_dt = start_dt.replace(hour=h, minute=m, second=0)

            if "end_time" in updates:
                h, m = updates["end_time"]
                end_dt = end_dt.replace(hour=h, minute=m, second=0)
            elif is_all_day:
                # Default end time = start + 1.5 hours when converting from all-day
                end_dt = start_dt.replace(hour=start_dt.hour + 1, minute=30, second=0)

            event["start"] = {"dateTime": start_dt.isoformat(), "timeZone": TZ}
            event["end"] = {"dateTime": end_dt.isoformat(), "timeZone": TZ}

        svc.events().update(calendarId="primary", eventId=event_id, body=event).execute()
        return True
    except Exception as e:
        logger.error(f"[GCal] modify_event failed: {e}")
        return False

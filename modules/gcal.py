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
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
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
            events.append({"datetime": date_str, "title": e.get("summary", "(no title)")})
        return events
    except Exception as e:
        logger.error(f"[GCal] get_week_events failed: {e}")
        return []


def add_event(title: str, start_dt: datetime, end_dt: datetime = None, description: str = "") -> bool:
    svc = _get_service()
    if not svc:
        return False
    try:
        if not end_dt:
            end_dt = start_dt + timedelta(hours=1)
        tz = "Asia/Macau"
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": tz},
        }
        svc.events().insert(calendarId="primary", body=event).execute()
        return True
    except Exception as e:
        logger.error(f"[GCal] add_event failed: {e}")
        return False

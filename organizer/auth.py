"""Gmail API authentication handler."""

import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar",
]

TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"


def _get_credentials() -> Credentials:
    """Load, refresh, or obtain OAuth credentials."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    f"Missing {CREDS_PATH}. Download it from Google Cloud Console. "
                    "See README.md for instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    return creds


def get_gmail_service():
    """Authenticate and return a Gmail API service object."""
    return build("gmail", "v1", credentials=_get_credentials())


def get_calendar_service():
    """Return a Google Calendar API service using already-loaded credentials."""
    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(
            "No token.json found. Run --auth first to grant Calendar permissions."
        )
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            raise PermissionError(
                "Calendar credentials invalid. Delete token.json and re-run --auth."
            )
    return build("calendar", "v3", credentials=creds)

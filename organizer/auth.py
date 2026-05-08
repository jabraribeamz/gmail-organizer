"""Gmail OAuth2 authentication.

Handles token refresh and initial OAuth flow.
Stores credentials in ~/.gmail-organizer/token.json.
"""

import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CONFIG_DIR = Path.home() / ".gmail-organizer"
TOKEN_PATH = CONFIG_DIR / "token.json"
CREDS_PATH = CONFIG_DIR / "credentials.json"


def get_service() -> Any:
    """Return an authenticated Gmail API service object.

    Returns:
        A Gmail API service resource built with valid OAuth2 credentials.

    Raises:
        FileNotFoundError: If credentials.json is missing from CONFIG_DIR.
        google.auth.exceptions.RefreshError: If token refresh fails.
    """
    CONFIG_DIR.mkdir(exist_ok=True)
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(
            str(TOKEN_PATH), SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"Place your Google OAuth credentials at"
                    f" {CREDS_PATH}\n"
                    "Download from: https://console.cloud.google.com"
                    "/apis/credentials"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDS_PATH), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_PATH.write_text(creds.to_json())
        logger.debug("Token written to %s", TOKEN_PATH)

    return build("gmail", "v1", credentials=creds)

import base64
import os
from datetime import datetime
from typing import Optional
from email import message_from_bytes
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import config
from app.utils.logging import get_logger

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    creds = None

    if os.path.exists(config.GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.GMAIL_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.GMAIL_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Gmail credentials file not found: {config.GMAIL_CREDENTIALS_FILE}\n"
                    "Download it from Google Cloud Console and place it in the project root."
                )
            flow = InstalledAppFlow.from_client_secrets_file(config.GMAIL_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(config.GMAIL_TOKEN_FILE, "w") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_message_ids(service, query: str, max_results: int = 100) -> list[str]:
    """Return Gmail message IDs matching the query."""
    message_ids = []
    page_token = None

    while len(message_ids) < max_results:
        kwargs = {"userId": "me", "q": query, "maxResults": min(100, max_results - len(message_ids))}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        messages = result.get("messages", [])
        message_ids.extend(m["id"] for m in messages)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return message_ids


def fetch_message(service, message_id: str) -> dict:
    """Fetch a single Gmail message and return a structured dict."""
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}

    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    date_str = headers.get("date", "")
    thread_id = msg.get("threadId", "")

    received_at = None
    if date_str:
        try:
            received_at = parsedate_to_datetime(date_str).replace(tzinfo=None)
        except Exception:
            pass

    raw_body = _extract_body(msg.get("payload", {}))

    return {
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id,
        "subject": subject,
        "sender": sender,
        "received_at": received_at,
        "raw_body": raw_body,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body, falling back to HTML."""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")
    parts = payload.get("parts", [])

    if mime_type == "text/plain" and body_data:
        return _decode_base64(body_data)

    if mime_type == "text/html" and body_data:
        return _html_to_text(_decode_base64(body_data))

    # multipart: prefer plain text parts
    plain_parts = [p for p in parts if p.get("mimeType") == "text/plain"]
    if plain_parts:
        return _decode_base64(plain_parts[0].get("body", {}).get("data", ""))

    html_parts = [p for p in parts if p.get("mimeType") == "text/html"]
    if html_parts:
        return _html_to_text(_decode_base64(html_parts[0].get("body", {}).get("data", "")))

    # recurse into nested multipart
    for part in parts:
        result = _extract_body(part)
        if result.strip():
            return result

    return ""


def _decode_base64(data: str) -> str:
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        return soup.get_text(separator="\n")
    except Exception:
        return html

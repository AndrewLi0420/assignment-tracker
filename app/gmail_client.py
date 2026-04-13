import base64
import json
import os
import tempfile
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


def _load_creds_from_env() -> Credentials | None:
    """Load token from GMAIL_TOKEN_JSON env var (used on Railway/production)."""
    token_json = os.getenv("GMAIL_TOKEN_JSON")
    if token_json:
        return Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
    return None


def _save_creds(creds: Credentials) -> None:
    """Persist token — to file if writable, always log the JSON for env-var setup."""
    token_json = creds.to_json()
    try:
        with open(config.GMAIL_TOKEN_FILE, "w") as f:
            f.write(token_json)
    except OSError:
        pass
    # If no file-based storage, print so the token can be copied into GMAIL_TOKEN_JSON
    if not os.path.exists(config.GMAIL_TOKEN_FILE):
        logger.info("GMAIL_TOKEN_JSON (copy this into your Railway env var):\n%s", token_json)


def _get_credentials_file() -> str:
    """Return path to credentials JSON, writing from env var if needed."""
    creds_json = os.getenv("GMAIL_CREDENTIALS_JSON")
    if creds_json:
        # Write to a temp file so InstalledAppFlow can read it
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(creds_json)
        tmp.close()
        return tmp.name
    if not os.path.exists(config.GMAIL_CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"Gmail credentials not found. Set GMAIL_CREDENTIALS_JSON env var "
            f"or place credentials.json at {config.GMAIL_CREDENTIALS_FILE}"
        )
    return config.GMAIL_CREDENTIALS_FILE


def get_gmail_service():
    # 1. Try env-var token (Railway/production)
    creds = _load_creds_from_env()

    # 2. Fall back to token file (local dev)
    if not creds and os.path.exists(config.GMAIL_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.GMAIL_TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_creds(creds)
            except Exception:
                logger.warning("Token refresh failed — re-auth required")
                if os.path.exists(config.GMAIL_TOKEN_FILE):
                    os.remove(config.GMAIL_TOKEN_FILE)
                creds = None

        if not creds or not creds.valid:
            if os.getenv("VERCEL"):
                raise RuntimeError(
                    "Gmail token is missing or expired. Re-run the local OAuth flow, "
                    "then update the GMAIL_TOKEN_JSON environment variable in Vercel."
                )
            creds_file = _get_credentials_file()
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
            _save_creds(creds)

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


def list_new_message_ids(
    service,
    query: str,
    known_ids: set,
    hard_limit: int = 2000,
    fetch_target: int = 50,
) -> list[str]:
    """
    Paginate Gmail results (newest-first) and return IDs not in known_ids.

    Stops listing after collecting fetch_target new IDs to keep each Vercel
    invocation short.  A second sync call will continue because the newly
    processed IDs will be in known_ids, causing the next page to be scanned.
    """
    new_ids = []
    page_token = None
    total_seen = 0

    while total_seen < hard_limit:
        kwargs = {"userId": "me", "q": query, "maxResults": min(100, hard_limit - total_seen)}
        if page_token:
            kwargs["pageToken"] = page_token

        result = service.users().messages().list(**kwargs).execute()
        page_ids = [m["id"] for m in result.get("messages", [])]
        total_seen += len(page_ids)

        new_ids.extend(mid for mid in page_ids if mid not in known_ids)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

        # Stop listing early once we have plenty to work with; subsequent
        # calls will naturally advance to the next page as known_ids grows.
        if len(new_ids) >= fetch_target:
            break

    return new_ids


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

    payload = msg.get("payload", {})
    raw_body = _extract_body(payload)
    has_attachment = _has_attachment(payload)

    return {
        "gmail_message_id": message_id,
        "gmail_thread_id": thread_id,
        "subject": subject,
        "sender": sender,
        "received_at": received_at,
        "raw_body": raw_body,
        "has_attachment": has_attachment,
    }


def _has_attachment(payload: dict) -> bool:
    """Return True if the message has any file attachment (PDF, image, video, etc.)."""
    # A part with a filename and an attachmentId is a real attachment
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        return True
    # Also catch inline images/files that have a filename but no attachmentId
    mime = payload.get("mimeType", "")
    if payload.get("filename") and mime.split("/")[0] in ("application", "image", "video", "audio"):
        return True
    for part in payload.get("parts", []):
        if _has_attachment(part):
            return True
    return False


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
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n")
    except Exception:
        return html

"""
Automatic ATS Email Verification & Security Code Reader for JobPulse Autopilot.

Connects via IMAP over SSL (e.g., imap.gmail.com:993) to automatically retrieve 8-character
Greenhouse security codes (and Lever / Ashby verification codes) sent during autonomous
application submission. Also supports a local manual code drop-box file so codes pasted
into the JobPulse UI are picked up immediately.
"""
import email
import imaplib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
PACKETS_DIR = BASE_DIR / "generated_packets"
MANUAL_CODE_FILE = PACKETS_DIR / "manual_security_code.json"


def save_manual_security_code(code: str, job_id: Optional[int] = None) -> None:
    """Stores a user-supplied security code on disk so an active Playwright runner can consume it."""
    PACKETS_DIR.mkdir(parents=True, exist_ok=True)
    MANUAL_CODE_FILE.write_text(
        json.dumps(
            {
                "code": code.strip(),
                "job_id": job_id,
                "timestamp": time.time(),
            }
        ),
        encoding="utf-8",
    )


def consume_manual_security_code(min_timestamp: float) -> Optional[str]:
    """Reads and consumes a fresh manual security code if entered after `min_timestamp`."""
    try:
        if MANUAL_CODE_FILE.exists():
            data = json.loads(MANUAL_CODE_FILE.read_text(encoding="utf-8"))
            ts = float(data.get("timestamp") or 0)
            code = (data.get("code") or "").strip()
            if code and ts >= min_timestamp - 30:
                MANUAL_CODE_FILE.unlink(missing_ok=True)
                return code
    except Exception:
        pass
    return None


def _decode_str(raw: Any) -> str:
    if not raw:
        return ""
    if isinstance(raw, str):
        parts = decode_header(raw)
        out = []
        for content, enc in parts:
            if isinstance(content, bytes):
                out.append(content.decode(enc or "utf-8", errors="replace"))
            else:
                out.append(str(content))
        return "".join(out)
    return str(raw)


def _extract_email_body(msg: email.message.Message) -> str:
    """Extracts plain text from a single or multipart email message."""
    plain_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if ctype == "text/plain":
                plain_parts.append(decoded)
            elif ctype == "text/html":
                html_parts.append(decoded)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(decoded)
            else:
                plain_parts.append(decoded)

    if plain_parts:
        return "\n".join(plain_parts)
    if html_parts:
        soup = BeautifulSoup("\n".join(html_parts), "html.parser")
        return soup.get_text(separator="\n")
    return ""


def extract_greenhouse_security_code_from_text(text: str) -> Optional[str]:
    """
    Extracts an 8-character Greenhouse security code (or 6-8 char verification code)
    from a Greenhouse verification email body.
    """
    if not text:
        return None

    # Common Greenhouse patterns:
    # "paste this code into the application form:\n\nAb3dEf7H"
    # "security code is: Ab3dEf7H"
    # Standalone line with an 8-character alphanumeric token
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Look for explicit label followed by 8-char code on same or next line
    for idx, line in enumerate(lines):
        low = line.lower()
        if any(
            phrase in low
            for phrase in (
                "code into the application",
                "verification code",
                "security code",
                "your code is",
                "enter the code",
                "8-character code",
            )
        ):
            # Check same line after colon
            if ":" in line:
                after_colon = line.split(":", 1)[1].strip()
                m = re.match(r"^([A-Za-z0-9]{6,8})\b", after_colon)
                if m and m.group(1).lower() not in ("security", "verifica", "applicat"):
                    return m.group(1)
            # Check next 1-2 lines for a standalone 8-char alphanumeric token
            for next_line in lines[idx + 1 : idx + 4]:
                m_next = re.match(r"^([A-Za-z0-9]{8})$", next_line)
                if m_next and m_next.group(1).lower() not in (
                    "security",
                    "linkedin",
                    "question",
                    "password",
                    "continue",
                ):
                    return m_next.group(1)

    # 2. Fallback: look for any standalone line that is strictly an 8-char mixed-case/digit token
    for line in lines:
        if re.match(r"^[A-Za-z0-9]{8}$", line):
            # Must contain at least one digit or uppercase+lowercase mix typical of Greenhouse codes
            if any(c.isdigit() for c in line) or (any(c.isupper() for c in line) and any(c.islower() for c in line)):
                if line.lower() not in ("security", "greenhou", "thankyou"):
                    return line

    return None


def fetch_latest_ats_security_code(
    imap_server: str,
    imap_email: str,
    imap_password: str,
    min_timestamp: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Connects to the IMAP server over SSL and searches the last 12 emails in INBOX
    for a Greenhouse / ATS security code email.
    Returns {"code": str, "subject": str, "from": str, "date": str} if found.
    """
    if not imap_server or not imap_email or not imap_password:
        return None

    clean_pw = imap_password.replace(" ", "").strip()
    cutoff = min_timestamp or (time.time() - 300)  # Default: within last 5 minutes

    try:
        mail = imaplib.IMAP4_SSL(imap_server.strip(), 993, timeout=10)
        mail.login(imap_email.strip(), clean_pw)
        mail.select("INBOX", readonly=True)

        status, data = mail.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            mail.logout()
            return None

        msg_ids = data[0].split()
        # Inspect newest 12 messages in reverse chronological order
        for m_id in reversed(msg_ids[-12:]):
            st, msg_data = mail.fetch(m_id, "(RFC822)")
            if st != "OK" or not msg_data or not msg_data[0]:
                continue
            raw_bytes = msg_data[0][1]
            if not isinstance(raw_bytes, bytes):
                continue
            msg = email.message_from_bytes(raw_bytes)
            subj = _decode_str(msg.get("Subject"))
            sender = _decode_str(msg.get("From"))
            date_hdr = msg.get("Date")

            # Check message age if Date header is parseable
            if date_hdr:
                try:
                    dt = parsedate_to_datetime(date_hdr)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    msg_ts = dt.timestamp()
                    if msg_ts < cutoff - 60:
                        continue
                except Exception:
                    pass

            combined_hdr = f"{subj} {sender}".lower()
            if not any(
                k in combined_hdr
                for k in ("greenhouse", "security code", "verification code", "application", "verify", "no-reply")
            ):
                continue

            body_text = _extract_email_body(msg)
            code = extract_greenhouse_security_code_from_text(body_text) or extract_greenhouse_security_code_from_text(subj)
            if code:
                mail.logout()
                return {
                    "code": code,
                    "subject": subj,
                    "from": sender,
                    "date": str(date_hdr or ""),
                }

        mail.logout()
    except Exception as e:
        logger.warning(f"IMAP security code fetch error: {e}")

    return None


def poll_for_security_code_sync(
    imap_server: Optional[str],
    imap_email: Optional[str],
    imap_password: Optional[str],
    min_timestamp: float,
    max_wait_seconds: int = 25,
) -> Optional[str]:
    """
    Polls both the local manual drop-box file and the configured IMAP inbox every 3 seconds
    up to `max_wait_seconds` for a newly arrived 8-character security code.
    """
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        # 1. Check if user pasted a manual code in the dashboard UI
        manual_code = consume_manual_security_code(min_timestamp)
        if manual_code:
            return manual_code

        # 2. Check IMAP inbox if credentials are configured
        if imap_server and imap_email and imap_password:
            found = fetch_latest_ats_security_code(
                imap_server=imap_server,
                imap_email=imap_email,
                imap_password=imap_password,
                min_timestamp=min_timestamp,
            )
            if found and found.get("code"):
                return found["code"]

        time.sleep(3.0)

    return None


def test_imap_connection(
    imap_server: str,
    imap_email: str,
    imap_password: str,
) -> Dict[str, Any]:
    """
    Verifies IMAP login credentials and checks if any recent Greenhouse security code
    is currently visible in the inbox.
    """
    if not imap_email or not imap_password:
        return {
            "success": False,
            "message": "Please provide both your email address and Gmail App Password.",
        }

    clean_pw = imap_password.replace(" ", "").strip()
    try:
        mail = imaplib.IMAP4_SSL((imap_server or "imap.gmail.com").strip(), 993, timeout=10)
        mail.login(imap_email.strip(), clean_pw)
        status, messages = mail.select("INBOX", readonly=True)
        total_msgs = int(messages[0]) if status == "OK" and messages and messages[0] else 0
        mail.logout()

        # Also check if there is a recent code in the last 30 minutes
        recent = fetch_latest_ats_security_code(
            imap_server=imap_server or "imap.gmail.com",
            imap_email=imap_email,
            imap_password=clean_pw,
            min_timestamp=time.time() - 1800,
        )
        msg = f"Connected to {imap_server or 'imap.gmail.com'} ({total_msgs} emails in INBOX)."
        if recent and recent.get("code"):
            msg += f" Found recent security code '{recent['code']}' from '{recent['subject']}'!"

        return {
            "success": True,
            "message": msg,
            "recent_code": recent.get("code") if recent else None,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"IMAP connection failed: {str(e)}",
        }

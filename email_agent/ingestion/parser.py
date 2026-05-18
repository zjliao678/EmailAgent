"""Email parsing: raw bytes → ParsedEmail with PII masking and prompt-injection protection."""

import email
import email.message
import re
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup


@dataclass
class Attachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class ParsedEmail:
    message_id: str
    sender: str
    to: str
    subject: str
    body: str  # always wrapped in <email_content> tags
    in_reply_to: Optional[str]
    references: Optional[str]
    attachments: list[Attachment] = field(default_factory=list)


# ── Public API ────────────────────────────────────────────────────────────────


def parse_email(raw: bytes) -> ParsedEmail:
    msg = email.message_from_bytes(raw)
    body_text = _extract_body(msg)
    wrapped = f"<email_content>\n{mask_pii(body_text)}\n</email_content>"
    return ParsedEmail(
        message_id=msg.get("Message-ID", ""),
        sender=msg.get("From", ""),
        to=msg.get("To", ""),
        subject=msg.get("Subject", ""),
        body=wrapped,
        in_reply_to=msg.get("In-Reply-To"),
        references=msg.get("References"),
        attachments=_extract_attachments(msg),
    )


# ── PII masking ───────────────────────────────────────────────────────────────

_PHONE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_CREDIT_CARD = re.compile(r"(?<!\d)(\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4})(?!\d)")
_ID_CARD = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")


def mask_pii(text: str) -> str:
    text = _PHONE.sub(lambda m: m.group()[:3] + "***" + m.group()[-4:], text)
    text = _CREDIT_CARD.sub("****-****-****-****", text)
    text = _ID_CARD.sub(lambda m: m.group()[:6] + "***" + m.group()[-4:], text)
    return text


# ── Internal helpers ──────────────────────────────────────────────────────────


def _extract_body(msg: email.message.Message) -> str:
    if not msg.is_multipart():
        return _text_from_part(msg)

    plain: Optional[str] = None
    html: Optional[str] = None
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain" and plain is None:
            plain = _decode_payload(part)
        elif ct == "text/html" and html is None:
            html = _decode_payload(part)

    if plain is not None:
        return plain
    if html is not None:
        return _html_to_text(html)
    return ""


def _text_from_part(part: email.message.Message) -> str:
    if part.get_content_type() == "text/html":
        return _html_to_text(_decode_payload(part))
    return _decode_payload(part)


def _decode_payload(part: email.message.Message) -> str:
    raw = part.get_payload(decode=True)
    if raw is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _html_to_text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)


def _extract_attachments(msg: email.message.Message) -> list[Attachment]:
    attachments = []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment":
            attachments.append(
                Attachment(
                    filename=part.get_filename() or "unnamed",
                    content_type=part.get_content_type(),
                    data=part.get_payload(decode=True) or b"",
                )
            )
    return attachments

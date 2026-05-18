"""Tests for email_agent.ingestion.parser — written before implementation (TDD)."""

import email.message
import email.mime.base
import email.mime.multipart
import email.mime.text
from email import encoders

import pytest

from email_agent.ingestion.parser import ParsedEmail, mask_pii, parse_email


# ── helpers ───────────────────────────────────────────────────────────────────


def _plain(
    from_addr="sender@example.com",
    to_addr="receiver@qq.com",
    subject="Test Subject",
    body="Hello World",
    message_id="<test-001@example.com>",
    in_reply_to=None,
) -> bytes:
    msg = email.message.Message()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = message_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    msg.set_payload(body, charset="utf-8")
    return msg.as_bytes()


def _html(html_body: str, plain_body: str = "") -> bytes:
    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["From"] = "sender@example.com"
    msg["To"] = "receiver@qq.com"
    msg["Subject"] = "HTML Email"
    msg["Message-ID"] = "<html-001@example.com>"
    if plain_body:
        msg.attach(email.mime.text.MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))
    return msg.as_bytes()


# ── ParsedEmail field tests ───────────────────────────────────────────────────


class TestParseEmailFields:
    def test_extracts_basic_fields(self):
        result = parse_email(_plain())
        assert result.sender == "sender@example.com"
        assert result.to == "receiver@qq.com"
        assert result.subject == "Test Subject"
        assert result.message_id == "<test-001@example.com>"

    def test_extracts_in_reply_to(self):
        result = parse_email(_plain(in_reply_to="<original@example.com>"))
        assert result.in_reply_to == "<original@example.com>"

    def test_missing_in_reply_to_is_none(self):
        result = parse_email(_plain())
        assert result.in_reply_to is None

    def test_html_stripped_to_plain_text(self):
        result = parse_email(_html("<html><body><p>Hello <b>World</b></p></body></html>"))
        assert "Hello" in result.body
        assert "World" in result.body
        assert "<b>" not in result.body   # HTML tags from email body are stripped
        assert "<p>" not in result.body

    def test_multipart_prefers_plain_over_html(self):
        result = parse_email(_html("<p>HTML version</p>", plain_body="Plain version"))
        assert "Plain version" in result.body
        assert "HTML" not in result.body

    def test_attachment_detected(self):
        msg = email.mime.multipart.MIMEMultipart()
        msg["From"] = "a@example.com"
        msg["To"] = "b@qq.com"
        msg["Subject"] = "With Attachment"
        msg["Message-ID"] = "<att-001@example.com>"
        msg.attach(email.mime.text.MIMEText("See attachment", "plain"))
        part = email.mime.base.MIMEBase("application", "octet-stream")
        part.set_payload(b"fake pdf content")
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename="doc.pdf")
        msg.attach(part)
        result = parse_email(msg.as_bytes())
        assert len(result.attachments) == 1
        assert result.attachments[0].filename == "doc.pdf"
        assert result.attachments[0].content_type == "application/octet-stream"

    def test_no_attachments_when_plain_only(self):
        result = parse_email(_plain())
        assert result.attachments == []


# ── Prompt injection protection ───────────────────────────────────────────────


class TestPromptInjectionProtection:
    def test_body_wrapped_in_email_content_tags(self):
        result = parse_email(_plain(body="Some content here"))
        assert result.body.startswith("<email_content>")
        assert result.body.endswith("</email_content>")

    def test_body_content_preserved_inside_tags(self):
        result = parse_email(_plain(body="Important message"))
        assert "Important message" in result.body


# ── PII masking ───────────────────────────────────────────────────────────────


class TestMaskPII:
    def test_masks_chinese_mobile_phone(self):
        masked = mask_pii("Call me at 13812345678 please")
        assert "13812345678" not in masked
        assert "***" in masked

    def test_masks_credit_card_with_spaces(self):
        masked = mask_pii("Card: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in masked

    def test_masks_chinese_id_card(self):
        masked = mask_pii("ID: 110101199001011234")
        assert "110101199001011234" not in masked
        assert "***" in masked

    def test_normal_text_unchanged(self):
        text = "Hello, project deadline is 2026-06-01"
        assert mask_pii(text) == text

    def test_multiple_phones_all_masked(self):
        text = "Alice: 13811112222, Bob: 15933334444"
        masked = mask_pii(text)
        assert "13811112222" not in masked
        assert "15933334444" not in masked

"""Logging configuration with PII/body sanitization filter."""

import logging
import re

from email_agent.ingestion.parser import mask_pii

_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
_BODY_RE = re.compile(r'<email_content>.*?</email_content>', re.DOTALL)


class SanitizingFilter(logging.Filter):
    """Strips email body content, email addresses, and PII from log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._sanitize(str(record.msg))
        if isinstance(record.args, dict):
            record.args = {
                k: self._sanitize(v) if isinstance(v, str) else v
                for k, v in record.args.items()
            }
        elif record.args:
            record.args = tuple(
                self._sanitize(a) if isinstance(a, str) else a
                for a in record.args
            )
        return True

    @staticmethod
    def _sanitize(text: str) -> str:
        text = _BODY_RE.sub('<email_content>[REDACTED]</email_content>', text)
        text = _EMAIL_RE.sub('***@***.***', text)
        text = mask_pii(text)
        return text

"""Attachment security scanning: size check + ClamAV virus scan."""

import logging
from enum import Enum

logger = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class FileTooLargeError(Exception):
    pass


class MaliciousFileError(Exception):
    pass


class ScanResult(str, Enum):
    CLEAN = "clean"
    SKIPPED = "skipped"  # ClamAV unavailable; logged as warning


# ── Public API ────────────────────────────────────────────────────────────────


def check_size(data: bytes, max_bytes: int = _DEFAULT_MAX_BYTES) -> bool:
    if len(data) > max_bytes:
        raise FileTooLargeError(
            f"Attachment size {len(data):,} bytes exceeds limit of {max_bytes:,} bytes"
        )
    return True


def scan_attachment(data: bytes, filename: str) -> ScanResult:
    """Size-check then ClamAV scan. Raises on violation; returns ScanResult otherwise."""
    check_size(data)
    try:
        virus_name = _clamav_scan(data)
    except ConnectionError as exc:
        logger.warning("ClamAV unavailable (%s) — skipping scan for %r.", exc, filename)
        return ScanResult.SKIPPED
    if virus_name:
        raise MaliciousFileError(
            f"Malicious content detected in {filename!r}: {virus_name}"
        )
    return ScanResult.CLEAN


# ── Internal helpers ──────────────────────────────────────────────────────────


def _clamav_scan(data: bytes) -> str | None:
    """Return virus name if infected, None if clean. Raise ConnectionError if daemon unreachable."""
    import pyclamd  # deferred import so absence of daemon doesn't break module load

    try:
        cd = pyclamd.ClamdUnixSocket()
    except Exception:
        cd = pyclamd.ClamdNetworkSocket()

    result = cd.scan_stream(data)
    if result:
        # pyclamd returns {'stream': ('FOUND', 'Virus-Name')} or {'stream': ('ERROR', ...)}
        status, name = result.get("stream", (None, None))
        if status == "FOUND":
            return name
    return None

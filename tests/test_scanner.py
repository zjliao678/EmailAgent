"""Tests for email_agent.ingestion.scanner — written before implementation (TDD)."""

import logging

import pytest

from email_agent.ingestion.scanner import (
    FileTooLargeError,
    MaliciousFileError,
    ScanResult,
    check_size,
    scan_attachment,
)

_10MB = 10 * 1024 * 1024


# ── check_size ────────────────────────────────────────────────────────────────


class TestCheckSize:
    def test_small_file_passes(self):
        assert check_size(b"x" * (5 * 1024 * 1024)) is True

    def test_exactly_10mb_passes(self):
        assert check_size(b"x" * _10MB) is True

    def test_one_byte_over_limit_raises(self):
        with pytest.raises(FileTooLargeError):
            check_size(b"x" * (_10MB + 1))

    def test_empty_file_passes(self):
        assert check_size(b"") is True

    def test_custom_limit_respected(self):
        with pytest.raises(FileTooLargeError):
            check_size(b"x" * 101, max_bytes=100)


# ── scan_attachment ───────────────────────────────────────────────────────────


class TestScanAttachment:
    def test_clean_file_returns_clean(self, mocker):
        mocker.patch(
            "email_agent.ingestion.scanner._clamav_scan",
            return_value=None,  # no virus
        )
        assert scan_attachment(b"clean content", "doc.pdf") == ScanResult.CLEAN

    def test_infected_file_raises_malicious_error(self, mocker):
        mocker.patch(
            "email_agent.ingestion.scanner._clamav_scan",
            return_value="Eicar-Test-Signature",
        )
        with pytest.raises(MaliciousFileError) as exc_info:
            scan_attachment(b"X5O!P...", "malware.exe")
        assert "Eicar-Test-Signature" in str(exc_info.value)

    def test_size_check_runs_before_clamav(self, mocker):
        """ClamAV must never receive a file that exceeds the size limit."""
        mock_scan = mocker.patch("email_agent.ingestion.scanner._clamav_scan")
        with pytest.raises(FileTooLargeError):
            scan_attachment(b"x" * (_10MB + 1), "big.pdf")
        mock_scan.assert_not_called()

    def test_clamav_unavailable_returns_skipped_with_warning(self, mocker, caplog):
        mocker.patch(
            "email_agent.ingestion.scanner._clamav_scan",
            side_effect=ConnectionError("ClamAV daemon not running"),
        )
        with caplog.at_level(logging.WARNING):
            result = scan_attachment(b"some data", "file.pdf")
        assert result == ScanResult.SKIPPED
        assert "ClamAV" in caplog.text

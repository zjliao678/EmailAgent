"""Tests for email_agent.ingestion.imap_client — written before implementation (TDD)."""

import asyncio
from typing import Callable, Awaitable
from unittest.mock import AsyncMock, patch

import pytest

from email_agent.ingestion.imap_client import IMAPClient, IMAPConfig, SMTPClient, SMTPConfig


# ── Mock IMAP protocol ────────────────────────────────────────────────────────


class MockIMAPProtocol:
    """In-memory substitute for AioimaplibProtocol."""

    def __init__(self):
        self.connected = False
        self._push_queue: asyncio.Queue = asyncio.Queue()
        self._unseen: list[str] = []

    async def connect(self, host, port, user, password):
        self.connected = True

    async def select(self, mailbox):
        pass

    async def idle_start(self):
        pass

    async def wait_push(self, timeout=1740):
        return await self._push_queue.get()

    async def idle_done(self):
        pass

    async def search_unseen(self) -> list[str]:
        return list(self._unseen)

    async def fetch_by_uid(self, uid: str) -> bytes:
        return b"raw email bytes for uid=" + uid.encode()

    async def disconnect(self):
        self.connected = False


# ── IMAPClient tests ──────────────────────────────────────────────────────────


@pytest.fixture
def imap_config():
    return IMAPConfig(host="imap.qq.com", port=993, user="test@qq.com", password="authcode")


class TestIMAPClientConnect:
    async def test_connect_marks_protocol_connected(self, imap_config):
        proto = MockIMAPProtocol()
        client = IMAPClient(imap_config, protocol=proto)
        await client.connect()
        assert proto.connected is True

    async def test_disconnect_marks_protocol_disconnected(self, imap_config):
        proto = MockIMAPProtocol()
        client = IMAPClient(imap_config, protocol=proto)
        await client.connect()
        await client.disconnect()
        assert proto.connected is False

    async def test_fetch_email_returns_raw_bytes(self, imap_config):
        proto = MockIMAPProtocol()
        client = IMAPClient(imap_config, protocol=proto)
        await client.connect()
        data = await client.fetch_email("42")
        assert b"42" in data


class TestIMAPClientIDLE:
    async def test_exists_push_triggers_callback_with_unseen_uids(self, imap_config):
        proto = MockIMAPProtocol()
        proto._unseen = ["42", "43"]
        client = IMAPClient(imap_config, protocol=proto, reconnect_delay=0.01)
        await client.connect()

        received: list[str] = []

        async def on_new_email(uid: str):
            received.append(uid)

        async def inject():
            await asyncio.sleep(0.05)
            await proto._push_queue.put(["3 EXISTS"])
            await asyncio.sleep(0.2)  # give callback time to run

        try:
            await asyncio.wait_for(
                asyncio.gather(client.idle_listen(on_new_email), inject()),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass

        assert "42" in received
        assert "43" in received

    async def test_non_exists_push_does_not_trigger_callback(self, imap_config):
        proto = MockIMAPProtocol()
        proto._unseen = ["99"]
        client = IMAPClient(imap_config, protocol=proto, reconnect_delay=0.01)
        await client.connect()

        received: list[str] = []

        async def inject():
            await asyncio.sleep(0.05)
            await proto._push_queue.put(["OK Still here"])  # no EXISTS
            await asyncio.sleep(0.15)

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    client.idle_listen(lambda uid: received.append(uid) or asyncio.sleep(0)),
                    inject(),
                ),
                timeout=0.4,
            )
        except asyncio.TimeoutError:
            pass

        assert received == []

    async def test_reconnects_after_connection_error(self, imap_config):
        proto = MockIMAPProtocol()
        connect_calls = 0
        original_connect = proto.connect

        async def counting_connect(*args, **kwargs):
            nonlocal connect_calls
            connect_calls += 1
            await original_connect(*args, **kwargs)

        proto.connect = counting_connect

        call_n = 0

        async def flaky_wait_push(timeout=1740):
            nonlocal call_n
            call_n += 1
            if call_n == 1:
                raise ConnectionError("Connection dropped")
            await asyncio.sleep(100)  # hang until cancelled

        proto.wait_push = flaky_wait_push

        client = IMAPClient(imap_config, protocol=proto, reconnect_delay=0.05)
        await client.connect()  # connect_calls = 1

        try:
            await asyncio.wait_for(
                client.idle_listen(AsyncMock()),
                timeout=0.5,
            )
        except asyncio.TimeoutError:
            pass

        assert connect_calls >= 2  # at least one reconnect happened


# ── SMTPClient tests ──────────────────────────────────────────────────────────


@pytest.fixture
def smtp_config():
    return SMTPConfig(host="smtp.qq.com", port=587, user="test@qq.com", password="authcode")


class TestSMTPClient:
    async def test_send_invokes_aiosmtplib(self, smtp_config):
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            client = SMTPClient(smtp_config)
            await client.send(to="recipient@example.com", subject="Hello", body="Body text")
        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs.get("hostname") == "smtp.qq.com"
        assert kwargs.get("port") == 587
        assert kwargs.get("start_tls") is True

    async def test_send_uses_correct_credentials(self, smtp_config):
        with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
            client = SMTPClient(smtp_config)
            await client.send(to="r@e.com", subject="S", body="B")
        _, kwargs = mock_send.call_args
        assert kwargs.get("username") == "test@qq.com"
        assert kwargs.get("password") == "authcode"

"""QQ Mail IMAP (receive) and SMTP (send) clients with IDLE and auto-reconnect."""

import asyncio
import logging
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Awaitable, Callable, Optional
from typing import runtime_checkable, Protocol

import aiosmtplib

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT = 29 * 60  # 29 min — RFC 2177 recommends < 30 min


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class IMAPConfig:
    host: str
    port: int
    user: str
    password: str


@dataclass
class SMTPConfig:
    host: str
    port: int
    user: str
    password: str


# ── IMAP protocol abstraction (enables mock injection in tests) ───────────────


@runtime_checkable
class IMAPProtocol(Protocol):
    async def connect(self, host: str, port: int, user: str, password: str) -> None: ...
    async def select(self, mailbox: str) -> None: ...
    async def idle_start(self) -> None: ...
    async def wait_push(self, timeout: float = _IDLE_TIMEOUT) -> list[str]: ...
    async def idle_done(self) -> None: ...
    async def search_unseen(self) -> list[str]: ...
    async def fetch_by_uid(self, uid: str) -> bytes: ...
    async def disconnect(self) -> None: ...


class AioimaplibProtocol:
    """Production implementation backed by aioimaplib."""

    def __init__(self):
        self._client = None

    async def connect(self, host: str, port: int, user: str, password: str) -> None:
        import aioimaplib  # deferred so tests don't require the real library

        self._client = aioimaplib.IMAP4_SSL(host=host, port=port)
        await self._client.wait_hello_from_server()
        res, _ = await self._client.login(user, password)
        if res != "OK":
            raise ConnectionError(f"IMAP login failed: {res}")

    async def select(self, mailbox: str) -> None:
        res, _ = await self._client.select(mailbox)
        if res != "OK":
            raise ConnectionError(f"IMAP SELECT failed: {res}")

    async def idle_start(self) -> None:
        await self._client.idle_start()

    async def wait_push(self, timeout: float = _IDLE_TIMEOUT) -> list[str]:
        return await asyncio.wait_for(self._client.wait_server_push(), timeout=timeout)

    async def idle_done(self) -> None:
        await self._client.idle_done()

    async def search_unseen(self) -> list[str]:
        res, data = await self._client.uid("search", "UNSEEN")
        if res != "OK" or not data or not data[0]:
            return []
        raw = data[0].decode() if isinstance(data[0], bytes) else data[0]
        return [uid for uid in raw.split() if uid]

    async def fetch_by_uid(self, uid: str) -> bytes:
        res, data = await self._client.uid("fetch", uid, "(RFC822)")
        if res != "OK":
            raise RuntimeError(f"IMAP FETCH failed for UID {uid}: {res}")
        for item in data:
            if isinstance(item, bytes) and len(item) > 50:
                return item
        raise RuntimeError(f"Empty FETCH response for UID {uid}")

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.logout()
            except Exception:
                pass


# ── IMAPClient ────────────────────────────────────────────────────────────────


class IMAPClient:
    def __init__(
        self,
        config: IMAPConfig,
        protocol: Optional[IMAPProtocol] = None,
        reconnect_delay: float = 5.0,
    ):
        self._config = config
        self._protocol: IMAPProtocol = protocol or AioimaplibProtocol()
        self._reconnect_delay = reconnect_delay
        self._connected = False

    async def connect(self) -> None:
        await self._protocol.connect(
            self._config.host, self._config.port,
            self._config.user, self._config.password,
        )
        await self._protocol.select("INBOX")
        self._connected = True

    async def disconnect(self) -> None:
        await self._protocol.disconnect()
        self._connected = False

    async def fetch_email(self, uid: str) -> bytes:
        return await self._protocol.fetch_by_uid(uid)

    async def idle_listen(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Continuously listen for new emails via IMAP IDLE. Reconnects on error. Never returns."""
        while True:
            try:
                if not self._connected:
                    await self.connect()
                    # Drain any unseen emails that arrived before this session started
                    existing = await self._protocol.search_unseen()
                    logger.info("IMAP connected — %d unseen email(s) found on startup", len(existing))
                    for uid in existing:
                        try:
                            await callback(uid)
                        except Exception as exc:
                            logger.error("Callback error for UID %s: %s", uid, exc)
                logger.debug("Entering IMAP IDLE...")
                await self._idle_cycle(callback)
            except Exception as exc:
                logger.warning(
                    "IMAP error: %s — reconnecting in %.1f s", exc, self._reconnect_delay
                )
                self._connected = False
                await asyncio.sleep(self._reconnect_delay)

    async def _idle_cycle(self, callback: Callable[[str], Awaitable[None]]) -> None:
        await self._protocol.idle_start()
        try:
            push_lines = await self._protocol.wait_push(timeout=_IDLE_TIMEOUT)
        except asyncio.TimeoutError:
            await self._protocol.idle_done()
            return
        await self._protocol.idle_done()

        if any("EXISTS" in line for line in push_lines):
            for uid in await self._protocol.search_unseen():
                try:
                    await callback(uid)
                except Exception as exc:
                    logger.error("Callback error for UID %s: %s", uid, exc)


# ── SMTPClient ────────────────────────────────────────────────────────────────


class SMTPClient:
    def __init__(self, config: SMTPConfig):
        self._config = config

    async def send(self, *, to: str, subject: str, body: str, from_addr: str = "") -> None:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = from_addr or self._config.user
        msg["To"] = to
        msg["Subject"] = subject

        await aiosmtplib.send(
            msg,
            hostname=self._config.host,
            port=self._config.port,
            username=self._config.user,
            password=self._config.password,
            start_tls=True,
        )

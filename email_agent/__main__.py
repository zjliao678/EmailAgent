"""EmailAgent main entry point.

Usage:
    python -m email_agent
"""

import asyncio
import logging
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from email_agent.audit.repository import AuditRepository
from email_agent.config import get_settings
from email_agent.dispatcher import dispatch
from email_agent.graph.builder import build_graph
from email_agent.graph.state import GraphState
from email_agent.ingestion.dedup import EmailRepository
from email_agent.ingestion.imap_client import IMAPClient, IMAPConfig, SMTPClient, SMTPConfig
from email_agent.ingestion.parser import parse_email
from email_agent.logging_config import SanitizingFilter
from email_agent.models.base import Base

# ── Logging setup ─────────────────────────────────────────────────────────────

_handler = logging.StreamHandler(sys.stdout)
_handler.addFilter(SanitizingFilter())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[_handler],
)
logger = logging.getLogger(__name__)

# ── Database setup ────────────────────────────────────────────────────────────

_cfg = get_settings()
_engine = create_engine(_cfg.database_url, echo=False)
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)

# ── Graph ─────────────────────────────────────────────────────────────────────

_graph = build_graph()


# ── Email processor ───────────────────────────────────────────────────────────

async def process_uid(uid: str, imap_client: IMAPClient, smtp_client) -> None:
    session = _Session()
    try:
        raw = await imap_client.fetch_email(uid)
        parsed = parse_email(raw)

        repo = EmailRepository(session)
        if repo.is_duplicate(parsed.message_id):
            logger.info("skip duplicate message_id=%s", parsed.message_id)
            return

        email_db = repo.try_acquire(parsed.message_id)

        state = GraphState(
            email_id=str(email_db.id),
            message_id=parsed.message_id,
            sender=parsed.sender,
            subject=parsed.subject,
            body=f"<email_content>{parsed.body}</email_content>",
        )

        result_state = _graph.invoke(state)

        if result_state.get("injection_detected"):
            logger.warning("injection detected, skipping email_id=%s", state.email_id)
            repo.mark_failed(email_db.id, "injection_detected")
            session.commit()
            return

        audit = AuditRepository(session)
        dispatch_results = await dispatch(result_state, repo=repo, audit=audit, smtp_client=smtp_client)

        repo.mark_done(email_db.id)
        session.commit()

        for dr in dispatch_results:
            logger.info("  → intent=%-25s status=%s", dr.intent_name, dr.status)

    except Exception as exc:
        logger.exception("failed to process uid=%s: %s", uid, exc)
        session.rollback()
    finally:
        session.close()


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    cfg = get_settings()

    if not cfg.imap_user or not cfg.deepseek_api_key:
        logger.error(
            "Missing required config. Set IMAP_USER, IMAP_PASSWORD, "
            "SMTP_USER, SMTP_PASSWORD, DEEPSEEK_API_KEY in .env"
        )
        sys.exit(1)

    imap_client = IMAPClient(
        IMAPConfig(
            host=cfg.imap_host,
            port=cfg.imap_port,
            user=cfg.imap_user,
            password=cfg.imap_password,
        )
    )
    smtp_client = SMTPClient(
        SMTPConfig(
            host=cfg.smtp_host,
            port=cfg.smtp_port,
            user=cfg.smtp_user,
            password=cfg.smtp_password,
        )
    )

    logger.info("EmailAgent started — monitoring %s", cfg.imap_user)

    async def on_new_email(uid: str) -> None:
        await process_uid(uid, imap_client, smtp_client)

    await imap_client.idle_listen(on_new_email)


if __name__ == "__main__":
    asyncio.run(main())

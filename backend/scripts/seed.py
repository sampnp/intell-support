"""Seed a realistic Acme Cloud demo: 2 agents, 2 users, the sample KB, and 8 tickets covering every
status, with replies, internal notes, an automatic transition, a close and a reopen.

Run inside the backend container (from /app):

    docker compose run --rm backend python -m scripts.seed           # skips if already seeded
    docker compose run --rm backend python -m scripts.seed --reset   # wipe everything, reseed

Everything goes through the real services, so events, suggestions and vectors are genuine.
The password for every account is $SEED_PASSWORD (default: demo-password).
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.db import SessionLocal
from app.models.document import Document
from app.models.ticket import Ticket, TicketStatus
from app.models.user import Role, User
from app.schemas.tickets import CommentCreate, TicketCreate
from app.services import tickets as ticket_service
from app.services import workflow
from app.services.embeddings import Embedder, get_embedder
from app.services.ingestion import ingest_bytes
from app.services.suggestions import snapshot_suggestions
from app.services.vector_store import VectorStore, get_vector_store

logger = logging.getLogger("app.seed")

DEFAULT_PASSWORD = "demo-password"
# Present after a successful seed; a plain run that finds it changes nothing.
MARKER_EMAIL = "priya@acme-demo.com"

# key, email, full name, role
USERS = [
    ("priya", "priya@acme-demo.com", "Priya Shah", Role.agent),
    ("marcus", "marcus@acme-demo.com", "Marcus Lee", Role.agent),
    ("dana", "dana@acme-demo.com", "Dana Whitfield", Role.user),
    ("sam", "sam@acme-demo.com", "Sam Ortiz", Role.user),
]

# TRUNCATE does not fire the row-level append-only trigger on ticket_events.
RESET_SQL = (
    "TRUNCATE ticket_suggestions, ticket_events, ticket_comments, tickets, "
    "document_chunks, documents, users RESTART IDENTITY CASCADE"
)


@dataclass
class SeedResult:
    skipped: bool = False
    users: int = 0
    documents: int = 0
    tickets: int = 0
    logins: list[tuple[str, str]] = field(default_factory=list)


class _Tickets:
    """Small helpers so the ticket stories below read like what happens to each ticket."""

    def __init__(self, db: Session, embedder: Embedder, store: VectorStore) -> None:
        self.db = db
        self.embedder = embedder
        self.store = store

    def create(
        self, owner: User, title: str, description: str, category: str, priority: str
    ) -> Ticket:
        data = TicketCreate(
            title=title, description=description, category=category, priority=priority
        )
        return ticket_service.create_ticket(
            self.db,
            owner,
            data,
            suggest=lambda t: snapshot_suggestions(self.db, t, self.embedder, self.store),
        )

    def assign(self, ticket: Ticket, agent: User) -> None:
        ticket_service.assign_ticket(self.db, agent, ticket, agent.id)

    def move(self, ticket: Ticket, actor: User, status: str) -> None:
        workflow.change_status(self.db, actor, ticket, TicketStatus(status))

    def reply(self, ticket: Ticket, author: User, body: str, *, internal: bool = False) -> None:
        ticket_service.add_comment(
            self.db, author, ticket, CommentCreate(body=body, is_internal=internal)
        )


def _create_tickets(t: _Tickets, u: dict[str, User]) -> int:
    priya, marcus, dana, sam = u["priya"], u["marcus"], u["dana"], u["sam"]

    # 1. Billing: agent asks for details, owner replies -> back to in_progress automatically.
    charged = t.create(
        dana,
        "Charged twice for my Personal plan",
        "My card was charged 9.99 USD twice this month for the same Personal subscription. "
        "Can you refund the duplicate charge?",
        "billing",
        "high",
    )
    t.assign(charged, priya)
    t.move(charged, priya, "in_progress")
    t.reply(
        charged,
        priya,
        "Sorry about that! I can see two charges on the same day. Could you send me both "
        "receipt numbers so I can refund the duplicate?",
    )
    t.move(charged, priya, "waiting_for_user")
    t.reply(charged, dana, "Sure - the receipts are AC-10442 and AC-10443.")

    # 2. Sync: new and unassigned.
    t.create(
        dana,
        "Large video file stuck on 'Syncing'",
        "A 4 GB video in my Acme Cloud folder has been stuck on Syncing for two days. "
        "Other files sync fine.",
        "sync",
        "medium",
    )

    # 3. Account: urgent and unassigned.
    t.create(
        sam,
        "Locked out after too many login attempts",
        "I mistyped my password a few times and now my account says it is locked. "
        "I need access urgently for a client meeting.",
        "account",
        "urgent",
    )

    # 4. Sharing question answered and resolved.
    expiry = t.create(
        sam,
        "How do I make a share link expire?",
        "I want to share a folder with a contractor, but the link should stop working at the "
        "end of the month.",
        "other",
        "low",
    )
    t.assign(expiry, marcus)
    t.move(expiry, marcus, "in_progress")
    t.reply(
        expiry,
        marcus,
        "Open the share dialog, choose the link settings and set an expiry date. Expiry dates "
        "are available on the Personal and Business plans.",
    )
    t.move(expiry, marcus, "resolved")

    # 5. Sync conflicts: internal note, then waiting for the customer.
    conflicts = t.create(
        dana,
        "Conflicted copies keep appearing in our team folder",
        "Several files in our team folder now have 'conflicted copy' versions next to them. "
        "Which one should we keep?",
        "sync",
        "medium",
    )
    t.assign(conflicts, priya)
    t.move(conflicts, priya, "in_progress")
    t.reply(
        conflicts,
        priya,
        "Two people edited the same spreadsheet offline on Monday - that is the likely cause.",
        internal=True,
    )
    t.reply(
        conflicts,
        priya,
        "Conflicted copies appear when the same file changes in two places before it syncs. "
        "Which files are affected, and who usually edits them?",
    )
    t.move(conflicts, priya, "waiting_for_user")

    # 6. Data export: resolved by the agent, then closed by the owner.
    export = t.create(
        sam,
        "Need an export of all my data before cancelling",
        "I am cancelling my subscription and want a full copy of my files and version "
        "history first.",
        "account",
        "medium",
    )
    t.assign(export, marcus)
    t.move(export, marcus, "in_progress")
    t.reply(
        export,
        marcus,
        "Go to Settings > Account > Export data and include files and version history. We "
        "email you the download links when the export is ready; they stay valid for 7 days.",
    )
    t.move(export, marcus, "resolved")
    t.reply(export, sam, "Got the export, thanks!")
    t.move(export, sam, "closed")

    # 7. 2FA: resolved too early, reopened by the owner.
    twofa = t.create(
        dana,
        "Authenticator codes are rejected",
        "Since I moved to a new phone, every code from my authenticator app is rejected "
        "at sign-in.",
        "account",
        "high",
    )
    t.assign(twofa, priya)
    t.move(twofa, priya, "in_progress")
    t.reply(
        twofa,
        priya,
        "This usually means the phone's clock is out of sync. Turn on automatic date and time "
        "and try the newest code.",
    )
    t.move(twofa, priya, "resolved")
    t.reply(twofa, dana, "Automatic time is already on and the codes still fail.")
    t.move(twofa, dana, "open")

    # 8. Desktop install: in progress with an internal note.
    install = t.create(
        sam,
        "Desktop app won't install on Windows",
        "The installer closes immediately on my Windows 11 laptop without any error message.",
        "technical",
        "medium",
    )
    t.assign(install, priya)
    t.move(install, priya, "in_progress")
    t.reply(
        install,
        priya,
        "Customer is on a managed company laptop - the installer may be blocked by IT policy.",
        internal=True,
    )
    return 8


def seed(
    db: Session,
    embedder: Embedder,
    store: VectorStore,
    *,
    sample_kb_dir: str | Path,
    password: str,
    reset: bool = False,
) -> SeedResult:
    if reset:
        db.execute(text(RESET_SQL))
        db.commit()
        store.drop_collection()
        logger.info("seed_reset")

    if db.scalar(select(User).where(User.email == MARKER_EMAIL)) is not None:
        logger.info("seed_skipped reason=already_seeded")
        return SeedResult(skipped=True)

    users: dict[str, User] = {}
    for key, email, full_name, role in USERS:
        users[key] = User(
            email=email, full_name=full_name, password_hash=hash_password(password), role=role
        )
        db.add(users[key])
    db.commit()

    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    documents = [
        ingest_bytes(
            db,
            users["priya"],
            path.name,
            path.read_bytes(),
            max_bytes=max_bytes,
            embedder=embedder,
            store=store,
        )
        for path in sorted(Path(sample_kb_dir).iterdir())
        if path.is_file()
    ]

    tickets = _create_tickets(_Tickets(db, embedder, store), users)
    result = SeedResult(
        users=len(users),
        documents=len(documents),
        tickets=tickets,
        logins=[(email, role.value) for _, email, _, role in USERS],
    )
    logger.info(
        "seed_done users=%s documents=%s tickets=%s",
        result.users,
        result.documents,
        result.tickets,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the Acme Cloud demo data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="truncate ALL tables and recreate the Qdrant collection before seeding",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.log_level)
    password = os.environ.get("SEED_PASSWORD", DEFAULT_PASSWORD)
    if not 8 <= len(password.encode("utf-8")) <= 72:
        print("SEED_PASSWORD must be 8-72 bytes long.", file=sys.stderr)
        return 2

    with SessionLocal() as db:
        result = seed(
            db,
            get_embedder(),
            get_vector_store(),
            sample_kb_dir=settings.sample_kb_dir,
            password=password,
            reset=args.reset,
        )
        if result.skipped:
            print(
                f"Already seeded ({MARKER_EMAIL} exists) - nothing changed. "
                "Run with --reset to wipe everything and reseed."
            )
            return 0
        ready = db.scalar(
            select(func.count()).select_from(Document).where(Document.status == "ready")
        )

    print(
        f"Seeded {result.users} users, {result.documents} documents ({ready} ready) "
        f"and {result.tickets} tickets."
    )
    print(f"Password for every account: {password}")
    for email, role in result.logins:
        print(f"  {role:<5}  {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

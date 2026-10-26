"""Measure retrieval quality on the seeded Acme Cloud knowledge base (docs/PLAN.md §9).

Run inside the backend container, after the seed script:

    docker compose run --rm backend python -m scripts.eval_retrieval

For each mode (semantic, keyword) it asks 12 customer-style questions whose answer lives in a
known sample document and reports hit@3 (the right document is in the top 3) and MRR@10. It also
asks 4 off-topic questions and compares semantic top scores against RETRIEVAL_SCORE_THRESHOLD:
relevant questions should score above it, off-topic ones below it.

Searches run with threshold 0 so the raw ranking is measured; the threshold is applied afterwards.
"""

import sys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.logging import configure_logging
from app.db import SessionLocal
from app.models.document import Document, DocumentStatus
from app.services import retrieval
from app.services.embeddings import Embedder, get_embedder
from app.services.vector_store import VectorStore, get_vector_store

K = 10
MODES = ("semantic", "keyword")
SWEEP = (0.4, 0.5, 0.55, 0.6, 0.65, 0.7)

# Phrased the way a customer would ask, not copied from the documents.
LABELLED = [
    ("How do I install the Acme Cloud app on my Mac?", "getting-started-guide.pdf"),
    ("I signed up but never got the email to activate my account", "getting-started-guide.pdf"),
    ("My card was charged two times this month, can I get my money back?", "billing-refund-policy.pdf"),
    ("What happens to my files if I stop paying for my plan?", "billing-refund-policy.pdf"),
    ("Can I make a shared link stop working after next Friday?", "sharing-permissions-faq.pdf"),
    ("What can a viewer do compared to an editor on a shared folder?", "sharing-permissions-faq.pdf"),
    ("I lost my phone and can't get past the two-step verification", "account-login-troubleshooting.txt"),
    ("My account got locked after typing the wrong password too often", "account-login-troubleshooting.txt"),
    ("Why are there files called conflicted copy in my folder?", "sync-troubleshooting.txt"),
    ("My laptop disk is full, can I keep some folders only in the cloud?", "sync-troubleshooting.txt"),
    ("How long do you keep my files after I delete them?", "security-data-privacy.txt"),
    ("Can Acme employees read my documents?", "security-data-privacy.txt"),
]

# Nothing in the knowledge base answers these.
OFF_TOPIC = [
    "What is a good recipe for banana bread?",
    "How do I change the oil in my car?",
    "Who won the football World Cup in 2018?",
    "Translate good morning into Spanish",
]


class MissingDocuments(Exception):
    pass


@dataclass(frozen=True)
class QueryResult:
    query: str
    expected: str
    rank: int | None  # 1-based position of the expected document among the hits, if present
    top_score: float | None
    top_title: str | None


@dataclass
class Report:
    results: dict[str, list[QueryResult]] = field(default_factory=dict)
    off_topic_scores: list[float] = field(default_factory=list)


def hit_at_k(ranks: list[int | None], k: int = 3) -> float:
    if not ranks:
        return 0.0
    return sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1 / rank if rank else 0.0 for rank in ranks) / len(ranks)


def _document_ids(db: Session) -> dict[str, int]:
    wanted = {filename for _, filename in LABELLED}
    rows = db.execute(
        select(Document.filename, Document.id).where(
            Document.filename.in_(wanted), Document.status == DocumentStatus.ready
        )
    ).all()
    ids = {filename: document_id for filename, document_id in rows}
    missing = wanted - ids.keys()
    if missing:
        raise MissingDocuments(", ".join(sorted(missing)))
    return ids


def evaluate(
    db: Session, embedder: Embedder, store: VectorStore, modes: tuple[str, ...] = MODES
) -> Report:
    ids = _document_ids(db)
    report = Report()
    for mode in modes:
        rows = []
        for query, filename in LABELLED:
            result = retrieval.search(db, embedder, store, query, K, mode=mode, threshold=0.0)
            documents = [hit.document_id for hit in result.results]
            expected_id = ids[filename]
            rank = documents.index(expected_id) + 1 if expected_id in documents else None
            top = result.results[0] if result.results else None
            rows.append(
                QueryResult(
                    query=query,
                    expected=filename,
                    rank=rank,
                    top_score=top.score if top else None,
                    top_title=top.document_title if top else None,
                )
            )
        report.results[mode] = rows

    if "semantic" in modes:
        for query in OFF_TOPIC:
            result = retrieval.search(db, embedder, store, query, K, mode="semantic", threshold=0.0)
            report.off_topic_scores.append(result.results[0].score if result.results else 0.0)
    return report


def format_report(report: Report, threshold: float) -> str:
    lines = []
    for mode, rows in report.results.items():
        ranks = [row.rank for row in rows]
        lines.append(f"\n== {mode} ==")
        lines.append(f"{'rank':>4}  {'top':>6}  query")
        for row in rows:
            rank = str(row.rank) if row.rank else "-"
            score = f"{row.top_score:.3f}" if row.top_score is not None else "-"
            lines.append(f"{rank:>4}  {score:>6}  {row.query}")
        lines.append(f"hit@3 = {hit_at_k(ranks):.2f}   MRR@{K} = {mean_reciprocal_rank(ranks):.2f}")

    semantic = report.results.get("semantic")
    if semantic:
        relevant = [r.top_score for r in semantic if r.rank == 1 and r.top_score is not None]
        kept = sum(1 for r in semantic if r.top_score is not None and r.top_score >= threshold)
        leaked = sum(1 for score in report.off_topic_scores if score >= threshold)
        lines.append("\n== semantic score spread ==")
        if relevant:
            lines.append(
                f"relevant top-1 scores (rank 1 hits): min {min(relevant):.3f}, "
                f"max {max(relevant):.3f}"
            )
        lines.append(
            "off-topic top scores: "
            + ", ".join(f"{score:.3f}" for score in report.off_topic_scores)
        )
        lines.append(
            f"configured threshold {threshold}: {kept}/{len(semantic)} relevant questions "
            f"answered, {leaked}/{len(report.off_topic_scores)} off-topic questions wrongly answered"
        )
        lines.append("\nthreshold sweep (relevant answered / off-topic wrongly answered):")
        for candidate in SWEEP:
            kept = sum(1 for r in semantic if r.top_score is not None and r.top_score >= candidate)
            leaked = sum(1 for score in report.off_topic_scores if score >= candidate)
            lines.append(
                f"  {candidate:.2f}: {kept}/{len(semantic)}  {leaked}/{len(report.off_topic_scores)}"
            )
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    configure_logging("WARNING")  # keep the per-search log lines out of the report
    with SessionLocal() as db:
        try:
            report = evaluate(db, get_embedder(), get_vector_store())
        except MissingDocuments as exc:
            print(
                f"Sample documents not ingested: {exc}. Run the seed first:\n"
                "  docker compose run --rm backend python -m scripts.seed",
                file=sys.stderr,
            )
            return 2
    print(format_report(report, settings.retrieval_score_threshold))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

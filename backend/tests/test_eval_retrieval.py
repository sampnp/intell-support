import pytest

from scripts.eval_retrieval import (
    LABELLED,
    OFF_TOPIC,
    MissingDocuments,
    evaluate,
    format_report,
    hit_at_k,
    mean_reciprocal_rank,
)


@pytest.mark.parametrize(
    ("ranks", "expected"),
    [
        ([1, 2, 3], 1.0),
        ([1, 4, None, 3], 0.5),
        ([None, None], 0.0),
        ([], 0.0),
    ],
)
def test_hit_at_3(ranks, expected):
    assert hit_at_k(ranks, 3) == expected


@pytest.mark.parametrize(
    ("ranks", "expected"),
    [
        ([1, 1], 1.0),
        ([1, 2], 0.75),
        ([3, None], pytest.approx(1 / 6)),
        ([None], 0.0),
        ([], 0.0),
    ],
)
def test_mean_reciprocal_rank(ranks, expected):
    assert mean_reciprocal_rank(ranks) == expected


def test_evaluate_runs_every_query_in_both_modes(db_session, embedder, vector_store, indexed_kb):
    # A smoke test with the hashing fake: shape and bounds, not a quality claim.
    report = evaluate(db_session, embedder, vector_store)

    assert set(report.results) == {"semantic", "keyword"}
    for rows in report.results.values():
        assert [row.query for row in rows] == [query for query, _ in LABELLED]
        ranks = [row.rank for row in rows]
        assert 0.0 <= hit_at_k(ranks) <= 1.0
        assert 0.0 <= mean_reciprocal_rank(ranks) <= 1.0
    assert len(report.off_topic_scores) == len(OFF_TOPIC)

    text = format_report(report, threshold=0.5)
    assert "hit@3" in text and "semantic score spread" in text


def test_evaluate_needs_the_seeded_documents(db_session, embedder, vector_store):
    with pytest.raises(MissingDocuments):
        evaluate(db_session, embedder, vector_store)

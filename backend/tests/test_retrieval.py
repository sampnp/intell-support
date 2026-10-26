import logging

import pytest

from app.config import get_settings
from app.services.embeddings import get_embedder
from app.services.vector_store import get_vector_store
from tests.fakes import BrokenStore, FailingEmbedder

SEARCH = "/api/kb/search"

# query -> sample document (file stem) it must surface in the top 3, in both modes
KNOWN_QUERIES = [
    ("duplicate charges refunded", "billing-refund-policy"),
    ("authenticator codes", "account-login-troubleshooting"),
    ("conflicted copy", "sync-troubleshooting"),
    ("share link expiry", "sharing-permissions-faq"),
    ("export your data", "security-data-privacy"),
    ("installing the desktop app installer", "getting-started-guide"),
]
HIT_FIELDS = {"chunk_id", "document_id", "document_title", "page", "snippet", "score"}


def search(client, auth_headers, user, q, **params):
    return client.get(SEARCH, params={"q": q, **params}, headers=auth_headers(user))


@pytest.mark.parametrize("mode", ["semantic", "keyword"])
@pytest.mark.parametrize(("q", "expected"), KNOWN_QUERIES)
def test_known_queries_find_their_document(
    client, auth_headers, user, indexed_kb, mode, q, expected
):
    response = search(client, auth_headers, user, q, mode=mode)

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == mode
    assert body["insufficient"] is False
    assert 1 <= len(body["results"]) <= 3
    assert indexed_kb[expected].id in [hit["document_id"] for hit in body["results"]]


def test_auto_uses_semantic_when_available(client, auth_headers, user, indexed_kb):
    body = search(client, auth_headers, user, "conflicted copy").json()

    assert body["mode"] == "semantic"


def test_response_shape(client, auth_headers, user, indexed_kb):
    body = search(client, auth_headers, user, "duplicate charges refunded").json()

    assert set(body) == {"mode", "insufficient", "results"}
    hit = body["results"][0]
    assert set(hit) == HIT_FIELDS
    assert hit["document_title"] == "billing-refund-policy"
    assert hit["page"] in (1, 2)
    assert "Duplicate charges" in hit["snippet"] or "refund" in hit["snippet"].lower()
    assert 0 < hit["score"] <= 1


@pytest.mark.parametrize("mode", ["auto", "semantic", "keyword"])
def test_empty_kb_is_insufficient(client, auth_headers, user, mode):
    body = search(client, auth_headers, user, "duplicate charges refunded", mode=mode).json()

    assert body["insufficient"] is True
    assert body["results"] == []


@pytest.mark.parametrize("mode", ["semantic", "keyword"])
def test_nonsense_query_is_insufficient(client, auth_headers, user, indexed_kb, mode):
    body = search(client, auth_headers, user, "zxqvw blorft", mode=mode).json()

    assert body["insufficient"] is True
    assert body["results"] == []


def test_results_below_threshold_are_dropped(
    client, auth_headers, user, indexed_kb, monkeypatch
):
    monkeypatch.setattr(get_settings(), "retrieval_score_threshold", 0.99)

    body = search(client, auth_headers, user, "conflicted copy", mode="semantic").json()

    assert body["mode"] == "semantic"
    assert body["insufficient"] is True
    assert body["results"] == []


def test_semantic_scores_never_below_threshold(
    client, auth_headers, user, indexed_kb, retrieval_threshold
):
    body = search(client, auth_headers, user, "sync storage quota", mode="semantic", k=10).json()

    assert body["results"]
    assert all(hit["score"] >= retrieval_threshold for hit in body["results"])


@pytest.mark.parametrize("broken", ["store", "embedder"])
def test_auto_falls_back_to_keyword(
    app, client, auth_headers, user, indexed_kb, caplog, broken
):
    if broken == "store":
        app.dependency_overrides[get_vector_store] = lambda: BrokenStore()
    else:
        app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()

    with caplog.at_level(logging.WARNING, logger="app.retrieval"):
        response = search(client, auth_headers, user, "conflicted copy")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "keyword"
    assert body["insufficient"] is False
    assert indexed_kb["sync-troubleshooting"].id in [h["document_id"] for h in body["results"]]
    assert any("retrieval_fallback" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("broken", ["store", "embedder"])
def test_explicit_semantic_is_503_when_unavailable(
    app, client, auth_headers, user, indexed_kb, broken
):
    if broken == "store":
        app.dependency_overrides[get_vector_store] = lambda: BrokenStore()
    else:
        app.dependency_overrides[get_embedder] = lambda: FailingEmbedder()

    response = search(client, auth_headers, user, "conflicted copy", mode="semantic")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SEMANTIC_UNAVAILABLE"


def test_keyword_prefers_passages_with_all_words(client, auth_headers, user, indexed_kb):
    body = search(client, auth_headers, user, "conflicted copy", mode="keyword", k=10).json()

    assert body["results"]
    for hit in body["results"]:
        text = hit["snippet"].lower()
        assert "conflict" in text and "cop" in text


def test_keyword_falls_back_to_any_word_for_long_text(client, auth_headers, user, indexed_kb):
    q = "Ever since yesterday I keep getting a conflicted copy of my budget spreadsheet"

    body = search(client, auth_headers, user, q, mode="keyword").json()

    assert body["insufficient"] is False
    assert body["results"][0]["document_id"] == indexed_kb["sync-troubleshooting"].id


def test_keyword_mode_does_not_need_qdrant(app, client, auth_headers, user, indexed_kb):
    app.dependency_overrides[get_vector_store] = lambda: BrokenStore()

    body = search(client, auth_headers, user, "conflicted copy", mode="keyword").json()

    assert body["mode"] == "keyword"
    assert body["results"]


def test_k_limits_results(client, auth_headers, user, indexed_kb):
    one = search(client, auth_headers, user, "desktop app sync", k=1).json()
    default = search(client, auth_headers, user, "desktop app sync").json()

    assert len(one["results"]) == 1
    assert len(default["results"]) == 3


@pytest.mark.parametrize(
    "params",
    [
        {"q": "x", "k": 0},
        {"q": "x", "k": 11},
        {"q": "   "},
        {"q": ""},
        {"q": "x", "mode": "fuzzy"},
    ],
)
def test_search_validation(client, auth_headers, user, params):
    response = client.get(SEARCH, params=params, headers=auth_headers(user))

    assert response.status_code == 422


def test_search_requires_token(client):
    assert client.get(SEARCH, params={"q": "refund"}).status_code == 401


def test_search_is_logged(client, auth_headers, user, indexed_kb, caplog):
    with caplog.at_level(logging.INFO, logger="app.retrieval"):
        search(client, auth_headers, user, "conflicted copy")

    assert any(
        "retrieval mode=semantic requested=auto" in r.getMessage() for r in caplog.records
    )

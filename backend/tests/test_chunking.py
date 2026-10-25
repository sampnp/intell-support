import pytest

from app.services.chunking import (
    OVERLAP_CHARS,
    TARGET_CHARS,
    chunk_pages,
    chunk_text,
    normalize_paragraphs,
)

# Upper bound for a whole chunk: new text, plus the overlap tail and the space that joins them.
MAX_CHUNK = TARGET_CHARS + OVERLAP_CHARS + 1


def words(prefix: str, count: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(count))


def sentences(prefix: str, count: int) -> str:
    return " ".join(f"Sentence {prefix}{i} has a few ordinary words in it." for i in range(count))


def overlap_length(previous: str, current: str) -> int:
    """Length of the prefix of `current` that repeats the end of `previous` (0 if none)."""
    for k in range(min(len(current) - 1, OVERLAP_CHARS), 0, -1):
        if current[k] == " " and previous.endswith(current[:k]):
            return k
    return 0


def assert_well_formed(chunks: list[str]) -> None:
    assert chunks
    assert len(chunks[0]) <= TARGET_CHARS
    for previous, current in zip(chunks, chunks[1:]):
        assert len(current) <= MAX_CHUNK
        k = overlap_length(previous, current)
        assert k > 0, f"chunk does not start with the previous chunk's tail: {current[:60]!r}"
        assert len(current) - k - 1 <= TARGET_CHARS  # new text stays within the target


def test_short_text_is_one_chunk():
    assert chunk_text("Hello world. This is short.") == ["Hello world. This is short."]


def test_empty_text_has_no_chunks():
    assert chunk_text("") == []
    assert chunk_text(" \n\n \x00 \n") == []


def test_normalize_paragraphs():
    text = "  first   line\n continues here \n\n\n  second\x00 para  \n\n   \n"

    assert normalize_paragraphs(text) == ["first line continues here", "second para"]


def test_paragraphs_are_packed_with_overlap():
    paragraphs = [words(f"p{n}w", 30) for n in range(20)]  # ~200 chars each

    chunks = chunk_text("\n\n".join(paragraphs))

    assert len(chunks) > 1
    assert_well_formed(chunks)
    for paragraph in paragraphs:  # each fits in a chunk, so none is cut
        assert any(paragraph in chunk for chunk in chunks)


def test_long_paragraph_is_split_by_sentence():
    text = sentences("s", 60)  # one ~3000-char paragraph

    chunks = chunk_text(text)

    assert len(chunks) >= 4
    assert_well_formed(chunks)
    for i in range(60):
        sentence = f"Sentence s{i} has a few ordinary words in it."
        assert any(sentence in chunk for chunk in chunks)


def test_run_on_text_is_split_by_words():
    text = words("w", 600)  # no sentence breaks at all

    chunks = chunk_text(text)

    assert_well_formed(chunks)
    covered = set(" ".join(chunks).split())
    assert covered == set(text.split())


def test_giant_single_word_is_hard_split():
    chunks = chunk_text("x" * 2000)

    assert all(len(chunk) <= TARGET_CHARS for chunk in chunks)
    assert "".join(chunks) == "x" * 2000  # no space to overlap on, so no overlap


def test_chunk_pages_never_mixes_pages():
    pages = [
        (1, sentences("one", 40)),
        (2, "   \n\n  "),
        (3, sentences("three", 40)),
    ]

    chunks = chunk_pages(pages)

    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert {c.page_number for c in chunks} == {1, 3}
    for chunk in chunks:
        if chunk.page_number == 1:
            assert "three" not in chunk.text
        else:
            assert "one" not in chunk.text
    first_page_three = next(c for c in chunks if c.page_number == 3)
    assert first_page_three.text.startswith("Sentence three0 ")  # no overlap from page 1


def test_chunk_pages_keeps_null_page_for_txt():
    chunks = chunk_pages([(None, sentences("t", 50))])

    assert len(chunks) > 1
    assert all(c.page_number is None for c in chunks)


@pytest.mark.parametrize("target, overlap", [(200, 40), (500, 100)])
def test_custom_sizes(target, overlap):
    chunks = chunk_text(sentences("c", 50), target=target, overlap=overlap)

    assert len(chunks[0]) <= target
    assert all(len(c) <= target + overlap + 1 for c in chunks)

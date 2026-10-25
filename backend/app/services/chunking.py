"""Paragraph-aware chunking (docs/PLAN.md §9 step 3). Pure functions, no I/O.

Each page is split into paragraphs; paragraphs longer than the target are broken into
sentences, then word windows. Pieces are packed greedily into chunks of at most TARGET_CHARS
new characters, and every chunk after the first on a page starts with the last
~OVERLAP_CHARS of the previous one (cut at a word boundary). Chunks never span pages.
"""

import re
from dataclasses import dataclass

TARGET_CHARS = 800
OVERLAP_CHARS = 150

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ChunkData:
    chunk_index: int
    page_number: int | None
    text: str


def normalize_paragraphs(text: str) -> list[str]:
    """Split on blank lines, collapse whitespace inside paragraphs, drop NULs and empties."""
    text = text.replace("\x00", "")
    paragraphs = (" ".join(p.split()) for p in _PARAGRAPH_BREAK.split(text))
    return [p for p in paragraphs if p]


def _split_words(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for word in text.split(" "):
        while len(word) > limit:  # a single "word" longer than a chunk
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:limit])
            word = word[limit:]
        if not word:
            continue
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= limit:
            current = candidate
        else:
            pieces.append(current)
            current = word
    if current:
        pieces.append(current)
    return pieces


def _split_paragraph(paragraph: str, limit: int) -> list[str]:
    if len(paragraph) <= limit:
        return [paragraph]
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(paragraph):
        if len(sentence) <= limit:
            pieces.append(sentence)
        else:
            pieces.extend(_split_words(sentence, limit))
    return pieces


def _tail(text: str, overlap: int) -> str:
    """The last <= overlap characters of text, starting at a word boundary."""
    if len(text) <= overlap:
        return text
    tail = text[-overlap:]
    if not text[-overlap - 1].isspace():
        _, space, rest = tail.partition(" ")
        tail = rest if space else ""
    return tail.strip()


def chunk_text(text: str, target: int = TARGET_CHARS, overlap: int = OVERLAP_CHARS) -> list[str]:
    # (piece, separator to use before it when it isn't the first piece in a chunk)
    units: list[tuple[str, str]] = []
    for paragraph in normalize_paragraphs(text):
        for i, piece in enumerate(_split_paragraph(paragraph, target)):
            units.append((piece, " " if i else "\n\n"))

    packed: list[str] = []
    current = ""
    for piece, separator in units:
        candidate = f"{current}{separator}{piece}" if current else piece
        if len(candidate) <= target:
            current = candidate
        else:
            packed.append(current)
            current = piece
    if current:
        packed.append(current)

    chunks = packed[:1]
    for previous, body in zip(packed, packed[1:]):
        tail = _tail(previous, overlap)
        chunks.append(f"{tail} {body}" if tail else body)
    return chunks


def chunk_pages(
    pages: list[tuple[int | None, str]],
    target: int = TARGET_CHARS,
    overlap: int = OVERLAP_CHARS,
) -> list[ChunkData]:
    """Chunk each page separately; chunk_index runs across the whole document."""
    chunks: list[ChunkData] = []
    for page_number, text in pages:
        for body in chunk_text(text, target, overlap):
            chunks.append(ChunkData(len(chunks), page_number, body))
    return chunks

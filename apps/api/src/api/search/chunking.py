"""Markdown-aware chunking: split on headings, then paragraphs, then sentences.

Each chunk carries a heading breadcrumb ("Title › Section › Subsection") that is embedded
and BM25-indexed with it, so a chunk deep in a document still matches its section's topic.
Plain text is just markdown without headings.
"""

import hashlib
import math
import re
from collections.abc import Iterator
from dataclasses import dataclass

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
BREADCRUMB = " › "


def estimate_tokens(text: str) -> int:
    """About four characters per token; close enough for sizing chunks."""
    return math.ceil(len(text) / 4)


def embed_text(heading: str, content: str) -> str:
    """What the embedder (and later the reranker) sees for a chunk."""
    return f"{heading}\n\n{content}"


@dataclass(frozen=True)
class Chunk:
    ord: int
    heading: str
    content: str
    token_count: int
    content_hash: bytes  # chunks with the same hash share an embedding


@dataclass(frozen=True)
class _Block:
    text: str
    code: bool


def chunk_document(
    title: str, text: str, *, target_tokens: int, max_tokens: int, overlap_tokens: int
) -> list[Chunk]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    drafts: list[tuple[str, str]] = []
    for path, blocks in _sections(text):
        heading = BREADCRUMB.join([title, *path])
        pieces = [p for block in blocks for p in _split_block(block, max_tokens, target_tokens)]
        current: list[_Block] = []
        size = 0
        for piece in pieces:
            tokens = estimate_tokens(piece.text)
            if current and size + tokens > target_tokens:
                drafts.append((heading, _join(current)))
                tail = _overlap(current[-1], overlap_tokens)
                fits = tail is not None and estimate_tokens(tail.text) + tokens <= max_tokens
                current = [tail] if tail is not None and fits else []
                size = sum(estimate_tokens(b.text) for b in current)
            current.append(piece)
            size += tokens
        if current:
            drafts.append((heading, _join(current)))

    return [
        Chunk(
            ord=i,
            heading=heading,
            content=content,
            token_count=estimate_tokens(embed_text(heading, content)),
            content_hash=hashlib.sha256(embed_text(heading, content).encode()).digest(),
        )
        for i, (heading, content) in enumerate(drafts)
    ]


def _sections(text: str) -> Iterator[tuple[list[str], list[_Block]]]:
    """Yields (heading path, blocks) per section. Lines inside code fences are never headings."""
    path: list[tuple[int, str]] = []
    blocks: list[_Block] = []
    paragraph: list[str] = []
    fence: list[str] | None = None
    marker = ""

    def end_paragraph() -> None:
        if paragraph:
            blocks.append(_Block("\n".join(paragraph).strip(), code=False))
            paragraph.clear()

    for line in text.split("\n"):
        if fence is not None:
            fence.append(line)
            if line.strip() == marker:
                blocks.append(_Block("\n".join(fence), code=True))
                fence = None
            continue
        if match := FENCE.match(line):
            end_paragraph()
            fence, marker = [line], match.group(1)
        elif match := HEADING.match(line):
            end_paragraph()
            if blocks:
                yield [t for _, t in path], list(blocks)
                blocks.clear()
            level = len(match.group(1))
            path = [(lv, t) for lv, t in path if lv < level] + [(level, match.group(2))]
        elif line.strip():
            paragraph.append(line)
        else:
            end_paragraph()

    if fence is not None:  # unclosed fence: keep what there is
        blocks.append(_Block("\n".join(fence), code=True))
    end_paragraph()
    if blocks:
        yield [t for _, t in path], blocks


def _split_block(block: _Block, max_tokens: int, piece_tokens: int) -> list[_Block]:
    """Cuts a block over max_tokens into pieces of about piece_tokens: code by lines, prose by
    sentences, then by words. Pieces stay under the target so the overlap still fits."""
    if estimate_tokens(block.text) <= max_tokens:
        return [block]
    limit = piece_tokens * 4
    units = block.text.split("\n") if block.code else SENTENCE_BREAK.split(block.text)
    joiner = "\n" if block.code else " "
    pieces: list[str] = []
    current = ""
    for unit in (part for u in units for part in _hard_split(u, limit)):
        candidate = f"{current}{joiner}{unit}" if current else unit
        if len(candidate) > limit and current:
            pieces.append(current)
            current = unit
        else:
            current = candidate
    if current:
        pieces.append(current)
    return [_Block(p, block.code) for p in pieces]


def _hard_split(text: str, limit: int) -> list[str]:
    """A last resort for one sentence or line longer than a whole chunk: cut at whitespace."""
    parts = []
    while len(text) > limit:
        cut = text.rfind(" ", 0, limit)
        cut = cut if cut > 0 else limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    return [*parts, text] if text else parts


def _overlap(block: _Block, overlap_tokens: int) -> _Block | None:
    """The trailing sentences of a prose block, up to overlap_tokens, to repeat next chunk."""
    if block.code or overlap_tokens <= 0:
        return None
    tail: list[str] = []
    for sentence in reversed(SENTENCE_BREAK.split(block.text)):
        if estimate_tokens(" ".join([sentence, *tail])) > overlap_tokens:
            break
        tail.insert(0, sentence)
    return _Block(" ".join(tail), code=False) if tail else None


def _join(blocks: list[_Block]) -> str:
    return "\n\n".join(b.text for b in blocks)

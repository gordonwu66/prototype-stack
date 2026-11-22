from api.search.chunking import Chunk, chunk_document, estimate_tokens


def chunk(text: str, title: str = "Doc", **kw: int) -> list[Chunk]:
    sizes = {"target_tokens": 400, "max_tokens": 800, "overlap_tokens": 50, **kw}
    return chunk_document(title, text, **sizes)


def test_headings_become_breadcrumbs() -> None:
    text = "Intro line.\n\n# Install\n\nRun it.\n\n## Linux\n\nUse apt.\n\n# Usage\n\nCall it."
    assert [(c.heading, c.content) for c in chunk(text)] == [
        ("Doc", "Intro line."),
        ("Doc › Install", "Run it."),
        ("Doc › Install › Linux", "Use apt."),
        ("Doc › Usage", "Call it."),
    ]
    assert [c.ord for c in chunk(text)] == [0, 1, 2, 3]


def test_code_fences_are_never_headings_or_split_from_their_section() -> None:
    text = "# Setup\n\n```bash\n# not a heading\npip install x\n\nmore\n```\n\nAfter."
    [only] = chunk(text)
    assert only.heading == "Doc › Setup"
    assert "# not a heading" in only.content and only.content.endswith("After.")


def test_long_sections_split_under_the_max_with_overlap() -> None:
    sentences = [
        f"Sentence number {i} talks about topic {i % 7} in some detail." for i in range(80)
    ]
    chunks = chunk("# Long\n\n" + " ".join(sentences), max_tokens=200, target_tokens=150)
    assert len(chunks) > 3
    assert all(estimate_tokens(c.content) <= 200 for c in chunks)
    assert all(c.heading == "Doc › Long" for c in chunks)
    # Each chunk starts by repeating whole sentences from the end of the one before it.
    for previous, current in zip(chunks, chunks[1:], strict=False):
        text = current.content
        repeated = next(
            (text[:i] for i in range(len(text), 0, -1) if previous.content.endswith(text[:i])), ""
        )
        assert repeated.endswith("detail.") and 0 < estimate_tokens(repeated) <= 50


def test_a_huge_unbroken_line_is_hard_split() -> None:
    chunks = chunk("word " * 2000, max_tokens=100, target_tokens=80, overlap_tokens=0)
    assert all(estimate_tokens(c.content) <= 100 for c in chunks)
    assert sum(c.content.count("word") for c in chunks) == 2000


def test_hash_covers_heading_and_content() -> None:
    [a], [b], [c] = chunk("Same text."), chunk("Same text."), chunk("Same text.", title="Other")
    assert a.content_hash == b.content_hash != c.content_hash


def test_empty_and_heading_only_documents_have_no_chunks() -> None:
    assert chunk("") == []
    assert chunk("# Just a heading\n\n## And another") == []

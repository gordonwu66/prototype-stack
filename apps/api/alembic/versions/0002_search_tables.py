"""search tables: collections, documents, chunks, and the BM25 statistics

See docs/HYBRID_SEARCH.md. Everything after the tables is hand-written; autogenerate
doesn't see extensions, materialized views or functions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20 02:42:24.102813
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Created by infra/rds/bootstrap.sql on RDS (it needs rds_superuser); a no-op there.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("collections_pkey")),
        sa.UniqueConstraint("name", name=op.f("collections_name_key")),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('upload', 'url', 'note')", name=op.f("documents_source_check")
        ),
        sa.ForeignKeyConstraint(
            ["collection_id"],
            ["collections.id"],
            name=op.f("documents_collection_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("documents_pkey")),
    )
    op.create_index(
        "documents_collection_id_created_at_idx",
        "documents",
        ["collection_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("ord", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.LargeBinary(), nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english'::regconfig, heading || ' ' || content)", persisted=True
            ),
            nullable=False,
        ),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("chunks_document_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("chunks_pkey")),
    )
    # halfvec: half-precision pgvector. Added by SQL so this migration doesn't import app code.
    op.execute("ALTER TABLE chunks ADD COLUMN embedding halfvec(1024)")
    # The embedder's queue: chunks still waiting for a vector.
    op.create_index(
        "chunks_pending_idx",
        "chunks",
        ["id"],
        unique=False,
        postgresql_where=sa.text("embedding IS NULL"),
    )
    op.create_index("chunks_collection_id_idx", "chunks", ["collection_id"], unique=False)
    op.create_index("chunks_document_id_ord_idx", "chunks", ["document_id", "ord"], unique=False)
    op.create_index(
        "chunks_embedding_idx",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )
    op.create_index("chunks_tsv_idx", "chunks", ["tsv"], unique=False, postgresql_using="gin")

    # BM25 statistics, refreshed in the background (api/search/embedder.py). The ts_stat
    # query is schema-qualified: Postgres 17+ refreshes views with a restricted search_path.
    op.execute("""
        CREATE MATERIALIZED VIEW lexeme_df AS
          SELECT word AS lexeme, ndoc AS df FROM ts_stat('SELECT tsv FROM public.chunks')
    """)
    op.execute("CREATE UNIQUE INDEX lexeme_df_lexeme_idx ON lexeme_df (lexeme)")
    op.execute("""
        CREATE MATERIALIZED VIEW corpus_stats AS
          SELECT 1 AS id, count(*)::float8 AS n, coalesce(avg(token_count), 1)::float8 AS avgdl
          FROM chunks
    """)
    op.execute("CREATE UNIQUE INDEX corpus_stats_id_idx ON corpus_stats (id)")
    # Runs as the views' owner, so the API's role can refresh them without owning them.
    op.execute("""
        CREATE FUNCTION refresh_search_stats() RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
        BEGIN
          REFRESH MATERIALIZED VIEW CONCURRENTLY lexeme_df;
          REFRESH MATERIALIZED VIEW CONCURRENTLY corpus_stats;
        END $$
    """)
    # Free text to an OR of stemmed lexemes. Postgres does the quoting, so no user text is
    # ever parsed as tsquery syntax.
    op.execute("""
        CREATE FUNCTION or_tsquery(q text) RETURNS tsquery
        LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
          SELECT replace(plainto_tsquery('english', q)::text, ' & ', ' | ')::tsquery
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION or_tsquery(text)")
    op.execute("DROP FUNCTION refresh_search_stats()")
    op.execute("DROP MATERIALIZED VIEW corpus_stats")
    op.execute("DROP MATERIALIZED VIEW lexeme_df")
    op.drop_index("chunks_tsv_idx", table_name="chunks", postgresql_using="gin")
    op.drop_index(
        "chunks_embedding_idx",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )
    op.drop_index("chunks_pending_idx", table_name="chunks")
    op.drop_index("chunks_document_id_ord_idx", table_name="chunks")
    op.drop_index("chunks_collection_id_idx", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("documents_collection_id_created_at_idx", table_name="documents")
    op.drop_table("documents")
    op.drop_table("collections")

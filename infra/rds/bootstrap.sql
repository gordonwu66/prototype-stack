-- One-time setup of the app's database and roles on the RDS instance.
-- Run as the master user (the one created with the instance), connected to `postgres`.
-- Steps and the exact command: infra/rds/README.md.
--
--   app_owner  owns the database and schema; Alembic connects as it (DB_MIGRATION_USER)
--   app        what the API connects as (DB_USER): reads and writes rows, no schema changes
\set ON_ERROR_STOP on

CREATE ROLE app_owner LOGIN PASSWORD :'owner_password';
CREATE ROLE app LOGIN PASSWORD :'app_password';
-- Postgres 16+ only lets a role create a database owned by a role it can SET ROLE to.
GRANT app_owner TO CURRENT_USER;
CREATE DATABASE prototype OWNER app_owner;

\connect prototype
REVOKE ALL ON DATABASE prototype FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE prototype TO app;
GRANT USAGE ON SCHEMA public TO app;
-- Tables and sequences that app_owner's migrations create are readable and writable by app.
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app;
-- pgvector, for the search tables (docs/HYBRID_SEARCH.md). Needs rds_superuser.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS agents (
    key text PRIMARY KEY,
    name text NOT NULL,
    registration_reference text NOT NULL,
    description text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE IF NOT EXISTS candidate_metadata (
    id uuid PRIMARY KEY,
    agent_key text NOT NULL REFERENCES agents(key),
    source_directory text NOT NULL,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    validated_json jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (agent_key, source_sha256)
);

CREATE TABLE IF NOT EXISTS reports (
    id uuid PRIMARY KEY,
    agent_key text NOT NULL REFERENCES agents(key),
    generated_at timestamptz NOT NULL,
    source_directory text NOT NULL,
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    report_sha256 text NOT NULL UNIQUE CHECK (report_sha256 ~ '^[0-9a-f]{64}$'),
    validated_json jsonb NOT NULL,
    evidence_files jsonb NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS reports_agent_generated ON reports(agent_key, generated_at DESC, imported_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_jobs (
    id uuid PRIMARY KEY,
    reference text NOT NULL,
    status text NOT NULL DEFAULT 'QUEUED'
        CHECK (status IN ('QUEUED','RUNNING','COMPLETE','NEEDS_INFO','UNSUPPORTED','FAILED')),
    stage text NOT NULL DEFAULT 'QUEUED'
        CHECK (stage IN ('QUEUED','COLLECTING','VERIFYING','REPORTING','DONE')),
    message text NOT NULL DEFAULT '已加入评价队列，平台将自动选择适用方案。',
    candidate_key text,
    report_id uuid REFERENCES reports(id),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_owner text,
    lease_until timestamptz,
    fencing_token bigint NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    CHECK ((status = 'RUNNING' AND lease_owner IS NOT NULL AND lease_until IS NOT NULL)
        OR (status <> 'RUNNING' AND lease_owner IS NULL AND lease_until IS NULL)),
    CHECK ((status = 'QUEUED' AND stage = 'QUEUED')
        OR (status = 'RUNNING' AND stage IN ('COLLECTING','VERIFYING','REPORTING'))
        OR (status IN ('COMPLETE','NEEDS_INFO','UNSUPPORTED','FAILED') AND stage = 'DONE')),
    CHECK (status <> 'COMPLETE' OR report_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS evaluation_jobs_active_reference
    ON evaluation_jobs(reference) WHERE status IN ('QUEUED','RUNNING');
CREATE INDEX IF NOT EXISTS evaluation_jobs_claim ON evaluation_jobs(created_at, id)
    WHERE status IN ('QUEUED','RUNNING');

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id text PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('public-off','scoped','online')),
    scope_reference text,
    stopped boolean NOT NULL DEFAULT false,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    last_seen_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((mode='scoped' AND scope_reference IS NOT NULL)
        OR (mode<>'scoped' AND scope_reference IS NULL))
);

CREATE OR REPLACE FUNCTION reject_published_evidence_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Published evidence is append-only' USING ERRCODE = '55000';
END;
$$;
CREATE OR REPLACE TRIGGER reports_append_only
    BEFORE UPDATE OR DELETE ON reports FOR EACH ROW EXECUTE FUNCTION reject_published_evidence_change();
CREATE OR REPLACE TRIGGER reports_no_truncate
    BEFORE TRUNCATE ON reports FOR EACH STATEMENT EXECUTE FUNCTION reject_published_evidence_change();
CREATE OR REPLACE TRIGGER candidate_metadata_append_only
    BEFORE UPDATE OR DELETE ON candidate_metadata FOR EACH ROW EXECUTE FUNCTION reject_published_evidence_change();
CREATE OR REPLACE TRIGGER candidate_metadata_no_truncate
    BEFORE TRUNCATE ON candidate_metadata FOR EACH STATEMENT EXECUTE FUNCTION reject_published_evidence_change();

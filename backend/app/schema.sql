CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_subject TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    profile_image_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    owner_id UUID NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    source_record_id TEXT NOT NULL,
    document_name TEXT NOT NULL,

    publish BOOLEAN NOT NULL DEFAULT FALSE,
    overall_score NUMERIC(5,3) NOT NULL DEFAULT 0
        CHECK (overall_score >= 0 AND overall_score <= 1),

    summary TEXT NOT NULL DEFAULT '',
    recommendations TEXT[] NOT NULL DEFAULT '{}',

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT documents_owner_source_record_unique
        UNIQUE (owner_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS risk_domains (
    domain_id SMALLSERIAL PRIMARY KEY,
    domain_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS risk_fields (
    field_id BIGSERIAL PRIMARY KEY,

    domain_id SMALLINT NOT NULL
        REFERENCES risk_domains(domain_id)
        ON DELETE RESTRICT,

    raw_name TEXT NOT NULL,

    UNIQUE (domain_id, raw_name)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    document_id UUID NOT NULL
        REFERENCES documents(document_id)
        ON DELETE CASCADE,

    decision TEXT NOT NULL
        CHECK (decision IN ('Publish', 'Do Not Publish')),

    publish BOOLEAN NOT NULL DEFAULT FALSE,

    overall_score NUMERIC(5,3) NOT NULL
        CHECK (overall_score >= 0 AND overall_score <= 1),

    threshold NUMERIC(5,3) NOT NULL DEFAULT 0.700
        CHECK (threshold >= 0 AND threshold <= 1),

    summary TEXT NOT NULL DEFAULT '',
    recommendations TEXT[] NOT NULL DEFAULT '{}',
    raw_result JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS analysis_runs_document_id_idx
    ON analysis_runs(document_id);

CREATE TABLE IF NOT EXISTS analysis_domain_scores (
    analysis_id UUID NOT NULL
        REFERENCES analysis_runs(analysis_id)
        ON DELETE CASCADE,

    domain_id SMALLINT NOT NULL
        REFERENCES risk_domains(domain_id)
        ON DELETE RESTRICT,

    score NUMERIC(5,3) NOT NULL
        CHECK (score >= 0 AND score <= 1),

    PRIMARY KEY (analysis_id, domain_id)
);

CREATE TABLE IF NOT EXISTS analysis_field_assessments (
    assessment_id BIGSERIAL PRIMARY KEY,

    analysis_id UUID NOT NULL
        REFERENCES analysis_runs(analysis_id)
        ON DELETE CASCADE,

    field_id BIGINT NOT NULL
        REFERENCES risk_fields(field_id)
        ON DELETE RESTRICT,

    score NUMERIC(5,3) NOT NULL
        CHECK (score >= 0 AND score <= 1),

    reason TEXT,
    high_risk BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (analysis_id, field_id)
);

CREATE INDEX IF NOT EXISTS analysis_field_analysis_id_idx
    ON analysis_field_assessments(analysis_id);
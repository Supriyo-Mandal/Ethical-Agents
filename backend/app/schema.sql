CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_record_id TEXT UNIQUE NOT NULL,
    document_name TEXT NOT NULL,
    publish BOOLEAN NOT NULL DEFAULT FALSE,
    overall_score NUMERIC(5,3) NOT NULL DEFAULT 0 CHECK (overall_score >= 0 AND overall_score <= 1),
    summary TEXT NOT NULL DEFAULT '',
    recommendations TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS risk_domains (
    domain_id SMALLSERIAL PRIMARY KEY,
    domain_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS risk_fields (
    field_id BIGSERIAL PRIMARY KEY,
    domain_id SMALLINT NOT NULL REFERENCES risk_domains(domain_id) ON DELETE RESTRICT,
    raw_name TEXT NOT NULL,
    UNIQUE (domain_id, raw_name)
);

CREATE TABLE IF NOT EXISTS document_domain_scores (
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    domain_id SMALLINT NOT NULL REFERENCES risk_domains(domain_id) ON DELETE RESTRICT,
    score NUMERIC(5,3) NOT NULL CHECK (score >= 0 AND score <= 1),
    PRIMARY KEY (document_id, domain_id)
);

CREATE TABLE IF NOT EXISTS document_field_assessments (
    assessment_id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    field_id BIGINT NOT NULL REFERENCES risk_fields(field_id) ON DELETE RESTRICT,
    score NUMERIC(5,3) NOT NULL CHECK (score >= 0 AND score <= 1),
    reason TEXT,
    high_risk BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, field_id)
);
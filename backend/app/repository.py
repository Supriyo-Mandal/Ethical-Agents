from __future__ import annotations
from psycopg.types.json import Jsonb
from typing import Any
from .db import get_db_connection


def _upsert_domain(cur, domain_name: str) -> int:
    cur.execute(
        """
        INSERT INTO risk_domains (domain_name)
        VALUES (%s)
        ON CONFLICT (domain_name) DO NOTHING
        """,
        (domain_name,),
    )

    cur.execute(
        """
        SELECT domain_id
        FROM risk_domains
        WHERE domain_name = %s
        """,
        (domain_name,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Unable to find domain: {domain_name}")
    return int(row[0])


def _get_or_create_field(cur, domain_id: int, field_name: str) -> int:
    cur.execute(
        """
        INSERT INTO risk_fields (domain_id, raw_name)
        VALUES (%s, %s)
        ON CONFLICT (domain_id, raw_name) DO NOTHING
        """,
        (domain_id, field_name),
    )

    cur.execute(
        """
        SELECT field_id
        FROM risk_fields
        WHERE domain_id = %s AND raw_name = %s
        """,
        (domain_id, field_name),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Unable to find field: {field_name}")
    return int(row[0])


def save_document_to_postgres(document_name: str, result: dict[str, Any], user: dict[str, Any], source_record_id: str) -> str:
    if not isinstance(result, dict):
        raise TypeError("Result must be a dict")

    if not source_record_id:
        raise ValueError("source_record_id is required")

    metadata = result.get("metadata") or {}
    domain_scores = metadata.get("domain_scores") or {}
    fields = metadata.get("fields") or []

    publish = bool(result.get("publish", False))
    overall_score = float(result.get("overall_score", 0.0))
    summary = str(result.get("summary", "") or "")
    recommendations = result.get("recommendations") or []
    if isinstance(recommendations, str):
        recommendations = [recommendations]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            owner_id = _get_or_create_user(cur, user)

            cur.execute(
                """
                INSERT INTO documents (
                    owner_id,
                    source_record_id,
                    document_name,
                    publish,
                    overall_score,
                    summary,
                    recommendations
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (owner_id, source_record_id) DO UPDATE SET
                    owner_id = EXCLUDED.owner_id,
                    document_name = EXCLUDED.document_name,
                    publish = EXCLUDED.publish,
                    overall_score = EXCLUDED.overall_score,
                    summary = EXCLUDED.summary,
                    recommendations = EXCLUDED.recommendations,
                    updated_at = now()
                RETURNING document_id
                """,
                (
                    owner_id,
                    source_record_id,
                    document_name,
                    publish,
                    overall_score,
                    summary,
                    recommendations,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("Unable to create document record")
            document_id = row[0]

            cur.execute(
                """
                INSERT INTO analysis_runs (
                    document_id,
                    decision,
                    publish,
                    overall_score,
                    threshold,
                    summary,
                    recommendations,
                    raw_result
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING analysis_id
                """,
                (
                    document_id,
                    str(result.get("decision", "Do Not Publish")),
                    publish,
                    overall_score,
                    0.7,
                    summary,
                    recommendations,
                    Jsonb(result),
                ),
            )

            analysis_row = cur.fetchone()
            if not analysis_row:
                raise RuntimeError("Unable to create analysis record")

            analysis_id = analysis_row[0]

            for domain_name, score in domain_scores.items():
                if not domain_name:
                    continue
                
                domain_id = _upsert_domain(cur, str(domain_name))

                cur.execute(
                    """
                    INSERT INTO analysis_domain_scores (
                        analysis_id,
                        domain_id,
                        score
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (analysis_id, domain_id)
                    DO UPDATE SET score = EXCLUDED.score
                    """,
                    (
                        analysis_id,
                        domain_id,
                        float(score),
                    ),
                )
            for item in fields:
                if not isinstance(item, dict):
                    continue

                domain_name = (
                    item.get("agent")
                    or item.get("domain")
                    or item.get("risk_domain")
                    or item.get("category")
                )
                field_name = (
                    item.get("field")
                    or item.get("field_name")
                    or item.get("name")
                    or item.get("label")
                )

                if not domain_name or not field_name:
                    continue

                domain_id = _upsert_domain(cur, str(domain_name))
                field_id = _get_or_create_field(cur, domain_id, str(field_name))

                reason = item.get("reason") or item.get("rationale") or ""
                score = float(item.get("score", 0.0))
                high_risk = bool(item.get("high_risk") or item.get("is_high_risk") or score >= 0.7)

                cur.execute(
                    """
                    INSERT INTO analysis_field_assessments (
                        analysis_id,
                        field_id,
                        score,
                        reason,
                        high_risk
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (analysis_id, field_id) DO UPDATE SET
                        score = EXCLUDED.score,
                        reason = EXCLUDED.reason,
                        high_risk = EXCLUDED.high_risk
                    """,
                    (analysis_id, field_id, score, reason, high_risk),
                )

    return str(analysis_id)

def _get_or_create_user(cur, user: dict[str, Any]) -> str:
    google_subject = str(user.get("sub", "")).strip()
    email = str(user.get("email","")).strip()
    display_name = str(
        user.get("name")
        or user.get("email")
        or "Google User"
    ).strip()
    profile_image_url = user.get("picture")

    if not google_subject or not email:
        raise ValueError("Authenticated user is missing Google identity fields")

    cur.execute(
        """

        INSERT INTO users (
            google_subject,
            email,
            display_name,
            profile_image_url
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (google_subject)
        DO UPDATE SET
            email = EXCLUDED.email,
            display_name = EXCLUDED.display_name,
            profile_image_url = EXCLUDED.profile_image_url,
            updated_at = now()
        RETURNING user_id
        
        """,
        (
            google_subject,
            email,
            display_name,
            profile_image_url,
        ),
    )

    row = cur.fetchone()
    if not row:
        raise RuntimeError("Unable to create or find authenticated user")

    return str(row[0])

def get_user_history(user: dict[str, Any]):
    google_subject = str(user.get("sub", "")).strip()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.analysis_id,
                    d.document_name,
                    a.publish,
                    a.overall_score,
                    a.summary,
                    a.raw_result,
                    a.created_at
                FROM analysis_runs a
                JOIN documents d
                    ON d.document_id = a.document_id
                JOIN users u
                    ON u.user_id = d.owner_id
                WHERE u.google_subject = %s
                ORDER BY a.created_at DESC
                """,
                (google_subject,),
            )

            rows = cur.fetchall()

    history: list[dict[str, Any]] = []

    for (
        analysis_id,
        document_name,
        publish,
        overall_score,
        summary,
        raw_result,
        created_at,
    ) in rows:
        result = raw_result if isinstance(raw_result, dict) else {}

        history.append({
            "id": str(analysis_id),
            "analysis_id": str(analysis_id),
            "document_name": document_name,
            "publish": publish,
            "overall_score": float(overall_score),
            "summary": summary,
            "metadata": result.get("metadata", {}),
            "created_at": created_at.isoformat(),
        })

    return history

def get_user_analysis(
    analysis_id: str,
    user: dict[str, Any],
) -> dict[str, Any] | None:
    google_subject = str(user.get("sub", "")).strip()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    a.analysis_id,
                    d.document_name,
                    a.publish,
                    a.overall_score,
                    a.summary,
                    a.raw_result,
                    a.created_at
                FROM analysis_runs a
                JOIN documents d
                    ON d.document_id = a.document_id
                JOIN users u
                    ON u.user_id = d.owner_id
                WHERE a.analysis_id = %s
                    AND u.google_subject = %s
                """,
                (analysis_id, google_subject),
            )

            row = cur.fetchone()

    if not row:
        return None

    (
        stored_analysis_id,
        document_name,
        publish,
        overall_score,
        summary,
        raw_result,
        created_at,
    ) = row

    result = raw_result if isinstance(raw_result, dict) else {}

    return {
        **result,
        "id": str(stored_analysis_id),
        "analysis_id": str(stored_analysis_id),
        "document_name": document_name,
        "publish": publish,
        "overall_score": float(overall_score),
        "summary": summary,
        "created_at": created_at.isoformat(),
    }
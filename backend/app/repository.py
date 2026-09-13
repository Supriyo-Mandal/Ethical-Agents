from __future__ import annotations

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


def save_document_to_postgres(document_name: str, result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        raise TypeError("Result must be a dict")

    source_record_id = str(result.get("id") or result.get("document_id") or result.get("analysis_id") or document_name)
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
            cur.execute(
                """
                INSERT INTO documents (
                    source_record_id,
                    document_name,
                    publish,
                    overall_score,
                    summary,
                    recommendations
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_record_id) DO UPDATE SET
                    document_name = EXCLUDED.document_name,
                    publish = EXCLUDED.publish,
                    overall_score = EXCLUDED.overall_score,
                    summary = EXCLUDED.summary,
                    recommendations = EXCLUDED.recommendations,
                    updated_at = now()
                RETURNING document_id
                """,
                (
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

            for domain_name, score in domain_scores.items():
                if not domain_name:
                    continue
                domain_id = _upsert_domain(cur, str(domain_name))

                cur.execute(
                    """
                    INSERT INTO document_domain_scores (document_id, domain_id, score)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (document_id, domain_id) DO UPDATE SET
                        score = EXCLUDED.score
                    """,
                    (document_id, domain_id, float(score)),
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
                    or item.get("name")
                    or item.get("label")
                )

                if not domain_name or not field_name:
                    continue

                domain_id = _upsert_domain(cur, str(domain_name))
                field_id = _get_or_create_field(cur, domain_id, str(field_name))

                reason = item.get("reason") or item.get("rationale") or ""
                score = float(item.get("score", 0.0))
                high_risk = bool(item.get("high_risk") or item.get("is_high_risk") or False)

                cur.execute(
                    """
                    INSERT INTO document_field_assessments (
                        document_id,
                        field_id,
                        score,
                        reason,
                        high_risk
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (document_id, field_id) DO UPDATE SET
                        score = EXCLUDED.score,
                        reason = EXCLUDED.reason,
                        high_risk = EXCLUDED.high_risk
                    """,
                    (document_id, field_id, score, reason, high_risk),
                )

    return source_record_id
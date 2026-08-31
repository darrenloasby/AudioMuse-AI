# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

"""Durable, idempotent records for the staged analysis pipeline."""

import json


CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS analysis_stage_result (
    run_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    model_revision TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_ref TEXT,
    result_json TEXT,
    error TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (run_id, track_id, stage, model_revision)
)
"""

UPSERT_RESULT_SQL = """
INSERT INTO analysis_stage_result
    (run_id, track_id, stage, model_revision, status, artifact_ref, result_json, error)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (run_id, track_id, stage, model_revision) DO UPDATE SET
    status = EXCLUDED.status,
    artifact_ref = EXCLUDED.artifact_ref,
    result_json = EXCLUDED.result_json,
    error = EXCLUDED.error,
    updated_at = CURRENT_TIMESTAMP
"""


def ensure_schema(cur):
    cur.execute(CREATE_SCHEMA_SQL)


def save_result(run_id, track_id, stage, model_revision, *, status='SUCCESS',
                artifact_ref=None, result=None, error=None, conn=None):
    if conn is None:
        from database import get_db

        conn = get_db()
        owns_connection = True
    else:
        owns_connection = False
    cur = conn.cursor()
    try:
        cur.execute(
            UPSERT_RESULT_SQL,
            (
                str(run_id), str(track_id), str(stage), str(model_revision),
                str(status), artifact_ref,
                json.dumps(result) if result is not None else None,
                error,
            ),
        )
        if owns_connection:
            conn.commit()
    finally:
        cur.close()


def get_result(run_id, track_id, stage, model_revision, conn=None):
    if conn is None:
        from database import get_db

        conn = get_db()
        owns_connection = True
    else:
        owns_connection = False
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT status, artifact_ref, result_json, error "
            "FROM analysis_stage_result "
            "WHERE run_id = %s AND track_id = %s AND stage = %s AND model_revision = %s",
            (str(run_id), str(track_id), str(stage), str(model_revision)),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        if owns_connection:
            conn.commit()
    if row is None:
        return None
    try:
        result = json.loads(row[2]) if row[2] else None
    except (TypeError, ValueError):
        result = None
    return {'status': row[0], 'artifact_ref': row[1], 'result': result, 'error': row[3]}

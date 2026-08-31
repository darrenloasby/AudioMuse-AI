# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

import json
from unittest.mock import MagicMock

from taskqueue import sql


def test_insert_job_persists_a_required_capability_without_putting_it_in_payload():
    cur = MagicMock()
    cur.fetchone.return_value = ('task-1',)

    sql.insert_job(
        cur,
        'task-1',
        'analysis_stage',
        'tasks.analysis.stages.run_stage',
        required_capability='musicnn',
        kwargs={'track_id': 'track-1'},
    )

    statement, params = cur.execute.call_args.args
    assert 'required_capability' in statement
    assert params[-1] == 'musicnn'
    assert json.loads(params[5])['kwargs'] == {'track_id': 'track-1'}


def test_claim_predicate_requires_a_matching_worker_capability():
    assert 'required_capability IS NULL' in sql._CLAIM
    assert 'required_capability = ANY(%s)' in sql._CLAIM


def test_claim_exposes_the_required_capability_to_the_worker():
    row = (
        'task-1', 'analysis_stage', None, 'tasks.analysis.stages.run_stage',
        json.dumps({'args': [], 'kwargs': {}}), 0, 3, 'musicnn',
    )
    cur = MagicMock()
    cur.fetchone.return_value = row

    job = sql.claim(cur, 'default', 0.0, capabilities=('musicnn',))

    assert job['required_capability'] == 'musicnn'

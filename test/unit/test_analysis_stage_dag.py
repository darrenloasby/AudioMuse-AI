# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

from unittest.mock import MagicMock

import pytest

from tasks.analysis import stages


def test_stage_task_ids_are_stable_per_run_track_and_stage():
    assert stages.stage_task_id('run-1', 'track-1', 'musicnn') == stages.stage_task_id(
        'run-1', 'track-1', 'musicnn'
    )
    assert stages.stage_task_id('run-1', 'track-1', 'musicnn') != stages.stage_task_id(
        'run-1', 'track-1', 'clap_audio'
    )


def test_stage_order_only_routes_the_requested_stages():
    assert stages.next_stage('musicnn', ('musicnn', 'clap_audio', 'lyrics')) == 'clap_audio'
    assert stages.next_stage('lyrics', ('musicnn', 'clap_audio', 'lyrics')) is None


def test_stage_capabilities_keep_materialisation_general_and_ml_specialised():
    assert stages.required_capability('materialize') is None
    assert stages.required_capability('musicnn') == 'musicnn'
    assert stages.required_capability('clap_audio') == 'clap_audio'
    assert stages.required_capability('lyrics') == 'lyrics_asr'


def test_work_mask_maps_missing_features_to_independent_lanes():
    assert stages.stages_for_work_mask(0, True, True) == (
        'musicnn', 'clap_audio', 'lyrics'
    )
    assert stages.stages_for_work_mask(1, True, True) == ('base', 'clap_audio', 'lyrics')
    assert stages.stages_for_work_mask(1 | 2 | 4 | 8, True, True) == ()


def test_enqueue_track_pipeline_enqueues_only_the_first_stage(monkeypatch):
    queued = []
    monkeypatch.setattr(
        stages.taskqueue,
        'enqueue',
        lambda *args, **kwargs: queued.append((args, kwargs)) or kwargs['task_id'],
    )

    first = stages.enqueue_track_pipeline(
        {'Id': 'provider-1', 'Name': 'Track'},
        run_id='run-1',
        parent_task_id='root-1',
        server_id='server-1',
        stages_to_run=('musicnn', 'clap_audio'),
    )

    assert first == queued[0][1]['task_id']
    assert queued[0][0][0] == stages.STAGE_FUNCTION
    assert queued[0][1]['required_capability'] is None
    assert queued[0][1]['parent_task_id'] == 'root-1'
    assert queued[0][1]['details']['stage'] == 'materialize'


def test_stage_result_upsert_is_idempotent(monkeypatch):
    import tasks.analysis.stage_store as store
    import database

    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    monkeypatch.setattr(database, 'get_db', lambda: conn)

    store.save_result('run-1', 'track-1', 'musicnn', 'v1', result={'ok': True})
    store.save_result('run-1', 'track-1', 'musicnn', 'v1', result={'ok': True})

    assert cur.execute.call_count == 2
    assert all('ON CONFLICT' in call.args[0] for call in cur.execute.call_args_list)


def test_unknown_stage_is_refused_before_enqueue():
    with pytest.raises(ValueError):
        stages.required_capability('not-a-stage')


def test_completed_stage_is_persisted_and_its_artifact_is_handed_to_successor(monkeypatch):
    saved = []
    queued = []
    monkeypatch.setattr(stages, 'execute_stage', lambda _stage, _payload: {
        'artifact_ref': 'abc123.m4a',
        'catalog_item_id': 'fp_new-track',
    })
    monkeypatch.setattr(
        stages.stage_store,
        'save_result',
        lambda *args, **kwargs: saved.append((args, kwargs)),
    )
    monkeypatch.setattr(
        stages.taskqueue,
        'enqueue',
        lambda *args, **kwargs: queued.append((args, kwargs)) or kwargs['task_id'],
    )
    payload = {
        'schema': 1,
        'run_id': 'run-1',
        'track_id': 'track-1',
        'item': {'Id': 'track-1'},
        'parent_task_id': 'root-1',
        'server_id': 'server-1',
        'stages': ['musicnn', 'clap_audio'],
        'stage': 'musicnn',
        'model_revision': 'v1',
    }

    summary = stages.run_stage_task('musicnn', payload)

    assert saved[0][0][:4] == ('run-1', 'track-1', 'musicnn', 'v1')
    assert summary['next_task_id'] == queued[0][1]['task_id']
    next_payload = queued[0][1]['args'][1]
    assert next_payload['artifact_ref'] == 'abc123.m4a'
    assert next_payload['item']['_catalog_item_id'] == 'fp_new-track'

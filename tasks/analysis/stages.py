# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

"""Capability-routed track analysis stages.

This module owns the durable handoff contract. The legacy album task remains the
default until callers explicitly choose ``ANALYSIS_PIPELINE=staged``.
"""

import hashlib
import os
import shutil
import tempfile

import taskqueue

from . import stage_store


STAGE_FUNCTION = 'tasks.analysis.stages.run_stage_task'
STAGE_ORDER = ('materialize', 'musicnn', 'clap_audio', 'lyrics')
STAGE_CAPABILITIES = {
    'materialize': None,
    'musicnn': 'musicnn',
    'clap_audio': 'clap_audio',
    'lyrics': 'lyrics_asr',
    'base': None,
}


def stages_for_work_mask(work_mask, clap_available, lyrics_enabled):
    """Return only the feature stages still missing from one track."""
    from .helper import WORK_BASE, WORK_CLAP, WORK_LYRICS, WORK_MUSICNN

    stages = []
    needs_musicnn = not work_mask & WORK_MUSICNN
    if needs_musicnn:
        stages.append('musicnn')
    elif not work_mask & WORK_BASE:
        stages.append('base')
    if clap_available and not work_mask & WORK_CLAP:
        stages.append('clap_audio')
    if lyrics_enabled and not work_mask & WORK_LYRICS:
        stages.append('lyrics')
    return tuple(stages)


def stage_task_id(run_id, track_id, stage):
    key = f'{run_id}:{track_id}:{stage}'.encode('utf-8')
    return f'analysis-stage-{hashlib.sha256(key).hexdigest()[:32]}'


def required_capability(stage):
    try:
        return STAGE_CAPABILITIES[stage]
    except KeyError as exc:
        raise ValueError(f'unknown analysis stage: {stage!r}') from exc


def next_stage(stage, stages_to_run):
    stages_to_run = tuple(stages_to_run)
    try:
        index = stages_to_run.index(stage)
    except ValueError as exc:
        raise ValueError(f'{stage!r} is not in the requested stage list') from exc
    return stages_to_run[index + 1] if index + 1 < len(stages_to_run) else None


def _payload(item, run_id, parent_task_id, server_id, stages_to_run, stage,
             album_id=None, album_name=None, top_n_moods=5):
    return {
        'schema': 1,
        'run_id': str(run_id),
        'track_id': str(item.get('_catalog_item_id') or item.get('Id') or item.get('id')),
        'item': dict(item),
        'parent_task_id': str(parent_task_id),
        'server_id': server_id,
        'album_id': album_id,
        'album_name': album_name,
        'top_n_moods': top_n_moods,
        'stages': ['materialize', *stages_to_run],
        'stage': stage,
        'model_revision': 'audiomuse-v3.5',
    }


def enqueue_track_pipeline(item, *, run_id, parent_task_id, server_id,
                           stages_to_run=('musicnn', 'clap_audio', 'lyrics'),
                           album_id=None, album_name=None, top_n_moods=5,
                           conn=None):
    stages_to_run = tuple(stages_to_run)
    if not stages_to_run:
        raise ValueError('at least one analysis stage is required')
    for stage in stages_to_run:
        required_capability(stage)
    first = 'materialize'
    payload = _payload(
        item, run_id, parent_task_id, server_id, stages_to_run, first,
        album_id=album_id, album_name=album_name, top_n_moods=top_n_moods,
    )
    return taskqueue.enqueue(
        STAGE_FUNCTION,
        args=(first, payload),
        task_id=stage_task_id(run_id, payload['track_id'], first),
        task_type='analysis_stage',
        queue=taskqueue.QUEUE_DEFAULT,
        parent_task_id=parent_task_id,
        sub_type_identifier=payload['track_id'],
        details={'pipeline': 'staged', 'stage': first, 'track_id': payload['track_id']},
        required_capability=required_capability(first),
        conn=conn,
    )


def run_stage_task(stage, payload):
    """Execute one handoff and enqueue its successor.

    The concrete model handlers are deliberately injected through ``execute_stage``
    so the queue contract can be tested without loading librosa or ONNX.
    """
    required_capability(stage)
    if not isinstance(payload, dict) or payload.get('schema') != 1:
        raise ValueError('unsupported analysis stage payload')
    try:
        result = execute_stage(stage, payload) or {}
    except Exception as exc:
        stage_store.save_result(
            payload['run_id'], payload['track_id'], stage,
            payload.get('model_revision', 'unknown'),
            status='FAIL', error=str(exc),
        )
        raise
    stage_store.save_result(
        payload['run_id'], payload['track_id'], stage,
        payload.get('model_revision', 'unknown'),
        artifact_ref=result.get('artifact_ref'), result=result,
    )
    following = next_stage(stage, payload.get('stages') or ())
    next_task_id = None
    if following is not None:
        next_payload = dict(payload)
        next_payload['stage'] = following
        next_payload.update(result)
        if result.get('catalog_item_id'):
            next_payload['item'] = dict(next_payload.get('item') or {})
            next_payload['item']['_catalog_item_id'] = result['catalog_item_id']
        try:
            next_task_id = taskqueue.enqueue(
                STAGE_FUNCTION,
                args=(following, next_payload),
                task_id=stage_task_id(payload['run_id'], payload['track_id'], following),
                task_type='analysis_stage',
                queue=taskqueue.QUEUE_DEFAULT,
                parent_task_id=payload['parent_task_id'],
                sub_type_identifier=payload['track_id'],
                details={
                    'pipeline': 'staged', 'stage': following,
                    'track_id': payload['track_id'],
                },
                required_capability=required_capability(following),
            )
        except taskqueue.TaskNotQueued:
            next_task_id = stage_task_id(payload['run_id'], payload['track_id'], following)
    return {
        'pipeline': 'staged',
        'stage': stage,
        'track_id': payload['track_id'],
        'next_task_id': next_task_id,
        'final': following is None,
        'result': result or {},
    }


def execute_stage(stage, payload):
    if stage == 'materialize':
        return materialize_audio(payload)
    if stage == 'musicnn':
        return run_musicnn_stage(payload)
    if stage == 'clap_audio':
        return run_clap_stage(payload)
    if stage == 'lyrics':
        return run_lyrics_stage(payload)
    if stage == 'base':
        return run_base_stage(payload)
    required_capability(stage)


def _artifact_path(artifact_ref):
    from config import ANALYSIS_ARTIFACT_ROOT

    name = os.path.basename(str(artifact_ref or ''))
    if not name or name != str(artifact_ref) or name in ('.', '..'):
        raise ValueError('invalid staged audio artifact reference')
    return os.path.join(ANALYSIS_ARTIFACT_ROOT, name)


def materialize_audio(payload):
    from config import ANALYSIS_ARTIFACT_ROOT, TEMP_DIR
    from flask_app import app
    from tasks.mediaserver import context as server_context, download_track
    from .helper import _bind_server_context

    os.makedirs(ANALYSIS_ARTIFACT_ROOT, exist_ok=True)
    if payload.get('artifact_ref'):
        existing = _artifact_path(payload['artifact_ref'])
        if os.path.isfile(existing):
            return {'artifact_ref': payload['artifact_ref']}
    item = dict(payload.get('item') or {})
    temp_path = None
    try:
        with app.app_context(), server_context.use_server(
            _bind_server_context(payload.get('server_id'))
        ):
            temp_path = download_track(TEMP_DIR, item)
        if not temp_path or not os.path.isfile(temp_path):
            raise RuntimeError(f"could not materialise audio for {payload['track_id']}")
        digest = hashlib.sha256()
        with open(temp_path, 'rb') as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(chunk)
        suffix = os.path.splitext(temp_path)[1].lower() or '.audio'
        artifact_ref = digest.hexdigest() + suffix
        destination = _artifact_path(artifact_ref)
        if not os.path.exists(destination):
            shutil.copyfile(temp_path, destination)
        return {'artifact_ref': artifact_ref}
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def _working_copy(payload):
    from config import TEMP_DIR

    source = _artifact_path(payload.get('artifact_ref'))
    if not os.path.isfile(source):
        raise FileNotFoundError(f"staged audio artifact is missing: {payload.get('artifact_ref')}")
    suffix = os.path.splitext(source)[1] or '.audio'
    fd, path = tempfile.mkstemp(prefix='audiomuse-stage-', suffix=suffix, dir=TEMP_DIR)
    os.close(fd)
    shutil.copyfile(source, path)
    return path


def run_musicnn_stage(payload):
    from config import EMBEDDING_MODEL_PATH, PREDICTION_MODEL_PATH
    from tasks.analysis import helper as analysis_helper
    from tasks.analysis.album import _analyze_single_track
    from tasks.analysis.helper import TrackPlan
    from tasks.analysis.song import cleanup_musicnn_sessions
    from tasks.memory_utils import SessionRecycler
    from flask_app import app
    from tasks.mediaserver import context as server_context

    item = dict(payload.get('item') or {})
    path = _working_copy(payload)
    sessions = None
    pending_track_maps = {}
    try:
        with app.app_context(), server_context.use_server(
            analysis_helper._bind_server_context(payload.get('server_id'))
        ):
            analysis_helper.attach_catalog_item_ids([item], payload.get('server_id'))
            sessions, _fingerprint_index = _analyze_single_track(
                item,
                TrackPlan(True, False, False, False),
                f"{item.get('Name', payload['track_id'])} by {item.get('AlbumArtist', 'Unknown')}",
                payload.get('album_id'), payload.get('album_name') or '',
                payload.get('parent_task_id'), payload.get('top_n_moods') or 5,
                {'embedding': EMBEDDING_MODEL_PATH, 'prediction': PREDICTION_MODEL_PATH},
                SessionRecycler(recycle_interval=None), sessions, None, None, {},
                pending_track_maps,
            )
            analysis_helper.flush_pending_track_maps(
                pending_track_maps, [], payload.get('album_name') or ''
            )
        return {'catalog_item_id': item.get('_catalog_item_id')}
    finally:
        cleanup_musicnn_sessions(sessions, context='staged task')
        if os.path.exists(path):
            os.remove(path)


def run_clap_stage(payload):
    from flask_app import app
    from tasks.mediaserver import context as server_context
    from tasks.analysis import helper as analysis_helper
    from tasks.analysis.album import _stage_clap

    item = dict(payload.get('item') or {})
    track_id = str(item.get('_catalog_item_id') or payload['track_id'])
    path = _working_copy(payload)
    try:
        with app.app_context(), server_context.use_server(
            analysis_helper._bind_server_context(payload.get('server_id'))
        ):
            from tasks.clap_analyzer import get_or_cache_other_feature_text_embeddings

            labels = get_or_cache_other_feature_text_embeddings()
            embedding, saved = _stage_clap(
                path, track_id, item.get('Name', track_id), labels,
            )
        return {'catalog_item_id': track_id, 'saved': bool(saved), 'has_embedding': embedding is not None}
    finally:
        if os.path.exists(path):
            os.remove(path)


def run_lyrics_stage(payload):
    from flask_app import app
    from tasks.mediaserver import context as server_context
    from tasks.analysis import helper as analysis_helper
    from tasks.analysis.album import _stage_lyrics

    item = dict(payload.get('item') or {})
    path = _working_copy(payload)
    try:
        with app.app_context(), server_context.use_server(
            analysis_helper._bind_server_context(payload.get('server_id'))
        ):
            saved = _stage_lyrics(
                item, path, None, None,
                f"{item.get('Name', payload['track_id'])} by {item.get('AlbumArtist', 'Unknown')}",
                payload.get('top_moods') or {}, lambda: path,
            )
        return {'catalog_item_id': str(item.get('_catalog_item_id') or payload['track_id']), 'saved': bool(saved)}
    finally:
        if os.path.exists(path):
            os.remove(path)


def run_base_stage(payload):
    from flask_app import app
    from tasks.mediaserver import context as server_context
    from tasks.analysis import helper as analysis_helper
    from tasks.analysis.album import _stage_base
    from tasks.analysis.song import extract_basic_features, robust_load_audio_with_fallback

    item = dict(payload.get('item') or {})
    track_id = str(item.get('_catalog_item_id') or payload['track_id'])
    path = _working_copy(payload)
    try:
        with app.app_context(), server_context.use_server(
            analysis_helper._bind_server_context(payload.get('server_id'))
        ):
            audio, sample_rate = robust_load_audio_with_fallback(path, target_sr=16000)
            if audio is None or sample_rate is None:
                return {'catalog_item_id': track_id, 'saved': False}
            tempo, energy, musical_key, scale = extract_basic_features(audio, sample_rate)
            saved = _stage_base(
                path, track_id, item.get('Name', track_id),
                precomputed=(tempo, energy, musical_key, scale),
            )
        return {'catalog_item_id': track_id, 'saved': bool(saved)}
    finally:
        if os.path.exists(path):
            os.remove(path)

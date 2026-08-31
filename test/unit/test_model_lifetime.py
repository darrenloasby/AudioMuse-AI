# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

import sys
from unittest.mock import MagicMock


def test_worker_policy_releases_only_at_shutdown(monkeypatch):
    import config
    from tasks.model_lifecycle import should_release_models

    monkeypatch.setattr(config, 'MODEL_LIFETIME', 'worker')

    assert should_release_models('song') is False
    assert should_release_models('album') is False
    assert should_release_models('job') is False
    assert should_release_models('shutdown') is True


def test_album_policy_preserves_album_boundary_cleanup(monkeypatch):
    import config
    from tasks.model_lifecycle import should_release_models

    monkeypatch.setattr(config, 'MODEL_LIFETIME', 'album')

    assert should_release_models('song') is False
    assert should_release_models('album') is True
    assert should_release_models('job') is True
    assert should_release_models('shutdown') is True


def test_worker_job_cleanup_does_not_unload_resident_models(monkeypatch):
    import config
    from taskqueue.worker import Worker

    worker = Worker.__new__(Worker)
    monkeypatch.setattr(config, 'MODEL_LIFETIME', 'worker')
    monkeypatch.setattr(
        worker,
        '_unload_resident_models',
        lambda: (_ for _ in ()).throw(AssertionError('resident models were unloaded')),
    )

    worker._unload_job_models()


def test_worker_shutdown_still_releases_resident_models(monkeypatch):
    import config
    from taskqueue.worker import Worker

    worker = Worker.__new__(Worker)
    released = []
    memory_utils = MagicMock()
    monkeypatch.setitem(sys.modules, 'tasks.memory_utils', memory_utils)
    monkeypatch.setattr(config, 'MODEL_LIFETIME', 'worker')
    monkeypatch.setattr(worker, '_unload_resident_models', lambda: released.append(True) or True)

    worker.release_models_for_shutdown()

    assert released == [True]
    memory_utils.release_memory_to_os.assert_called_once()


def test_worker_policy_disables_periodic_session_recycling(monkeypatch):
    import config
    from tasks.memory_utils import SessionRecycler

    monkeypatch.setattr(config, 'MODEL_LIFETIME', 'worker')
    recycler = SessionRecycler(recycle_interval=None)
    recycler.increment()

    assert recycler.should_recycle() is False

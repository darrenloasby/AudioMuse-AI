# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[2]


def _load_assembler():
    path = ROOT / 'scripts' / 'standalone' / 'assemble_model.py'
    spec = importlib.util.spec_from_file_location('assemble_model_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_release_defaults_to_upstream_when_building_from_a_fork(monkeypatch):
    module = _load_assembler()
    monkeypatch.delenv('MODEL_REPO', raising=False)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'darrenloasby/AudioMuse-AI')
    assert module._model_repo() == 'NeptuneHub/AudioMuse-AI'


def test_model_release_repo_can_be_overridden_for_private_mirrors(monkeypatch):
    module = _load_assembler()
    monkeypatch.setenv('MODEL_REPO', 'example/model-mirror')
    assert module._model_repo() == 'example/model-mirror'

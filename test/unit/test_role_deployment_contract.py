# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path


ROOT = Path(__file__).parents[2]


def test_role_example_contains_only_non_secret_worker_contracts():
    text = (ROOT / 'deployment' / 'roles.example.env').read_text(encoding='utf-8')
    assert 'DATABASE_URL=provided-by-deployment-secret-store' in text
    assert 'AUDIOMUSE_CAPABILITIES=' not in text
    assert 'PASSWORD' not in text.upper()
    assert 'TOKEN' not in text.upper()
    assert 'GH_TOKEN' not in text
    assert 'API_KEY=' not in text


def test_role_example_selects_staged_pipeline_and_resident_models():
    text = (ROOT / 'deployment' / 'roles.example.env').read_text(encoding='utf-8')
    assert 'ANALYSIS_PIPELINE=staged' in text
    assert 'MODEL_LIFETIME=worker' in text
    assert 'MUSICNN_COREML_ENABLED=true' in text


def test_sync_document_keeps_deployment_values_out_of_the_source_fork():
    text = (ROOT / 'docs' / 'upstream-sync.md').read_text(encoding='utf-8')
    assert 'git fetch upstream --prune' in text
    assert 'infrastructure repository' in text
    assert 'Passage' in text

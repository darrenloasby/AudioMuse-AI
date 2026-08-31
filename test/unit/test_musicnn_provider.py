# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

from pathlib import Path

import config


def test_macos_builds_can_enable_coreml_for_musicnn():
    assert hasattr(config, 'MUSICNN_COREML_ENABLED')
    assert isinstance(config.MUSICNN_COREML_ENABLED, bool)


def test_macos_builds_can_enable_coreml_for_text_embeddings():
    assert hasattr(config, 'LYRICS_GTE_COREML_ENABLED')
    assert isinstance(config.LYRICS_GTE_COREML_ENABLED, bool)
    assert hasattr(config, 'CLAP_TEXT_COREML_ENABLED')
    assert isinstance(config.CLAP_TEXT_COREML_ENABLED, bool)


def test_musicnn_session_creation_passes_the_coreml_flag_to_provider_resolution():
    source = Path('tasks/analysis/song.py').read_text(encoding='utf-8')
    assert 'allow_coreml=MUSICNN_COREML_ENABLED' in source


def test_text_embedding_sessions_pass_coreml_flags_to_provider_resolution():
    gte_source = Path('lyrics/gte_onnx.py').read_text(encoding='utf-8')
    clap_source = Path('tasks/clap_analyzer.py').read_text(encoding='utf-8')
    assert 'allow_coreml=LYRICS_GTE_COREML_ENABLED' in gte_source
    assert 'allow_coreml=config.CLAP_TEXT_COREML_ENABLED' in clap_source


def test_coreml_provider_remains_optional_and_cpu_is_last_resort():
    source = Path('tasks/onnx_utils.py').read_text(encoding='utf-8')
    assert "'CoreMLExecutionProvider' in available" in source
    assert "providers=['CPUExecutionProvider']" in source

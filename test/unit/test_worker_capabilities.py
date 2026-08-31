# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

from worker_capabilities import configured_capabilities, parse_capabilities


def test_capability_parser_normalizes_deduplicates_and_discards_unknown_values():
    assert parse_capabilities(' musicnn, clap_audio, MUSICNN, not-a-role ') == (
        'clap_audio', 'musicnn'
    )


def test_empty_environment_means_legacy_workers_claim_only_unlabelled_work():
    assert configured_capabilities({}) == ()


def test_configured_capabilities_reads_a_mapping_without_touching_process_environment():
    assert configured_capabilities({'AUDIOMUSE_CAPABILITIES': 'lyrics_asr,musicnn'}) == (
        'lyrics_asr', 'musicnn'
    )

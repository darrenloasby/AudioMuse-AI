# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

"""Capability declarations used by the PostgreSQL task claim."""

import os


KNOWN_CAPABILITIES = frozenset({
    'musicnn',
    'clap_audio',
    'lyrics_asr',
    'lyrics_embedding',
    'persist',
})


def parse_capabilities(value):
    if not value:
        return ()
    if isinstance(value, str):
        values = value.split(',')
    else:
        values = value
    return tuple(sorted({
        str(item).strip().lower()
        for item in values
        if str(item).strip().lower() in KNOWN_CAPABILITIES
    }))


def configured_capabilities(environment=None):
    source = os.environ if environment is None else environment
    return parse_capabilities(source.get('AUDIOMUSE_CAPABILITIES', ''))

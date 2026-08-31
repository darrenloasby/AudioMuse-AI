# AudioMuse-AI - https://github.com/NeptuneHub/AudioMuse-AI
# Copyright (C) 2025 NeptuneHub
# SPDX-License-Identifier: AGPL-3.0-only

"""Small, dependency-light model lifetime policy helpers.

The worker imports this module only when it is about to clean up models, so the
policy can be used before the analysis stack is imported. ``idle`` currently
has the same retention behavior as ``worker``; an idle timer can evict it in a
later provider-specific change without changing callers.
"""

import config


MODEL_LIFETIMES = frozenset({'song', 'album', 'worker', 'idle'})
MODEL_SCOPES = frozenset({'song', 'album', 'job', 'shutdown'})


def configured_model_lifetime():
    value = str(getattr(config, 'MODEL_LIFETIME', 'song')).strip().lower()
    return value if value in MODEL_LIFETIMES else 'song'


def should_release_models(scope):
    if scope not in MODEL_SCOPES:
        raise ValueError(f'unknown model cleanup scope: {scope!r}')
    lifetime = configured_model_lifetime()
    if scope == 'shutdown':
        return True
    if lifetime in ('worker', 'idle'):
        return False
    if lifetime == 'album':
        return scope in ('album', 'job')
    return True

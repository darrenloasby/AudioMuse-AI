# Role-Based Analysis Lanes

## Goal

Split AudioMuse analysis into durable, capability-routed stages so the CT162
coordinator can feed specialised native workers on Xenon and Argon, while
preserving the current PostgreSQL queue, recovery semantics, database schema,
and upstream merge path.

## Repository strategy

The fork is `darrenloasby/AudioMuse-AI` with `origin` pointing at the fork and
`upstream` pointing at `NeptuneHub/AudioMuse-AI`. `main` tracks upstream. The
deployed v3.5-compatible line is kept on `compat/v3.5`; feature branches are
small enough to rebase or upstream independently:

1. `feature/model-session-lifecycle`
2. `feature/capability-aware-task-queue`
3. `feature/staged-analysis-dag`
4. `feature/coreml-musicnn`
5. `integration/role-lanes-v3.5`

Deployment files remain in a separate infrastructure repository. The source
fork contains code, migrations, tests, and provider adapters, but no Passage
secrets, launchd plists, host paths, or CT162-specific values.

## Runtime architecture

CT162 remains the only coordinator. It creates a durable task row per stage in
the existing PostgreSQL-backed queue. Each worker declares capabilities at
startup and claims only compatible tasks. Existing jobs with no capability
metadata continue to use the legacy queue path.

The analysis path becomes:

```text
coordinator -> materialise audio -> MusicNN -> CLAP audio
                                      |             |
                                      +-> base ----+
                                      |
                                      +-> lyrics/Parakeet -> GTE -> persist
```

Audio is stored as a content-addressed temporary artifact and passed between
hosts by reference. Embeddings and stage metadata are committed idempotently
to PostgreSQL. Audio bytes are never placed in queue payloads.

Each stage uses at-least-once delivery, a lease/heartbeat, retry, and a
dead-letter outcome. The result key is `(run_id, track_id, stage,
model_revision)`, so a reclaimed task can safely repeat a completed stage.

## Worker roles

Roles are capability declarations, not hard-coded host names. A deployment can
therefore scale lanes independently:

- Xenon: `clap_audio`, `musicnn`, and optionally `lyrics_asr`
- Argon: `musicnn`/`clap_audio` fallback and initial catch-up capacity
- Either host: `lyrics_embedding` when GTE is enabled
- CT162: coordinator, persistence, and recovery only

Parakeet remains accessed through the existing Xenon gateway on port 1234 and
is not pinned. A dedicated CLAP-text lane is intentionally excluded because
the text model is cached and infrequently used.

## Model lifetime and GPU work

Native workers gain an explicit model lifetime policy. The default remains the
current safe behavior. Role workers opt into worker-lifetime retention and only
evict on idle timeout, explicit shutdown, or memory pressure. The current
`PER_SONG_MODEL_RELOAD` setting remains accepted for compatibility.

CLAP already has a macOS CoreML path. MusicNN gets a separate CoreML provider
adapter behind a feature flag, with fixture-based numerical parity tests. GTE,
VAD, audio decoding, and basic scalar features remain CPU-bound initially
because their measured cost does not justify a remote or alternate embedding
model. Replacing GTE with Qwen or Jina is out of scope because it would require
re-embedding and migrating the existing lyric index.

## Compatibility and rollout

Schema changes are additive. Legacy album jobs remain runnable during rollout.
The staged path is shadow-tested, then canaried on a small track set before
being enabled for the full library. A deployment can revert to the previous
source commit and legacy queue path without data deletion.

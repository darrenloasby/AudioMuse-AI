# Role-Based Analysis Lanes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mergeable foundation for role-based AudioMuse analysis: resident native-worker model sessions, PostgreSQL capability routing, durable track stages, and a macOS CoreML MusicNN adapter.

**Architecture:** Preserve the existing PostgreSQL task queue and legacy album task. Add capability metadata and stage rows additively, then route only new staged tasks to workers that advertise matching capabilities. Keep deployment-specific host configuration outside the source fork.

**Tech Stack:** Python 3, PostgreSQL, psycopg2, pytest, ONNX Runtime, CoreML execution provider, existing AudioMuse taskqueue and native supervisors.

---

### Task 1: Resident model lifetime

**Files:**
- Modify: `config.py:1072-1080`
- Modify: `taskqueue/worker.py:460-601`
- Modify: `tasks/analysis/album.py:653-719`
- Modify: `tasks/analysis/song.py:567-579`
- Test: `test/unit/test_taskqueue_job_cleanup.py`
- Test: `test/unit/test_model_lifetime.py`

- [ ] **Step 1: Write the failing tests**

Add tests proving that `MODEL_LIFETIME=worker` skips job-end optional-model cleanup, that an explicit `album` policy still cleans up at album boundaries, and that `MODEL_LIFETIME=worker` does not disable cleanup after an explicit worker shutdown.

```python
def test_worker_lifetime_does_not_unload_at_job_end(monkeypatch):
    import config
    from taskqueue.worker import Worker

    worker = Worker.__new__(Worker)
    monkeypatch.setattr(config, "MODEL_LIFETIME", "worker")
    monkeypatch.setattr(worker, "_unload_resident_models", lambda: (_ for _ in ()).throw(AssertionError()))
    worker._unload_job_models()

def test_album_lifetime_keeps_existing_album_cleanup(monkeypatch):
    import config
    from tasks.analysis import album

    monkeypatch.setattr(config, "MODEL_LIFETIME", "album")
    assert album.should_release_models("album") is True

def test_worker_lifetime_releases_on_shutdown(monkeypatch):
    import config
    from taskqueue.worker import Worker

    worker = Worker.__new__(Worker)
    released = []
    monkeypatch.setattr(config, "MODEL_LIFETIME", "worker")
    monkeypatch.setattr(worker, "_unload_resident_models", lambda: released.append(True) or True)
    worker.release_models_for_shutdown()
    assert released == [True]
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run: `pytest -q test/unit/test_model_lifetime.py test/unit/test_taskqueue_job_cleanup.py`

Expected: FAIL because `MODEL_LIFETIME`, `should_release_models`, and `release_models_for_shutdown` do not yet exist.

- [ ] **Step 3: Implement the policy seam**

Add `MODEL_LIFETIME` in `config.py`, accepting `song`, `album`, `worker`, and `idle`, defaulting to `song` so existing installations retain their safety behavior. Add `should_release_models(scope)` in `tasks/analysis/album.py`. Change worker job-end cleanup to return immediately for `worker` and `idle`, and add `release_models_for_shutdown()` for the final process cleanup path. Guard album/finally cleanup with `should_release_models("album")`.

- [ ] **Step 4: Run the focused tests and the existing cleanup tests**

Run: `pytest -q test/unit/test_model_lifetime.py test/unit/test_taskqueue_job_cleanup.py`

Expected: all tests pass with zero failures.

- [ ] **Step 5: Commit the isolated change**

Run: `git add config.py taskqueue/worker.py tasks/analysis/album.py tasks/analysis/song.py test/unit/test_model_lifetime.py test/unit/test_taskqueue_job_cleanup.py && git commit -m "feat: support resident worker model lifetime"`

### Task 2: Capability-aware queue primitives

**Files:**
- Modify: `taskqueue/sql.py:80-100,328-449`
- Modify: `taskqueue/__init__.py:159-207`
- Modify: `taskqueue/worker.py:153-289`
- Create: `worker_capabilities.py`
- Test: `test/unit/test_worker_capabilities.py`
- Test: `test/unit/test_taskqueue_capabilities.py`

- [ ] **Step 1: Write tests for capability parsing and claim filtering**

Cover canonical capability parsing, the legacy empty-capability behavior, and the SQL claim parameters for a worker with `musicnn` but not `clap_audio`.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest -q test/unit/test_worker_capabilities.py test/unit/test_taskqueue_capabilities.py`

Expected: FAIL because the capability module, queue column, and filtered claim path do not exist.

- [ ] **Step 3: Add additive capability metadata**

Add `capabilities TEXT[]` to `task_status`, `capability` to the insert API, and a claim predicate that treats a NULL/empty capability as legacy-compatible while requiring membership for staged tasks. Parse `AUDIOMUSE_CAPABILITIES` once before heavy model imports. Include the claimed capability in the hydrated job dictionary.

- [ ] **Step 4: Verify queue tests and schema SQL tests**

Run: `pytest -q test/unit/test_worker_capabilities.py test/unit/test_taskqueue_capabilities.py test/unit/test_taskqueue_sql_vocabulary.py test/unit/test_taskqueue_ownership.py`

Expected: all tests pass with zero failures.

- [ ] **Step 5: Commit the queue primitive**

Run: `git add worker_capabilities.py taskqueue/sql.py taskqueue/__init__.py taskqueue/worker.py test/unit/test_worker_capabilities.py test/unit/test_taskqueue_capabilities.py && git commit -m "feat: route queued work by worker capability"`

### Task 3: Durable staged analysis

**Files:**
- Create: `tasks/analysis/stages.py`
- Modify: `tasks/analysis/main.py`
- Modify: `tasks/analysis/album.py`
- Modify: `database.py`
- Modify: `taskqueue/sql.py`
- Test: `test/unit/test_analysis_stage_dag.py`
- Test: `test/integration/test_analysis_staged_pipeline.py`

- [ ] **Step 1: Add failing tests for stage creation, idempotent completion, and recovery**

Test that one track produces the materialise/MusicNN/CLAP/lyrics/GTE/persist dependency chain, that a duplicate completion is ignored by the result key, and that an expired stage lease requeues only the unfinished stage.

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `pytest -q test/unit/test_analysis_stage_dag.py`

Expected: FAIL because the stage row and orchestration functions do not exist.

- [ ] **Step 3: Implement the stage schema and orchestration helpers**

Use additive tables/columns, content-addressed artifact references, JSON schema versioning, upserted stage results, and parent progress derived from stage state. Keep payloads free of audio bytes and credentials.

- [ ] **Step 4: Add the legacy fallback and staged canary switch**

Use `ANALYSIS_PIPELINE=legacy|staged|shadow`, defaulting to `legacy`. In `shadow`, materialise and execute stages but do not overwrite production embeddings; record timing and parity details instead.

- [ ] **Step 5: Run unit and integration coverage**

Run: `pytest -q test/unit/test_analysis_stage_dag.py test/unit/test_taskqueue_reclaim.py test/integration/test_analysis_staged_pipeline.py`

Expected: all tests pass with zero failures.

- [ ] **Step 6: Commit the staged pipeline**

Run: `git add tasks/analysis/stages.py tasks/analysis/main.py tasks/analysis/album.py database.py taskqueue/sql.py test/unit/test_analysis_stage_dag.py test/integration/test_analysis_staged_pipeline.py && git commit -m "feat: add durable staged analysis pipeline"`

### Task 4: MusicNN CoreML provider

**Files:**
- Modify: `tasks/onnx_utils.py`
- Modify: `tasks/analysis/song.py`
- Modify: `config.py`
- Modify: `requirements/macos.txt`
- Create: `test/unit/test_musicnn_provider.py`
- Create: `test/integration/test_musicnn_coreml_parity.py`

- [ ] **Step 1: Write provider-selection and parity tests**

Verify the provider is selected only when enabled on macOS, that non-macOS and disabled configurations retain the current ONNX path, and that fixture embeddings stay within the configured cosine tolerance.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest -q test/unit/test_musicnn_provider.py`

Expected: FAIL because the MusicNN provider flag and provider adapter do not exist.

- [ ] **Step 3: Implement the guarded provider adapter**

Reuse the existing provider resolver, keep static input shapes, expose a configuration flag, and fall back to the current ONNX provider when CoreML creation fails.

- [ ] **Step 4: Run provider and analysis regression tests**

Run: `pytest -q test/unit/test_musicnn_provider.py test/unit/test_musicnn_chunking.py test/unit/test_analysis.py`

Expected: all tests pass with zero failures.

- [ ] **Step 5: Commit the GPU adapter**

Run: `git add tasks/onnx_utils.py tasks/analysis/song.py config.py requirements/macos.txt test/unit/test_musicnn_provider.py test/integration/test_musicnn_coreml_parity.py && git commit -m "feat: add guarded CoreML MusicNN execution"`

### Task 5: Deployment contract and upstream-friendly integration

**Files:**
- Create: `deployment/roles.example.env`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/GPU.md`
- Create: `docs/upstream-sync.md`
- Test: `test/unit/test_role_deployment_contract.py`

- [ ] **Step 1: Write deployment contract tests**

Assert that the example declares capabilities without host secrets, that legacy mode remains the default, and that macOS workers can enable resident models and MusicNN CoreML independently.

- [ ] **Step 2: Run the tests and verify they fail**

Run: `pytest -q test/unit/test_role_deployment_contract.py`

Expected: FAIL because the role example and documentation contract do not exist.

- [ ] **Step 3: Add source-repo-safe deployment examples and upstream workflow documentation**

Document `origin`/`upstream`, branch order, rebase procedure, pinned release commits, rollback, and the separate infrastructure repository boundary. Do not include live CT162, Xenon, Argon, Passage, Neon, or token values.

- [ ] **Step 4: Run the complete relevant suite**

Run: `pytest -q test/unit/test_service_roles.py test/unit/test_worker_role_declaration.py test/unit/test_role_deployment_contract.py test/unit/test_taskqueue_job_cleanup.py test/unit/test_analysis_stage_dag.py test/unit/test_musicnn_provider.py`

Expected: all tests pass with zero failures.

- [ ] **Step 5: Commit the deployment contract**

Run: `git add deployment/roles.example.env docs/ARCHITECTURE.md docs/DEPLOYMENT.md docs/GPU.md docs/upstream-sync.md test/unit/test_role_deployment_contract.py && git commit -m "docs: define role lane deployment contract"`

### Task 6: Review, publish, and integrate

**Files:**
- Review all commits on `feature/model-session-lifecycle`, then create stacked branches from each completed commit.

- [ ] **Step 1: Run the full source test command**

Run: `pytest -q`

Expected: the repository’s full test suite exits 0. Any pre-existing failure is recorded with its exact test name and output before integration.

- [ ] **Step 2: Inspect the diff and branch ancestry**

Run: `git diff upstream/main...HEAD --stat && git log --oneline --decorate --graph --all -20`

Expected: source changes are confined to the planned files, no secrets are present, and each feature branch has a single focused purpose.

- [ ] **Step 3: Push the feature branches to the fork**

Run: `git push -u origin feature/model-session-lifecycle`

Repeat for each completed feature branch after its focused tests pass.

- [ ] **Step 4: Rebase before upstream comparison**

Run: `git fetch upstream --prune && git rebase upstream/main`

Expected: clean rebase or a small, reviewable conflict set; do not force-push without confirming the branch is not being used by another reviewer.

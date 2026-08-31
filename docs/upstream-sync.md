# Maintaining the AudioMuse fork

The fork keeps the upstream source and local deployment concerns separate.

```bash
cd /Users/dlo/Source/AudioMuse-AI
git fetch upstream --prune
git checkout main
git merge --ff-only upstream/main
git push origin main
```

Feature branches are based on the smallest required parent:

```text
main
└── feature/model-session-lifecycle
    └── feature/capability-aware-task-queue
        └── feature/staged-analysis-dag
            └── feature/coreml-musicnn
                └── integration/role-lanes-v3.5
```

Rebase a feature branch before opening or refreshing its pull request:

```bash
git fetch upstream --prune
git rebase upstream/main
git push --force-with-lease origin feature/model-session-lifecycle
```

The deployed v3.5 line should be pinned to a commit on `compat/v3.5`. The
infrastructure repository records that commit, the model manifest, and the
artifact checksum. It owns CT162 service definitions, Xenon/Argon launchd
configuration, Passage references, and Neon connection references. None of
those values belong in this source repository.

If an upstream update conflicts with the staged pipeline, merge the lifecycle
and queue branches first, then resolve the stage adapter separately. The legacy
album path remains the rollback target until a staged canary has passed.

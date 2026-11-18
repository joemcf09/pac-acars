# Deploy / rollback tests

End-to-end tests for the versioned-release deploy and automatic rollback, run in
an isolated throwaway directory. No systemd, no live server, no network: the real
production scripts (`deploy/update.sh`, `deploy/rollback.sh`, `deploy/lib.sh`) run
unchanged against a fake service (`svc.sh`) that launches the real app on a test
port, pointed at a throwaway data directory.

Three runners (each exits non-zero if any check fails; combined output is saved in
`RESULTS.txt`):

```bash
bash tests/deploy/run.sh            # baseline deploy/rollback behavior
bash tests/deploy/run_findings.sh   # regressions for the seven PR review findings
bash tests/deploy/run_migration.sh  # migration-script fixes (bulk data, checksums, local edits, disk, units)
bash tests/deploy/run_staging.sh    # production-equivalent: real venv, migrate, systemd unit
```

Migration-fix coverage (`run_migration.sh`):

- **M1** releases exclude bulk pilot data but keep the reference JSON.
- **M2** the pilot-data copy is checksum-verified for completeness (a dropped file aborts).
- **M3** locally-modified reference files (e.g. a hand-edited `missions.json`) are preserved and backed up, never silently overwritten.
- **M4** a disk-space preflight blocks a migration that would not fit.
- **M5** both service units use the release dir and shared-data config.

`run.sh` and `run_findings.sh` are hermetic (fast fake venv, container python, no
network). `run_staging.sh` builds a real virtualenv from the pinned requirements
(needs PyPI) and runs the app from the release's own venv python.

Review-finding coverage (`run_findings.sh`, plus `run_staging.sh` for #4):

- **F1** a failed `svc_restart` falls through to the health gate instead of a premature `set -e` exit.
- **F2** migration `--undo` verifies the copy-back before removing anything and never deletes the only good copy.
- **F3** backup failures block the deploy; archives are integrity-checked.
- **F4** production-equivalent staging: real venv install, migration, systemd unit validation.
- **F5** a failed first deploy (no previous release) leaves nothing broken wired up and recovers.
- **F6** manual rollback is transactional: a bad target restores the previous working release.
- **F7** the `deploy.py` SSH command returns the update's exit code, not the cleanup's.

What it proves:

- A first deploy comes up healthy (checked on `/up`).
- A second deploy advances `current`, records `previous`, and leaves all pilot
  data byte-for-byte intact (reservation, in-progress flight state, an upload, a
  sentinel).
- An additive DB migration (a new column) is tolerated, so a rollback to older
  code stays safe.
- A release that will not start is **automatically rolled back** to the previous
  release, and the site stays up.
- A dependency-install failure aborts the deploy **before** any switch, so the
  old release keeps serving with no downtime.
- A manual rollback to a specific earlier release works and preserves data.

`datatool.py` seeds and verifies the pilot data; `svc.sh` is the stand-in for
`systemctl ... pac`.

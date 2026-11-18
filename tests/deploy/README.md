# Deploy / rollback tests

End-to-end tests for the versioned-release deploy and automatic rollback, run in
an isolated throwaway directory. No systemd, no live server, no network: the real
production scripts (`deploy/update.sh`, `deploy/rollback.sh`, `deploy/lib.sh`) run
unchanged against a fake service (`svc.sh`) that launches the real app on a test
port, pointed at a throwaway data directory.

Run:

```bash
bash tests/deploy/run.sh
```

It exits non-zero if any check fails. Latest run output is saved in `RESULTS.txt`.

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

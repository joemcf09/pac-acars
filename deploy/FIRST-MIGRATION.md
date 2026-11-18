# First migration on Ubuntu 24.04

Use a maintenance window and a Bash shell as `pac`. Keep the console and sudo access available. Run each block only after the previous check succeeds. The reported 7.7 GB free and 3.6 GB of application data are planning figures. The backup, checkout and release all compete for space if they share a filesystem.

## 1. Capture the flat install

Confirm the downloaded Windows installation copy and verified database backup are accessible. Keep both. Make a private recovery directory **outside** the installation. Use a separately mounted private volume for SAVE if space is tight.

```bash
set -euo pipefail
umask 077
ROOT=/home/pac/pac-acars
SAVE=$(mktemp -d /home/pac/pac-migration.XXXXXXXX)
echo "$SAVE"   # record this path for recovery
cd "$ROOT"
git rev-parse HEAD > "$SAVE/flat-commit"
git status --short > "$SAVE/status"
git diff --binary HEAD -- > "$SAVE/working-tree.patch"
git diff --cached --binary > "$SAVE/index.patch"
cp -a data/missions.json "$SAVE/"
sha256sum data/missions.json > "$SAVE/missions.sha256"
cat "$SAVE/status"
for unit in pac pac-discord; do
  systemctl is-active "$unit"
  systemctl cat "$unit" > "$SAVE/$unit.effective"
  systemctl show "$unit" -p FragmentPath -p DropInPaths -p ExecStart -p WorkingDirectory
done
df -h "$ROOT" "$SAVE"
```

Confirm the missions edit and both deleted tracked client-build files appear as expected. Copy any additional untracked local configuration to SAVE and investigate other differences before proceeding. Record the effective flat data path, service users, environment files and hardening settings from the units privately. Confirm the running website uses `$ROOT/data/logbook.db`. Record representative pilot, reservation and recent flight details for later read-only comparison.

## 2. Obtain the reviewed scripts without changing branches

Copy the reviewed full commit SHA from PR #4. Use a separate shallow checkout and require the fetched tip to match that SHA. A changed tip requires review. The flat checkout, index, local missions and deleted files stay in place.

```bash
read -rp 'Reviewed PR #4 commit SHA: ' SHA
git clone --depth 1 --single-branch -b acars-1.2-migration-fixes \
  https://github.com/joemcf09/pac-acars.git "$SAVE/reviewed"
test "$(git -C "$SAVE/reviewed" rev-parse HEAD)" = "$SHA"
test -x "$ROOT/.venv/bin/python"
grep -n PAC_DATA_DIR "$ROOT/app.py"
diff -u "$ROOT/app.py" "$SAVE/reviewed/app.py" || true
```

Verify the flat application already supports shared pilot data and release-local reference files. Review any runtime differences affecting this split before proceeding. The initial release copies the installed application. The new migration also needs its matching library and units. Save the old deployment directory if present, then overlay only the reviewed deployment files. Stop on unexpected local edits under deploy. Confirm no existing shared, releases, current or previous paths (including dangling links), alternate data mounts or deployment-path overrides. Confirm python3-venv, SQLite CLI, pip package access and systemd tools are available before downtime.

```bash
if test -e deploy; then cp -a deploy "$SAVE/flat-deploy"; fi
mkdir -p deploy
cp -a "$SAVE/reviewed/deploy/." deploy/
MIG="$ROOT/deploy/migrate_to_releases.sh"
export PAC_DEPLOY_ROOT="$ROOT"
unset PAC_DISK_AVAIL_KB PAC_VENV_MARGIN_KB PAC_DISK_SAFETY_KB PAC_VENV_BUILD PAC_SHARED_DATA PAC_RELEASES_DIR
bash "$MIG" --dry-run
```

Review the pilot, release, reference backup, venv and safety budgets. Published downloads under static belong in the release. Allow additional space for a final backup. A dry run while services are active is provisional.

## 3. Freeze writes and take the final backup

Close public access using the site's maintenance procedure and pause scheduled writers, imports and deployments. If `pac-missions.timer` exists, stop it and wait for `pac-missions.service` to become inactive. Stop the bot first. Keep ingress closed until validation finishes.

```bash
sudo systemctl stop pac-missions.timer
sudo systemctl stop pac-missions.service
sudo systemctl stop pac-discord.service pac.service
for unit in pac pac-discord pac-missions; do
  test "$(systemctl show "$unit" -p ActiveState --value)" = inactive
done
test -s data/logbook.db
sqlite3 -readonly data/logbook.db ".backup '$SAVE/logbook-final.db'"
test "$(sqlite3 -readonly "$SAVE/logbook-final.db" 'PRAGMA integrity_check;')" = ok
sha256sum "$SAVE/logbook-final.db" > "$SAVE/logbook-final.sha256"
sha256sum -c "$SAVE/missions.sha256"
bash "$MIG" --dry-run
```

Transfer the final backup and checksum privately off-host and verify the digest there. Other pilot files and databases are covered by the stopped migration copy and retained flat tree. If the backup or second preflight fails, resume the original units using the recovery instructions.

## 4. Apply and inspect before starting services

```bash
bash "$MIG" --apply
REL=$(readlink -e current)
test "$(dirname "$REL")" = "$ROOT/releases"
test -x "$REL/.venv/bin/python"
cmp "$SAVE/missions.json" "$REL/data/missions.json"
cmp "$SAVE/missions.json" "$ROOT"/reference-local-backup-*/missions.json
cmp data/logbook.db shared/data/logbook.db
test "$(sqlite3 -readonly shared/data/logbook.db 'PRAGMA integrity_check;')" = ok
test ! -e "$REL/data/logbook.db"
```

Require the migration's checksum verification to report zero missing and corrupt pilot files. Keep the flat venv and all original data in place.

## 5. Switch the website, bot and mission worker units and verify

Use named drop-ins so existing unit files, credentials and overrides remain available. Compare the two reviewed units in current/deploy with the effective unit snapshots. Reconcile any custom launcher arguments, extra processes or sandbox paths before continuing. These commands assume the existing services run app.py and discord_bot.py as pac. Verify that no later drop-in or EnvironmentFile overrides the selected values.

```bash
for unit in pac pac-discord; do
  entry=app.py
  if test "$unit" = pac-discord; then entry=discord_bot.py; fi
  dir=/etc/systemd/system/$unit.service.d
  file=$dir/99-pac-first-migration.conf
  test ! -e "$file" && test ! -L "$file" || exit 1
  sudo mkdir -p "$dir"
  sudo tee "$file" >/dev/null <<UNIT
[Service]
WorkingDirectory=$ROOT/current
ExecStart=
ExecStart=$ROOT/current/.venv/bin/python $entry
Environment=PAC_DATA_DIR=$ROOT/shared/data
ReadWritePaths=$ROOT/shared/data
UNIT
done
sudo systemctl daemon-reload
sudo systemd-analyze verify pac.service pac-discord.service
systemctl show pac pac-discord -p WorkingDirectory -p ExecStart -p ReadWritePaths
```

If the mission timer exists, give its worker the same release and shared data paths. The worker's lock and status files must use `PAC_DATA_DIR` as well as its database connection.

```bash
dir=/etc/systemd/system/pac-missions.service.d
file=$dir/99-pac-first-migration.conf
test ! -e "$file" && test ! -L "$file" || exit 1
sudo mkdir -p "$dir"
sudo tee "$file" >/dev/null <<UNIT
[Service]
WorkingDirectory=$ROOT/current
ExecStart=
ExecStart=$ROOT/current/.venv/bin/python mission_worker.py
Environment=PAC_DATA_DIR=$ROOT/shared/data
ReadWritePaths=$ROOT/shared/data
UNIT
sudo systemctl daemon-reload
sudo systemd-analyze verify pac-missions.service
systemctl show pac-missions -p WorkingDirectory -p ExecStart -p Environment -p ReadWritePaths
```

Start the website and bot. Keep the mission timer stopped until the first updated release containing the `PAC_DATA_DIR` worker fix has deployed, then start it and verify the shared worker status file advances after a timer run.

```bash
sudo systemctl start pac
curl --retry 15 --retry-connrefused --retry-delay 2 -fsS http://127.0.0.1:5050/up
sudo systemctl start pac-discord
for unit in pac pac-discord; do
  systemctl is-active "$unit"
  pid=$(systemctl show "$unit" -p MainPID --value)
  test "$(sudo readlink -e "/proc/$pid/cwd")" = "$REL"
  sudo cat "/proc/$pid/environ" | tr '\0' '\n' | grep -Fx "PAC_DATA_DIR=$ROOT/shared/data"
done
test "$(systemctl show pac-missions.timer -p ActiveState --value)" = inactive
```

Deploy the first updated release with `update.sh` before restarting the mission timer. Then verify the timer and shared worker status.

```bash
sudo systemctl start pac-missions.timer
systemctl is-active pac-missions.timer
sudo journalctl -u pac -u pac-discord --since '10 minutes ago' --no-pager
```

Check for repeated restarts, permission errors and bot connection errors. Verify the expected bot state (including intentional standby), website login, pilot/flight records, missions and a representative static download. Reopen traffic and resume scheduled jobs only after both services pass. Carry the production missions change into future release packages through review before running update.sh.

## Recovery

* **Before either new service starts**, the stopped flat data and original venv remain authoritative. Leave partial shared/releases directories intact for diagnosis. If the unit switch started, remove **only the drop-in files created in step 5** for pac, pac-discord and pac-missions using `sudo unlink /etc/systemd/system/<unit>.service.d/99-pac-first-migration.conf` for each affected unit, then run `sudo systemctl daemon-reload`. Compare effective units with SAVE, start pac, verify /up, then start pac-discord and pac-missions.timer and recheck the records. To restore the original deploy scripts, move the overlaid deploy directory to SAVE and copy flat-deploy back if it existed.
* **Once either new service has started**, assume shared/data has new writes even with ingress closed. Stop both services and other writers again. Keep both trees and take a fresh verified SQLite backup of shared/data/logbook.db. Prefer repairing the release or units in place. For a flat fallback, confirm flat-code/schema compatibility and space for an additional stopped data copy. As pac, create a private sibling staging directory on the same filesystem as flat data. Copy `shared/data/.` there with `cp -a`, compare with `diff -qr` while stopped, and check SQLite integrity there. Add the seven reference JSON files listed in the migration script from the release's data directory, preserving the saved missions version. Rename the old flat data directory to an unused recovery name, then rename the verified staged directory to `$ROOT/data`. If the second rename fails, restore the first name before starting anything. Restore flat unit configuration as above and verify both services before reopening. Preserve shared/data and all recovery copies.
* The first migration has no previous release. The migration's --undo overlays code and removes the flat venv. Leave it unused for this fallback. If space, compatibility or verification fails, keep writers stopped and recover on a larger volume from the verified backups. Returning to the Windows snapshot or final backup can discard subsequent writes and requires an explicit recovery decision.

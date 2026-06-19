# Scheduling the inventory

Run Phase 1 on a schedule so new books are picked up automatically. The scan is
**idempotent and incremental** — re-running only hashes new/changed files, flags
deletes/moves via `missing_since`, and (with `--prune`) removes rows for files
that are gone. Safe to run as often as you like.

Before scheduling: create `config/pipeline.local.json` (copy `config/pipeline.json`)
and set `roots` to your real library path.

## Option A — systemd user timer (recommended)

Runs as your user, no root, output in the journal. Assumes the repo is at
`~/knowledge-rag`; edit `WorkingDirectory` in the `.service` if not.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/knowledge-rag-inventory.service ~/.config/systemd/user/
cp deploy/systemd/knowledge-rag-inventory.timer   ~/.config/systemd/user/

systemctl --user daemon-reload
systemctl --user enable --now knowledge-rag-inventory.timer

# Let timers run when you're logged out (optional, for a headless box):
sudo loginctl enable-linger "$USER"
```

Verify / operate:

```bash
systemctl --user list-timers knowledge-rag-inventory.timer   # next run time
systemctl --user start knowledge-rag-inventory.service       # run now, on demand
journalctl --user -u knowledge-rag-inventory -f              # watch output
```

To enable pruning of deleted/moved files, add `--prune` to `ExecStart` in the
`.service`, then `systemctl --user daemon-reload`.

## Option B — cron

```cron
# Sundays 03:00 — weekly inventory refresh
0 3 * * 0 cd "$HOME/knowledge-rag" && /usr/bin/python3 scripts/run_inventory.py --config config/pipeline.local.json >> data/inventory.log 2>&1
```

(`data/` is gitignored, so the log stays local.)

## Notes

- **One run at a time.** Don't schedule overlapping inventory jobs against the
  same catalog. (SQLite WAL makes concurrent *reads* fine — querying while a
  scan runs is OK — but two writers are not.)
- **Deletes/moves:** without `--prune`, vanished files are just flagged
  (`missing_since` set); a moved file appears as a new row plus a stale one
  (same `sha256`). With `--prune`, stale rows under the scanned roots are
  deleted. Start without `--prune`, eyeball the `missing` count, then turn it on.

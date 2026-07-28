# Clone Policy

## Canonical Clone

`~/Documents/GitHub/mutx-dev` is the canonical git clone.

All autonomous scripts resolve `REPO` automatically:
1. `MUTX_REPO` env var (explicit override)
2. `Path(__file__).resolve().parents[2]` relative to script location

No autonomy script hardcodes `/Users/fortune/MUTX` in path assignments.

## Secondary Clone

`~/MUTX` may exist as a runtime clone. It drifts from canonical. Do not treat it as authoritative.

To sync runtime clone to canonical:
```bash
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.next' \
  ~/Documents/GitHub/mutx-dev/scripts/autonomy/ ~/MUTX/scripts/autonomy/
rsync -a --exclude='.git' --exclude='node_modules' --exclude='.next' \
  ~/Documents/GitHub/mutx-dev/docs/ ~/MUTX/docs/
```

## Node.js Runtime Alignment

MUTX and OpenClaw share Node 24.15+ as the recommended runtime lane. If OpenClaw is
deliberately tested on another supported major, keep that executable isolated on PATH.

- **MUTX toolchain** (build/test): Node 24.15+ (CI standard)
- **OpenClaw runtime**: Node 24.15+ recommended; 22.22.3+ and 25.9+ supported

Use the shared Node 24.15+ path by default. Explicitly qualify `node` paths in scripts and cron
jobs that exercise an alternate OpenClaw major.

## Stale Node Backup

`/usr/local/bin/node.v20.15.1.bak` — remove if present. It is an old v20 leftover that can cause version confusion even though MUTX CI now runs on Node 24.

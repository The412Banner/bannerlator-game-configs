# configs/

Community-uploaded Bannerlator game configs live here — **one subfolder per game**:

```
configs/
  <sanitized-game-name>/
    <game>-<manufacturer>-<model>-<soc>-<unixSeconds>.json
    ...
```

Every upload the worker receives is written to `configs/<game>/<file>.json`, so the
repository root stays clean (just the index files + `tools/` + this one `configs/`
directory). Per-game subfolders are collapsed under here — the root never fills up
with game folders no matter how many are shared.

These files are read by the Bannerlator app via the community-configs worker
(`?ns=bannerlator`) and folded into `games_canonical.json` by `tools/canonicalize.py`.
Do not hand-edit — uploads/deletes are managed by the worker.

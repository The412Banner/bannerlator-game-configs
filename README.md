# Bannerlator Game Configs

A **Bannerlator-owned** game-config index, derived from the community configs in
[The412Banner/bannerhub-game-configs](https://github.com/The412Banner/bannerhub-game-configs).

## Isolation guarantee
This repo is **read-only** toward BannerHub: the daily sync fetches BannerHub's public
`games.json` / `devices.json`, and **writes only here.** Nothing in this repo ever modifies
`bannerhub-game-configs`, so it cannot affect BannerHub app/site builds.

## What's here
| File | Contents |
|---|---|
| `games_canonical.json` | Games **merged by Steam appid** → `{appid: {name, folders[], devices[], config_count}}`. This is the primary index Bannerlator matches against — one entry per real game, pooling every device config across duplicate upstream folder-names. |
| `steam_index.json` | `appid → [folders]` reverse index. |
| `games_steam.json` | Flat `folder → {appid, method, steam_name}` (resolution cache; keeps the sync incremental). |
| `unresolved.json` | Folders with no appid, tagged by reason (`non-game` = tools/installers to filter, else exe-abbrev / niche / non-Steam → alias or SteamGridDB). |
| `steam_aliases.json` | Manual `folder → appid` overrides (always win; for exe-abbreviation folders the resolver misses). |
| `CANON_REPORT.txt` | Last sync's stats (canonical resolve rate, merges, examples). |

## How matching works (Bannerlator side)
Resolve the user's game → Steam appid (Bannerlator already resolves via SteamGridDB / Steam) →
look up `games_canonical.json[appid]` → offer its pooled per-device configs (suggest, or apply on
high confidence).

## Merge rule
Folders are merged **only on exact Steam appid** (safe). Two *unresolved* folders are never fused
on name similarity alone. This both raises the effective match rate (duplicate folder-names of one
game collapse to a single entry) and expands each game's options (device configs pool together).

## Sync
`.github/workflows/sync-from-bannerhub.yml` runs daily (and on manual dispatch, with an optional
`force` full re-resolve). Resolution reuses the public BannerHub search Worker; the incremental cache
means a normal run makes near-zero external calls.

*Improving coverage: add exe-abbreviation fixes to `steam_aliases.json`; the resolver's normalization
ladder (naive → apostrophe/edition normalization → fuzzy) handles the rest.*

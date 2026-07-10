#!/usr/bin/env python3
"""
enrich_steam_ids.py — bake Steam appids for BannerHub game-config folders into SIDECAR files.

SAFETY: This NEVER touches games.json. It only writes:
  - games_steam.json   {folder: {appid, steam_name, cover, method}}   (human-diffable source of truth)
  - steam_index.json   {appid: [folder, ...]}                          (reverse index Bannerlator joins on)
games.json is regenerated on a 30-min cron by update-games-json.yml and is read by the site + app;
we deliberately leave it byte-identical so nothing on the BannerHub side can break.

INCREMENTAL: only NEW folders (not already in games_steam.json) are resolved, so a normal run makes
near-zero Worker calls. Set FORCE_RERESOLVE=1 to re-resolve everything (e.g. after improving normalization).
Manual fixes go in steam_aliases.json ({folder: appid}) and always win.
"""
import json, os, re, subprocess, urllib.parse, time

CONFIGS_DIR = os.environ.get("CONFIGS_DIR", "configs")
OUT_MAP     = "games_steam.json"
OUT_INDEX   = "steam_index.json"
ALIAS_FILE  = "steam_aliases.json"
WORKER      = os.environ.get("BH_WORKER", "https://bannerhub-configs-worker.the412banner.workers.dev")
FORCE       = os.environ.get("FORCE_RERESOLVE") == "1"

# Folders that are tools/installers/launchers, not games — don't waste Worker calls, flag for the app to filter.
NON_GAME = re.compile(
    r'(7[-_ ]?zip|4gb[-_ ]?patch|all[-_ ]?in[-_ ]?one|direct\s?x|vc_?redist|d3dx|dotnet|\.net|winrar|notepad|'
    r'installer|setup|bootstrap|packagedgame|redist|runtime|framework|created_with_gamemaker|'
    r'launcher|redirector|www[-_ ]|_com_|_biz|apunkagames|ipcgames|wifi4games|apkpure|repack|crack|'
    r'google_play_games|games_for_windows|steamdrm|^steam$|rockstar_games)', re.I)

def naive(n):  # matches the site's prettyName
    return re.sub(r'\s+', ' ', n.replace('_', ' ')).strip()

def norm(n):   # the big wins: apostrophe (_s_ -> 's), strip trailing padding/dividers, editions/demo, camelCase
    s = n.replace('_s_', "'s ")
    s = re.sub(r'_-_|_+-|-_+', ' ', s)              # _-_ / _- dividers -> space
    s = re.sub(r'_+', ' ', s)                       # collapse underscore runs / trailing padding
    s = re.sub(r'\s*[-–]\s*$', '', s)               # trailing dash left after padding strip
    s = re.sub(r'\s+\b(DEMO|BETA|Repack|Rehydrated|PC|Portable|Final)\b.*$', '', s, flags=re.I)
    s = re.sub(r"\s*[-:]?\s*(HD|Remastered|Definitive Edition|GOTY|Game of the Year Edition|Complete Edition|"
               r"Enhanced Edition|Deluxe Edition|Ultimate Edition|Directors? Cut( Edition)?)\s*$", '', s, flags=re.I)
    s = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', s)      # ACOdyssey -> AC Odyssey (partial)
    return re.sub(r'\s+', ' ', s).strip()

def fuzzy(n):  # last resort: drop publisher prefixes + trailing junk numbers
    s = re.sub(r'\b(activision|ubisoft|electronic arts|ea|2k sports|rockstar games|feral interactive)\b', '', norm(n), flags=re.I)
    s = re.sub(r'\s+\d+\s*$', '', s.strip())
    return re.sub(r'\s+', ' ', s).strip()

def query(term):
    if not term: return {}
    try:
        out = subprocess.run(
            ["curl", "-sSL", "--max-time", "15", "-A", "bh-enrich",
             WORKER + "/steam/search?name=" + urllib.parse.quote(term)],
            capture_output=True, text=True, timeout=20).stdout
        return json.loads(out) or {}
    except Exception:
        return {}

def resolve(folder):
    for method, term in (("naive", naive(folder)), ("norm", norm(folder)), ("fuzzy", fuzzy(folder))):
        r = query(term)
        if r.get("appid"):
            return {"appid": r["appid"], "steam_name": r.get("name"), "cover": r.get("cover"), "method": method}
        time.sleep(0.05)
    return {"appid": None, "method": "unresolved"}

def main():
    folders = sorted(d for d in os.listdir(CONFIGS_DIR)
                     if os.path.isdir(os.path.join(CONFIGS_DIR, d)) and not d.startswith("."))
    idx     = json.load(open(OUT_MAP))     if os.path.exists(OUT_MAP)    else {}
    aliases = json.load(open(ALIAS_FILE))  if os.path.exists(ALIAS_FILE) else {}

    new = resolved = 0
    for f in folders:
        if f in aliases:                                  # manual fixes always win, no Worker call
            idx[f] = {"appid": aliases[f], "method": "alias"}; continue
        if not FORCE and f in idx:                        # incremental: keep existing (incl. remembered nulls)
            continue
        if NON_GAME.search(f):                            # tools/installers: flag, don't query
            idx[f] = {"appid": None, "method": "non-game"}; continue
        idx[f] = resolve(f); new += 1
        if idx[f].get("appid"): resolved += 1

    idx = {f: v for f, v in idx.items() if f in set(folders)}   # prune deleted games

    # reverse index appid -> [folders]  (what Bannerlator joins the user's game appid against)
    rev = {}
    for f, v in idx.items():
        if v.get("appid"):
            rev.setdefault(str(v["appid"]), []).append(f)

    json.dump(idx, open(OUT_MAP, "w"),   indent=2, sort_keys=True)
    json.dump(rev, open(OUT_INDEX, "w"), indent=2, sort_keys=True)

    have = sum(1 for v in idx.values() if v.get("appid"))
    print(f"folders={len(folders)} newly_queried={new} newly_resolved={resolved} "
          f"total_with_appid={have} ({round(100*have/max(1,len(folders)))}%) unique_appids={len(rev)}")

if __name__ == "__main__":
    main()

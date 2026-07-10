#!/usr/bin/env python3
"""
canonicalize.py — turn BannerHub's ~2113 raw game folders into MERGED canonical games for Bannerlator.

Produces:
  games_canonical.json  {appid: {name, folders:[...], devices:[{m,d,s}...], config_count}}   (resolved games, MERGED by appid)
  unresolved.json       [{folder, reason}]                                                     (no appid: exe-abbrev / non-game / niche)
  games_steam.json      {folder: {appid, method, steam_name}}                                   (flat per-folder, refreshed)
  steam_index.json      {appid: [folders]}                                                       (reverse index)

Merge rule: ONLY by exact appid (safe). Never fuses two unresolved folders on name alone.
Incremental-friendly: reuses existing games_steam.json appids; only re-resolves folders without one.
Reads BannerHub read-only (games.json/devices.json). Writes ONLY this repo.
"""
import json, os, re, subprocess, urllib.parse, urllib.request, time
from concurrent.futures import ThreadPoolExecutor
import enrich_steam_ids as E   # reuse naive/norm/fuzzy/query/NON_GAME

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BH_RAW = "https://raw.githubusercontent.com/The412Banner/bannerhub-game-configs/main"

def fetch_json(url):
    try:
        out = subprocess.run(["curl","-sSL","--max-time","30","-A","bgc-sync",url],
                             capture_output=True, text=True, timeout=40).stdout
        return json.loads(out)
    except Exception: return None

def main():
    games = fetch_json(f"{BH_RAW}/games.json") or []
    folders = [g["name"] for g in games]
    devices = fetch_json(f"{BH_RAW}/devices.json") or {}
    counts  = {g["name"]: g.get("count",0) for g in games}

    FORCE = os.environ.get("FORCE_RERESOLVE") == "1"
    seed = {} if FORCE else (json.load(open(f"{BASE}/games_steam.json")) if os.path.exists(f"{BASE}/games_steam.json") else {})
    aliases = {k:v for k,v in (json.load(open(f"{BASE}/steam_aliases.json")).items()
               if os.path.exists(f"{BASE}/steam_aliases.json") else {}) if not k.startswith("_")}
    # Franchise map (non-Steam titles like classic PES): folder -> "name:<slug>" identity or appid.
    if os.path.exists(f"{BASE}/franchise_aliases.json"):
        aliases.update({k:v for k,v in json.load(open(f"{BASE}/franchise_aliases.json")).items() if not k.startswith("_")})

    # classify
    need = []
    flat = {}
    for f in folders:
        if f in aliases:
            flat[f] = {"appid": aliases[f], "method":"alias"}; continue
        prev = seed.get(f)
        if prev and prev.get("appid"):
            flat[f] = {"appid": prev["appid"], "method": prev.get("method","seed"), "steam_name": prev.get("steam_name")}; continue
        if E.NON_GAME.search(f):
            flat[f] = {"appid": None, "method":"non-game"}; continue
        if not FORCE and prev is not None:          # already attempted this run's cache — don't re-hit the Worker
            flat[f] = {"appid": None, "method": prev.get("method","unresolved")}; continue
        need.append(f)                              # only brand-new folders reach the resolver

    # re-resolve the unresolved via the improved ladder (naive->norm->fuzzy)
    def work(f): return (f, E.resolve(f))
    with ThreadPoolExecutor(max_workers=4) as ex:
        for f, r in ex.map(work, need):
            flat[f] = r

    # MERGE by appid
    canon = {}
    unresolved = []
    for f, v in flat.items():
        a = v.get("appid")
        if a:
            key = str(a)
            e = canon.setdefault(key, {"name": v.get("steam_name"), "folders": [], "devices": [], "config_count": 0})
            e["folders"].append(f)
            e["config_count"] += counts.get(f, 0)
            if not e["name"] and v.get("steam_name"): e["name"] = v["steam_name"]
            for dv in devices.get(f, []):
                if dv not in e["devices"]: e["devices"].append(dv)
        else:
            unresolved.append({"folder": f, "reason": v.get("method","unresolved")})

    for key, e in canon.items():            # readable names for name-key + hardcoded/delisted appids w/o a Steam name
        if not e["name"]:
            if key.startswith("name:"):
                nm = key[5:].replace("-", " ").title()
            else:                           # aliased delisted appid (no Steam name) -> cleanest member folder
                nm = re.sub(r'_+', ' ', min(e["folders"], key=len)).strip().title()
            nm = re.sub(r'\bPes\b', 'PES', nm); nm = re.sub(r'\bEfootball\b', 'eFootball', nm)
            nm = re.sub(r'\bGta\b', 'GTA', nm)
            e["name"] = nm

    rev = {a: sorted(e["folders"]) for a, e in canon.items()}
    json.dump(canon,      open(f"{BASE}/games_canonical.json","w"), indent=2, sort_keys=True)
    json.dump(unresolved, open(f"{BASE}/unresolved.json","w"),      indent=2)
    json.dump(flat,       open(f"{BASE}/games_steam.json","w"),     indent=2, sort_keys=True)
    json.dump(rev,        open(f"{BASE}/steam_index.json","w"),     indent=2, sort_keys=True)

    non_game = sum(1 for v in flat.values() if v.get("method")=="non-game")
    real_unres = sum(1 for u in unresolved if u["reason"] != "non-game")
    canonical_games = len(canon)
    denom = canonical_games + real_unres   # real distinct games (exclude non-game junk)
    total_cfgs = sum(counts.values())
    res_cfgs = sum(e["config_count"] for e in canon.values())
    unres_cfgs = sum(counts.get(u["folder"],0) for u in unresolved if u["reason"] != "non-game")
    cfg_cov = round(100*res_cfgs/max(1,res_cfgs+unres_cfgs))
    rep = (f"raw folders: {len(folders)}   total configs: {total_cfgs}\n"
           f"non-game (filtered out): {non_game}\n"
           f"MERGED canonical games (have appid): {canonical_games}\n"
           f"  folders collapsed by merge: {sum(len(e['folders']) for e in canon.values()) - canonical_games}\n"
           f"still-unresolved real games (no appid): {real_unres}\n"
           f"GAME-COUNT RATE: {canonical_games}/{denom} = {round(100*canonical_games/max(1,denom))}%  (vs 67% raw baseline)\n"
           f"CONFIG-COVERAGE (matters for matching): {res_cfgs}/{res_cfgs+unres_cfgs} = {cfg_cov}%\n"
           f"top-merged examples:\n" +
           "\n".join(f"  appid {a}: {len(e['folders'])} folders, {e['config_count']} configs, {len(e['devices'])} devices  {e['folders'][:3]}"
                     for a,e in sorted(canon.items(), key=lambda kv:-len(kv[1]['folders']))[:8]))
    open(f"{BASE}/CANON_REPORT.txt","w").write(rep)
    print(rep)

if __name__ == "__main__":
    main()

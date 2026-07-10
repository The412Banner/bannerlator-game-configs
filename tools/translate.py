#!/usr/bin/env python3
"""
translate.py — turn a BannerHub (XiaoJi com.xj.winemu) game config into a Bannerlator .container.

Maps the pc_ls_* settings to Bannerlator's container schema, extracts the component version each
config wants (DXVK / VKD3D / Turnip / Proton / FEX), and emits BOTH the .container and a
component-resolution report (what versions it needs — to be matched against our catalog).

Drops XiaoJi-only fields (steam_client, hub_type, base component) — different Steam stack.
Usage: translate.py <bannerhub_config.json> <game_name>
"""
import json, re, sys

def jname(v):
    """pc_ls_* component values are JSON blobs; pull the human 'name'/'displayName'."""
    try:
        d = json.loads(v) if isinstance(v, str) else v
        return d.get("name") or d.get("displayName") or ""
    except Exception:
        return str(v)

# --- component version extractors: raw XiaoJi name -> clean version + our-catalog target guess ---
def dxvk_ver(n):   # "dxvk-v2.7.1-1-async" -> "2.7.1-1-async"
    return re.sub(r'^dxvk[-_ ]?v?', '', n, flags=re.I).strip()
def vkd3d_ver(n):  # "vkd3d-proton-3.0b" -> "3.0b"
    return re.sub(r'^vkd3d[-_ ]?(proton[-_ ]?)?', '', n, flags=re.I).strip()
def turnip_ver(n): # "turnip_v26.1.0_b12" -> "Mesa Turnip v26.1.0"
    m = re.search(r'v?(\d+\.\d+\.\d+)', n)
    return f"Mesa Turnip v{m.group(1)}" if m else n
def proton_ver(n): # "proton10.0-arm64x-2" -> "proton-10.0-arm64ec"
    m = re.search(r'(\d+\.\d+)', n)
    arm = "arm64ec" if re.search(r'arm64x|arm64ec', n, re.I) else ""
    return f"proton-{m.group(1)}{('-'+arm) if arm else ''}" if m else n
def fex_ver(n):    # "Fex-20260321" -> "fex-20260321"
    return n.lower().replace("fex-", "fex-").strip()

def translate(cfg, game_name):
    s = cfg.get("settings", {})
    need = []   # components the config asks for -> validate against our catalog

    def comp(key, extract, label):
        raw = jname(s.get(key, ""))
        if not raw: return None
        v = extract(raw)
        need.append({"type": label, "wants": raw, "target": v})
        return v

    dxvk   = comp("pc_ls_DXVK",       dxvk_ver,   "DXVK")
    vkd3d  = comp("pc_ls_VK3k",       vkd3d_ver,  "VKD3D")
    turnip = comp("pc_ls_GPU_DRIVER_",turnip_ver, "Turnip")
    proton = comp("pc_ls_CONTAINER_LIST", proton_ver, "Proton/Wine")
    fex    = comp("pc_set_constant_95",fex_ver,    "FEXCore")

    is_fex = bool(fex) or "fex" in json.dumps(s).lower()
    has_vkd3d = bool(vkd3d)
    dxwrapper = "dxvk+vkd3d" if has_vkd3d else ("dxvk" if dxvk else "wined3d")
    async_on = "1" if dxvk and "async" in dxvk.lower() else "0"

    # dxwrapperConfig (mirror the user's real container key order/format)
    dxw = (f"version={dxvk or ''},framerate=0,async={async_on},asyncCache=0,"
           f"vkd3dVersion={vkd3d or ''},vkd3dLevel=12_1,ddrawrapper=none,csmt=3,"
           f"gpuName=NVIDIA GeForce GTX 480,videoMemorySize=2048,strict_shader_math=1,"
           f"OffscreenRenderingMode=fbo,renderer=gl,dxvkConfigFile=")

    gdc = (f"vulkanVersion=1.3;version={turnip or 'Mesa Turnip'};blacklistedExtensions=;"
           f"maxDeviceMemory=0;presentMode=mailbox;syncFrame=1;disablePresentWait=0;resourceType=auto;"
           f"bcnEmulation=auto;bcnEmulationType=compute;bcnEmulationCache=0;gpuName=Device;fdDevFeatures=0")

    boot = str(s.get("pc_ls_boot_option", "") or "").strip()
    envv = str(s.get("pc_ls_environment_variable", "") or "").strip()
    xinput = s.get("pc_ls_update_enable_xinput", True)

    container = {
        "name": game_name,
        "screenSize": "1280x720",
        "envVars": envv,
        "cpuList": "0,1,2,3,4,5,6,7",
        "cpuListWoW64": "0,1,2,3,4,5,6,7",
        "emulator": "fexcore" if is_fex else "box64",
        "fexcoreVersion": fex or "",
        "fexcorePreset": "Game Presets" if is_fex else "",
        "wineVersion": proton or "",
        "graphicsDriver": "wrapper-original",
        "graphicsDriverConfig": gdc,
        "dxwrapper": dxwrapper,
        "dxwrapperConfig": dxw,
        "audioDriver": "pulseaudio" if str(s.get("pc_ls_AUDIO_DRIVER", 1)) == "1" else "alsa",
        "wincomponents": "direct3d=1,directsound=0,directmusic=0,directshow=0,directplay=0,xaudio=0,vcrun2010=1",
        "inputType": "1" if xinput else "0",
        "extraData": {"source": "bannerhub", "device": cfg.get("meta", {}).get("device"),
                      "soc": cfg.get("meta", {}).get("soc"), "launchArgs": boot},
    }
    return container, need

if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1]))
    name = sys.argv[2] if len(sys.argv) > 2 else "Imported Game"
    container, need = translate(cfg, name)
    print("=== TRANSLATED .container ===")
    print(json.dumps(container, indent=2))
    print("\n=== COMPONENTS TO RESOLVE against our catalog ===")
    for c in need:
        print(f"  {c['type']:12s} wants '{c['wants']}'  -> target '{c['target']}'")

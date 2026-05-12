"""
warframe_loadout.py — Reads EE.log to detect current Warframe loadout.
Extracts: frame name, primary, secondary, melee, companion.
Saves loadout context to game session metadata.
"""
import os, re, json

EE_LOG = os.path.expanduser(
    "~/.local/share/Steam/steamapps/compatdata/230410/pfx/drive_c"
    "/users/steamuser/AppData/Local/Warframe/EE.log"
)

# ── INTERNAL NAME → DISPLAY NAME MAP ─────────────────────────────────────────
# Maps partial internal names to friendly display names
# Add more as you discover them
NAME_MAP = {
    # Frames
    "MonkeyKingPrime":      "Wukong Prime",
    "MonkeyKing":           "Wukong Prime",
    "WukongPrime":          "Wukong Prime",
    "Wukong":               "Wukong",
    "HydroidPrime":         "Hydroid Prime",
    "Hydroid":              "Hydroid",
    "NekrosPrime":          "Nekros Prime",
    "Nekros":               "Nekros",
    "Necro":                "Nekros",
    "NecroBaseSuit":        "Nekros",
    "KhoraPrime":           "Khora Prime",
    "Khora":                "Khora",
    "MesaPrime":            "Mesa Prime",
    "SarynPrime":           "Saryn Prime",
    "OctaviaPrime":         "Octavia Prime",
    "HildrynPrime":         "Hildryn Prime",

    # Primaries
    "PrimeAcceltraWeapon":  "Acceltra Prime",
    "AcceltraWeapon":       "Acceltra",
    "ThanoTechLongGun":     "Cedo",
    "ArchonTridentPlayerWep": "Archon Continuity (Trident)",

    # Secondaries
    "PrimeEpitaphSidearmWeapon": "Epitaph Prime",
    "EpitaphSidearmWeapon": "Epitaph",

    # Primaries (continued)
    "ThanoTechLongGun":     "Cedo",
    "TenetCedo":            "Tenet Cedo",
    # Melee
    "KorummMeleeWeapon":    "Korumm",
    "PrimeKorummMeleeWeapon": "Korumm Prime",

    # Companions
    "DreamersBond":         "Dreamer's Bond",
    "SentinelVacuumCompanion": "Carrier",
}

# Slot → weapon type
SLOT_MAP = {
    "SLOT_0": "frame",
    "SLOT_1": "secondary",
    "SLOT_2": "primary",
    "SLOT_3": "melee",
    "SLOT_4": "companion",
    "SLOT_5": "arch_gun",
    "SLOT_3": "melee",
    "SLOT_6": "arch_melee",
    "SLOT_11": "arch_primary",
}

def _internal_to_display(name):
    """Convert internal item name to display name."""
    # Direct map check
    for key, display in NAME_MAP.items():
        if key.lower() in name.lower():
            return display
    # Clean up internal name as fallback
    # Remove common suffixes
    clean = re.sub(r'(Weapon|SidearmWeapon|LongGun|MeleeWeapon|PlayerWep|Companion)$', '', name)
    # Split CamelCase
    clean = re.sub(r'([A-Z])', r' \1', clean).strip()
    # Remove "Prime" duplication
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def read_loadout_from_log():
    """
    Parse EE.log to extract the most recent loadout.
    Returns dict with frame, primary, secondary, melee, companion.
    """
    if not os.path.exists(EE_LOG):
        return None

    loadout = {
        "frame":     "Unknown",
        "primary":   "Unknown",
        "secondary": "Unknown",
        "melee":     "Unknown",
        "companion": "Unknown",
        "raw":       {}
    }

    try:
        # Read last 500KB of log (loadout info is near session start)
        with open(EE_LOG, 'r', errors='ignore') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 500000))
            lines = f.readlines()

        # Find last StoreInventoryItem block
        slot_items = {}
        for line in lines:
            m = re.search(r'StoreInventoryItem slot:(SLOT_\d+) loadOutType:LOT_NORMAL, item: (\S+)', line)
            if m:
                slot = m.group(1)
                item = m.group(2)
                slot_items[slot] = item

        # Also look for PowerSuit (frame) directly
        for line in lines:
            if "PowerSuit found" in line or "PlayerSuit" in line:
                m = re.search(r'/Lotus/Powersuits/(\w+)/\w+', line)
                if m:
                    loadout["frame"] = _internal_to_display(m.group(1))

        # Map slots to loadout
        loadout["raw"] = slot_items
        for slot, item in slot_items.items():
            wtype = SLOT_MAP.get(slot)
            display = _internal_to_display(item)
            if wtype == "secondary":
                loadout["secondary"] = display
            elif wtype == "primary":
                loadout["primary"] = display
            elif wtype in ("melee", "arch_melee"):
                loadout["melee"] = display
            elif wtype == "companion":
                loadout["companion"] = display

        # Get frame — find FavouriteLoadOut section, first Powersuits ability loaded = equipped frame
        in_favourite = False
        for line in lines:
            if "FavouriteLoadOut" in line:
                in_favourite = True
            if in_favourite and "Spot-loading" in line and "Powersuits/" in line:
                m = re.search(r"Powersuits/(\w+)/", line)
                if m:
                    raw = m.group(1).lower()
                    if raw not in {"powersuitabilities", "helminth", "tenno"}:
                        loadout["frame"] = _internal_to_display(m.group(1))
                        break
        # Fallback: first Powersuits/ Spot-loading with known frame names
        if loadout["frame"] == "Unknown":
            KNOWN = {"monkeyking": "Wukong Prime", "hydroid": "Hydroid",
                     "necro": "Nekros", "nekros": "Nekros",
                     "khora": "Khora", "trapper": "Khora",
                     "mesa": "Mesa", "saryn": "Saryn",
                     "octavia": "Octavia", "hildryn": "Hildryn",
                     "wisp": "Wisp", "titania": "Titania", "nidus": "Nidus",
                     "protea": "Protea", "lavos": "Lavos", "yareli": "Yareli",
                     "ember": "Ember", "frost": "Frost", "volt": "Volt",
                     "loki": "Loki", "mag": "Mag", "trinity": "Trinity",
                     "excalibur": "Excalibur", "rhino": "Rhino", "ash": "Ash",
                     "nova": "Nova", "vauban": "Vauban", "banshee": "Banshee",
                     "oberon": "Oberon", "zephyr": "Zephyr", "limbo": "Limbo",
                     "chroma": "Chroma", "atlas": "Atlas", "ivara": "Ivara",
                     "inaros": "Inaros", "revenant": "Revenant", "baruuk": "Baruuk",
                     "grendel": "Grendel", "xaku": "Xaku", "garuda": "Garuda",
                     "gauss": "Gauss", "gyre": "Gyre", "caliban": "Caliban",
                     "voruna": "Voruna", "styanax": "Styanax", "citrine": "Citrine",
                     "kullervo": "Kullervo", "dagath": "Dagath", "qorvex": "Qorvex",
                     "dante": "Dante", "jade": "Jade", "cyte09": "Cyte-09"}
            for line in lines:
                if "Spot-loading" in line and "Powersuits/" in line:
                    m = re.search(r'Powersuits/(\w+)/', line)
                    if m and m.group(1).lower() in KNOWN:
                        loadout["frame"] = KNOWN[m.group(1).lower()]
                        break

    except Exception as e:
        print(f"[loadout] Parse error: {e}")

    return loadout

def get_loadout_summary():
    """Return a one-line loadout summary string."""
    l = read_loadout_from_log()
    if not l:
        return "Loadout unknown"
    return (f"{l['frame']} | {l['primary']} | "
            f"{l['secondary']} | {l['melee']}")

def save_loadout_to_session(session_path):
    """Add loadout info to an existing session JSON file."""
    if not os.path.exists(session_path):
        return
    try:
        data = json.load(open(session_path))
        loadout = read_loadout_from_log()
        if loadout:
            data["metadata"]["loadout"] = loadout
            data["metadata"]["loadout_summary"] = get_loadout_summary()
            json.dump(data, open(session_path, "w"), indent=2)
            print(f"[loadout] Saved to session: {get_loadout_summary()}")
    except Exception as e:
        print(f"[loadout] Save error: {e}")

if __name__ == "__main__":
    print("Reading loadout from EE.log...")
    l = read_loadout_from_log()
    if l:
        print(f"Frame:     {l['frame']}")
        print(f"Primary:   {l['primary']}")
        print(f"Secondary: {l['secondary']}")
        print(f"Melee:     {l['melee']}")
        print(f"Companion: {l['companion']}")
        print(f"\nSummary: {get_loadout_summary()}")
        print(f"\nRaw slots: {l['raw']}")
    else:
        print("EE.log not found or no loadout data")

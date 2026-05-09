import os, json, argparse

RULES_PATH = os.path.join(os.path.dirname(__file__), "rules", "effects.json")

CROP_HINTS     = ("crop","farm","harvest","growth","sprout","seed","scarecrow")
FLOWER_HINTS   = ("flower","bloom","pansy","daffodil","carnation","lotus","gladiolus","clover")
FRUIT_HINTS    = ("fruit","apple","orange","blueberry","banana","lemon")
TREE_HINTS     = ("tree","lumber","wood","chop")
ANIMAL_HINTS   = ("animal","hen","chicken","cow","sheep","feed","barn")
MINERAL_HINTS  = ("rock","ore","iron","gold","mine","forge","stone","crimstone","sunstone")
BEE_HINTS      = ("bee","honey","pollen","beehive")
COOK_HINTS     = ("cook","chef","kitchen","feast","soup","bake","deli")
COMPOST_HINTS  = ("compost","bin","bale")

TYPE_ORDER = [
    ("crops",    CROP_HINTS),
    ("flowers",  FLOWER_HINTS),
    ("fruits",   FRUIT_HINTS),
    ("trees",    TREE_HINTS),
    ("animals",  ANIMAL_HINTS),
    ("minerals", MINERAL_HINTS),
    ("beehives", BEE_HINTS),
    ("cooking",  COOK_HINTS),
    ("compost",  COMPOST_HINTS),
]

def guess_type(name: str) -> str | None:
    n = name.lower()
    for t, hints in TYPE_ORDER:
        if any(h in n for h in hints):
            return t
    return None

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        return default
    except Exception:
        return default

def skills_from_payload(payload: dict) -> dict:
    return ((payload or {}).get("farm", {}).get("bumpkin", {}).get("skills", {}) or {})

def collectibles_from_payload(payload: dict) -> dict:
    farm = (payload or {}).get("farm", {})
    out = {}
    home = ((farm.get("home") or {}).get("collectibles") or {})
    if isinstance(home, dict):
        for name, arr in home.items():
            if isinstance(arr, list) and arr:
                out[name] = out.get(name, 0) + len(arr)
    buildings = farm.get("buildings") or {}
    if isinstance(buildings, dict):
        for name, arr in buildings.items():
            if isinstance(arr, list) and arr:
                out[name] = out.get(name, 0) + len(arr)
    island = farm.get("island") or {}
    if isinstance(island, dict):
        for name, val in island.items():
            if isinstance(val, list) and val:
                out[name] = out.get(name, 0) + len(val)
            elif isinstance(val, dict) and val:
                out[name] = out.get(name, 0) + 1
    return out

def merge_rules(effects: dict, payload: dict) -> tuple[dict, list[str]]:
    updated = list()
    effects.setdefault("global", 1.0)
    effects.setdefault("skills", {})
    effects.setdefault("collectibles", {})

    for s_name in skills_from_payload(payload).keys():
        if s_name not in effects["skills"]:
            t = guess_type(s_name)
            entry = {}
            if t: entry["types"] = {t: 1.0}
            effects["skills"][s_name] = entry
            updated.append(f"skill + {s_name} -> types.{t if t else '(none)'}=1.0")

    for c_name in collectibles_from_payload(payload).keys():
        if c_name not in effects["collectibles"]:
            t = guess_type(c_name)
            entry = {}
            if t: entry["types"] = {t: 1.0}
            effects["collectibles"][c_name] = entry
            updated.append(f"collectible + {c_name} -> types.{t if t else '(none)'}=1.0")

    return effects, updated

def main():
    ap = argparse.ArgumentParser(description="Sync rules/effects.json con il payload")
    ap.add_argument("--from-file", required=True, help="payload JSON salvato")
    ap.add_argument("--write", action="store_true", help="scrive su rules/effects.json")
    args = ap.parse_args()

    payload = load_json(args.from_file, {})
    effects = load_json(RULES_PATH, {"global": 1.0, "skills": {}, "collectibles": {}})

    merged, changes = merge_rules(effects, payload)

    if not changes:
        print("Niente da aggiornare — già allineato ✅")
        return

    print("Aggiunte:")
    for c in changes:
        print(" -", c)

    if args.write:
        with open(RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"\\nSalvato: {RULES_PATH}")
    else:
        print("\\n(DRY-RUN) Usa --write per salvare.")

if __name__ == "__main__":
    main()

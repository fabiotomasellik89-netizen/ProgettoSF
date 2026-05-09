TYPE_LABELS = {
    "crops":   ("bed", "beds"),
    "fruits":  ("plant", "plants"),
    "animals": ("animal", "animals"),
    "minerals":("node", "nodes"),
    "trees":   ("tree", "trees"),
    "flowers": ("plant", "plants"),
    "cooking": ("batch", "batches"),
    "compost": ("bin", "bins"),
}

def get_label(item_type: str, count: int) -> str:
    sg, pl = TYPE_LABELS.get(item_type, ("unit", "units"))
    return sg if count == 1 else pl

# Puoi mettere override qui, altrimenti default 1.0 <item_name>
YIELD_PER_UNIT = {
    # "Wheat": {"amount": 1.0, "unit": "Wheat"},
}

def get_yield_per_unit(item_name: str):
    data = YIELD_PER_UNIT.get(item_name)
    if data:
        return float(data.get("amount", 1.0)), str(data.get("unit", item_name or "")).strip() or item_name
    # default: 1.0 e unit = item_name
    return 1.0, item_name or ""

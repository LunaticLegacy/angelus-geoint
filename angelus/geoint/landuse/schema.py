from __future__ import annotations
from typing import Any

def normalize_category_schema(value: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the portable value-to-class mapping stored with an asset."""
    value=value or {}; classes=value.get("classes", [])
    if not isinstance(classes,list): raise ValueError("land-use classes must be a list")
    output=[]
    for item in classes:
        if not isinstance(item,dict) or "value" not in item or not isinstance(item.get("label"),str): raise ValueError("invalid land-use class")
        output.append({"value":item["value"],"label":item["label"],"agricultural":bool(item.get("agricultural",False))})
    return {"classes":output, "unknown_policy":value.get("unknown_policy","exclude")}

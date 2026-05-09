# aoe.py — utilità per Basic Scarecrow (solo coordinate)

from __future__ import annotations
from typing import Any, Dict, Set, Tuple

__all__ = ["get_basic_scarecrow_cells"]


def _as_int(v: Any) -> int | None:
    try:
        if isinstance(v, bool):
            return None
        return int(v)
    except Exception:
        try:
            return int(str(v).strip())
        except Exception:
            return None


def _find_aoe_root(node: Any) -> Dict[str, Any] | None:
    if isinstance(node, dict):
        aoe = node.get("aoe")
        if isinstance(aoe, dict):
            return aoe
        for v in node.values():
            found = _find_aoe_root(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _find_aoe_root(v)
            if found is not None:
                return found
    return None


def get_basic_scarecrow_cells(payload: dict) -> set[tuple[int, int]]:
    """
    Ritorna l'insieme di celle (x, y) coperte dal Basic Scarecrow.
    Il payload espone:
      payload["aoe"]["Basic Scarecrow"][str(x)][str(y)] = <timestamp>
    I timestamp NON vengono usati per gating: Basic è considerato sempre attivo.
    """
    cells: set[tuple[int, int]] = set()
    aoe = payload.get("aoe") or {}
    basic = aoe.get("Basic Scarecrow") or {}
    if isinstance(basic, dict):
        for xs, ymap in basic.items():
            try:
                x = int(xs)
            except Exception:
                continue
            if isinstance(ymap, dict):
                for ys in ymap.keys():
                    try:
                        y = int(ys)
                        cells.add((x, y))
                    except Exception:
                        continue
    return cells


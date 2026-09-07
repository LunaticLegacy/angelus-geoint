"""Safe, declarative defaults for browser vector display.

The map document keeps these simple values rather than OpenLayers objects so a
layer style survives a page reload and can be reviewed or changed by an Agent
without coupling the persisted format to one browser library.
"""
from __future__ import annotations

from typing import Any


DEFAULT_VECTOR_RENDER = {
    "kind": "vector",
    "stroke_color": "#3f82e8",
    "fill_color": "#3f82e8",
    "fill_opacity": 0.11,
}


def default_vector_render() -> dict[str, Any]:
    """Return a fresh default vector style record for a new map layer."""
    return dict(DEFAULT_VECTOR_RENDER)


def effective_vector_render(render: object) -> dict[str, Any]:
    """Merge old or partial vector records over the stable display default.

    Existing documents used ``{kind: "vector", mode: "single"}`` (and some
    user-created layers used an empty object) before configurable styling was
    introduced.  They remain displayable without a migration write.
    """
    if not isinstance(render, dict) or render.get("kind") != "vector":
        return default_vector_render()
    return {**DEFAULT_VECTOR_RENDER, **{key: render[key] for key in DEFAULT_VECTOR_RENDER if key in render}}


__all__ = ["DEFAULT_VECTOR_RENDER", "default_vector_render", "effective_vector_render"]

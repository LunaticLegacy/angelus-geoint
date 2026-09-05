"""Basemap HTTP contract; canonical configuration lives in BasemapStore."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ..geoint.basemaps import XYZConfig
from ..geoint.tianditu_tiles import fetch_tile

router = APIRouter(prefix="/api/geoint/basemaps", tags=["geoint-basemaps"])


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(min_length=1, max_length=80)


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    key: str = Field(max_length=128)


def mutate(operation, *args):
    try:
        return operation(*args)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None


@router.get("")
def get_sources(request: Request):
    return request.app.state.basemaps.snapshot()


@router.post("")
def add_source(config: XYZConfig, request: Request):
    return mutate(request.app.state.basemaps.add, config)


@router.put("/selection")
def select_source(selection: Selection, request: Request):
    return mutate(request.app.state.basemaps.select, selection.source_id)


@router.put("/tianditu-key")
def set_key(value: KeyInput, request: Request):
    return mutate(request.app.state.basemaps.set_key, value.key)


@router.delete("/{source_id}")
def delete_source(source_id: str, request: Request):
    return mutate(request.app.state.basemaps.delete, source_id)


@router.put("/{source_id}")
def update_source(source_id: str, config: XYZConfig, request: Request):
    return mutate(request.app.state.basemaps.update, source_id, config)


@router.get("/tianditu/{layer}/{z}/{x}/{y}")
def tile(layer: str, z: int, x: int, y: int, request: Request):
    try:
        body, mime = fetch_tile(request.app.state.basemaps.tianditu_key(), layer, z, x, y)
    except ValueError as error:
        raise HTTPException(400, str(error)) from None
    except RuntimeError as error:
        raise HTTPException(502, str(error)) from None
    return Response(body, media_type=mime, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})

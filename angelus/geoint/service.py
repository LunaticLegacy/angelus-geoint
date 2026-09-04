"GEOINT drought-analysis domain service with optional PostGIS persistence."

from __future__ import annotations

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any
import uuid

from .geometry import geometry_bbox, geometry_contains_point, geometry_representative_point
from .crs import crs_convention
from .local_assets import LocalAssetCatalog, LocalAssetError
from .local_results import LocalResultStore
from .catalog import GeoAssetCatalog
from .processing import DerivationService
from .prototype import synthetic_features
from .risk_model import DEFAULT_DROUGHT_WEIGHTS, clamp, drought_level, drought_score, indicator_features, normalize_weights, summarize

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - install metadata normally provides it.
    psycopg = None
    dict_row = None
    Jsonb = None


class GeoIntError(RuntimeError):
    """Base error for GEOINT service failures."""


class PostGISUnavailable(GeoIntError):
    """Raised when an operation requires PostGIS but no usable database exists."""


class GeoIntService:
    """Own drought analysis and the optional PostGIS-backed evidence store."""

    def __init__(
        self,
        database_url: str | None = None,
        state_root: Path | None = None,
        data_root: Path | None = None,
    ) -> None:
        self._database_url = database_url
        self._asset_catalog = LocalAssetCatalog(state_root, data_root) if state_root is not None else None
        self._result_store = LocalResultStore(state_root) if state_root is not None else None
        # New catalog state is separate from the legacy GeoJSON-only registry.
        # ``data/derived`` is Angelus-owned even when sources live on removable media.
        self.catalog = GeoAssetCatalog(state_root / "catalog") if state_root is not None else None
        self.derivations = DerivationService(self.catalog, (data_root or (Path.cwd() / "data")) / "derived") if self.catalog else None
        self._analyses: dict[str, dict[str, Any]] = {}
        self._observations: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    @property
    def database_url(self) -> str | None:
        return self._database_url or os.environ.get("ANGELUS_GEOINT_DATABASE_URL")

    def _connect(self):
        if psycopg is None:
            raise PostGISUnavailable("psycopg is not installed")
        if not self.database_url:
            raise PostGISUnavailable(
                "Set ANGELUS_GEOINT_DATABASE_URL, for example "
                "postgresql://postgres:password@127.0.0.1:5432/geoint"
            )
        try:
            return psycopg.connect(self.database_url, row_factory=dict_row)
        except Exception as exc:  # pragma: no cover - depends on external DB.
            raise PostGISUnavailable(str(exc)) from exc

    def health(self) -> dict[str, Any]:
        base = {
            "configured": bool(self.database_url),
            "driver_available": psycopg is not None,
            "connected": False,
            "postgis_version": None,
            "error": None,
        }
        if not base["configured"] or not base["driver_available"]:
            return base
        try:
            with self._connect() as conn:
                row = conn.execute("SELECT PostGIS_Full_Version() AS version").fetchone()
                base["connected"] = True
                base["postgis_version"] = row["version"] if row else None
        except Exception as exc:
            base["error"] = str(exc)
        return base

    def bootstrap(self) -> dict[str, Any]:
        """Create the minimal PostGIS schema used by the GEOINT prototype."""
        with self._connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS postgis")
            conn.execute("CREATE SCHEMA IF NOT EXISTS angelus_geoint")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS angelus_geoint.analyses (
                    id uuid PRIMARY KEY,
                    session_id text NULL,
                    kind text NOT NULL,
                    start_date date NOT NULL,
                    end_date date NOT NULL,
                    aoi geometry(Geometry, 4326) NOT NULL,
                    parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
                    summary jsonb NOT NULL DEFAULT '{}'::jsonb,
                    result jsonb NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS analyses_aoi_gix
                ON angelus_geoint.analyses USING gist (aoi)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS angelus_geoint.observations (
                    id uuid PRIMARY KEY,
                    session_id text NULL,
                    analysis_id uuid NULL,
                    source text NOT NULL,
                    indicator text NOT NULL,
                    value double precision NULL,
                    confidence double precision NOT NULL DEFAULT 1.0,
                    geom geometry(Geometry, 4326) NULL,
                    properties jsonb NOT NULL DEFAULT '{}'::jsonb,
                    created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS observations_geom_gix
                ON angelus_geoint.observations USING gist (geom)
                """
            )
        return {"status": "ready", **self.health()}

    def analyze_drought(
        self,
        *,
        aoi: dict[str, Any],
        start_date: date,
        end_date: date,
        session_id: str | None = None,
        indicators: list[dict[str, Any]] | None = None,
        grid_size: int = 5,
        weights: dict[str, float] | None = None,
        analysis_mode: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if start_date > end_date:
            raise ValueError("start_date must not be later than end_date")
        geometry_bbox(aoi)
        mode = analysis_mode or ("indicator-input" if indicators else "prototype-synthetic")
        features = (
            indicator_features(indicators, weights=weights)
            if indicators
            else synthetic_features(aoi, grid_size)
        )
        analysis_id = str(uuid.uuid4())
        result = {
            "id": analysis_id,
            "kind": "drought_stress",
            "session_id": session_id,
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "analysis_mode": mode,
            "model": {
                "id": "drought-anomaly-weighted-v1",
                "weights": normalize_weights(weights),
                "inputs": ["ndvi_anomaly", "rainfall_anomaly", "soil_moisture_anomaly"],
            },
            "provenance": dict(provenance or {}),
            "aoi": aoi,
            "summary": summarize(features),
            "feature_collection": {
                "type": "FeatureCollection",
                "features": features,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "persistence": {"mode": "memory", "error": None},
        }
        with self._lock:
            self._analyses[analysis_id] = result

        if self._result_store is not None:
            try:
                self._result_store.save(result)
                result["persistence"] = {"mode": "local-file", "error": None}
            except Exception as exc:
                result["persistence"] = {"mode": "memory", "error": str(exc)}

        if self.database_url and psycopg is not None:
            try:
                self._persist_analysis(result)
                result["persistence"] = {"mode": "postgis", "error": None}
            except Exception as exc:
                result["persistence"] = {"mode": "memory", "error": str(exc)}
        return result

    def local_asset_configuration(self) -> dict[str, Any]:
        """Expose backend-owned local analysis choices and the local data root."""
        data_root = self._asset_catalog.data_root if self._asset_catalog else (Path.cwd() / "data")
        return {
            "crs": crs_convention(),
            "data_root": str(data_root),
            "analysis_units": [{"id": "dataset_features", "label": "数据集空间单元"}],
            "model": {
                "id": "drought-anomaly-weighted-v1",
                "default_weights": normalize_weights(),
                "required_indicators": ["ndvi_anomaly", "rainfall_anomaly", "soil_moisture_anomaly"],
            },
            "accepted_asset": {
                "kind": "drought_indicator_geojson",
                "extensions": [".geojson", ".json"],
                "feature_properties": ["ndvi_anomaly", "rainfall_anomaly", "soil_moisture_anomaly", "confidence"],
            },
        }

    def list_local_assets(self) -> list[dict[str, Any]]:
        return self._require_assets().list()

    def register_local_indicator_asset(self, *, name: str, relative_path: str) -> dict[str, Any]:
        if not name.strip():
            raise LocalAssetError("asset name is required")
        return self._require_assets().register_indicator_geojson(name=name, relative_path=relative_path)

    def analyze_local_asset(
        self,
        *,
        asset_id: str,
        aoi: dict[str, Any],
        start_date: date,
        end_date: date,
        session_id: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """Run the no-network local data path for source spatial units in the AOI."""
        geometry_bbox(aoi)
        asset, source_features = self._require_assets().read_indicator_features(asset_id)
        selected: list[dict[str, Any]] = []
        for feature in source_features:
            geometry = feature.get("geometry")
            if not isinstance(geometry, dict):
                continue
            if not geometry_contains_point(aoi, geometry_representative_point(geometry)):
                continue
            properties = dict(feature.get("properties") or {})
            selected.append({
                "id": feature.get("id"),
                "geometry": geometry,
                "ndvi_anomaly": properties["ndvi_anomaly"],
                "rainfall_anomaly": properties["rainfall_anomaly"],
                "soil_moisture_anomaly": properties["soil_moisture_anomaly"],
                "confidence": properties.get("confidence", 1.0),
                "properties": {**properties, "source_asset_id": asset_id},
            })
        if not selected:
            raise LocalAssetError("selected AOI contains no spatial units from this local dataset")
        result = self.analyze_drought(
            aoi=aoi,
            start_date=start_date,
            end_date=end_date,
            session_id=session_id,
            indicators=selected,
            weights=weights,
            analysis_mode="local-asset-indicators",
            provenance={
                "asset_id": asset_id,
                "asset_name": asset["name"],
                "asset_sha256": asset["sha256"],
                "asset_quality": asset["quality"],
                "selection": "feature representative point inside AOI",
            },
        )
        result["evidence"] = {
            "asset_id": asset_id,
            "source_units": len(source_features),
            "units_in_aoi": len(selected),
            "quality": asset["quality"],
        }
        if self._result_store is not None:
            self._result_store.save(result)
        return result

    def _require_assets(self) -> LocalAssetCatalog:
        if self._asset_catalog is None:
            raise LocalAssetError("local asset catalog is not configured")
        return self._asset_catalog

    def _require_catalog(self) -> GeoAssetCatalog:
        if self.catalog is None:
            raise GeoIntError("GEOINT asset catalog is not configured")
        return self.catalog

    def _persist_analysis(self, analysis: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO angelus_geoint.analyses
                    (id, session_id, kind, start_date, end_date, aoi, parameters, summary, result)
                VALUES
                    (%s, %s, %s, %s, %s,
                     ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                     %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    analysis["id"],
                    analysis.get("session_id"),
                    analysis["kind"],
                    analysis["period"]["start"],
                    analysis["period"]["end"],
                    json.dumps(analysis["aoi"]),
                    Jsonb({"analysis_mode": analysis["analysis_mode"]}),
                    Jsonb(analysis["summary"]),
                    Jsonb(analysis),
                ),
            )

    def list_analyses(self, limit: int = 25) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 100))
        if self.database_url and psycopg is not None:
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT result
                        FROM angelus_geoint.analyses
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (bounded,),
                    ).fetchall()
                    return [dict(row["result"]) for row in rows]
            except Exception:
                pass
        with self._lock:
            in_memory = list(reversed(tuple(self._analyses.values())))[:bounded]
        if in_memory:
            return in_memory
        if self._result_store is not None:
            return self._result_store.list(bounded)
        return []

    def get_analysis(self, analysis_id: str) -> dict[str, Any]:
        with self._lock:
            if analysis_id in self._analyses:
                return self._analyses[analysis_id]
        if self.database_url and psycopg is not None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result FROM angelus_geoint.analyses WHERE id = %s",
                    (analysis_id,),
                ).fetchone()
                if row:
                    return dict(row["result"])
        if self._result_store is not None:
            return self._result_store.get(analysis_id)
        raise KeyError(analysis_id)

    def add_observation(
        self,
        *,
        source: str,
        indicator: str,
        geometry: dict[str, Any] | None,
        value: float | None = None,
        confidence: float = 1.0,
        session_id: str | None = None,
        analysis_id: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        observation_id = str(uuid.uuid4())
        observation = {
            "id": observation_id,
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "source": source,
                "indicator": indicator,
                "value": value,
                "confidence": clamp(confidence),
                "session_id": session_id,
                "analysis_id": analysis_id,
                **dict(properties or {}),
            },
        }
        with self._lock:
            self._observations[observation_id] = observation
        if self.database_url and psycopg is not None:
            try:
                with self._connect() as conn:
                    geom_json = json.dumps(geometry) if geometry else None
                    conn.execute(
                        """
                        INSERT INTO angelus_geoint.observations
                            (id, session_id, analysis_id, source, indicator, value,
                             confidence, geom, properties)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s,
                             CASE WHEN %s IS NULL THEN NULL
                                  ELSE ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) END,
                             %s)
                        """,
                        (
                            observation_id,
                            session_id,
                            analysis_id,
                            source,
                            indicator,
                            value,
                            clamp(confidence),
                            geom_json,
                            geom_json,
                            Jsonb(dict(properties or {})),
                        ),
                    )
            except Exception:
                pass
        return observation

    def list_observations(self, limit: int = 200) -> dict[str, Any]:
        bounded = max(1, min(int(limit), 1000))
        if self.database_url and psycopg is not None:
            try:
                with self._connect() as conn:
                    rows = conn.execute(
                        """
                        SELECT
                            id::text AS id,
                            source,
                            indicator,
                            value,
                            confidence,
                            session_id,
                            analysis_id::text AS analysis_id,
                            properties,
                            CASE WHEN geom IS NULL THEN NULL
                                 ELSE ST_AsGeoJSON(geom)::jsonb END AS geometry
                        FROM angelus_geoint.observations
                        ORDER BY created_at DESC
                        LIMIT %s
                        """,
                        (bounded,),
                    ).fetchall()
                    return {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "id": row["id"],
                                "type": "Feature",
                                "geometry": row["geometry"],
                                "properties": {
                                    "source": row["source"],
                                    "indicator": row["indicator"],
                                    "value": row["value"],
                                    "confidence": row["confidence"],
                                    "session_id": row["session_id"],
                                    "analysis_id": row["analysis_id"],
                                    **dict(row["properties"] or {}),
                                },
                            }
                            for row in rows
                        ],
                    }
            except Exception:
                pass
        with self._lock:
            features = list(reversed(tuple(self._observations.values())))[:bounded]
        return {"type": "FeatureCollection", "features": features}

    def intersection(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        """Return exact PostGIS geometry intersection."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    ST_IsEmpty(g) AS empty,
                    CASE WHEN ST_IsEmpty(g) THEN NULL
                         ELSE ST_AsGeoJSON(g)::jsonb END AS geometry
                FROM (
                    SELECT ST_Intersection(
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326),
                        ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)
                    ) AS g
                ) q
                """,
                (json.dumps(left), json.dumps(right)),
            ).fetchone()
            return {
                "mode": "postgis",
                "empty": bool(row["empty"]),
                "geometry": row["geometry"],
            }


__all__ = [
    "GeoIntError",
    "GeoIntService",
    "PostGISUnavailable",
    "DEFAULT_DROUGHT_WEIGHTS",
    "drought_level",
    "drought_score",
    "geometry_bbox",
    "geometry_contains_point",
    "geometry_representative_point",
]

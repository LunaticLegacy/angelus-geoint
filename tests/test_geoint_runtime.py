"""Composition and persistence tests for the core-owned GEOINT runtime."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore
from angelus.geoint import CatalogError, GeoIntToolProvider, MapPresentationStore, map_representation


def _editable(*, zoom: float = 7, title: str = "") -> dict[str, object]:
    return {
        "viewport": {"projection": "EPSG:3857", "center": [108.95, 34.27], "zoom": zoom, "rotation": 0},
        "groups": [],
        "layers": [],
    }


class GeoIntRuntimeTests(unittest.TestCase):
    def test_representation_projection_never_advertises_unimplemented_xyz(self):
        vector = map_representation({"format": "GeoJSON", "metadata": {}}, asset_id="asset_vector")
        raster = map_representation({"format": "GeoTIFF", "metadata": {}}, asset_id="asset_raster")
        self.assertEqual(vector["kind"], "vector")
        self.assertEqual(raster["kind"], "cog")
        with self.assertRaises(CatalogError):
            map_representation({"format": "Shapefile", "metadata": {"render_source_kinds": ["xyz"]}}, asset_id="asset_shape")

    def test_nondefault_core_root_is_shared_by_http_and_agent_tools(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            state_root = temporary / "isolated-state"
            core = AngelusCore(state_root=state_root)
            provider = GeoIntToolProvider(core)

            self.assertIs(provider.runtime, core.geoint_runtime)
            self.assertIs(provider.catalog, core.geoint_runtime.catalog)
            self.assertIs(provider.derivations, core.geoint_runtime.derivations)
            self.assertIs(provider.presentation, core.geoint_runtime.presentation)
            self.assertEqual(provider.downloads, state_root / "geoint" / "downloads")

            app = FastAPI()
            include_api_routes(app, core)
            client = TestClient(app)
            response = client.post(
                "/api/geoint/observations",
                json={"source": "test", "indicator": "ndvi", "session_id": "session-runtime"},
            )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(
                core.geoint_runtime.service.list_observations()["features"][0]["properties"]["session_id"],
                "session-runtime",
            )
            self.assertFalse((temporary / ".angelus-state").exists())

    def test_presentation_put_and_proposal_are_session_locked_and_atomic(self):
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            store = MapPresentationStore(temporary / "state")
            session_id = "session-presentation"
            store.put(session_id, _editable(zoom=6))
            store.propose(session_id, _editable(zoom=8))

            def update_user(index: int) -> None:
                store.put(session_id, _editable(zoom=6 + (index % 10)))

            def update_agent(index: int) -> None:
                store.propose(session_id, _editable(zoom=10 + (index % 10)))

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(update_user, item) for item in range(32)]
                futures += [executor.submit(update_agent, item) for item in range(32)]
                for future in futures:
                    future.result()

            path = temporary / "state" / "sessions" / session_id / "map-presentation.json"
            persisted = json.loads(path.read_text(encoding="utf-8"))
            document = store.get(session_id)
            self.assertEqual(persisted["schema_version"], 2)
            self.assertEqual(document["user_overrides"]["viewport"]["projection"], "EPSG:3857")
            self.assertEqual(document["agent_proposal"]["viewport"]["projection"], "EPSG:3857")

    def test_user_can_remove_layer_reference_without_deleting_its_asset(self):
        with TemporaryDirectory() as directory:
            store = MapPresentationStore(Path(directory) / "state")
            session_id = "session-layer-removal"
            layer = {
                "id": "layer_vegetation", "asset_id": "asset_vegetation", "title": "植被指数",
                "source": {}, "visible": True, "opacity": 1, "z_index": 1,
                "min_zoom": None, "max_zoom": None, "render": {}, "attribute_view": {},
            }
            store.propose(session_id, {**_editable(), "layers": [layer]})
            result = store.put(session_id, {**_editable(), "removed_layer_ids": ["layer_vegetation"]})

            self.assertEqual(result["effective"]["layers"], [])
            self.assertEqual(result["user_overrides"]["removed_layer_ids"], ["layer_vegetation"])
            # The map document only keeps a tombstone; it does not own or
            # delete catalog data, which remains the catalog's responsibility.
            self.assertNotIn("asset_vegetation", json.dumps(result["user_overrides"]))


if __name__ == "__main__":
    unittest.main()

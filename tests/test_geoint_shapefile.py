from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from angelus.geoint.ingestion.shapefile import ShapefileError, convert_shapefile_to_geojson, inspect_shapefile, shapefile_groups


class ShapefileBundleTests(unittest.TestCase):
    def test_requires_shp_shx_and_dbf(self):
        with self.assertRaisesRegex(ShapefileError, "missing required members"):
            shapefile_groups([{"file_id": "file_01", "name": "fields.shp"}])

    def test_validates_one_same_stem_bundle(self):
        groups = shapefile_groups([
            {"file_id": "file_01", "name": "FIELDS.SHP"},
            {"file_id": "file_02", "name": "fields.shx"},
            {"file_id": "file_03", "name": "fields.dbf"},
            {"file_id": "file_04", "name": "fields.prj"},
        ])
        self.assertEqual(len(groups), 1)

    @unittest.skipUnless(__import__("importlib").util.find_spec("osgeo"), "GDAL/OGR is optional")
    def test_inspects_and_converts_managed_bundle(self):
        from osgeo import ogr, osr
        with TemporaryDirectory() as raw, TemporaryDirectory() as output:
            root = Path(raw)
            reference = osr.SpatialReference(); reference.ImportFromEPSG(4326)
            dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(root / "field.shp"))
            layer = dataset.CreateLayer("field", reference, ogr.wkbPoint)
            layer.CreateField(ogr.FieldDefn("crop", ogr.OFTString))
            feature = ogr.Feature(layer.GetLayerDefn()); feature.SetField("crop", "maize")
            point = ogr.Geometry(ogr.wkbPoint); point.AddPoint(108.95, 34.27); feature.SetGeometry(point); layer.CreateFeature(feature)
            feature = None; dataset = None
            members = [{"file_id": f"file_{index:02}", "name": path.name, "path": path} for index, path in enumerate(sorted(root.glob("field.*")), 1)]
            candidate = inspect_shapefile(members, dataset_id="dataset_01", name="field.shp")
            target = Path(output) / "field.geojson"
            convert_shapefile_to_geojson(members, target)
            self.assertEqual(candidate["format"], "Shapefile")
            self.assertEqual(candidate["fields"][0]["name"], "crop")
            self.assertTrue(target.is_file())

    @unittest.skipUnless(__import__("importlib").util.find_spec("osgeo"), "GDAL/OGR is optional")
    def test_converts_complete_bundle_without_prj(self):
        """A missing CRS is a warning, not a reason to reject valid geometry."""
        from osgeo import ogr
        with TemporaryDirectory() as raw, TemporaryDirectory() as output:
            root = Path(raw)
            dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(root / "province.shp"))
            layer = dataset.CreateLayer("province", None, ogr.wkbPoint)
            feature = ogr.Feature(layer.GetLayerDefn()); point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(108.95, 34.27); feature.SetGeometry(point); layer.CreateFeature(feature)
            feature = None; dataset = None
            members = [{"file_id": f"file_{index:02}", "name": path.name, "path": path} for index, path in enumerate(sorted(root.glob("province.*")), 1)]
            self.assertFalse(any(Path(item["name"]).suffix.lower() == ".prj" for item in members))
            target = Path(output) / "province.geojson"
            convert_shapefile_to_geojson(members, target)
            self.assertTrue(target.is_file())

    @unittest.skipUnless(__import__("importlib").util.find_spec("osgeo"), "GDAL/OGR is optional")
    def test_infers_web_mercator_for_missing_prj_with_metre_coordinates(self):
        """A common GIS export remains visible rather than becoming invalid GeoJSON."""
        from osgeo import ogr
        import json
        with TemporaryDirectory() as raw, TemporaryDirectory() as output:
            root = Path(raw)
            dataset = ogr.GetDriverByName("ESRI Shapefile").CreateDataSource(str(root / "province.shp"))
            layer = dataset.CreateLayer("province", None, ogr.wkbPoint)
            feature = ogr.Feature(layer.GetLayerDefn()); point = ogr.Geometry(ogr.wkbPoint)
            point.AddPoint(12_025_080, 3_810_415); feature.SetGeometry(point); layer.CreateFeature(feature)
            feature = None; dataset = None
            members = [{"file_id": f"file_{index:02}", "name": path.name, "path": path} for index, path in enumerate(sorted(root.glob("province.*")), 1)]
            target = Path(output) / "province.geojson"
            convert_shapefile_to_geojson(members, target)
            longitude, latitude = json.loads(target.read_text(encoding="utf-8"))["features"][0]["geometry"]["coordinates"]
            self.assertLess(abs(longitude), 180)
            self.assertLess(abs(latitude), 90)

"""Geometrías sintéticas SOLO para pruebas; no son lugares reales."""

import json
import unittest
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import Point, mapping, shape

from visor.datos import (DataError, Layer, coverage_geometry, import_points,
                         read_geojson, safe_data_path, transform, validate_boundary)


def encoded(features, crs=None):
    data = {"type": "FeatureCollection", "features": features}
    if crs:
        data["crs"] = {"type": "name", "properties": {"name": crs}}
    return json.dumps(data).encode()


def feature(geometry, properties=None):
    return {"type": "Feature", "geometry": geometry, "properties": properties or {}}


BOUNDARY = {"type": "Polygon", "coordinates": [[[-74.1, 4.5], [-74.09, 4.5], [-74.09, 4.51], [-74.1, 4.51], [-74.1, 4.5]]]}


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.boundary = validate_boundary(encoded([feature(BOUNDARY, {"SCACODIGO": "001405"})]))
        self.layer = Layer(id="prueba", title="Datos sintéticos de prueba")

    def test_requires_exact_official_code(self):
        for wrong in ["001406", "1405", 1405]:
            with self.assertRaises(DataError):
                validate_boundary(encoded([feature(BOUNDARY, {"SCACODIGO": wrong})]))

    def test_includes_boundary_point_and_rejects_outside(self):
        content = encoded([feature(mapping(Point(-74.095, 4.505))), feature(mapping(Point(-74.1, 4.505))), feature(mapping(Point(-74.08, 4.505)))])
        result = import_points(content, "p.geojson", self.layer, self.boundary)
        self.assertEqual(len(result.points), 2)
        self.assertEqual(result.outside, 1)

    def test_polygon_hole_excludes_point(self):
        outer = BOUNDARY["coordinates"][0]
        hole = [[-74.097, 4.502], [-74.093, 4.502], [-74.093, 4.508], [-74.097, 4.508], [-74.097, 4.502]]
        boundary = validate_boundary(encoded([feature({"type": "Polygon", "coordinates": [outer, hole]}, {"SCACODIGO": "001405"})]))
        result = import_points(encoded([feature(mapping(Point(-74.095, 4.505)))]), "p.geojson", self.layer, boundary)
        self.assertEqual(result.outside, 1)

    def test_csv_decimal_comma_and_quoted_delimiters(self):
        content = 'nombre;longitud;latitud\n"Nombre con ""comillas""; y separador";-74,095;4,505'.encode()
        result = import_points(content, "p.csv", self.layer, self.boundary)
        self.assertEqual(result.points[0]["nombre"], 'Nombre con "comillas"; y separador')
        self.assertEqual(result.points[0]["longitud"], -74.095)

    def test_invalid_row_does_not_abort_valid_rows(self):
        rows = [feature(mapping(Point(-74.095, 4.505))), feature({"type": "Point", "coordinates": ["no", 4.5]}), feature(None)]
        result = import_points(encoded(rows), "p.geojson", self.layer, self.boundary)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(len(result.rejected), 2)

    def test_swapped_axes_rejected(self):
        result = import_points(encoded([feature(mapping(Point(4.505, -74.095)))]), "p.geojson", self.layer, self.boundary)
        self.assertEqual(len(result.rejected), 1)

    def test_declared_crs_reprojected(self):
        project = Transformer.from_crs(4326, 3857, always_xy=True).transform
        geom = mapping(transform(project, Point(-74.095, 4.505)))
        result = import_points(encoded([feature(geom)], "EPSG:3857"), "p.geojson", self.layer, self.boundary)
        self.assertAlmostEqual(result.points[0]["longitud"], -74.095, places=8)

    def test_unknown_crs_fails_explicitly(self):
        with self.assertRaises(DataError):
            read_geojson(encoded([], "EPSG:999999"))

    def test_reprojection_rejects_only_invalid_geometry(self):
        project = Transformer.from_crs(4326, 3857, always_xy=True).transform
        valid = mapping(transform(project, Point(-74.095, 4.505)))
        result = import_points(encoded([feature(valid), feature({"type": "Point", "coordinates": ["bad", "bad"]})], "EPSG:3857"), "p.geojson", self.layer, self.boundary)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(len(result.rejected), 1)

    def test_polygon_is_clipped_without_centroid(self):
        polygon = {"type": "Polygon", "coordinates": [[[-74.101, 4.502], [-74.095, 4.502], [-74.095, 4.508], [-74.101, 4.508], [-74.101, 4.502]]]}
        result = import_points(encoded([feature(polygon)]), "p.geojson", self.layer, self.boundary)
        self.assertIsNone(result.points[0]["longitud"])
        self.assertTrue(shape(self.boundary["features"][0]["geometry"]).covers(shape(result.points[0]["geometría"])))

    def test_nearby_is_labeled_outside_sector(self):
        content = encoded([feature(mapping(Point(-74.089, 4.505)))])
        result = import_points(content, "p.geojson", self.layer, self.boundary, 300)
        self.assertEqual(len(result.points), 1)
        self.assertEqual(result.points[0]["ubicación"], "Cercano (fuera del sector)")
        self.assertTrue(100 < result.points[0]["distancia_sector_m"] < 120)
        self.assertGreater(coverage_geometry(self.boundary, 300).area, shape(BOUNDARY).area)

    def test_catalog_path_cannot_escape_data(self):
        with self.assertRaises(DataError):
            safe_data_path(Path.cwd(), "../privado.json")


if __name__ == "__main__":
    unittest.main()

"""Core independiente de Streamlit: no realiza solicitudes al importar."""

from __future__ import annotations

import csv
import io
import json
import math
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union
from shapely import transform as transform_coordinates
from shapely.errors import ShapelyError
from pyproj import CRS, Transformer

SECTOR_CODE = "001405"
BOUNDARY_SERVICE = "https://serviciosgis.catastrobogota.gov.co/arcgis/rest/services/Mapa_Referencia/Mapa_Referencia/MapServer/37"
BOUNDARY_QUERY = BOUNDARY_SERVICE + "/query?" + urlencode({
    "where": "SCACODIGO='001405'", "outFields": "SCACODIGO,SCANOMBRE",
    "outSR": "4326", "returnGeometry": "true", "f": "geojson",
})
CATEGORIES = ["Comercio", "Gastronomía", "Mercados", "Parques", "Droguerías", "Cultura", "Seguridad / CAI", "Transporte", "Otros"]


def transform(function, geometry):
    return transform_coordinates(geometry, function, interleaved=False)


class DataError(ValueError):
    """Error de datos que puede mostrarse al usuario sin traceback."""


@dataclass
class Layer:
    id: str
    title: str
    agency: str = ""
    url: str = ""
    date: str = "No informada"
    category: str = "Otros"
    path: str = ""
    longitude: str = "longitud"
    latitude: str = "latitud"
    notes: str = ""
    category_field: str = ""
    name_field: str = ""
    address_field: str = ""
    encoding: str = "utf-8-sig"
    license: str = "No informada"
    role: str = "poi"
    missing_name_values: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    points: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)
    outside: int = 0
    total: int = 0


def normalize(value: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c)).lower().strip()


def _lookup(props: dict, aliases: list[str], default: str = "", *, ignored_values: tuple[str, ...] = ()) -> str:
    keys = {normalize(k): k for k in props}
    for alias in aliases:
        if alias in keys and props[keys[alias]] is not None:
            value = str(props[keys[alias]]).strip()
            if value and value not in ignored_values:
                return value
    return default


def read_geojson(content: bytes) -> dict:
    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DataError("El archivo debe ser un GeoJSON UTF-8 válido.") from exc
    if not isinstance(data, dict):
        raise DataError("Se esperaba un objeto GeoJSON.")
    if "error" in data:
        raise DataError(f"El servicio devolvió un error: {data['error']}")
    crs = data.get("crs")
    transformer = None
    if crs:
        if not isinstance(crs, dict) or not isinstance(crs.get("properties"), dict):
            raise DataError("La declaración de CRS no tiene un formato reconocido.")
        name = str(crs.get("properties", {}).get("name", "")).upper()
        if name not in {"EPSG:4326", "URN:OGC:DEF:CRS:OGC:1.3:CRS84", "OGC:CRS84", "CRS84", "URN:OGC:DEF:CRS:EPSG::4326"}:
            try:
                origin = CRS.from_user_input(name)
                transformer = Transformer.from_crs(origin, "EPSG:4326", always_xy=True)
            except Exception as exc:
                raise DataError(f"CRS no admitido ({name or 'desconocido'}). Reproyecta a EPSG:4326 / CRS84 antes de importar.") from exc
    if data.get("type") == "Feature":
        data = {"type": "FeatureCollection", "features": [data]}
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise DataError("El GeoJSON debe contener FeatureCollection o Feature.")
    if transformer:
        for feature in data["features"]:
            if isinstance(feature, dict) and feature.get("geometry"):
                try:
                    feature["geometry"] = mapping(transform(transformer.transform, shape(feature["geometry"])))
                except Exception:
                    feature["_import_error"] = "No se pudo transformar la geometría del CRS declarado a EPSG:4326"
        data.pop("crs", None)
    return data


def validate_boundary(content: bytes, code_field: str = "SCACODIGO") -> dict:
    data = read_geojson(content)
    selected = []
    for feature in data["features"]:
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        if not isinstance(props, dict):
            continue
        code = str(props.get(code_field, "")).strip()
        if code != SECTOR_CODE:
            continue
        try:
            geom = shape(feature.get("geometry"))
        except Exception as exc:
            raise DataError("El límite del sector tiene una geometría ilegible.") from exc
        if geom.geom_type not in {"Polygon", "MultiPolygon"} or geom.is_empty or not geom.is_valid:
            raise DataError("El límite 001405 debe tener un polígono válido y no vacío.")
        _validate_bounds(geom.bounds)
        selected.append(geom)
    if not selected:
        raise DataError(f"No se encontró un polígono con {code_field} = '001405'. Se conserva el cero inicial del código.")
    combined = unary_union(selected)
    return {"type": "FeatureCollection", "features": [{
        "type": "Feature", "geometry": mapping(combined),
        "properties": {"SCACODIGO": SECTOR_CODE, "SCANOMBRE": "20 DE JULIO"},
    }]}


def _validate_bounds(bounds: tuple) -> None:
    if len(bounds) != 4 or not all(math.isfinite(x) for x in bounds) or not (-180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90):
        raise DataError("Coordenadas fuera de EPSG:4326: orden longitud, latitud, en grados.")
    # Esta aplicación es local: previene interpretar metros o ejes intercambiados como Bogotá.
    if not (-75 <= bounds[0] <= bounds[2] <= -73 and 3 <= bounds[1] <= bounds[3] <= 6):
        raise DataError("Las coordenadas no corresponden al entorno de Bogotá. Comprueba CRS y orden longitud/latitud.")


def fetch_boundary(timeout: float = 20) -> tuple[dict, str]:
    request = Request(BOUNDARY_QUERY, headers={"User-Agent": "Visor20Julio/1.0", "Accept": "application/geo+json,application/json"})
    with urlopen(request, timeout=timeout) as response:
        content = response.read(10_000_001)
    if len(content) > 10_000_000:
        raise DataError("La respuesta del límite excede el tamaño admitido.")
    return validate_boundary(content), datetime.now(timezone.utc).isoformat(timespec="seconds")


def coverage_geometry(boundary: dict, radius_m: float = 0):
    polygon = shape(boundary["features"][0]["geometry"])
    if not radius_m:
        return polygon
    forward = Transformer.from_crs("EPSG:4326", "EPSG:3116", always_xy=True).transform
    backward = Transformer.from_crs("EPSG:3116", "EPSG:4326", always_xy=True).transform
    return transform(backward, transform(forward, polygon).buffer(radius_m))


def import_points(content: bytes, filename: str, layer: Layer, boundary: dict, radius_m: float = 0) -> ImportResult:
    result = ImportResult()
    missing_names = tuple(layer.missing_name_values)
    polygon = shape(boundary["features"][0]["geometry"])
    search_area = coverage_geometry(boundary, radius_m if layer.role != "context" else 0)
    project = Transformer.from_crs("EPSG:4326", "EPSG:3116", always_xy=True).transform
    projected_boundary = transform(project, polygon)
    if filename.lower().endswith(".csv"):
        try:
            decoded = content.decode(layer.encoding)
            dialect = csv.Sniffer().sniff(decoded.splitlines()[0], delimiters=",;\t")
            rows = list(csv.DictReader(io.StringIO(decoded), dialect=dialect, doublequote=True))
        except (UnicodeError, csv.Error) as exc:
            raise DataError("El CSV debe ser UTF-8 y usar coma, punto y coma o tabulador como separador.") from exc
        features = [{"type": "Feature", "properties": row, "geometry": {"type": "Point", "coordinates": [row.get(layer.longitude), row.get(layer.latitude)]}} for row in rows]
    else:
        features = read_geojson(content)["features"]
    for index, feature in enumerate(features, 1):
        result.total += 1
        try:
            if not isinstance(feature, dict) or not isinstance(feature.get("properties") or {}, dict):
                raise DataError("registro sin propiedades válidas")
            if feature.get("_import_error"):
                raise DataError(feature["_import_error"])
            geom = feature.get("geometry") or {}
            if geom.get("type") == "Point":
                coordinates = geom.get("coordinates", [])
                if len(coordinates) < 2:
                    raise DataError("faltan longitud o latitud")
                lon, lat = (float(str(value).strip().replace(",", ".")) for value in coordinates[:2])
                feature_geom = Point(lon, lat)
            else:
                feature_geom = shape(geom)
                if feature_geom.geom_type not in {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}:
                    raise DataError("tipo de geometría no admitido")
                lon, lat = None, None
            if feature_geom.is_empty or not feature_geom.is_valid:
                raise DataError("geometría vacía o inválida")
            _validate_bounds(feature_geom.bounds)
            if not search_area.intersects(feature_geom):
                result.outside += 1
                continue
            props = feature.get("properties") or {}
            name = _lookup(
                props,
                [normalize(layer.name_field), "nombre", "name", "nom_establecimiento",
                 "nombre_establecimiento", "nombre_comercial", "razon_social", "razon social",
                 "nombresitio", "nombre_equipamiento", "nom_equipam"],
                "Sin nombre informado",
                ignored_values=missing_names,
            )
            address = _lookup(props, [normalize(layer.address_field), "direccion", "dirección", "address", "direcc", "dir", "direccion_establecimiento", "direccion_comercial"], "No informada")
            category = str(props.get(layer.category_field, layer.category) or layer.category)
            inside = polygon.intersects(feature_geom)
            result.points.append({"nombre": name, "categoría": category, "dirección": address,
                "fuente": layer.title, "entidad": layer.agency, "fecha_dato": layer.date,
                "url_fuente": layer.url, "longitud": lon, "latitud": lat, "capa": layer.id,
                "geometría": mapping(feature_geom.intersection(search_area)), "tipo_geometría": feature_geom.geom_type, "rol": layer.role,
                "ubicación": "Sector 001405" if inside else "Cercano (fuera del sector)",
                "distancia_sector_m": 0 if inside else round(projected_boundary.distance(transform(project, feature_geom)), 1)})
        except (DataError, TypeError, ValueError, IndexError, KeyError, AttributeError, ShapelyError) as exc:
            result.rejected.append(f"Registro {index}: {exc}")
    return result


def load_catalog(root: Path) -> tuple[dict, list[Layer]]:
    path = root / "data" / "catalogo.json"
    if not path.exists():
        return {}, []
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        layers = [Layer(**entry) for entry in raw.get("layers", [])]
        return raw.get("boundary", {}), layers
    except (ValueError, TypeError, OSError) as exc:
        raise DataError(f"No se pudo leer data/catalogo.json: {exc}") from exc


def safe_data_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to((root / "data").resolve()):
        raise DataError("Las rutas del catálogo deben permanecer dentro de data/.")
    return path

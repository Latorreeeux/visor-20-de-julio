"""Mapa HTML autocontenido, sin teselas ni recursos externos."""

from html import escape
from pathlib import Path

import folium
from branca.element import Element
from shapely.geometry import mapping
from visor.datos import coverage_geometry

COLORS = {"Comercio": "#c35a24", "Gastronomía": "#c35a24", "Mercados": "#986022", "Parques": "#27834c", "Droguerías": "#a64c89", "Cultura": "#7452b8", "Seguridad / CAI": "#285fc1", "Transporte": "#b58413", "Otros": "#527077"}


def build_map(boundary: dict, records: list[dict], root: Path, radius: int = 0) -> str:
    assets = root / "assets" / "leaflet"
    map_view = folium.Map(tiles=None, control_scale=True, prefer_canvas=True, zoom_control=True)
    map_view.default_js = []
    map_view.default_css = []
    header = map_view.get_root().header
    header.add_child(Element("<style>" + (assets / "leaflet.css").read_text(encoding="utf-8") + "\n.leaflet-container{background:#e9eeeb;font-family:system-ui,sans-serif}.leaflet-popup-content{max-width:310px;overflow-wrap:anywhere}.leaflet-control-layers-toggle{background-image:none!important;width:64px!important;height:34px!important;text-decoration:none;display:flex;align-items:center;justify-content:center}.leaflet-control-layers-toggle:after{content:'Capas';font:600 13px system-ui;color:#183e33}.leaflet-control-layers-expanded{max-width:min(330px,70vw);max-height:440px;overflow:auto}td,th{text-align:left;padding:3px;vertical-align:top}th{font-weight:600}</style>"))
    header.add_child(Element("<script>" + (assets / "leaflet.js").read_text(encoding="utf-8") + "</script>"))
    folium.GeoJson(boundary, name="Límite catastral 001405", style_function=lambda _: {"color": "#183e33", "weight": 3, "fillColor": "#f8fbf9", "fillOpacity": 0.65}, tooltip="Sector catastral 001405 · 20 de Julio").add_to(map_view)
    if radius:
        folium.GeoJson(mapping(coverage_geometry(boundary, radius)), name="Cercanía: 300 m", style_function=lambda _: {"color": "#7d8580", "weight": 2, "dashArray": "6 6", "fillOpacity": 0}).add_to(map_view)
    layers: dict[str, list] = {}
    for row in sorted(records, key=lambda row: row["rol"] != "context"):
        layers.setdefault(row["fuente"], []).append(row)
    for source, rows in layers.items():
        features = []
        for row in rows:
            props = {k: escape(str(v)) for k, v in row.items() if k in {"nombre", "categoría", "dirección", "fuente", "entidad", "fecha_dato", "url_fuente", "ubicación", "distancia_sector_m"}}
            props["color"] = COLORS.get(row["categoría"], COLORS["Otros"])
            props["contexto"] = row["rol"] == "context"
            features.append({"type": "Feature", "properties": props, "geometry": row["geometría"]})
        folium.GeoJson({"type": "FeatureCollection", "features": features}, name=escape(source),
            marker=folium.CircleMarker(radius=7, weight=2, fill=True, fill_opacity=0.9),
            style_function=lambda feature: {"color": "#9aa6a0" if feature["properties"]["contexto"] else feature["properties"]["color"], "weight": 2, "fillColor": feature["properties"]["color"], "fillOpacity": 0.85 if feature["geometry"]["type"] == "Point" else 0.3},
            highlight_function=lambda _: {"weight": 4},
            tooltip=folium.GeoJsonTooltip(fields=["nombre"], labels=False),
            popup=folium.GeoJsonPopup(fields=["nombre", "categoría", "ubicación", "distancia_sector_m", "dirección", "fuente", "entidad", "fecha_dato", "url_fuente"], aliases=["Nombre", "Categoría", "Ubicación", "Distancia al sector (m)", "Dirección", "Fuente", "Entidad", "Fecha del dato", "Enlace fuente"], localize=False, max_width=400),
        ).add_to(map_view)
    folium.LayerControl(collapsed=True).add_to(map_view)
    categories = sorted({r["categoría"] for r in records if r["rol"] != "context"})
    legend = "".join(f'<div><span style="display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;background:{COLORS.get(category, COLORS["Otros"])}"></span>{escape(category)}</div>' for category in categories)
    map_view.get_root().html.add_child(Element('<div style="position:fixed;bottom:28px;left:12px;z-index:999;background:rgba(255,255,255,.95);padding:10px 12px;border-radius:7px;font:12px/1.7 system-ui;box-shadow:0 1px 5px #0002"><strong>Categorías</strong>' + legend + '</div>'))
    from shapely.geometry import shape
    minx, miny, maxx, maxy = coverage_geometry(boundary, radius).bounds
    map_view.fit_bounds([[miny, minx], [maxy, maxx]], padding=(25, 25))
    return map_view.get_root().render()

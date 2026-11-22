"""Ejecutar: python -m streamlit run app.py"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from urllib.error import HTTPError, URLError

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from visor.datos import (BOUNDARY_QUERY, CATEGORIES, DataError, Layer, fetch_boundary,
                         import_points, load_catalog, normalize, safe_data_path,
                         validate_boundary)
from visor.mapa import COLORS, build_map

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="20 de Julio · Visor oficial", page_icon="📍", layout="wide")
st.title("20 de Julio")
st.markdown("**Comercios y lugares de interés · sector catastral 001405 · San Cristóbal, Bogotá**")
st.caption("Fuentes públicas gubernamentales. La cobertura depende de cada inventario y su fecha; no representa todos los establecimientos del barrio.")


@st.cache_data(show_spinner=False)
def parse_boundary(content: bytes, field: str = "SCACODIGO"):
    return validate_boundary(content, field)


@st.cache_data(show_spinner=False)
def parse_points(content: bytes, filename: str, metadata: dict, boundary: dict, radius: int):
    return import_points(content, filename, Layer(**metadata), boundary, radius)


try:
    boundary_info, catalog_layers = load_catalog(ROOT)
except DataError as exc:
    st.error(str(exc))
    boundary_info, catalog_layers = {}, []

boundary = None
boundary_label = "Sin límite cargado"
with st.sidebar:
    st.header("Área de consulta")
    proximity = st.checkbox("Incluir cercanos hasta 300 m del sector", value=True)
    radius = 300 if proximity else 0
    st.caption("Los lugares cercanos quedan identificados como fuera del sector; la distancia se mide al contorno, no por recorrido peatonal.")
    st.header("Límite del sector")
    st.caption("El código oficial 001405 es obligatorio para activar el filtro espacial.")
    if st.button("Actualizar límite desde Catastro", width="stretch"):
        try:
            with st.spinner("Consultando Catastro…"):
                downloaded, timestamp = fetch_boundary()
            st.session_state["online_boundary"] = (downloaded, timestamp)
            st.success("Límite verificado y actualizado para esta sesión.")
        except (DataError, URLError, HTTPError, TimeoutError, OSError) as exc:
            st.error(f"No se pudo consultar el servicio: {exc}. Puedes usar el archivo local o importar un GeoJSON oficial.")
    uploaded_boundary = st.file_uploader("Importar límite oficial", type=["geojson", "json"], key="boundary_file")
    code_field = st.text_input("Campo del código catastral", value="SCACODIGO") if uploaded_boundary else "SCACODIGO"
    st.header("Agregar capa oficial")
    point_uploads = st.file_uploader("GeoJSON o CSV", type=["geojson", "json", "csv"], accept_multiple_files=True, key="poi_files")
    st.caption("GeoJSON: CRS declarado o coordenadas RFC 7946 (longitud, latitud WGS84). CSV: columnas geográficas en grados, UTF-8 o Windows-1252.")
    st.caption("Las cargas permanecen en la sesión; no se escriben al catálogo.")

try:
    if uploaded_boundary:
        boundary = parse_boundary(uploaded_boundary.getvalue(), code_field)
        boundary_label = f"Archivo aportado: {uploaded_boundary.name} · procedencia aportada por el usuario"
    elif "online_boundary" in st.session_state:
        boundary, timestamp = st.session_state["online_boundary"]
        boundary_label = f"Catastro Bogotá · consulta {timestamp}"
    elif boundary_info.get("path"):
        boundary = parse_boundary(safe_data_path(ROOT, boundary_info["path"]).read_bytes())
        boundary_label = f"{boundary_info.get('title', 'Límite oficial local')} · {boundary_info.get('date', 'fecha no informada')}"
except (DataError, OSError) as exc:
    st.error(f"Límite no disponible: {exc}")

st.caption(boundary_label)
all_records = []
layer_status = []
for layer in catalog_layers:
    if boundary is None:
        layer_status.append((layer, None, "Pendiente: se necesita el límite validado"))
        continue
    try:
        file_path = safe_data_path(ROOT, layer.path)
        result = parse_points(file_path.read_bytes(), file_path.name, asdict(layer), boundary, radius)
        all_records.extend(result.points)
        layer_status.append((layer, result, "Archivo oficial local"))
    except (DataError, OSError) as exc:
        layer_status.append((layer, None, str(exc)))

for index, upload in enumerate(point_uploads):
    with st.sidebar.expander(f"Configurar {upload.name}", expanded=True):
        title = st.text_input("Fuente / título", value=upload.name, key=f"title{index}")
        agency = st.text_input("Entidad pública", key=f"agency{index}")
        url = st.text_input("URL de la fuente oficial", key=f"url{index}")
        date = st.text_input("Fecha del inventario", value="No informada", key=f"date{index}")
        category = st.selectbox("Categoría", CATEGORIES, key=f"category{index}")
        name_field = st.text_input("Campo de nombre (opcional)", key=f"name{index}")
        address_field = st.text_input("Campo de dirección (opcional)", key=f"address{index}")
        encoding, longitude, latitude = "utf-8-sig", "longitud", "latitud"
        if upload.name.lower().endswith(".csv"):
            longitude = st.text_input("Columna longitud", value="longitud", key=f"lon{index}")
            latitude = st.text_input("Columna latitud", value="latitud", key=f"lat{index}")
            encoding = st.selectbox("Codificación CSV", ["utf-8-sig", "cp1252"], key=f"encoding{index}")
    layer = Layer(id=f"upload{index}", title=title, agency=agency, url=url, date=date, category=category,
                  longitude=longitude, latitude=latitude, encoding=encoding, name_field=name_field, address_field=address_field)
    if boundary is None:
        layer_status.append((layer, None, "Pendiente: se necesita el límite validado"))
    elif not agency.strip() or not url.startswith("https://"):
        layer_status.append((layer, None, "Completa entidad pública y URL https de procedencia para importar"))
    else:
        try:
            result = parse_points(upload.getvalue(), upload.name, asdict(layer), boundary, radius)
            all_records.extend(result.points)
            layer_status.append((layer, result, "Archivo aportado; procedencia declarada por el usuario"))
        except DataError as exc:
            layer_status.append((layer, None, str(exc)))

pois = [row for row in all_records if row["rol"] != "context"]
context = [row for row in all_records if row["rol"] == "context"]
filter_columns = st.columns([2, 2, 3])
with filter_columns[0]:
    query = st.text_input("Buscar nombre o dirección", placeholder="Ej. plaza, droguería…")
with filter_columns[1]:
    categories = sorted({row["categoría"] for row in pois})
    selected_categories = st.multiselect("Categorías", categories, default=categories)
with filter_columns[2]:
    sources = list(dict.fromkeys(row["fuente"] for row in pois))
    selected_sources = st.multiselect("Fuentes", sources, default=sources)
selected = [row for row in pois if row["categoría"] in selected_categories and row["fuente"] in selected_sources
            and normalize(query) in normalize(row["nombre"] + " " + row["dirección"])]
metrics = st.columns(3)
metrics[0].metric("Lugares visibles", len(selected))
metrics[1].metric("Registros que intersectan el sector", sum(r["ubicación"] == "Sector 001405" for r in pois))
metrics[2].metric("Registros cercanos fuera del sector", sum(r["ubicación"] != "Sector 001405" for r in pois))

if boundary:
    context_enabled = st.checkbox("Mostrar cartografía oficial de contexto", value=True) if context else False
    rendered_map = build_map(boundary, selected + (context if context_enabled else []), ROOT, radius)
    if hasattr(st, "iframe"):
        st.iframe(rendered_map, height=620, alt="Mapa interactivo de fuentes oficiales del sector 001405 y su cercanía")
    else:
        components.html(rendered_map, height=620, scrolling=False)
    st.caption("Sin mapa base de teselas. Contorno oscuro: sector catastral oficial; contorno discontinuo: área adicional de 300 m, cuando se activa. Se incluyen puntos sobre el borde y se recortan las demás geometrías al área de consulta. Pulsa cada lugar para ver su fuente y su ubicación dentro o fuera del sector.")
    if selected:
        st.caption(" · ".join(f"{category}" for category in sorted({row['categoría'] for row in selected})))
    else:
        st.info("No hay lugares con los filtros actuales. Revisa las categorías y fuentes, o importa otra capa oficial.")
    visible_columns = ["nombre", "categoría", "ubicación", "distancia_sector_m", "dirección", "fuente", "entidad", "fecha_dato", "tipo_geometría", "longitud", "latitud", "url_fuente"]
    table = pd.DataFrame(selected, columns=visible_columns)
    st.subheader("Lugares encontrados")
    st.dataframe(table, hide_index=True, width="stretch",
                 column_config={"url_fuente": st.column_config.LinkColumn("Fuente oficial")})
    download_columns = st.columns(3)
    download_columns[0].download_button("Descargar resultados CSV", table.to_csv(index=False).encode("utf-8-sig"), "lugares_001405.csv", "text/csv")
    geojson = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": row["geometría"], "properties": {k: v for k, v in row.items() if k != "geometría"}} for row in selected]}
    download_columns[1].download_button("Descargar resultados GeoJSON", json.dumps(geojson, ensure_ascii=False), "lugares_001405.geojson", "application/geo+json")
    download_columns[2].download_button("Descargar mapa sin conexión", rendered_map, "mapa_001405.html", "text/html")
else:
    st.warning("Carga un límite oficial con código 001405 para habilitar el mapa y la clasificación espacial. No se usan límites aproximados.")

st.subheader("Fuentes, fechas y cobertura")
st.caption("Los registros de distintos inventarios pueden referirse al mismo sitio. El conteo corresponde a registros publicados, sin deduplicación automática. La ausencia de un lugar no significa que no exista. Las fuentes locales son instantáneas de la fecha indicada.")
for layer, result, status in layer_status:
    with st.expander(f"{layer.title} · {len(result.points) if result else 0} en el área de consulta"):
        st.write(f"**Entidad:** {layer.agency or 'No informada'} · **Fecha del dato:** {layer.date}")
        st.write(f"**Estado:** {status} · **Licencia:** {layer.license}")
        if layer.url.startswith("https://"):
            st.link_button("Consultar fuente", layer.url)
        if layer.notes:
            st.info(layer.notes)
        if result:
            count_inside = sum(r["ubicación"] == "Sector 001405" for r in result.points)
            st.write(f"Leídos: {result.total} · Intersectan sector: {count_inside} · Cercanos fuera: {len(result.points) - count_inside} · Fuera del área de consulta: {result.outside} · Inválidos: {len(result.rejected)}")
            if result.rejected:
                st.warning("Se omitieron registros inválidos. No se movieron ni corrigieron coordenadas automáticamente.")
                st.text("\n".join(result.rejected[:20]))
                st.download_button("Descargar incidencias", "\n".join(result.rejected), f"incidencias_{layer.id}.txt", key=f"errors{layer.id}")
        elif status not in {"Pendiente: se necesita el límite validado"}:
            st.warning(status)
with st.expander("Límite catastral y alcance"):
    st.write("El área de consulta es el sector catastral 001405. Un sector catastral y un barrio de uso cotidiano pueden tener límites diferentes. La clasificación utiliza la geometría oficial, no el campo de barrio de cada inventario.")
    st.link_button("Consulta del límite en Catastro Bogotá", BOUNDARY_QUERY)
    st.write("CRS de trabajo: WGS84 (EPSG:4326). Si un GeoJSON declara otro CRS reconocido, se transforma con PROJ. Los archivos sin CRS se interpretan según RFC 7946. Las geometrías y coordenadas inválidas se rechazan.")

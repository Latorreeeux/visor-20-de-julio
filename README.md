# Visor de 20 de Julio

Aplicación Python para explorar comercios y sitios de interés del sector catastral **001405**, en San Cristóbal, Bogotá, y hasta 300 metros de cercanía opcional. Usa datos abiertos gubernamentales locales y permite importar nuevas capas oficiales.

El mapa no utiliza OpenStreetMap. No utiliza teselas ni servicios de mapas externos: dibuja el límite oficial, las vías oficiales y las capas disponibles. Leaflet y sus estilos están incluidos para funcionar sin conexión después de instalar las dependencias.

## Ejecutar en Windows

Requiere Python 3.12. Desde PowerShell en esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Abre la dirección local que imprime Streamlit, normalmente `http://127.0.0.1:8501`. Si el entorno virtual ya está instalado, ejecuta la última línea del bloque anterior. También puedes usar `iniciar.ps1` cuando tu configuración de PowerShell permita ejecutar scripts locales.

Si usas `uv`, la instalación equivalente es:

```powershell
uv --cache-dir .cache/uv venv .venv
uv --cache-dir .cache/uv pip install --python .venv/Scripts/python.exe -r requirements-lock.txt
```

`requirements-lock.txt` fija las versiones verificadas con Python 3.12 en Windows. `requirements.txt` declara las dependencias directas y sus rangos. La instalación requiere internet; el uso normal con los archivos incluidos no lo requiere. Solo el botón **Actualizar límite desde Catastro** consulta un servicio remoto.

## Qué incluye

| Capa | Entidad | Fecha del dato / consulta |
| --- | --- | --- |
| Sector catastral 001405 | Catastro Distrital | Consulta: 2026-11-21 |
| Plazas de mercado | IPES | 2025-02-03 |
| Centros comerciales y plazoletas administrados por IPES | IPES | 2020-10-22 |
| Droguerías y establecimientos farmacéuticos | Secretaría Distrital de Salud | 2024-01-09 |
| Parques y escenarios deportivos | IDRD | 2026-06-30 |
| Inventario turístico | IDT | 2025-05-31 |
| CAI | Secretaría de Seguridad | 2026-07-31 |
| Estaciones troncales | TransMilenio | Consulta: 2026-11-21 |
| Vías de contexto | Mapa de Referencia del Distrito | Consulta: 2026-11-21 |

El catálogo `data/catalogo.json` contiene los enlaces oficiales, entidades, fechas, licencias y campos de cada capa. Los originales o extractos descargados están en `data/oficial/`.

Las fechas de consulta no equivalen a una fecha de actualización de toda la capa. Los inventarios pueden omitir establecimientos, contener información histórica o registrar el mismo sitio varias veces. La capa farmacéutica no confirma que un negocio continúe abierto. El inventario turístico publica ubicaciones aproximadas.

No se incluyó un inventario general de restaurantes: el recurso de gastronomía encontrado contenía registros que no correspondían a la capa anunciada y se excluyó. La plazoleta de comidas aparece en el inventario comercial del IPES. Las categorías solo muestran registros que las fuentes realmente publican.

## Usar el visor

- Busca por nombre o dirección y combina categorías y fuentes.
- Pulsa un punto o geometría para consultar nombre, dirección, fuente, fecha y si queda en el sector o en su cercanía.
- Desactiva **Incluir cercanos hasta 300 m del sector** para limitar la consulta al sector 001405.
- Activa o desactiva las vías oficiales. El control de capas del mapa permite ocultar cada fuente.
- Revisa **Fuentes, fechas y cobertura** para ver registros incluidos, fuera del área e inválidos.
- Descarga los resultados filtrados en CSV o GeoJSON, o el mapa HTML con sus recursos incrustados.

La Plaza de Mercado y el Portal 20 de Julio están cerca del límite catastral, pero sus coordenadas publicadas quedan fuera del polígono. El modo de cercanía permite consultarlos sin presentarlos como parte del sector. Un barrio de uso cotidiano puede tener un contorno diferente del sector catastral.

Los puntos sobre el borde se incluyen. Los parques y otras geometrías se seleccionan por intersección y se recortan al área de consulta; no se sustituyen por centroides. Las distancias de cercanía se calculan en metros con **MAGNA-SIRGAS / Colombia Bogotá zone (EPSG:3116)**, desde la geometría hasta el límite. Son distancias geométricas, no rutas peatonales. Los tramos viales son contexto y no se cuentan como lugares.

## Importar archivos oficiales

La barra lateral permite cargar un límite y nuevas capas sin modificar archivos del proyecto. Cada capa requiere entidad pública y enlace HTTPS de procedencia; el visor muestra esa procedencia como declarada por el usuario, sin certificarla automáticamente.

**Límite:** GeoJSON `FeatureCollection` o `Feature`, con geometría `Polygon` o `MultiPolygon`, campo `SCACODIGO` igual a la cadena `001405`. El campo se puede configurar. Si falta el límite o no pasa la validación, se deshabilita la clasificación espacial; no se genera un contorno aproximado.

**Capas:** GeoJSON con geometrías `Point`, `Polygon`, `MultiPolygon`, `LineString` o `MultiLineString`; o CSV con columnas de longitud y latitud. Se pueden configurar los campos de nombre y dirección. GeoJSON debe usar UTF-8; CSV admite UTF-8 o Windows-1252 y coma, punto y coma o tabulador como separador, incluyendo decimales con coma cuando el delimitador lo permite.

El CRS de trabajo es EPSG:4326, en orden **longitud, latitud**. Un GeoJSON sin CRS se interpreta según RFC 7946; si declara un CRS reconocido por PROJ, se reproyecta. El CSV debe venir en coordenadas geográficas WGS84 en grados. No se adivinan ni intercambian ejes. Se rechazan coordenadas inválidas o ajenas al entorno de Bogotá, y el detalle se puede descargar como informe de incidencias.

Para dejar una capa permanente, guarda su archivo dentro de `data/` y agrega una entrada a `data/catalogo.json`:

```json
{
  "id": "identificador_unico",
  "title": "Título del inventario oficial",
  "agency": "Entidad responsable",
  "url": "https://dominio-oficial.gov.co/enlace-del-recurso",
  "date": "Fecha de publicación verificada",
  "category": "Cultura",
  "path": "data/oficial/nombre_del_archivo.geojson",
  "name_field": "NOMBRE",
  "address_field": "DIRECCION",
  "license": "Licencia publicada",
  "notes": "Alcance y limitaciones de esa fuente"
}
```

La entrada se añade al arreglo `layers`. Para CSV agrega `encoding`, `longitude` y `latitude`. Usa `role: "context"` para cartografía de referencia que no debe contarse como lugares. Las rutas del catálogo se restringen a `data/`. Las cargas desde la interfaz duran solo durante la sesión.

## Verificar

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Las pruebas validan borde, huecos, selección y recorte espacial, reproyección, cercanía, CSV con coma decimal y comillas, rechazo de registros inválidos y protección de rutas del catálogo. Las geometrías sintéticas de `tests/` son exclusivamente pruebas y no se cargan al visor.

La interfaz se verifica con `streamlit.testing.v1.AppTest`, incluyendo arranque sin peticiones de red, búsqueda y alternancia entre sector estricto y cercanía. Los recursos del mapa son locales; su licencia de Leaflet está en `assets/leaflet/LICENSE`. Cada capa conserva su propia atribución y licencia.

# Contrato de la API `/congreso`

Es el acuerdo entre el router `apps/api/src/vigia_api/routers/congreso.py`
(Fase 4) y la sección web `apps/web/app/(app)/congreso/` (Fase 5). Las dos
se construyen en paralelo contra este documento: **si alguna necesita
cambiarlo, se cambia acá primero** y se avisa a la otra.

Datos: tablas de la migración 0012 (`legislador`, `congreso_sesion`,
`votacion`, `voto`, `asunto_tratado`, `reunion_comision`). El cruce con los
proyectos (`norma` tipo PROYECTO) es por solapamiento de expedientes
canónicos (`norma.expedientes && <tabla>.expedientes`, GIN en las dos puntas).

## Convenciones

- **Públicos**, como todos los endpoints de datos: sin auth y sin BFF. El
  gating de la sección es del web (`proxy.js`), no de la API. Prefijo
  `/congreso`, que va en `_CACHEABLE_PREFIXES`.
- Listas: `{ "items": [...], "total": int, "limit": int, "offset": int }`,
  con `limit` 1-100 (default 20) y `offset` 0-100000, igual que `/avisos`.
- `camara`: `"S"` (Senado) | `"D"` (Diputados). Si se omite, las dos.
- Fechas: `fecha` en ISO `YYYY-MM-DD`; `fecha_hora` en ISO 8601 con offset
  (`2026-10-20T10:00:00-03:00`).
- **Nunca se exponen `raw` ni `search_vector`.**
- Un id inexistente da 404 `{"detail": "no_encontrado"}`.
- `q` es FTS español (`plainto_tsquery`) donde la tabla tiene `search_vector`:
  `votacion` y `reunion_comision`. En `legislador` es `ILIKE` sobre el nombre.
- `proyectos` es la lista de normas cruzadas por expediente. Siempre va (vacía
  si no hay cruce), con un máximo de 10 por ítem:

```json
{ "id": 423838, "titulo": "LEY DE MODERNIZACION LABORAL.", "numero": "0010-PE-2026",
  "estado": "Media sanción", "fecha_publicacion": "2026-01-12" }
```

## Endpoints

### `GET /congreso/resumen`
KPIs del hub. Cacheado 300 s (`core.cache.cached`).
```json
{
  "S": { "reuniones_proximas": 4, "votaciones_30d": 12, "sesiones_30d": 3,
         "proyectos_30d": 180, "ultima_sesion": "2026-09-24" },
  "D": { "reuniones_proximas": 5, "votaciones_30d": null, "sesiones_30d": 2,
         "proyectos_30d": 410, "ultima_sesion": "2026-10-07" },
  "actualizado": "2026-10-19T18:00:00+00:00"
}
```
- `votaciones_30d` de `D` es `null`, **no 0**: no hay fuente de voto nominal
  (reCAPTCHA). El web muestra "sin datos", no un cero.
- `proyectos_30d` cuenta las normas PROYECTO de la cámara con
  `fecha_publicacion` en los últimos 30 días: `hcdn_proyectos` para D y
  `senado_proyectos` para S.

### `GET /congreso/agenda`
Parámetros: `camara`, `desde` (default hoy), `hasta` (default desde + 7 días),
`comision` (ILIKE), `q`, `limit`, `offset`. Orden: `fecha_hora ASC`.
```json
{ "items": [ {
    "id": 12, "camara": "S", "fecha_hora": "2026-10-20T10:00:00-03:00",
    "comision": "PRESUPUESTO Y HACIENDA", "sala": "Salón Azul", "tipo": "Reunión",
    "temario": "texto plano (sin HTML)", "expedientes": ["0271-PE-2026"],
    "url_citacion": "https://...pdf", "proyectos": [ ... ]
} ], "total": 9, "limit": 20, "offset": 0 }
```

### `GET /congreso/votaciones`
Parámetros: `camara`, `q`, `desde`, `hasta`, `resultado` (`afirmativo` |
`negativo` | ...), `expediente` (cualquier forma: se normaliza con
`normalizar_expediente`), `limit`, `offset`. Orden: `fecha DESC, id DESC`.
```json
{ "items": [ {
    "id": 2628, "camara": "S", "fecha": "2026-02-11T02:29:00-03:00",
    "numero_acta": "6", "titulo": "Modernización Laboral. Título V.",
    "etapa": "particular", "resultado": "afirmativo", "mayoria": "SIMPLE",
    "afirmativos": 42, "negativos": 30, "abstenciones": 0, "ausentes": 0,
    "expedientes": ["0159-PE-2025"], "ordenes_del_dia": ["699/2025"],
    "sesion_id": 1811, "url": "...", "url_pdf": "...", "video_url": "..."
} ], "total": 2126, "limit": 20, "offset": 0 }
```
`id` es el id interno de la tabla, no el número de acta del Senado.

### `GET /congreso/votaciones/{id}`
El ítem de la lista, y además:
```json
{
  "proyectos": [ ... ],
  "sesion": { "id": 1811, "fecha": "2026-02-11", "tipo": "ESPECIAL EXTRAORDINARIA" },
  "por_bloque": [ { "bloque": "JUSTICIALISTA", "afirmativo": 0, "negativo": 21,
                    "abstencion": 0, "ausente": 0, "otro": 0, "total": 21 } ],
  "votos": [ { "legislador_id": 77, "nombre": "MAYANS, JOSÉ MIGUEL ÁNGEL",
               "bloque": "JUSTICIALISTA", "distrito": "FORMOSA", "voto": "negativo" } ]
}
```
- `por_bloque` va ordenado por `total DESC`, con los bloques del momento del
  voto (`voto.bloque`).
- `votos` va ordenado por bloque y nombre. `voto` ∈ afirmativo | negativo |
  abstencion | ausente | presidente | otro.

### `GET /congreso/sesiones`
Parámetros: `camara`, `desde`, `hasta`, `limit`, `offset`. Orden: `fecha DESC`.
```json
{ "items": [ {
    "id": 1811, "camara": "S", "fecha": "2026-02-11", "tipo": "ESPECIAL EXTRAORDINARIA",
    "periodo": null, "reunion": 13, "numero_sesion": 2,
    "url": null, "url_taquigrafica": "...", "url_diario": "...",
    "votaciones": 7, "asuntos": 0
} ], "total": 1818, "limit": 20, "offset": 0 }
```
`votaciones` y `asuntos` son conteos: el Senado tiene votaciones, Diputados
tiene asuntos tratados.

### `GET /congreso/sesiones/{id}`
El ítem de la lista, y además:
```json
{
  "votaciones": [ /* ítems de /votaciones, sin votos */ ],
  "asuntos": [ { "id": 5, "clave": "0007-PE-2026", "orden_del_dia": "12",
                 "tipo": "LEY", "sumario": "...", "resultado": "APROBADO SIN MODIFICACIONES",
                 "expedientes": ["0007-PE-2026"], "proyectos": [ ... ] } ]
}
```

### `GET /congreso/legisladores`
Parámetros: `camara`, `bloque` (exacto), `distrito` (exacto), `q`, `activo`
(default `true`), `limit` (hasta 300, para listar una cámara entera),
`offset`. Orden: `nombre ASC`.
```json
{ "items": [ { "id": 77, "camara": "S", "nombre": "MAYANS, JOSÉ MIGUEL ÁNGEL",
               "bloque": "JUSTICIALISTA", "distrito": "FORMOSA",
               "mandato_desde": "2021-12-10", "mandato_hasta": "2027-12-09", "activo": true } ],
  "total": 72, "limit": 20, "offset": 0 }
```

### `GET /congreso/legisladores/{id}`
El ítem de la lista, y además:
```json
{
  "estadisticas": { "votaciones": 140, "presentes": 131, "presentismo": 0.936,
                    "alineamiento_bloque": 0.97 },
  "votos_recientes": [ { "votacion_id": 2628, "fecha": "2026-02-11T02:29:00-03:00",
                         "titulo": "...", "voto": "negativo", "resultado": "afirmativo" } ]
}
```
- `estadisticas` se calcula sobre los últimos 365 días.
  - `presentismo` = (votos − ausentes) / votos.
  - `alineamiento_bloque` = fracción de las votaciones con voto afirmativo o
    negativo en que votó igual que la mayoría de su bloque en esa misma
    votación.
  - En Diputados, sin votos, todo `estadisticas` es `null`.
- `votos_recientes`: los últimos 20.

### `GET /congreso/actividad`
Timeline unificado para el hub. Parámetros: `camara`, `desde` (default
hoy − 14 días), `limit` (default 30). Orden: `fecha DESC`; las reuniones
futuras de la agenda **no** entran (para eso está `/agenda`).
```json
{ "items": [ { "tipo": "votacion" | "sesion" | "reunion", "id": 2628, "camara": "S",
               "fecha": "2026-02-11T02:29:00-03:00", "titulo": "Modernización Laboral. Título V.",
               "detalle": "afirmativo 42-30" } ] }
```

### Cambio en `GET /normas/{id}`
`NormaDetail` (en `vigia_shared/schemas.py`) suma un campo opcional:
```json
"congreso": {
  "votaciones": [ /* ítems de /votaciones, como mucho 20, fecha DESC */ ],
  "asuntos":    [ /* asuntos tratados con la fecha de su sesión */ ],
  "reuniones":  [ /* reuniones de agenda, las próximas primero */ ]
}
```
Vale `null` cuando la norma no tiene `expedientes` o no hay ningún cruce.
**No toca `/v1`**, que es contrato con terceros.

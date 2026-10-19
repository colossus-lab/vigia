/* Vocabulario y formato de la sección Congreso.

   Módulo puro (sin React ni browser) para que se pueda testear con node:
   `pnpm test:congreso`, igual que `lib/plural.js`. Las páginas de
   `app/(app)/congreso/` no deciden colores ni formatos por su cuenta: todo
   sale de acá. */

export const TZ = 'America/Argentina/Buenos_Aires';

/* ── Cámaras ─────────────────────────────────────────────────── */

export const CAMARAS = {
  S: { label: 'Senado', largo: 'Senado de la Nación', tint: 'tint-blue', color: '#74ACDF', legislador: 'senador/a', legisladores: 'senadores' },
  D: { label: 'Diputados', largo: 'Cámara de Diputados', tint: 'tint-amber', color: '#F6B40E', legislador: 'diputado/a', legisladores: 'diputados' },
};

export const camaraLabel = (c) => CAMARAS[c]?.label || c || '—';
export const camaraTint = (c) => CAMARAS[c]?.tint || 'tint-gray';

/* ── Votos ───────────────────────────────────────────────────── */

// Orden fijo: es el de las barras apiladas y el de la leyenda.
export const VOTOS = {
  afirmativo: { label: 'Afirmativo', corto: 'Sí', tint: 'tint-green', color: '#34D399' },
  negativo: { label: 'Negativo', corto: 'No', tint: 'tint-red', color: '#F87171' },
  abstencion: { label: 'Abstención', corto: 'Abst.', tint: 'tint-amber', color: '#F6B40E' },
  ausente: { label: 'Ausente', corto: 'Aus.', tint: 'tint-gray', color: '#4B5568' },
  presidente: { label: 'Presidencia', corto: 'Pres.', tint: 'tint-purple', color: '#A78BFA' },
  otro: { label: 'Otro', corto: 'Otro', tint: 'tint-gray', color: '#8892A8' },
};

const votoMeta = (v) => VOTOS[v] || VOTOS.otro;
export const votoLabel = (v) => (v in VOTOS ? VOTOS[v].label : v ? sentence(v) : VOTOS.otro.label);
export const votoTint = (v) => votoMeta(v).tint;

/* ── Resultados ──────────────────────────────────────────────── */

const sinTildes = (s) => s.normalize('NFD').replace(/[̀-ͯ]/g, '');

/**
 * Tono del resultado de una votación (Senado: "afirmativo") o de un asunto
 * tratado (Diputados: "APROBADO SIN MODIFICACIONES", "MEDIA SANCION"...).
 * Lo que no se reconoce queda neutro: mejor gris que un verde equivocado.
 */
export function resultadoTono(resultado) {
  if (!resultado) return 'neutro';
  const r = sinTildes(String(resultado)).toLowerCase();
  if (/\b(negativ|rechaz|desaprob)/.test(r)) return 'negativo';
  if (/\b(afirmativ|aprob|sancion)/.test(r)) return 'positivo';
  return 'neutro';
}

const TONO_TINT = { positivo: 'tint-green', negativo: 'tint-red', neutro: 'tint-gray' };
const TONO_COLOR = { positivo: '#34D399', negativo: '#F87171', neutro: '#636E85' };
export const resultadoTint = (r) => TONO_TINT[resultadoTono(r)];
export const resultadoColor = (r) => TONO_COLOR[resultadoTono(r)];
export const resultadoLabel = (r) => (r ? sentence(String(r)) : 'Sin resultado');

/* ── Texto ───────────────────────────────────────────────────── */

export const sentence = (s) => (s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s);

const MINUSCULAS = new Set(['de', 'del', 'la', 'las', 'los', 'el', 'y', 'e', 'en', 'a', 'al', 'o', 'u', 'con', 'por', 'para']);

/**
 * "MAYANS, JOSÉ MIGUEL ÁNGEL" -> "Mayans, José Miguel Ángel";
 * "PRESUPUESTO Y HACIENDA" -> "Presupuesto y Hacienda".
 * El Senado manda todo en mayúsculas; Diputados ya viene bien y no se toca
 * (si hay alguna minúscula, se asume que el original sabe más que nosotros).
 */
export function nombrePropio(s) {
  if (!s) return s;
  if (s !== s.toUpperCase()) return s;
  return s
    .toLowerCase()
    .split(/(\s+|-|\(|\/)/)
    .map((w, i) => {
      if (!w || /^(\s+|-|\(|\/)$/.test(w)) return w;
      if (i > 0 && MINUSCULAS.has(w)) return w;
      return w.charAt(0).toUpperCase() + w.slice(1);
    })
    .join('');
}

/* ── Fechas ──────────────────────────────────────────────────── */

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb'];
const DIAS_LARGOS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const SOLO_FECHA = /^(\d{4})-(\d{2})-(\d{2})$/;

let _fmt;
const partesFmt = () =>
  (_fmt ||= new Intl.DateTimeFormat('en-US', {
    timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }));

/**
 * Descompone una fecha de la API en hora argentina. Acepta `YYYY-MM-DD`
 * (una `fecha` de sesión: sin hora y sin corrimiento de zona) y ISO 8601 con
 * offset (`fecha_hora`, y la `fecha` de las votaciones, que trae la hora).
 *
 * El `YYYY-MM-DD` NO pasa por `new Date()`: lo interpretaría como medianoche
 * UTC y en Argentina quedaría el día anterior.
 */
export function partesFecha(s) {
  if (!s) return null;
  const solo = SOLO_FECHA.exec(s);
  if (solo) {
    const [, y, m, d] = solo.map(Number);
    return { y, m, d, hh: null, mm: null, dow: new Date(Date.UTC(y, m - 1, d)).getUTCDay() };
  }
  const t = new Date(s);
  if (Number.isNaN(t.getTime())) return null;
  const p = Object.fromEntries(partesFmt().formatToParts(t).map((x) => [x.type, x.value]));
  const y = Number(p.year), m = Number(p.month), d = Number(p.day);
  return { y, m, d, hh: Number(p.hour), mm: Number(p.minute), dow: new Date(Date.UTC(y, m - 1, d)).getUTCDay() };
}

const dos = (n) => String(n).padStart(2, '0');

/** Día en hora argentina, `YYYY-MM-DD`: la clave para agrupar la agenda. */
export function diaKey(s) {
  const p = partesFecha(s);
  return p ? `${p.y}-${dos(p.m)}-${dos(p.d)}` : null;
}

/** Hoy en Argentina, `YYYY-MM-DD` (la máquina puede estar en UTC). */
export const hoyKey = (ahora = new Date()) => diaKey(ahora.toISOString());

/** `YYYY-MM-DD` + n días, sin pasar por la zona horaria local. */
export function sumarDias(key, n) {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
}

/** "mié 11 feb 2026". Sin año si es el año de `hoy`. */
export function formatFecha(s, { hoy = new Date(), conDia = true } = {}) {
  const p = partesFecha(s);
  if (!p) return '—';
  const anio = partesFecha(hoy.toISOString())?.y;
  const base = `${p.d} ${MESES[p.m - 1]}${p.y !== anio ? ` ${p.y}` : ''}`;
  return conDia ? `${DIAS[p.dow]} ${base}` : base;
}

/** "10:00" en hora argentina, o null si la fecha no trae hora. */
export function formatHora(s) {
  const p = partesFecha(s);
  return p && p.hh != null ? `${dos(p.hh)}:${dos(p.mm)}` : null;
}

/** "mié 11 feb 2026 · 02:29" (o sin hora, si no tiene). */
export function formatFechaHora(s, opts) {
  const h = formatHora(s);
  return h ? `${formatFecha(s, opts)} · ${h}` : formatFecha(s, opts);
}

/** "Hoy", "Mañana" o "Miércoles 21 de octubre": encabezado de día de la agenda. */
export function tituloDia(key, { hoy = new Date() } = {}) {
  const p = partesFecha(key);
  if (!p) return key;
  const h = diaKey(hoy.toISOString());
  const manana = diaKey(new Date(hoy.getTime() + 864e5).toISOString());
  const largo = `${DIAS_LARGOS[p.dow]} ${p.d} de ${MESES_LARGOS[p.m - 1]}`;
  if (key === h) return `Hoy · ${largo}`;
  if (key === manana) return `Mañana · ${largo}`;
  return largo.charAt(0).toUpperCase() + largo.slice(1);
}
const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];

/**
 * Agrupa ítems de agenda por día argentino, manteniendo el orden de llegada
 * (la API ya ordena por `fecha_hora ASC`).
 */
export function agruparPorDia(items, campo = 'fecha_hora') {
  const grupos = [];
  const idx = new Map();
  for (const it of items || []) {
    const k = diaKey(it[campo]) || 'sin-fecha';
    if (!idx.has(k)) {
      idx.set(k, grupos.length);
      grupos.push({ dia: k, items: [] });
    }
    grupos[idx.get(k)].items.push(it);
  }
  return grupos;
}

/** "2021 → 2027" a partir de mandato_desde/hasta. */
export function mandato(l) {
  const a = l?.mandato_desde?.slice(0, 4);
  const b = l?.mandato_hasta?.slice(0, 4);
  if (!a && !b) return null;
  return `${a || '?'} → ${b || '?'}`;
}

/* ── Números ─────────────────────────────────────────────────── */

/** 0.936 -> "93,6 %". null -> null (el que llama decide qué mostrar). */
export function porcentaje(x, decimales = 1) {
  if (x == null || Number.isNaN(x)) return null;
  return `${(x * 100).toLocaleString('es-AR', { minimumFractionDigits: decimales, maximumFractionDigits: decimales })} %`;
}

/** "42–30", o "42–30–1" si hubo abstenciones. */
export function marcador(v) {
  if (!v || v.afirmativos == null) return null;
  const base = `${v.afirmativos}–${v.negativos ?? 0}`;
  return v.abstenciones ? `${base}–${v.abstenciones}` : base;
}

/**
 * Proporciones para la barra afirmativo/negativo de una votación. La base son
 * los votos emitidos (sí + no + abstención): los ausentes no votaron y meterlos
 * achicaría las dos barras sin decir nada del resultado. null si no hubo votos.
 */
export function proporcionVotos(v) {
  const a = v?.afirmativos || 0, n = v?.negativos || 0, ab = v?.abstenciones || 0;
  const total = a + n + ab;
  if (!total) return null;
  return { afirmativo: a / total, negativo: n / total, abstencion: ab / total, total };
}

/* ── Gráfico por bloque ──────────────────────────────────────── */

// Las cuatro que pide la lectura política. `otro` y la presidencia se suman
// solo si aparecen, para no llenar la leyenda de series vacías.
export const SERIES_BLOQUE = ['afirmativo', 'negativo', 'abstencion', 'ausente'];

const recortar = (s, n) => (s.length > n ? `${s.slice(0, n - 1).trimEnd()}…` : s);

/**
 * `por_bloque` de `/congreso/votaciones/{id}` -> filas para un BarChart apilado
 * de recharts. Ordena por total (la API ya lo hace, pero no dependemos de eso)
 * y junta lo que pase de `top` en "Otros bloques", porque el Senado llega a
 * 20+ bloques unipersonales y el gráfico se vuelve ilegible.
 *
 * Devuelve `{ data, series }`: `series` son las claves con algún voto, en el
 * orden de VOTOS.
 */
export function datosPorBloque(porBloque, { top = 10, largo = 26 } = {}) {
  const filas = [...(porBloque || [])]
    .map((b) => ({
      bloque: b.bloque || 'Sin bloque',
      afirmativo: b.afirmativo || 0,
      negativo: b.negativo || 0,
      abstencion: b.abstencion || 0,
      ausente: b.ausente || 0,
      otro: (b.otro || 0) + (b.presidente || 0),
    }))
    .map((b) => ({ ...b, total: b.afirmativo + b.negativo + b.abstencion + b.ausente + b.otro }))
    .sort((x, y) => y.total - x.total || x.bloque.localeCompare(y.bloque));

  let data = filas.slice(0, top);
  const resto = filas.slice(top);
  if (resto.length) {
    const otros = { bloque: `Otros ${resto.length} bloques`, afirmativo: 0, negativo: 0, abstencion: 0, ausente: 0, otro: 0, total: 0 };
    for (const b of resto) for (const k of [...SERIES_BLOQUE, 'otro', 'total']) otros[k] += b[k];
    data = [...data, otros];
  }
  data = data.map((b) => ({ ...b, nombre: recortar(nombrePropio(b.bloque), largo) }));

  const series = [...SERIES_BLOQUE, 'otro'].filter((k) => SERIES_BLOQUE.includes(k) || data.some((b) => b[k] > 0));
  return { data, series };
}

/** Votos de una votación filtrados por texto (nombre, bloque, distrito) y tipo de voto. */
export function filtrarVotos(votos, { q = '', voto = '' } = {}) {
  const needle = sinTildes(q.trim()).toLowerCase();
  return (votos || []).filter((v) => {
    if (voto && v.voto !== voto) return false;
    if (!needle) return true;
    return sinTildes(`${v.nombre} ${v.bloque || ''} ${v.distrito || ''}`).toLowerCase().includes(needle);
  });
}

/* ── Legisladores ────────────────────────────────────────────── */

/** Bancas por bloque, de mayor a menor; lo que pase de `top` va junto (`resto: true`). */
export function composicionPorBloque(legisladores, top = 10) {
  const c = new Map();
  for (const l of legisladores || []) {
    const b = l.bloque || 'Sin bloque';
    c.set(b, (c.get(b) || 0) + 1);
  }
  const filas = [...c].map(([bloque, cantidad]) => ({ bloque, cantidad }))
    .sort((a, b) => b.cantidad - a.cantidad || a.bloque.localeCompare(b.bloque));
  if (filas.length <= top) return filas;
  const resto = filas.slice(top);
  return [
    ...filas.slice(0, top),
    { bloque: `Otros ${resto.length} bloques`, cantidad: resto.reduce((s, f) => s + f.cantidad, 0), resto: true },
  ];
}

/** Filtro en el browser de una cámara entera: nombre sin tildes, bloque y distrito exactos. */
export function filtrarLegisladores(items, { q = '', bloque = '', distrito = '' } = {}) {
  const needle = sinTildes(q.trim()).toLowerCase();
  return (items || []).filter((l) =>
    (!bloque || l.bloque === bloque) &&
    (!distrito || l.distrito === distrito) &&
    (!needle || sinTildes(l.nombre || '').toLowerCase().includes(needle))
  );
}

/* ── Actividad ───────────────────────────────────────────────── */

export const ACTIVIDAD = {
  votacion: { label: 'Votación', tint: 'tint-green' },
  sesion: { label: 'Sesión', tint: 'tint-blue' },
  reunion: { label: 'Comisión', tint: 'tint-purple' },
};

/** A dónde lleva un ítem de `/congreso/actividad`. Las reuniones no tienen detalle propio. */
export function hrefActividad(it) {
  if (it?.tipo === 'votacion') return `/congreso/votaciones/${it.id}`;
  if (it?.tipo === 'sesion') return `/congreso/sesiones/${it.id}`;
  return `/congreso/agenda${it?.camara ? `?camara=${it.camara}` : ''}`;
}

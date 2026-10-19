/* Fixtures de la API /congreso, con los shapes EXACTOS de docs/congreso-api.md.

   Solo para dev y tests (`scripts/test-congreso.mjs`): ninguna página los
   importa. Sirvieron para construir la sección mientras la API se hacía en
   paralelo; si el contrato cambia, cambian acá también. */

const PROYECTO_LABORAL = {
  id: 423838, titulo: 'LEY DE MODERNIZACION LABORAL.', numero: '0010-PE-2026',
  estado: 'Media sanción', fecha_publicacion: '2026-01-12',
};
const PROYECTO_PRESUPUESTO = {
  id: 431002, titulo: 'PRESUPUESTO DE GASTOS Y RECURSOS DE LA ADMINISTRACION NACIONAL PARA EL EJERCICIO 2027.',
  numero: '0271-PE-2026', estado: 'En comisión', fecha_publicacion: '2026-09-15',
};

export const RESUMEN = {
  S: { reuniones_proximas: 4, votaciones_30d: 12, sesiones_30d: 3, proyectos_30d: 180, ultima_sesion: '2026-09-24' },
  D: { reuniones_proximas: 5, votaciones_30d: null, sesiones_30d: 2, proyectos_30d: 410, ultima_sesion: '2026-10-07' },
  actualizado: '2026-10-19T18:00:00+00:00',
};

export const AGENDA = {
  items: [
    {
      id: 12, camara: 'S', fecha_hora: '2026-10-20T10:00:00-03:00',
      comision: 'PRESUPUESTO Y HACIENDA', sala: 'Salón Azul', tipo: 'Reunión',
      temario: 'Consideración del proyecto de ley del Poder Ejecutivo sobre el Presupuesto 2027. Invitado: Ministro de Economía.',
      expedientes: ['0271-PE-2026'], url_citacion: 'https://www.senado.gob.ar/upload/citacion-12.pdf',
      proyectos: [PROYECTO_PRESUPUESTO],
    },
    {
      id: 1365, camara: 'D', fecha_hora: '2026-10-20T11:30:00-03:00',
      comision: 'Presupuesto y Hacienda, Legislación del Trabajo', sala: 'Sala 2 - Anexo A', tipo: 'Informativa · Conjunta',
      temario: 'Exposición de funcionarios del Ministerio de Economía.',
      expedientes: [], url_citacion: null, proyectos: [],
    },
    {
      id: 13, camara: 'S', fecha_hora: '2026-10-21T14:00:00-03:00',
      comision: 'TRABAJO Y PREVISION SOCIAL', sala: 'Salón Illia', tipo: 'Reunión',
      temario: 'Dictamen sobre modernización laboral.', expedientes: ['0010-PE-2026'],
      url_citacion: null, proyectos: [PROYECTO_LABORAL],
    },
    {
      id: 1370, camara: 'D', fecha_hora: '2026-10-22T12:00:00-03:00',
      comision: 'Acción Social y Salud Pública', sala: 'Sala 1 - Anexo C', tipo: 'Informativa',
      temario: '', expedientes: [], url_citacion: null, proyectos: [],
    },
  ],
  total: 4, limit: 20, offset: 0,
};

const VOTACION_BASE = {
  id: 2628, camara: 'S', fecha: '2026-02-11T02:29:00-03:00',
  numero_acta: '6', titulo: 'Modernización Laboral. Título V.',
  etapa: 'particular', resultado: 'afirmativo', mayoria: 'SIMPLE',
  afirmativos: 42, negativos: 30, abstenciones: 0, ausentes: 0,
  expedientes: ['0159-PE-2025'], ordenes_del_dia: ['699/2025'],
  sesion_id: 1811, url: 'https://www.senado.gob.ar/votaciones/detalleActa/2628',
  url_pdf: 'https://www.senado.gob.ar/votaciones/actas/2628.pdf', video_url: null,
};

export const VOTACIONES = {
  items: [
    VOTACION_BASE,
    {
      ...VOTACION_BASE, id: 2627, fecha: '2026-02-11T01:58:00-03:00', numero_acta: '5',
      titulo: 'Modernización Laboral. En general.', etapa: 'general',
      afirmativos: 44, negativos: 27, abstenciones: 1, ausentes: 0,
    },
    {
      ...VOTACION_BASE, id: 2601, fecha: '2025-12-18T19:10:00-03:00', numero_acta: '2',
      titulo: 'Pliego de ascenso. Temas Varios Expedientes.', etapa: null, resultado: 'negativo',
      mayoria: 'DOS TERCIOS', afirmativos: 30, negativos: 38, abstenciones: 0, ausentes: 4,
      expedientes: [], ordenes_del_dia: [], sesion_id: null, url_pdf: null,
    },
  ],
  total: 2126, limit: 20, offset: 0,
};

export const VOTACION_DETALLE = {
  ...VOTACION_BASE,
  proyectos: [PROYECTO_LABORAL],
  sesion: { id: 1811, fecha: '2026-02-11', tipo: 'ESPECIAL EXTRAORDINARIA' },
  por_bloque: [
    { bloque: 'LA LIBERTAD AVANZA', afirmativo: 20, negativo: 0, abstencion: 0, ausente: 0, otro: 0, total: 20 },
    { bloque: 'JUSTICIALISTA', afirmativo: 0, negativo: 21, abstencion: 0, ausente: 0, otro: 0, total: 21 },
    { bloque: 'UNION CIVICA RADICAL', afirmativo: 10, negativo: 0, abstencion: 0, ausente: 0, otro: 0, total: 10 },
    { bloque: 'PRO', afirmativo: 6, negativo: 0, abstencion: 0, ausente: 0, otro: 0, total: 6 },
    { bloque: 'CONVICCION FEDERAL', afirmativo: 3, negativo: 2, abstencion: 0, ausente: 0, otro: 0, total: 5 },
    { bloque: 'FRENTE CIVICO DE SANTIAGO', afirmativo: 1, negativo: 3, abstencion: 0, ausente: 0, otro: 0, total: 4 },
    { bloque: 'PROVINCIAS UNIDAS', afirmativo: 2, negativo: 1, abstencion: 0, ausente: 0, otro: 0, total: 3 },
    { bloque: 'MISIONES', afirmativo: 0, negativo: 1, abstencion: 0, ausente: 0, otro: 1, total: 2 },
    { bloque: 'INDEPENDENCIA', afirmativo: 0, negativo: 1, abstencion: 0, ausente: 0, otro: 0, total: 1 },
  ],
  votos: [
    { legislador_id: 77, nombre: 'MAYANS, JOSÉ MIGUEL ÁNGEL', bloque: 'JUSTICIALISTA', distrito: 'FORMOSA', voto: 'negativo' },
    { legislador_id: 78, nombre: 'BULLRICH, PATRICIA', bloque: 'LA LIBERTAD AVANZA', distrito: 'CIUDAD AUTÓNOMA DE BUENOS AIRES', voto: 'afirmativo' },
    { legislador_id: 79, nombre: 'ABAD, MAXIMILIANO', bloque: 'UNION CIVICA RADICAL', distrito: 'BUENOS AIRES', voto: 'afirmativo' },
    { legislador_id: 80, nombre: 'DE LA ROSA, MARÍA', bloque: 'MISIONES', distrito: 'MISIONES', voto: 'presidente' },
  ],
};

export const SESIONES = {
  items: [
    {
      id: 2201, camara: 'D', fecha: '2026-10-07', tipo: 'Sesión Ordinaria Especial',
      periodo: 144, reunion: 6, numero_sesion: 4,
      url: 'https://www.hcdn.gob.ar/sesiones/sesion.html?id=144-6', url_taquigrafica: null, url_diario: null,
      votaciones: 0, asuntos: 9,
    },
    {
      id: 1811, camara: 'S', fecha: '2026-02-11', tipo: 'ESPECIAL EXTRAORDINARIA',
      periodo: null, reunion: 13, numero_sesion: 2,
      url: null, url_taquigrafica: 'https://www.senado.gob.ar/vt/1811.pdf', url_diario: 'https://www.senado.gob.ar/ds/1811.pdf',
      votaciones: 7, asuntos: 0,
    },
  ],
  total: 1818, limit: 20, offset: 0,
};

export const SESION_DETALLE_S = {
  ...SESIONES.items[1],
  votaciones: VOTACIONES.items.slice(0, 2),
  asuntos: [],
};

export const ASUNTO = {
  id: 5, clave: '0007-PE-2026', orden_del_dia: '12', tipo: 'LEY',
  sumario: 'Régimen de incentivo para grandes inversiones: modificaciones.',
  resultado: 'APROBADO SIN MODIFICACIONES', expedientes: ['0007-PE-2026'], proyectos: [],
};

export const SESION_DETALLE_D = {
  ...SESIONES.items[0],
  votaciones: [],
  asuntos: [
    ASUNTO,
    { id: 6, clave: 'OD-15', orden_del_dia: '15', tipo: 'RESOLUCION', sumario: 'Pedido de informes al Poder Ejecutivo.', resultado: 'RECHAZADO', expedientes: [], proyectos: [] },
    { id: 7, clave: '#3', orden_del_dia: null, tipo: null, sumario: 'Homenajes.', resultado: 'RENDIDO', expedientes: [], proyectos: [] },
  ],
};

export const LEGISLADORES = {
  items: [
    { id: 79, camara: 'S', nombre: 'ABAD, MAXIMILIANO', bloque: 'UNION CIVICA RADICAL', distrito: 'BUENOS AIRES', mandato_desde: '2021-12-10', mandato_hasta: '2027-12-09', activo: true },
    { id: 77, camara: 'S', nombre: 'MAYANS, JOSÉ MIGUEL ÁNGEL', bloque: 'JUSTICIALISTA', distrito: 'FORMOSA', mandato_desde: '2021-12-10', mandato_hasta: '2027-12-09', activo: true },
    { id: 512, camara: 'D', nombre: 'Menem, Martín', bloque: 'La Libertad Avanza', distrito: 'La Rioja', mandato_desde: '2025-12-10', mandato_hasta: '2029-12-09', activo: true },
  ],
  total: 3, limit: 20, offset: 0,
};

export const LEGISLADOR_S = {
  ...LEGISLADORES.items[1],
  estadisticas: { votaciones: 140, presentes: 131, presentismo: 0.936, alineamiento_bloque: 0.97 },
  votos_recientes: [
    { votacion_id: 2628, fecha: '2026-02-11T02:29:00-03:00', titulo: 'Modernización Laboral. Título V.', voto: 'negativo', resultado: 'afirmativo' },
    { votacion_id: 2627, fecha: '2026-02-11T01:58:00-03:00', titulo: 'Modernización Laboral. En general.', voto: 'negativo', resultado: 'afirmativo' },
  ],
};

export const LEGISLADOR_D = { ...LEGISLADORES.items[2], estadisticas: null, votos_recientes: [] };

export const ACTIVIDAD = {
  items: [
    { tipo: 'reunion', id: 1360, camara: 'D', fecha: '2026-10-15T11:00:00-03:00', titulo: 'Presupuesto y Hacienda', detalle: 'Informativa' },
    { tipo: 'sesion', id: 2201, camara: 'D', fecha: '2026-10-07T12:00:00-03:00', titulo: 'Sesión Ordinaria Especial', detalle: '9 asuntos tratados' },
    { tipo: 'votacion', id: 2628, camara: 'S', fecha: '2026-02-11T02:29:00-03:00', titulo: 'Modernización Laboral. Título V.', detalle: 'afirmativo 42-30' },
  ],
};

// `norma.congreso` en GET /normas/{id}. Cada asunto es el de /sesiones/{id}
// más `sesion_id`, `fecha` y `camara` de su sesión.
export const NORMA_CONGRESO = {
  votaciones: VOTACIONES.items.slice(0, 2),
  asuntos: [{ ...ASUNTO, sesion_id: 2201, fecha: '2026-10-07', camara: 'D' }],
  reuniones: AGENDA.items.slice(2, 3),
};

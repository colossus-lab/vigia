/**
 * Helpers de la sección Congreso (`lib/congreso.js`), contra los fixtures que
 * calcan docs/congreso-api.md.
 *
 * Lo que se cuida acá es lo que no se ve en la preview: la zona horaria (una
 * fecha `YYYY-MM-DD` no puede correrse al día anterior, y una votación de las
 * 02:29 tiene que caer en el día argentino correcto aunque el server esté en
 * UTC), que Diputados no muestre un 0 donde la API dice null, y el armado del
 * gráfico por bloque.
 *
 *   node apps/web/scripts/test-congreso.mjs
 */
import {
  camaraLabel, camaraTint, votoLabel, votoTint, resultadoTono, resultadoTint, resultadoLabel,
  nombrePropio, partesFecha, diaKey, formatFecha, formatHora, formatFechaHora, tituloDia,
  agruparPorDia, mandato, porcentaje, marcador, proporcionVotos, datosPorBloque, filtrarVotos,
  hrefActividad, SERIES_BLOQUE, hoyKey, sumarDias, nombreComision, textoLegible, composicionPorBloque, filtrarLegisladores,
} from '../lib/congreso.js';
import * as F from '../lib/congreso.fixtures.js';

let fallos = 0;
function afirmar(condicion, descripcion) {
  console.log(`  ${condicion ? 'ok  ' : 'FALLA'} ${descripcion}`);
  if (!condicion) fallos++;
}
const igual = (a, b, desc) => afirmar(JSON.stringify(a) === JSON.stringify(b), `${desc}${JSON.stringify(a) === JSON.stringify(b) ? '' : ` (dio ${JSON.stringify(a)})`}`);

// El test tiene que dar lo mismo en una máquina en UTC (Vercel, CI) que en una
// en Argentina: forzamos UTC para que un bug de zona horaria no pase de largo.
process.env.TZ = 'UTC';
const HOY = new Date('2026-10-19T15:00:00Z'); // lunes 19/10/2026, 12:00 ART

console.log('cámaras');
igual(camaraLabel('S'), 'Senado', 'S -> Senado');
igual(camaraLabel('D'), 'Diputados', 'D -> Diputados');
igual(camaraTint('X'), 'tint-gray', 'cámara desconocida -> gris, sin explotar');

console.log('votos');
igual(votoLabel('abstencion'), 'Abstención', 'abstencion lleva tilde en el label');
igual(votoTint('afirmativo'), 'tint-green', 'afirmativo verde');
igual(votoTint('negativo'), 'tint-red', 'negativo rojo');
igual(votoTint('raro'), 'tint-gray', 'voto desconocido -> gris');
igual(votoLabel('presidente'), 'Presidencia', 'presidente -> Presidencia');

console.log('resultados');
igual(resultadoTono('afirmativo'), 'positivo', 'Senado: afirmativo');
igual(resultadoTono('negativo'), 'negativo', 'Senado: negativo');
igual(resultadoTono('APROBADO SIN MODIFICACIONES'), 'positivo', 'Diputados: aprobado');
igual(resultadoTono('SANCIONADO DEFINITIVAMENTE'), 'positivo', 'Diputados: sancionado');
igual(resultadoTono('MEDIA SANCION'), 'positivo', 'Diputados: media sanción');
igual(resultadoTono('RECHAZADO'), 'negativo', 'Diputados: rechazado');
igual(resultadoTono('DESAPROBADO'), 'negativo', 'desaprobado no es "aprobado"');
igual(resultadoTono('RENDIDO'), 'neutro', 'rendido (homenaje) -> neutro');
igual(resultadoTono(null), 'neutro', 'sin resultado -> neutro');
igual(resultadoTint('RECHAZADO'), 'tint-red', 'tint de rechazado');
igual(resultadoLabel('APROBADO SIN MODIFICACIONES'), 'Aprobado sin modificaciones', 'label en sentence case');

console.log('nombres');
igual(nombrePropio('MAYANS, JOSÉ MIGUEL ÁNGEL'), 'Mayans, José Miguel Ángel', 'nombre del Senado');
igual(nombrePropio('PRESUPUESTO Y HACIENDA'), 'Presupuesto y Hacienda', 'comisión: conectores en minúscula');
igual(nombrePropio('DE LA ROSA, MARÍA'), 'De la Rosa, María', 'la primera palabra siempre va en mayúscula');
igual(nombrePropio('Menem, Martín'), 'Menem, Martín', 'Diputados ya viene bien: no se toca');
igual(nombrePropio('FRENTE CIVICO DE SANTIAGO'), 'Frente Civico de Santiago', 'bloque');
igual(nombrePropio('UCR - UNIÓN CÍVICA RADICAL'), 'UCR - Unión Cívica Radical', 'las siglas quedan en mayúsculas');
igual(nombrePropio('FRENTE PRO'), 'Frente PRO', 'PRO es sigla');
igual(nombrePropio('PROVINCIAS UNIDAS'), 'Provincias Unidas', 'una palabra que empieza con una sigla no se toca');
igual(nombrePropio(null), null, 'null -> null');
igual(nombreComision('DE EDUCACIÓN Y CULTURA'), 'Educación y Cultura', 'comisión del Senado sin el "DE" inicial');
igual(nombreComision('Acción Social y Salud Pública'), 'Acción Social y Salud Pública', 'comisión de Diputados intacta');
igual(
  textoLegible('PROYECTOS DE LEY: SERVICIOS AÉREOS: PE-271/26, MENSAJE N° 225/26. INVITADO EL MINISTRO DE LA UCR.'),
  'Proyectos de ley: Servicios aéreos: PE-271/26, mensaje n° 225/26. Invitado el ministro de la UCR.',
  'temario en mayúsculas -> oración, sin tocar expedientes ni siglas'
);
igual(textoLegible('Exposición de funcionarios.'), 'Exposición de funcionarios.', 'texto con minúsculas: intacto');
igual(textoLegible('SALÓN AZUL'), 'Salón azul', 'texto corto en mayúsculas también');

console.log('fechas (con TZ=UTC)');
igual(diaKey('2026-02-11'), '2026-02-11', 'YYYY-MM-DD no se corre al día anterior');
igual(diaKey('2026-02-11T02:29:00-03:00'), '2026-02-11', 'votación 02:29 ART -> mismo día argentino');
igual(diaKey('2026-10-21T01:00:00+00:00'), '2026-10-20', '01:00 UTC -> día anterior en Argentina');
igual(formatHora('2026-10-20T10:00:00-03:00'), '10:00', 'hora argentina');
igual(formatHora('2026-02-11'), null, 'una fecha sin hora no inventa 00:00');
igual(formatFecha('2026-02-11', { hoy: HOY }), 'mié 11 feb', 'mismo año: sin año');
igual(formatFecha('2025-12-18T19:10:00-03:00', { hoy: HOY }), 'jue 18 dic 2025', 'otro año: con año');
igual(formatFechaHora('2026-02-11T02:29:00-03:00', { hoy: HOY }), 'mié 11 feb · 02:29', 'fecha y hora');
igual(formatFecha(null), '—', 'null -> raya');
igual(formatFecha('basura'), '—', 'fecha inválida -> raya');
igual(partesFecha('2026-10-20T10:00:00-03:00').dow, 2, '20/10/2026 es martes');
igual(tituloDia('2026-10-19', { hoy: HOY }), 'Hoy · lunes 19 de octubre', 'hoy');
igual(tituloDia('2026-10-20', { hoy: HOY }), 'Mañana · martes 20 de octubre', 'mañana');
igual(tituloDia('2026-10-22', { hoy: HOY }), 'Jueves 22 de octubre', 'otro día');

igual(hoyKey(new Date('2026-10-20T02:00:00Z')), '2026-10-19', 'hoy argentino: a las 23:00 ART sigue siendo el 19');
igual(sumarDias('2026-12-28', 7), '2027-01-04', 'sumar días cruza el año');
igual(sumarDias('2026-10-19', 0), '2026-10-19', 'sumar 0 días');

console.log('agenda');
const grupos = agruparPorDia(F.AGENDA.items);
igual(grupos.map((g) => g.dia), ['2026-10-20', '2026-10-21', '2026-10-22'], 'agrupa por día en orden');
igual(grupos[0].items.map((i) => i.id), [12, 1365], 'mantiene el orden dentro del día');
igual(agruparPorDia([]), [], 'agenda vacía -> sin grupos');

console.log('números');
igual(porcentaje(0.936), '93,6 %', 'presentismo con coma decimal');
igual(porcentaje(null), null, 'null -> null: Diputados no muestra 0 %');
igual(porcentaje(1, 0), '100 %', 'sin decimales');
igual(marcador(F.VOTACIONES.items[0]), '42–30', 'marcador sin abstenciones');
igual(marcador(F.VOTACIONES.items[1]), '44–27–1', 'marcador con abstenciones');
const p = proporcionVotos(F.VOTACIONES.items[2]);
afirmar(Math.abs(p.afirmativo - 30 / 68) < 1e-9, 'la barra no cuenta a los ausentes');
igual(proporcionVotos({ afirmativos: 0, negativos: 0, abstenciones: 0 }), null, 'votación sin votos -> null');
igual(mandato(F.LEGISLADORES.items[0]), '2021 → 2027', 'mandato');
igual(mandato({}), null, 'sin mandato -> null');

console.log('resumen: Diputados sin votaciones');
afirmar(F.RESUMEN.D.votaciones_30d === null, 'el fixture respeta el contrato (null, no 0)');

console.log('gráfico por bloque');
const { data, series } = datosPorBloque(F.VOTACION_DETALLE.por_bloque, { top: 5 });
igual(data.length, 6, 'top 5 + "Otros"');
igual(data[0].bloque, 'JUSTICIALISTA', 'ordena por total aunque la API no lo haga');
igual(data[5].bloque, 'Otros 4 bloques', 'junta el resto');
igual(data[5].negativo, 6, 'los negativos del resto se suman (3+1+1+1)');
igual(data[5].otro, 1, 'el "otro" del resto se suma');
igual(data[0].nombre, 'Justicialista', 'el nombre del eje va en tipo propio');
igual(series, [...SERIES_BLOQUE, 'otro'], 'aparece "otro" porque hay un voto así');
const sinOtros = datosPorBloque(F.VOTACION_DETALLE.por_bloque.slice(0, 3));
igual(sinOtros.series, SERIES_BLOQUE, 'sin votos "otro": solo las cuatro series');
igual(sinOtros.data.length, 3, 'menos bloques que el top: no agrega "Otros"');
const total = data.reduce((s, b) => s + b.total, 0);
igual(total, F.VOTACION_DETALLE.por_bloque.reduce((s, b) => s + b.total, 0), 'no se pierde ningún voto al agrupar');
afirmar(datosPorBloque([{ bloque: 'UN BLOQUE CON UN NOMBRE LARGUÍSIMO DE VERDAD', afirmativo: 1 }]).data[0].nombre.endsWith('…'), 'nombres largos se recortan');
igual(datosPorBloque(null).data, [], 'sin por_bloque -> vacío');

console.log('tabla de votos');
igual(filtrarVotos(F.VOTACION_DETALLE.votos, { voto: 'afirmativo' }).length, 2, 'filtra por voto');
igual(filtrarVotos(F.VOTACION_DETALLE.votos, { q: 'jose miguel' }).map((v) => v.legislador_id), [77], 'busca sin tildes');
igual(filtrarVotos(F.VOTACION_DETALLE.votos, { q: 'formosa' }).length, 1, 'busca por distrito');
igual(filtrarVotos(F.VOTACION_DETALLE.votos, { q: 'radical', voto: 'negativo' }).length, 0, 'combina filtros');

console.log('legisladores');
const muchos = Array.from({ length: 14 }, (_, i) => ({ id: i, nombre: `X${i}`, bloque: i < 4 ? 'GRANDE' : `B${i}` }));
const comp = composicionPorBloque(muchos, 5);
igual(comp[0], { bloque: 'GRANDE', cantidad: 4 }, 'el bloque más grande primero');
igual(comp.length, 6, 'top 5 + resto');
igual(comp[5].resto && comp[5].cantidad, 6, 'el resto suma las bancas que faltan (14 - 4 - 4)');
igual(composicionPorBloque(F.LEGISLADORES.items).length, 3, 'pocos bloques: sin resto');
igual(filtrarLegisladores(F.LEGISLADORES.items, { q: 'jose' }).map((l) => l.id), [77], 'busca nombre sin tildes');
igual(filtrarLegisladores(F.LEGISLADORES.items, { bloque: 'JUSTICIALISTA', distrito: 'FORMOSA' }).length, 1, 'bloque + distrito');
igual(filtrarLegisladores(F.LEGISLADORES.items, { distrito: 'formosa' }).length, 0, 'distrito es exacto, como en la API');

console.log('actividad');
igual(hrefActividad(F.ACTIVIDAD.items[2]), '/congreso/votaciones/2628', 'votación -> su detalle');
igual(hrefActividad(F.ACTIVIDAD.items[1]), '/congreso/sesiones/2201', 'sesión -> su detalle');
igual(hrefActividad(F.ACTIVIDAD.items[0]), '/congreso/agenda?camara=D', 'reunión -> agenda de su cámara');

console.log(fallos ? `\n${fallos} fallo(s)` : '\ntodo ok');
process.exit(fallos ? 1 : 0);

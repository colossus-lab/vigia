// Vocabulario de dominio (espejo de packages/shared/constants.py).
export const TIPOS_NORMA = {
  DNU: { label: 'DNU', color: '#ef4444', description: 'Decreto de Necesidad y Urgencia' },
  DECRETO: { label: 'Decreto', color: '#f59e0b', description: 'Decreto del Poder Ejecutivo' },
  LEY: { label: 'Ley', color: '#10b981', description: 'Ley sancionada por el Congreso' },
  RESOLUCION: { label: 'Resolución', color: '#3b82f6', description: 'Resolución ministerial' },
  DISPOSICION: { label: 'Disposición', color: '#8b5cf6', description: 'Disposición administrativa' },
  PROYECTO: { label: 'Proyecto', color: '#06b6d4', description: 'Proyecto de ley en trámite' },
  COMUNICACION: { label: 'Comunicación', color: '#f472b6', description: 'Comunicación del BCRA (serie A)' },
  CONSULTA: { label: 'Consulta', color: '#fb923c', description: 'Consulta pública / anteproyecto en consulta' },
  OTRA: { label: 'Otra', color: '#64748b', description: 'Otra norma' },
};

export const JURISDICCIONES = [
  'Nacional', 'Buenos Aires', 'CABA', 'Córdoba', 'Santa Fe', 'Mendoza', 'Tucumán', 'Entre Ríos',
];

export const SECTORES = [
  'Economía', 'Energía', 'Salud', 'Educación', 'Justicia', 'Trabajo', 'Ambiente', 'Tecnología',
  'Comercio', 'Transporte', 'Minería', 'Agro', 'Defensa', 'Seguridad',
];

// Organismos emisores canónicos (`norma.emisor`) que acepta una alerta — espejo
// de EMISORES en constants.py, mismo orden. La API rechaza con 422 una clave que
// no esté allá.
export const EMISORES = [
  { clave: 'ARCA', label: 'Agencia de Recaudación (ex AFIP)' },
  { clave: 'CNV', label: 'Comisión Nacional de Valores' },
  { clave: 'CNDC', label: 'Defensa de la Competencia' },
  { clave: 'BCRA', label: 'Banco Central' },
  { clave: 'ENACOM', label: 'Ente Nacional de Comunicaciones' },
  { clave: 'SSN', label: 'Superintendencia de Seguros' },
  { clave: 'ENRE', label: 'Ente Regulador de la Electricidad' },
  { clave: 'ENARGAS', label: 'Ente Regulador del Gas' },
  { clave: 'ANMAT', label: 'ANMAT' },
  { clave: 'UIF', label: 'Unidad de Información Financiera' },
  { clave: 'IGJ', label: 'Inspección General de Justicia' },
  { clave: 'SENASA', label: 'SENASA' },
];

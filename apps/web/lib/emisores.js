// Icono por organismo emisor (lucide), compartido por el facet del feed y las
// alertas. Fallback a Building2.
import {
  Building2,
  Landmark, Receipt, Antenna, Umbrella, Zap, Pill, Flame, Sprout, CandlestickChart, ShieldAlert, Scale,
} from 'lucide-react';

export const EMISOR_ICON = {
  BCRA: Landmark, ARCA: Receipt, ENACOM: Antenna, SSN: Umbrella, ENRE: Zap,
  ANMAT: Pill, ENARGAS: Flame, SENASA: Sprout, CNV: CandlestickChart,
  IGJ: Building2, UIF: ShieldAlert, CNDC: Scale,
};

export const iconoEmisor = (clave) => EMISOR_ICON[clave] || Building2;

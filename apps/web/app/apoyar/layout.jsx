/* Metadata propia de la sección Apoyar. Vive en el layout porque `page.jsx` es
   client component (usa el botón de copiar CBU) y no puede exportar metadata.
   Sobrescribe título/descripción del root para que la tarjeta compartida sea la
   de la sección, junto al opengraph-image.jsx de esta misma carpeta. */

const TITLE = 'Apoyar a Vigía — la plataforma es y seguirá siendo gratis';
const DESCRIPTION =
  'Vigía monitorea el Boletín Oficial, el Congreso y el BCRA, y es gratis para todos. Lo sostenemos con aportes de quienes lo usan: desde $3.000 por Mercado Pago o transferencia a la Fundación Colossus Lab.';

export const metadata = {
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: 'https://vigia.openarg.org/apoyar',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
  },
};

export default function ApoyarLayout({ children }) {
  return children;
}

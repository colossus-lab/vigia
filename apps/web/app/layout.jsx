import './globals.css';
import Providers from '@/components/Providers';
import { Analytics } from '@vercel/analytics/next';

const TITLE = 'Vigía — Inteligencia Legislativa Argentina';
const DESCRIPTION =
  'La normativa argentina, vigilada. Monitoreo del Boletín Oficial y el Congreso: 533.000+ normas indexadas, búsqueda full-text, alertas por email y tracker de DNU. Por OpenArg.';

export const metadata = {
  metadataBase: new URL('https://vigia.openarg.org'),
  title: {
    default: TITLE,
    template: '%s · Vigía',
  },
  description: DESCRIPTION,
  keywords: ['boletín oficial', 'normativa argentina', 'DNU', 'InfoLEG', 'inteligencia legislativa', 'compliance', 'OpenArg'],
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: 'https://vigia.openarg.org',
    siteName: 'Vigía por OpenArg',
    locale: 'es_AR',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: TITLE,
    description: DESCRIPTION,
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="es">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;600;700&family=Familjen+Grotesk:ital,wght@0,400..700;1,400..700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Providers>{children}</Providers>
        <Analytics />
      </body>
    </html>
  );
}

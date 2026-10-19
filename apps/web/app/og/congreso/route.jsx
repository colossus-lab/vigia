import { ImageResponse } from 'next/og';

/* OpenGraph (1200×630) de la sección Congreso — misma editorial OpenArg que
   la raíz y Boletines, con un hemiciclo de 72 bancas (las del Senado) como
   motivo. Es decorativo a propósito: no representa ninguna votación real.

   Es un route handler en /og/congreso y no un `opengraph-image.jsx` dentro de
   (app)/congreso por dos motivos:
   - la sección va con login, y el bot que arma la preview de un link no tiene
     sesión: /og no está en PROTECTED_PREFIXES, así que no lo gatea proxy.js;
   - dentro de un route group Next publica la imagen con un hash en la ruta
     (/congreso/opengraph-image-xu7h1x), y no conviene apuntarle a eso.
   El login la usa en sus metadatos cuando el destino es /congreso
   (lib/ogDestino.js). */

const size = { width: 1200, height: 630 };

// Se genera una vez en el build (como los opengraph-image.jsx), no por request:
// cada render baja tres fuentes de jsDelivr.
export const dynamic = 'force-static';

const FONT_BASE = 'https://cdn.jsdelivr.net/fontsource/fonts';

async function loadFont(path) {
  const res = await fetch(`${FONT_BASE}/${path}`);
  if (!res.ok) throw new Error(`font ${path}: ${res.status}`);
  return res.arrayBuffer();
}

const CHIPS = ['VOTACIONES', 'AGENDA', 'SESIONES', 'LEGISLADORES'];

// Hemiciclo: 4 arcos concéntricos con 72 bancas en total, repartidas en
// proporción al radio (los arcos de afuera son más largos).
const ARCOS = [
  { r: 80, n: 13 },
  { r: 106, n: 17 },
  { r: 132, n: 19 },
  { r: 158, n: 23 },
];
const BANCA = 13;
const CAJA = { w: 340, h: 176 };
const CX = CAJA.w / 2; // centro del hemiciclo, abajo al medio de su caja
const CY = CAJA.h - BANCA / 2 - 1;

function bancas() {
  const out = [];
  ARCOS.forEach(({ r, n }, arco) => {
    for (let i = 0; i < n; i++) {
      const t = Math.PI * (1 - i / (n - 1)); // de 180° a 0°
      out.push({
        x: CX + r * Math.cos(t) - BANCA / 2,
        y: CY - r * Math.sin(t) - BANCA / 2,
        // Los arcos se apagan hacia afuera; una sola banca en sol, al centro
        // del arco interior, como acento.
        color:
          arco === 0 && i === Math.floor(n / 2)
            ? '#F6B40E'
            : `rgba(116,172,223,${0.95 - arco * 0.17})`,
      });
    }
  });
  return out;
}

export async function GET() {
  const [displayBold, displayItalic, mono] = await Promise.all([
    loadFont('familjen-grotesk@latest/latin-700-normal.ttf'),
    loadFont('familjen-grotesk@latest/latin-700-italic.ttf'),
    loadFont('jetbrains-mono@latest/latin-500-normal.ttf'),
  ]);

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: '#06090F',
          backgroundImage:
            'radial-gradient(ellipse 900px 600px at 10% -10%, rgba(116,172,223,0.16), transparent 60%), radial-gradient(ellipse 700px 500px at 100% 110%, rgba(246,180,14,0.10), transparent 55%)',
          position: 'relative',
        }}
      >
        {/* Franja bandera */}
        <div style={{ display: 'flex', height: 10, width: '100%' }}>
          <div style={{ flex: 1, backgroundColor: '#74ACDF' }} />
          <div style={{ flex: 1, backgroundColor: '#FFFFFF' }} />
          <div style={{ flex: 1, backgroundColor: '#74ACDF' }} />
        </div>

        {/* Cuerpo: texto a la izquierda, hemiciclo a la derecha */}
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', padding: '0 72px 0 88px' }}>
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div
              style={{
                fontFamily: 'JetBrains Mono',
                fontSize: 20,
                letterSpacing: 4,
                color: '#74ACDF',
                marginBottom: 26,
                display: 'flex',
              }}
            >
              SENADO Y DIPUTADOS · CONGRESO DE LA NACIÓN
            </div>

            <div
              style={{
                fontFamily: 'Familjen Grotesk',
                fontWeight: 700,
                fontSize: 82,
                lineHeight: 1.04,
                letterSpacing: -3,
                color: '#E8ECF4',
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <span>Todo lo que pasa</span>
              <span style={{ display: 'flex' }}>
                en el&nbsp;<span style={{ fontStyle: 'italic', color: '#F6B40E' }}>Congreso.</span>
              </span>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginTop: 34 }}>
              {CHIPS.map((c) => (
                <div
                  key={c}
                  style={{
                    display: 'flex',
                    fontFamily: 'JetBrains Mono',
                    fontSize: 19,
                    letterSpacing: 1,
                    color: '#93C5F8',
                    padding: '9px 18px',
                    borderRadius: 12,
                    border: '1px solid rgba(116,172,223,0.32)',
                    backgroundColor: 'rgba(116,172,223,0.12)',
                  }}
                >
                  {c}
                </div>
              ))}
            </div>
          </div>

          {/* Hemiciclo */}
          <div style={{ display: 'flex', position: 'relative', width: CAJA.w, height: CAJA.h, marginLeft: 24 }}>
            {bancas().map((b, i) => (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: b.x,
                  top: b.y,
                  width: BANCA,
                  height: BANCA,
                  borderRadius: BANCA,
                  backgroundColor: b.color,
                }}
              />
            ))}
          </div>
        </div>

        {/* Pie */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 88px 52px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <div
              style={{
                width: 54,
                height: 54,
                borderRadius: 14,
                border: '2px solid rgba(116,172,223,0.45)',
                backgroundColor: 'rgba(116,172,223,0.12)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#74ACDF" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontFamily: 'Familjen Grotesk', fontWeight: 700, fontSize: 30, color: '#E8ECF4', letterSpacing: 1 }}>
                VIGÍA
              </span>
              <span style={{ fontFamily: 'JetBrains Mono', fontSize: 15, letterSpacing: 4, color: '#636E85' }}>
                POR OPENARG
              </span>
            </div>
          </div>

          <div style={{ fontFamily: 'JetBrains Mono', fontSize: 18, color: '#8892A8', display: 'flex' }}>
            senado.gob.ar · hcdn.gob.ar · datos abiertos
          </div>
        </div>
      </div>
    ),
    {
      ...size,
      fonts: [
        { name: 'Familjen Grotesk', data: displayBold, weight: 700, style: 'normal' },
        { name: 'Familjen Grotesk', data: displayItalic, weight: 700, style: 'italic' },
        { name: 'JetBrains Mono', data: mono, weight: 500, style: 'normal' },
      ],
    }
  );
}

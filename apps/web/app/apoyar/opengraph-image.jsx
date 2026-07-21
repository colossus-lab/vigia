import { ImageResponse } from 'next/og';

/* OpenGraph (1200×630) de la sección Apoyar — misma editorial OpenArg que el
   resto, con el acento en sol (gratitud/aporte) y la tesis de la página:
   la plataforma es gratis y se sostiene con aportes. */

export const alt =
  'Vigía es y seguirá siendo gratis. Bancá el proyecto con un aporte mensual desde $3.000 —o el monto que quieras— por Mercado Pago, o con una transferencia única. Inteligencia legislativa por OpenArg.';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

const FONT_BASE = 'https://cdn.jsdelivr.net/fontsource/fonts';

async function loadFont(path) {
  const res = await fetch(`${FONT_BASE}/${path}`);
  if (!res.ok) throw new Error(`font ${path}: ${res.status}`);
  return res.arrayBuffer();
}

const CHIPS = ['DESDE $3.000 / MES', 'O EL MONTO QUE QUIERAS'];

export default async function OpengraphImage() {
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
            'radial-gradient(ellipse 900px 600px at 12% -10%, rgba(246,180,14,0.16), transparent 60%), radial-gradient(ellipse 750px 520px at 100% 110%, rgba(116,172,223,0.14), transparent 55%)',
          position: 'relative',
        }}
      >
        {/* Franja bandera */}
        <div style={{ display: 'flex', height: 10, width: '100%' }}>
          <div style={{ flex: 1, backgroundColor: '#74ACDF' }} />
          <div style={{ flex: 1, backgroundColor: '#FFFFFF' }} />
          <div style={{ flex: 1, backgroundColor: '#74ACDF' }} />
        </div>

        {/* Cuerpo */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            padding: '0 88px',
          }}
        >
          <div
            style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 20,
              letterSpacing: 4,
              color: '#F6B40E',
              marginBottom: 26,
              display: 'flex',
            }}
          >
            APOYAR · DATOS PÚBLICOS ABIERTOS · ARGENTINA
          </div>

          <div
            style={{
              fontFamily: 'Familjen Grotesk',
              fontWeight: 700,
              fontSize: 80,
              lineHeight: 1.04,
              letterSpacing: -3,
              color: '#E8ECF4',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <span>Vigía es y seguirá siendo</span>
            <span style={{ fontStyle: 'italic', color: '#F6B40E' }}>gratis.</span>
          </div>

          <div
            style={{
              fontFamily: 'JetBrains Mono',
              fontSize: 22,
              color: '#8892A8',
              marginTop: 26,
              display: 'flex',
            }}
          >
            Lo sostenemos con aportes de quienes lo usan.
          </div>

          {/* Montos sugeridos */}
          <div style={{ display: 'flex', gap: 14, marginTop: 30 }}>
            {CHIPS.map((c) => (
              <div
                key={c}
                style={{
                  display: 'flex',
                  fontFamily: 'JetBrains Mono',
                  fontSize: 22,
                  letterSpacing: 1,
                  color: '#F8CC5C',
                  padding: '10px 22px',
                  borderRadius: 12,
                  border: '1px solid rgba(246,180,14,0.32)',
                  backgroundColor: 'rgba(246,180,14,0.12)',
                }}
              >
                {c}
              </div>
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
            Mercado Pago · Transferencia
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

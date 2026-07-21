import { ImageResponse } from 'next/og';

/* Gráficos estáticos (PNG) para emails. Los clientes de correo no ejecutan JS,
   así que los charts del dashboard no sirven: acá se renderizan con el mismo
   motor que los opengraph-image, pero con DATOS REALES de la API de stats.

   Rutas: /email/img/actividad · /email/img/sectores · /email/img/corpus
   Se cachean 1h: un envío masivo puede disparar cientos de fetch a la vez. */

export const revalidate = 3600;

const API = process.env.NEXT_PUBLIC_API_URL || 'https://vigia-api.openarg.org';
const FONT_BASE = 'https://cdn.jsdelivr.net/fontsource/fonts';

const SIZE = { width: 1200, height: 600 };
const BG = '#0D1117';
const TX = '#E8ECF4';
const TX2 = '#8892A8';
const TX3 = '#636E85';
const CELESTE = '#74ACDF';
const SOL = '#F6B40E';

async function loadFont(path) {
  const res = await fetch(`${FONT_BASE}/${path}`);
  if (!res.ok) throw new Error(`font ${path}: ${res.status}`);
  return res.arrayBuffer();
}

const nf = (n) => Number(n || 0).toLocaleString('es-AR');

function Frame({ eyebrow, titulo, children, pie }) {
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: BG,
        padding: '44px 52px',
      }}
    >
      <div style={{ display: 'flex', fontFamily: 'JetBrains Mono', fontSize: 20, letterSpacing: 4, color: CELESTE }}>
        {eyebrow}
      </div>
      <div
        style={{
          display: 'flex',
          fontFamily: 'Familjen Grotesk',
          fontWeight: 700,
          fontSize: 44,
          color: TX,
          marginTop: 10,
          letterSpacing: -1,
        }}
      >
        {titulo}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, marginTop: 28 }}>{children}</div>
      {pie ? (
        <div style={{ display: 'flex', fontFamily: 'JetBrains Mono', fontSize: 18, color: TX3, marginTop: 12 }}>
          {pie}
        </div>
      ) : null}
    </div>
  );
}

/* Barras horizontales: label + barra proporcional + valor. */
function BarrasH({ items, color }) {
  const max = Math.max(...items.map((i) => i.valor), 1);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {items.map((i) => (
        <div key={i.label} style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div
            style={{
              display: 'flex',
              width: 220,
              fontFamily: 'JetBrains Mono',
              fontSize: 22,
              color: TX2,
            }}
          >
            {i.label}
          </div>
          <div style={{ display: 'flex', flex: 1, height: 34, backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 8 }}>
            <div
              style={{
                display: 'flex',
                width: `${Math.max((i.valor / max) * 100, 2)}%`,
                backgroundColor: color,
                borderRadius: 8,
              }}
            />
          </div>
          <div
            style={{
              display: 'flex',
              width: 150,
              justifyContent: 'flex-end',
              fontFamily: 'JetBrains Mono',
              fontSize: 24,
              color: TX,
            }}
          >
            {nf(i.valor)}
          </div>
        </div>
      ))}
    </div>
  );
}

export async function GET(_req, ctx) {
  const { chart } = await ctx.params;
  const [displayBold, displayItalic, mono] = await Promise.all([
    loadFont('familjen-grotesk@latest/latin-700-normal.ttf'),
    loadFont('familjen-grotesk@latest/latin-700-italic.ttf'),
    loadFont('jetbrains-mono@latest/latin-500-normal.ttf'),
  ]);
  const fonts = [
    { name: 'Familjen Grotesk', data: displayBold, weight: 700, style: 'normal' },
    { name: 'Familjen Grotesk', data: displayItalic, weight: 700, style: 'italic' },
    { name: 'JetBrains Mono', data: mono, weight: 500, style: 'normal' },
  ];

  let node;

  if (chart === 'hero') {
    // Cabecera del email: es la única forma de que el mail lleve la tipografía
    // real de Vigía (los clientes de correo no cargan webfonts).
    return new ImageResponse(
      (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            backgroundColor: BG,
            backgroundImage:
              'radial-gradient(ellipse 820px 520px at 8% -20%, rgba(246,180,14,0.14), transparent 62%), radial-gradient(ellipse 700px 480px at 105% 120%, rgba(116,172,223,0.12), transparent 58%)',
          }}
        >
          <div style={{ display: 'flex', height: 8, width: '100%' }}>
            <div style={{ flex: 1, backgroundColor: CELESTE }} />
            <div style={{ flex: 1, backgroundColor: '#FFFFFF' }} />
            <div style={{ flex: 1, backgroundColor: CELESTE }} />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '40px 56px 44px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div
                style={{
                  width: 46,
                  height: 46,
                  borderRadius: 12,
                  border: `2px solid rgba(116,172,223,0.45)`,
                  backgroundColor: 'rgba(116,172,223,0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={CELESTE} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ fontFamily: 'Familjen Grotesk', fontWeight: 700, fontSize: 26, color: TX, letterSpacing: 2 }}>VIGÍA</span>
                <span style={{ fontFamily: 'JetBrains Mono', fontSize: 13, letterSpacing: 4, color: TX3, marginTop: 2 }}>POR OPENARG</span>
              </div>
            </div>

            <div style={{ display: 'flex', flex: 1, flexDirection: 'column', justifyContent: 'flex-end' }}>
              <div style={{ display: 'flex', fontFamily: 'JetBrains Mono', fontSize: 17, letterSpacing: 5, color: SOL, marginBottom: 18 }}>
                TU COLABORACIÓN
              </div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  fontFamily: 'Familjen Grotesk',
                  fontWeight: 700,
                  fontSize: 58,
                  lineHeight: 1.08,
                  letterSpacing: -2,
                  color: TX,
                }}
              >
                <span>Nos alegra que le estés</span>
                <span>dando uso a{' '}<span style={{ fontStyle: 'italic', color: SOL }}>Vigía.</span></span>
              </div>
            </div>
          </div>
        </div>
      ),
      { width: 1200, height: 470, fonts }
    );
  }

  if (chart === 'sectores') {
    const d = await (await fetch(`${API}/stats/dashboard`, { next: { revalidate } })).json();
    const items = (d.por_sector || []).slice(0, 6).map((s) => ({ label: s.sector, valor: s.cantidad }));
    node = (
      <Frame
        eyebrow="VIGÍA / COBERTURA POR SECTOR"
        titulo="Ahora podés seguir un sector entero"
        pie="Normas clasificadas por sector · datos en vivo de la plataforma"
      >
        <BarrasH items={items} color={CELESTE} />
      </Frame>
    );
  } else if (chart === 'actividad') {
    const serie = await (await fetch(`${API}/stats/series?months=3&granularity=week`, { next: { revalidate } })).json();
    const semanas = (serie || []).slice(-12);
    const max = Math.max(...semanas.map((s) => s.total), 1);
    node = (
      <Frame
        eyebrow="VIGÍA / ACTIVIDAD SEMANAL"
        titulo="Cuánto se publica, semana a semana"
        pie="Últimas 12 semanas · así estimamos el volumen de tus alertas"
      >
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 14, flex: 1 }}>
          {semanas.map((s, idx) => (
            <div key={s.mes} style={{ display: 'flex', flexDirection: 'column', flex: 1, alignItems: 'center' }}>
              <div style={{ display: 'flex', fontFamily: 'JetBrains Mono', fontSize: 18, color: TX2, marginBottom: 8 }}>
                {nf(s.total)}
              </div>
              <div
                style={{
                  display: 'flex',
                  width: '100%',
                  height: Math.max((s.total / max) * 250, 6),
                  backgroundColor: idx === semanas.length - 1 ? SOL : CELESTE,
                  borderRadius: 6,
                }}
              />
              <div style={{ display: 'flex', fontFamily: 'JetBrains Mono', fontSize: 15, color: TX3, marginTop: 10 }}>
                {String(s.mes).slice(5)}
              </div>
            </div>
          ))}
        </div>
      </Frame>
    );
  } else {
    const d = await (await fetch(`${API}/stats/dashboard`, { next: { revalidate } })).json();
    const items = (d.por_tipo || []).slice(0, 5).map((t) => ({ label: t.tipo, valor: t.cantidad }));
    node = (
      <Frame eyebrow="VIGÍA / EL CORPUS" titulo={`${nf(d.total_normas)} normas indexadas`} pie="Boletín Oficial · Congreso · BCRA · CABA · PBA · actualización diaria">
        <BarrasH items={items} color={SOL} />
      </Frame>
    );
  }

  return new ImageResponse(node, { ...SIZE, fonts });
}

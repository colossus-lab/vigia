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
  const [displayBold, mono] = await Promise.all([
    loadFont('familjen-grotesk@latest/latin-700-normal.ttf'),
    loadFont('jetbrains-mono@latest/latin-500-normal.ttf'),
  ]);
  const fonts = [
    { name: 'Familjen Grotesk', data: displayBold, weight: 700, style: 'normal' },
    { name: 'JetBrains Mono', data: mono, weight: 500, style: 'normal' },
  ];

  let node;

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

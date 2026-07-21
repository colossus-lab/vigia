import Link from 'next/link';
import { Eye, ArrowLeft } from 'lucide-react';
import FadeIn from '@/components/FadeIn';

export const metadata = {
  title: 'Términos y privacidad — Vigía',
  description: 'Qué datos guarda Vigía, para qué los usa y cuáles son tus derechos.',
};

const SECCIONES = [
  {
    num: 'I.',
    titulo: 'El servicio',
    cuerpo: [
      <>Vigía es una plataforma de inteligencia legislativa y regulatoria argentina, desarrollada por <strong className="text-text-primary">Colossus Lab</strong> (familia OpenArg). Monitorea fuentes oficiales públicas — Boletín Oficial, InfoLEG, Congreso, BCRA y consultas públicas —, las indexa y te avisa cuando aparece normativa que te interesa.</>,
      <>El corpus normativo que mostramos es <strong className="text-text-primary">información pública</strong>: proviene de fuentes oficiales del Estado argentino y cada norma linkea a su fuente original verificable.</>,
    ],
  },
  {
    num: 'II.',
    titulo: 'Responsable de la base de datos',
    cuerpo: [
      <>El responsable del tratamiento de tus datos personales es la <strong className="text-text-primary">Fundación Colossus Lab</strong>. Para cualquier consulta sobre tus datos, escribinos a <a href="mailto:devops@colossuslab.org" className="textlink">devops@colossuslab.org</a>.</>,
      <>Tratamos tus datos conforme a la <strong className="text-text-primary">Ley N° 25.326</strong> de Protección de los Datos Personales y su reglamentación.</>,
    ],
  },
  {
    num: 'III.',
    titulo: 'Qué datos guardamos',
    cuerpo: [
      <>Si creás una cuenta, guardamos lo que tu cuenta de Google nos da al iniciar sesión: <strong className="text-text-primary">email, nombre y foto de perfil</strong>. No accedemos a tu correo, contactos ni archivos.</>,
      <>Además guardamos lo que vos creás dentro de la plataforma: tu workspace, sus miembros, las alertas que configurás (keywords y sectores) y los emails de las personas que invitás.</>,
      <>Por seguridad y trazabilidad, registramos también datos técnicos de tu actividad de cuenta: tu <strong className="text-text-primary">dirección IP</strong>, el <strong className="text-text-primary">navegador y dispositivo</strong> (user-agent), la fecha de tu último acceso y un registro de eventos relevantes (inicios de sesión, invitaciones enviadas o aceptadas y cambios de membresía). Conservamos este registro por un máximo de <strong className="text-text-primary">12 meses</strong> y luego lo borramos automáticamente.</>,
    ],
  },
  {
    num: 'IV.',
    titulo: 'Para qué los usamos',
    cuerpo: [
      <>Para que el servicio funcione: autenticarte, mantener tu workspace y mandarte los emails que pediste — el digest de tus alertas y las invitaciones que enviás. Son emails operativos.</>,
      <>Ocasionalmente podemos escribirte para contarte <strong className="text-text-primary">novedades relevantes del servicio</strong>: cambios en cómo funciona, funciones nuevas o avisos importantes. Son pocos y podés <strong className="text-text-primary">darte de baja</strong> con un clic desde el pie de esos emails, sin perder los avisos de tus alertas. Nunca usamos tu email para publicidad ni lo cedemos a terceros.</>,
    ],
  },
  {
    num: 'V.',
    titulo: 'Lo que no hacemos',
    cuerpo: [
      <>No vendemos ni compartimos tus datos con terceros. No mostramos publicidad. No usamos trackers de terceros ni perfiles de comportamiento. Tu monitoreo — qué keywords vigilás, qué buscás — es tuyo.</>,
    ],
  },
  {
    num: 'VI.',
    titulo: 'Servicios de terceros y transferencia internacional',
    cuerpo: [
      <>Para operar usamos: <strong className="text-text-primary">Google</strong> (inicio de sesión), <strong className="text-text-primary">Resend</strong> (envío de emails), <strong className="text-text-primary">Amazon Web Services</strong> (infraestructura y base de datos) y <strong className="text-text-primary">Vercel</strong> (hosting del sitio). Si está activo el resumen automático con IA, usamos <strong className="text-text-primary">Anthropic / AWS Bedrock</strong>, que recibe únicamente el texto público de las normas — nunca tus datos personales. Cada proveedor recibe solo lo mínimo necesario para su función.</>,
      <>Estos servicios alojan datos en servidores ubicados en <strong className="text-text-primary">los Estados Unidos</strong>. Al usar Vigía prestás tu consentimiento para esa transferencia internacional de datos, en los términos del artículo 12 de la Ley N° 25.326.</>,
    ],
  },
  {
    num: 'VII.',
    titulo: 'Cookies',
    cuerpo: [
      <>Usamos únicamente la cookie de sesión necesaria para mantenerte logueado. Es una cookie estrictamente técnica: no requiere consentimiento previo. Sin cookies de publicidad ni de analytics de terceros.</>,
    ],
  },
  {
    num: 'VIII.',
    titulo: 'Tus datos, tus derechos',
    cuerpo: [
      <>Tenés derecho a <strong className="text-text-primary">acceder</strong> a tus datos, <strong className="text-text-primary">rectificarlos</strong>, <strong className="text-text-primary">actualizarlos</strong> y pedir su <strong className="text-text-primary">supresión</strong>. Desde <strong className="text-text-primary">Configuración → Tu cuenta</strong> podés descargar todos tus datos o eliminar tu cuenta por completo en cualquier momento. También podés ejercer estos derechos escribiendo a <a href="mailto:devops@colossuslab.org" className="textlink">devops@colossuslab.org</a>.</>,
      <>El acceso es <strong className="text-text-primary">gratuito</strong> a intervalos no inferiores a seis meses. Respondemos los pedidos de acceso dentro de los <strong className="text-text-primary">10 días corridos</strong> y los de rectificación, actualización o supresión dentro de los <strong className="text-text-primary">5 días hábiles</strong>, conforme a la Ley N° 25.326.</>,
      <em className="block text-[12px] text-text-tertiary leading-relaxed not-italic border-l-2 border-border-light pl-4">El titular de los datos personales tiene la facultad de ejercer el derecho de acceso a los mismos en forma gratuita a intervalos no inferiores a seis meses, salvo que se acredite un interés legítimo al efecto conforme lo establecido en el artículo 14, inciso 3 de la Ley N° 25.326. La AGENCIA DE ACCESO A LA INFORMACIÓN PÚBLICA, en su carácter de Órgano de Control de la Ley N° 25.326, tiene la atribución de atender las denuncias y reclamos que interpongan quienes resulten afectados en sus derechos por incumplimiento de las normas vigentes en materia de protección de datos personales.</em>,
    ],
  },
  {
    num: 'IX.',
    titulo: 'Términos de uso',
    cuerpo: [
      <>Vigía está en <strong className="text-text-primary">beta</strong> y se ofrece "tal cual". Hacemos lo posible por la frescura y fidelidad de los datos (monitoreamos cada fuente con SLOs), pero las fuentes oficiales pueden contener errores, demoras u omisiones — y nuestro procesamiento también puede fallar.</>,
      <>Vigía <strong className="text-text-primary">no es asesoramiento legal</strong>. Los resúmenes — incluidos los generados automáticamente con IA — son orientativos: ante cualquier decisión, verificá siempre el texto completo en la fuente oficial (cada norma incluye el link).</>,
      <>Vigía es <strong className="text-text-primary">gratuito</strong>: no hay período de prueba ni funciones pagas. Se sostiene con aportes voluntarios (ver <Link href="/apoyar" className="textlink">Apoyar</Link>), que no destraban nada — todas las funciones están disponibles para todos, y los datos normativos públicos son de libre acceso.</>,
    ],
  },
  {
    num: 'X.',
    titulo: 'Cambios',
    cuerpo: [
      <>Si esta página cambia, actualizamos la fecha de abajo. Si el cambio es relevante para tus datos, te avisamos por email.</>,
    ],
  },
];

export default function LegalPage() {
  return (
    <div className="min-h-screen">
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />

      <header className="sticky top-0 z-50 bg-bg-secondary/80 backdrop-blur border-b border-border-light">
        <div className="max-w-3xl mx-auto px-5 md:px-10 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2.5 group">
            <div className="w-7 h-7 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center">
              <Eye size={14} className="text-celeste" />
            </div>
            <div>
              <p className="text-[13px] font-bold text-text-primary leading-none" style={{ fontFamily: 'var(--font-display)' }}>VIGÍA</p>
              <p className="text-[8px] text-text-tertiary uppercase tracking-[0.18em] font-mono mt-0.5">por OpenArg</p>
            </div>
          </Link>
          <Link href="/" className="flex items-center gap-1.5 text-[12px] text-text-tertiary hover:text-text-primary transition-colors">
            <ArrowLeft size={12} /> Volver al inicio
          </Link>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-5 md:px-10 pb-16">
        <section className="pt-12 md:pt-16 pb-10">
          <FadeIn>
            <p className="eyebrow mb-4">
              <span className="eyebrow-num">LEGAL</span>
              <span className="mx-2 text-text-tertiary">·</span>
              Claro y en una sola página
            </p>
          </FadeIn>
          <FadeIn delay={80}>
            <h1 className="display-section text-text-primary mb-4">
              Términos y <em>privacidad.</em>
            </h1>
          </FadeIn>
          <FadeIn delay={140}>
            <p className="text-[14px] text-text-secondary leading-relaxed max-w-xl">
              La versión corta: guardamos lo mínimo para que el servicio funcione,
              no vendemos tus datos, y podés irte — con todo borrado — cuando quieras.
              La versión completa, abajo.
            </p>
          </FadeIn>
        </section>

        <div className="border-t-2 border-text-primary/70">
          {SECCIONES.map(({ num, titulo, cuerpo }, i) => (
            <FadeIn key={num} delay={i * 50}>
              <section className="grid grid-cols-1 md:grid-cols-[180px_1fr] gap-2 md:gap-8 py-7 border-b border-border-light">
                <p className="eyebrow">
                  <span className="eyebrow-num">{num}</span>
                  <span className="ml-2">{titulo}</span>
                </p>
                <div className="space-y-3">
                  {cuerpo.map((parrafo, j) => (
                    <p key={j} className="text-[13px] text-text-secondary leading-relaxed">{parrafo}</p>
                  ))}
                </div>
              </section>
            </FadeIn>
          ))}
        </div>

        <FadeIn>
          <p className="text-[10px] text-text-tertiary font-mono pt-6">
            Última actualización: 20 de julio de 2026 · Fundación Colossus Lab · Buenos Aires
          </p>
        </FadeIn>
      </main>
    </div>
  );
}

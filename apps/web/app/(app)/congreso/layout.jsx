'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const SUBNAV = [
  { href: '/congreso', label: 'Resumen' },
  { href: '/congreso/agenda', label: 'Agenda' },
  { href: '/congreso/votaciones', label: 'Votaciones' },
  { href: '/congreso/sesiones', label: 'Sesiones' },
  { href: '/congreso/legisladores', label: 'Legisladores' },
];

/* Sub-navegación de la sección: va en el layout para que esté igual en el hub
   y en cada subpágina (y en los detalles, marcando la sección madre). */
export default function CongresoLayout({ children }) {
  const pathname = usePathname();
  return (
    <div className="max-w-5xl mx-auto">
      {/* En mobile las cinco pestañas no entran y la nav scrollea sola. El
          `contain` hace falta: sin él, el ancho del contenido (min-w-max) sube
          como ancho intrínseco por los flex del layout y la PÁGINA entera
          queda más ancha que la pantalla, aunque la nav tenga overflow-x-auto. */}
      <nav aria-label="Secciones del Congreso" className="-mx-1 mb-2 overflow-x-auto [contain:inline-size]">
        <ul className="flex gap-1 px-1 min-w-max border-b border-border-light">
          {SUBNAV.map(({ href, label }) => {
            const activo = href === '/congreso' ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <li key={href}>
                <Link
                  href={href}
                  aria-current={activo ? 'page' : undefined}
                  className={`block px-3 py-2 text-[12px] font-medium border-b-2 -mb-px transition-colors ${
                    activo
                      ? 'border-celeste text-celeste-bright'
                      : 'border-transparent text-text-tertiary hover:text-text-primary'
                  }`}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      {children}
    </div>
  );
}

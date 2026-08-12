'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Building2, KeyRound } from 'lucide-react';

// El engranaje de la barra entra siempre a /settings/workspace, así que sin esto
// /settings/api no tendría cómo alcanzarse desde la app.
const SECCIONES = [
  { href: '/settings/workspace', label: 'Workspace', icon: Building2 },
  { href: '/settings/api', label: 'API', icon: KeyRound },
];

export default function SettingsNav() {
  const pathname = usePathname();
  return (
    <nav className="flex items-center gap-1 mb-6 border-b border-border-light">
      {SECCIONES.map(({ href, label, icon: Icon }) => {
        const activa = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-medium border-b-2 -mb-px transition-colors ${
              activa
                ? 'border-celeste text-celeste'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            <Icon size={13} /> {label}
          </Link>
        );
      })}
    </nav>
  );
}

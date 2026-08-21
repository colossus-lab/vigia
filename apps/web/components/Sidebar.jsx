'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Newspaper, BarChart3, Search, Bell, Shield, X, Eye, Landmark, Building2, Heart } from 'lucide-react';
import CreditosBar from '@/components/CreditosBar';

const NAV_ITEMS = [
  { to: '/feed', label: 'Feed Normativo', icon: Newspaper },
  { to: '/boletines', label: 'Boletines Oficiales', icon: Landmark },
  { to: '/dashboard', label: 'Estadísticas', icon: BarChart3 },
  { to: '/search', label: 'Buscador', icon: Search },
  { to: '/alerts', label: 'Alertas', icon: Bell },
  { to: '/dnu', label: 'Tracker DNU', icon: Shield },
  { to: '/avisos', label: 'Radar societario', icon: Building2 },
];

export default function Sidebar({ open, onClose }) {
  const pathname = usePathname();
  return (
    <>
      {open && <div className="fixed inset-0 bg-black/20 z-40 lg:hidden" onClick={onClose} />}

      <aside
        className={`fixed top-0 left-0 h-full w-60 bg-bg-primary border-r border-border-light z-50 flex flex-col transition-transform duration-200 lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Logo */}
        <div className="px-5 py-5 border-b border-border-light">
          <div className="flex items-center justify-between">
            <Link href="/" className="flex items-center gap-2.5 group">
              <div className="w-8 h-8 rounded-lg bg-celeste/10 border border-celeste/30 flex items-center justify-center group-hover:bg-celeste/20 transition-colors">
                <Eye size={16} className="text-celeste" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-text-primary tracking-wide">VIGÍA</h1>
                <p className="text-[9px] text-text-tertiary uppercase tracking-[0.15em] font-mono">por OpenArg</p>
              </div>
            </Link>
            <button onClick={onClose} className="lg:hidden text-text-tertiary hover:text-text-primary">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 py-4 px-3 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => {
            const isActive = pathname === to || pathname.startsWith(to + '/');
            return (
              <Link
                key={to}
                href={to}
                onClick={onClose}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-colors ${
                  isActive
                    ? 'bg-celeste/10 text-celeste-bright border border-celeste/25'
                    : 'text-text-secondary hover:bg-bg-tertiary hover:text-text-primary border border-transparent'
                }`}
              >
                <Icon size={16} className="shrink-0" />
                <span>{label}</span>
              </Link>
            );
          })}
          {/* Apoyar — dentro de la navegación (no en el pie) y separado de las
              secciones de datos, para que se vea sin scrollear. */}
          <div className="pt-2 mt-2 border-t border-border-light space-y-2">
            <CreditosBar />
            <Link
              href="/apoyar"
              onClick={onClose}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] font-bold border transition-colors ${
                pathname === '/apoyar' || pathname.startsWith('/apoyar/')
                  ? 'bg-sol/15 text-sol border-sol/40'
                  : 'bg-sol/[0.07] text-sol border-sol/25 hover:bg-sol/15 hover:border-sol/40'
              }`}
            >
              <Heart size={16} className="shrink-0" />
              <span>Apoyar a Vigía</span>
            </Link>
          </div>
        </nav>

        {/* Footer */}
        <div className="px-4 py-4 border-t border-border-light">
          <div className="flex items-center gap-2">
            <Landmark size={12} className="text-text-tertiary" />
            <p className="text-[10px] text-text-tertiary font-mono">Colossus Lab · BA</p>
          </div>
        </div>
      </aside>
    </>
  );
}

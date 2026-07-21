'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Menu, Bell, Heart } from 'lucide-react';
import AuthButton from '@/components/AuthButton';

export default function Header({ onMenuToggle }) {
  const [time, setTime] = useState(null);

  useEffect(() => {
    setTime(new Date());
    const interval = setInterval(() => setTime(new Date()), 60000);
    return () => clearInterval(interval);
  }, []);

  const formattedDate = time
    ? time.toLocaleDateString('es-AR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
    : '';
  const formattedTime = time ? time.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <header className="sticky top-0 z-30 bg-bg-primary/85 backdrop-blur border-b border-border-light">
      <div className="flex items-center justify-between px-4 md:px-6 lg:px-8 h-14">
        <div className="flex items-center gap-4">
          <button
            onClick={onMenuToggle}
            className="lg:hidden p-1.5 rounded text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          >
            <Menu size={18} />
          </button>
          <span className="hidden md:block text-xs text-text-tertiary capitalize font-mono">
            {formattedDate}{formattedTime && ` — ${formattedTime}`}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden md:inline-block text-[10px] font-medium border tint-green px-2.5 py-1 rounded-full">
            ● Datos reales · InfoLEG / Boletín Oficial
          </span>
          <Link
            href="/apoyar"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-sol/10 text-sol border border-sol/30 hover:bg-sol/20 transition-colors whitespace-nowrap"
          >
            <Heart size={13} />
            <span className="hidden sm:inline">Apoyar</span>
          </Link>
          <button className="relative p-1.5 rounded text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors">
            <Bell size={16} />
            <span className="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-status-red" />
          </button>
          <AuthButton />
        </div>
      </div>
    </header>
  );
}

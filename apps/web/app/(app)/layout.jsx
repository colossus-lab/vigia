'use client';

import { useState } from 'react';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';
import OnboardingBanner from '@/components/OnboardingBanner';
import OnboardingGate from '@/components/OnboardingGate';
import CreditosProvider from '@/components/CreditosProvider';
import SinCreditosBanner from '@/components/SinCreditosBanner';

export default function AppLayout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <CreditosProvider>
    <div className="min-h-screen flex flex-col">
      <OnboardingGate />
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />
      <div className="flex flex-1">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <div className="flex-1 flex flex-col min-h-screen lg:ml-60">
          <Header onMenuToggle={() => setSidebarOpen(!sidebarOpen)} />
          <main className="flex-1 p-4 md:p-6 lg:p-8 overflow-auto">
            <OnboardingBanner />
            {/* Va en el layout y no en /alerts: quien se queda sin creditos se
                entera porque NO le llegan mails, asi que el aviso tiene que
                estar donde entre. */}
            <SinCreditosBanner />
            {children}
          </main>
        </div>
      </div>
    </div>
    </CreditosProvider>
  );
}

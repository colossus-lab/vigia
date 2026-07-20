'use client';

import { useState } from 'react';
import Sidebar from '@/components/Sidebar';
import Header from '@/components/Header';
import TrialGate from '@/components/TrialGate';
import OnboardingBanner from '@/components/OnboardingBanner';
import OnboardingGate from '@/components/OnboardingGate';

export default function AppLayout({ children }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      <OnboardingGate />
      <TrialGate />
      <div className="flag-stripe fixed top-0 inset-x-0 z-[60]" />
      <div className="flex flex-1">
        <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

        <div className="flex-1 flex flex-col min-h-screen lg:ml-60">
          <Header onMenuToggle={() => setSidebarOpen(!sidebarOpen)} />
          <main className="flex-1 p-4 md:p-6 lg:p-8 overflow-auto">
            <OnboardingBanner />
            {children}
          </main>
        </div>
      </div>
    </div>
  );
}

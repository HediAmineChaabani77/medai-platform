import "./globals.css";
import type { ReactNode } from "react";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import Sidebar from "@/components/shell/Sidebar";
import TopBar from "@/components/shell/TopBar";
import OfflineBanner from "@/components/OfflineBanner";

import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "MedAI Assistant — Console clinicienne",
  description: "Assistance au diagnostic, à la rédaction et à la prescription. Local-first, HIPAA/RGPD.",
  applicationName: "MedAI Assistant",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FAFAF7" },
    { media: "(prefers-color-scheme: dark)", color: "#0F0F0E" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="fr"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="font-sans antialiased">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:bg-ink focus:text-paper focus:px-3 focus:py-2 focus:rounded-md focus:text-[13px]"
        >
          Aller au contenu principal
        </a>
        <OfflineBanner />
        <div className="flex min-h-dvh">
          <Sidebar />
          <div className="flex-1 flex flex-col min-w-0">
            <TopBar />
            <main id="main" tabIndex={-1} className="flex-1 px-6 lg:px-10 pb-16 focus:outline-none">
              {children}
            </main>
          </div>
        </div>
      </body>
    </html>
  );
}

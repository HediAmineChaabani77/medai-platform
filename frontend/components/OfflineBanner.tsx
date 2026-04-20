"use client";
import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function OfflineBanner() {
  const [online, setOnline] = useState<boolean | null>(null);

  useEffect(() => {
    const check = async () => {
      try {
        const r = await fetch(`${API}/health`, { cache: "no-store" });
        const j = await r.json();
        setOnline(Boolean(j.online));
      } catch { setOnline(false); }
    };
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  if (online === null || online) return null;
  return (
    <div className="bg-warn/10 border-b border-warn/30 text-warn">
      <div className="max-w-[1600px] mx-auto px-6 py-2 text-[12px] flex items-center gap-2">
        <WifiOff className="h-3.5 w-3.5" strokeWidth={2} />
        <span><strong>Mode hors ligne</strong> — IA locale activée. Toutes les fonctions cliniques restent disponibles.</span>
      </div>
    </div>
  );
}

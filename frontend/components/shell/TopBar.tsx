"use client";
import { useEffect, useState } from "react";
import { Circle, Cpu, ShieldCheck } from "lucide-react";
import { Badge } from "@/components/ui/Badge";

type Health = { status: string; online: boolean } | null;
type Models = { local: { model: string }; cloud: { provider: string; model: string }; force_local_only: boolean } | null;

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

export default function TopBar() {
  const [health, setHealth] = useState<Health>(null);
  const [models, setModels] = useState<Models>(null);

  useEffect(() => {
    const tick = async () => {
      try {
        const [h, m] = await Promise.all([
          fetch(`${API}/health`, { cache: "no-store" }).then(r => r.json()),
          fetch(`${API}/api/admin/models`, { cache: "no-store" }).then(r => r.json()),
        ]);
        setHealth(h); setModels(m);
      } catch {
        setHealth({ status: "down", online: false });
      }
    };
    tick();
    const id = setInterval(tick, 15000);
    return () => clearInterval(id);
  }, []);

  const online = health?.online;
  const localOnly = models?.force_local_only;
  const localModel = models?.local.model ?? "—";

  return (
    <header className="h-14 shrink-0 flex items-center gap-4 px-6 rule border-b bg-paper">
      <div className="kicker hidden md:block">Console clinicienne</div>

      <div className="flex-1" />

      <div className="flex items-center gap-2">
        <Badge tone={online ? "good" : "warn"} dot>
          {online ? "En ligne" : "Hors ligne"}
        </Badge>

        {localOnly && (
          <Badge tone="accent" dot>
            <ShieldCheck className="h-3 w-3" strokeWidth={2} />
            Local uniquement
          </Badge>
        )}

        <span className="pill">
          <Cpu className="h-3 w-3" strokeWidth={2} />
          <span className="font-mono text-[11px]">{localModel}</span>
        </span>

        <div className="w-px h-6 bg-line mx-1" />

        <div className="flex items-center gap-2 text-[12px]">
          <Circle className="h-2 w-2 fill-accent text-accent" />
          <span className="text-muted">Dr. Chaabani</span>
        </div>
      </div>
    </header>
  );
}

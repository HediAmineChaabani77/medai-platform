"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight, Stethoscope, FileText, Pill, Gauge } from "lucide-react";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";

type Metrics = {
  window_hours: number;
  requests_total: number;
  requests_local: number;
  requests_cloud: number;
  avg_latency_ms_local: number | null;
  avg_latency_ms_cloud: number | null;
  error_rate: number;
};

type FetchState = "loading" | "ok" | "err";

export default function Home() {
  const [m, setM] = useState<Metrics | null>(null);
  const [state, setState] = useState<FetchState>("loading");

  useEffect(() => {
    api.get<Metrics>("/api/admin/metrics?hours=24")
      .then((r) => { setM(r); setState("ok"); })
      .catch(() => setState("err"));
  }, []);

  return (
    <div>
      <PageHeader
        kicker="Aperçu"
        title={<>Bonjour, <span className="display-italic">docteur</span>.</>}
        description="Trois modules cliniques et un module d'administration. Les requêtes sensibles restent sur le modèle local. Le routage est basé sur règles avec un entraînement heuristique préparant l'étape RL."
      />

      <section
        className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8"
        aria-live="polite"
        {...(state === "loading" ? { "aria-busy": "true" as const } : {})}
      >
        {state === "loading" ? (
          <>
            <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
          </>
        ) : state === "err" ? (
          <Card className="md:col-span-3">
            <div className="px-5 py-4 text-[13px] text-muted">
              Impossible de récupérer les métriques. Vérifiez que le backend est démarré, puis rechargez la page.
            </div>
          </Card>
        ) : (
          <>
            <Metric label="Requêtes 24 h" value={m?.requests_total ?? 0} kicker="total" />
            <Metric label="Local" value={m?.requests_local ?? 0} kicker="on-prem" />
            <Metric label="Cloud" value={m?.requests_cloud ?? 0} kicker="api" />
          </>
        )}
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
        <UCCard
          uc="UC1"
          icon={Stethoscope}
          title="Aide au diagnostic"
          desc="Saisie des symptômes, contexte DMP, hypothèses différentielles avec citations sources."
          href="/diagnostic"
        />
        <UCCard
          uc="UC2"
          icon={FileText}
          title="Génération de compte-rendu"
          desc="Texte libre, audio, ou template. Signature électronique et archivage DPI."
          href="/report"
        />
        <UCCard
          uc="UC3"
          icon={Pill}
          title="Vérification d'ordonnance"
          desc="Recherche médicament, interactions, contre-indications, alternatives. Toujours local."
          href="/prescription"
        />
        <UCCard
          uc="UC4"
          icon={Gauge}
          title="Administration"
          desc="Politiques de routage, monitoring, audit chaîné HMAC, versioning modèles."
          href="/admin"
        />
      </section>

      <section className="mt-8">
        <Card>
          <div className="px-5 py-4 flex items-center justify-between">
            <div>
              <div className="kicker mb-1">Architecture</div>
              <p className="text-[13px] text-muted max-w-xl">
                Routage hybride entre Ollama local et fournisseur cloud compatible OpenAI. PHI détecté, IDs hashés, journal d'audit HMAC chaîné, et boucle d'ajustement basée sur feedback.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone="accent">Local-first</Badge>
              <Badge>RL bootstrap</Badge>
              <Badge>HIPAA/RGPD</Badge>
            </div>
          </div>
        </Card>
      </section>
    </div>
  );
}

function Metric({ label, value, kicker }: { label: string; value: number | string; kicker?: string }) {
  return (
    <Card>
      <div className="px-5 py-4">
        <div className="kicker">{kicker ?? label}</div>
        <div className="mt-1.5 flex items-baseline gap-2">
          <span className="display-italic text-[40px] leading-none tabular-nums">{value}</span>
          <span className="text-[12px] text-muted">{label}</span>
        </div>
      </div>
    </Card>
  );
}

function MetricSkeleton() {
  return (
    <Card>
      <div className="px-5 py-4">
        <div className="h-[11px] w-16 rounded bg-line/50" />
        <div className="mt-2 h-[34px] w-24 rounded bg-line/30" />
      </div>
    </Card>
  );
}

function UCCard({
  uc, icon: Icon, title, desc, href,
}: {
  uc: string; icon: any; title: string; desc: string; href: string;
}) {
  return (
    <Link href={href} className="group">
      <Card className="transition-colors hover:border-ink/30">
        <div className="px-5 py-5 flex items-start gap-4">
          <div className="size-10 rounded-lg border border-line flex items-center justify-center shrink-0">
            <Icon className="size-5" strokeWidth={1.5} aria-hidden="true" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="kicker">{uc}</span>
            </div>
            <h2 className="mt-0.5 font-medium text-[15px] text-balance">{title}</h2>
            <p className="text-[13px] text-muted mt-1 leading-relaxed text-pretty">{desc}</p>
          </div>
          <ArrowUpRight className="size-4 text-subtle group-hover:text-ink transition-colors" strokeWidth={1.5} aria-hidden="true" />
        </div>
      </Card>
    </Link>
  );
}

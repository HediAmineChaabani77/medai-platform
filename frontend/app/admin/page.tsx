"use client";
import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Trash2, Plus, ShieldCheck, Cpu, Loader2, LogOut } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, BarChart, Bar, CartesianGrid } from "recharts";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { api, setAuthToken } from "@/lib/api";

type Metrics = {
  window_hours: number;
  requests_total: number;
  requests_local: number;
  requests_cloud: number;
  avg_latency_ms_local: number | null;
  avg_latency_ms_cloud: number | null;
  error_rate: number;
  cloud_cost_estimate_eur?: number;
};
type Policy = { id: number; use_case: string; department: string | null; override: string; reason: string | null; created_at?: string };
type ModelsInfo = {
  local: { model: string; host: string; embed_model: string };
  cloud: { provider: string; model: string; base_url: string };
  force_local_only: boolean;
};
type AuditRow = {
  id: number;
  created_at: string;
  event_type: string;
  use_case?: string | null;
  provider?: string | null;
  model?: string | null;
  rule?: string | null;
  latency_ms?: number | null;
};

export default function AdminPage() {
  return (
    <Suspense fallback={null}>
      <AdminPageInner />
    </Suspense>
  );
}

function AdminPageInner() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const filterUC = sp.get("uc") ?? "";
  const filterEvent = sp.get("event") ?? "";

  const [authenticated, setAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [totp, setTotp] = useState("");

  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [models, setModels] = useState<ModelsInfo | null>(null);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [chainOk, setChainOk] = useState<boolean | null>(null);
  const [newPolicy, setNewPolicy] = useState<Partial<Policy>>({ use_case: "UC2_REPORT", override: "local" });
  const [rlStatus, setRlStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const auditQS = new URLSearchParams({ limit: "20" });
      if (filterUC) auditQS.set("use_case", filterUC);
      if (filterEvent) auditQS.set("event_type", filterEvent);
      const [m, mo, p, a, v] = await Promise.all([
        api.get<Metrics>("/api/admin/metrics?hours=24"),
        api.get<ModelsInfo>("/api/admin/models"),
        api.get<Policy[]>("/api/admin/routing-policies"),
        api.get<AuditRow[]>(`/api/admin/audit?${auditQS}`),
        api.get<{ ok: boolean }>("/api/admin/audit/verify"),
      ]);
      setMetrics(m);
      setModels(mo);
      setPolicies(p);
      setAudit(a);
      setChainOk(v.ok);
      setAuthenticated(true);
      setAuthError(null);
    } catch (e: any) {
      if (e?.status === 401 || e?.status === 403) {
        setAuthenticated(false);
        setAuthError("Authentification administrateur requise.");
      } else {
        setAuthError("Impossible de charger le dashboard.");
      }
    } finally {
      setBusy(false);
      setAuthChecked(true);
    }
  }, [filterUC, filterEvent]);

  useEffect(() => {
    api.get<{ authenticated: boolean }>("/auth/me")
      .then((me) => setAuthenticated(Boolean(me.authenticated)))
      .catch(() => setAuthenticated(false))
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (authenticated) refresh();
  }, [authenticated, refresh]);

  const login = async () => {
    setAuthError(null);
    try {
      const r = await api.post<{ access_token: string }>("/auth/login", {
        username,
        password,
        totp_code: totp || null,
      });
      setAuthToken(r.access_token);
      setAuthenticated(true);
      await refresh();
    } catch (e: any) {
      setAuthError(e?.body?.detail || e?.message || "Échec de connexion");
    }
  };

  const fillDevTotp = async () => {
    try {
      const r = await api.get<{ totp_now: string }>(`/auth/dev/totp-now?username=${encodeURIComponent(username)}`);
      setTotp(r.totp_now);
    } catch {
      setAuthError("Impossible de récupérer le code TOTP dev.");
    }
  };

  const bootstrapAdmin = async () => {
    try {
      await api.post("/auth/bootstrap-admin", {});
      setAuthError("Compte admin seedé. Utilisez admin / admin123 + code TOTP.");
    } catch (e: any) {
      setAuthError(e?.body?.detail || "Bootstrap admin impossible");
    }
  };

  const logout = () => {
    setAuthToken(null);
    setAuthenticated(false);
    setMetrics(null);
    setPolicies([]);
    setAudit([]);
    setChainOk(null);
  };

  const updateFilter = (key: "uc" | "event", value: string) => {
    const next = new URLSearchParams(sp.toString());
    if (value) next.set(key, value); else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`);
  };

  const createPolicy = async () => {
    if (!newPolicy.use_case || !newPolicy.override) return;
    setBusy(true);
    try {
      await api.post("/api/admin/routing-policies", newPolicy);
      setNewPolicy({ use_case: "UC2_REPORT", override: "local" });
      await refresh();
    } finally { setBusy(false); }
  };
  const deletePolicy = async (id: number) => {
    const ok = window.confirm(`Supprimer la politique #${id} ?`);
    if (!ok) return;
    await api.del(`/api/admin/routing-policies/${id}`);
    await refresh();
  };
  const runRL = async () => {
    try {
      const r = await api.post<{ run_id: number; recommendation_count?: number; recommendations?: any[] }>("/api/admin/rl/train", {});
      setRlStatus(`run #${r.run_id}`);
    } catch (e: any) {
      setRlStatus(`error ${e?.status ?? ""}`.trim());
    }
  };

  if (!authChecked || (!authenticated && busy)) {
    return <div className="py-10 text-sm text-slate-500">Chargement…</div>;
  }

  if (!authenticated) {
    return (
      <div className="max-w-xl mt-10">
        <PageHeader
          kicker="UC4 · Administration"
          title={<>Connexion <span className="display-italic">administrateur</span></>}
          description="Accès protégé par rôle + TOTP (2FA)."
        />
        <Card className="mt-6">
          <div className="px-5 py-5 space-y-4">
            <div>
              <Label>Username</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </div>
            <div>
              <Label>Password</Label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </div>
            <div>
              <Label>TOTP (6 digits)</Label>
              <Input value={totp} onChange={(e) => setTotp(e.target.value)} placeholder="123456" autoComplete="one-time-code" />
            </div>
            <div className="flex gap-2">
              <Button onClick={login}>Se connecter</Button>
              <Button variant="ghost" onClick={fillDevTotp}>Code TOTP (dev)</Button>
              <Button variant="ghost" onClick={bootstrapAdmin}>Bootstrap admin (dev)</Button>
            </div>
            {authError && <p className="text-sm text-red-700">{String(authError)}</p>}
          </div>
        </Card>
      </div>
    );
  }

  const seriesTotal = audit.slice(0, 20).map((a, i) => ({ t: i, latency: a.latency_ms ?? 0 })).reverse();
  const providerMix = [
    { name: "Local", value: metrics?.requests_local ?? 0 },
    { name: "Cloud", value: metrics?.requests_cloud ?? 0 },
  ];

  return (
    <div>
      <PageHeader
        kicker="UC4 · Administration"
        title={<>Monitoring et <span className="display-italic">politique</span> de routage.</>}
        description="Dashboard admin protégé par JWT + 2FA, audit HMAC, règles, versions modèles et entraînement RL (heuristique)."
        actions={
          <div className="flex gap-2">
            <Button variant="ghost" onClick={refresh} aria-label="Rafraîchir">
              <Loader2 className={`size-3.5 ${busy ? "animate-spin" : ""}`} /> Rafraîchir
            </Button>
            <Button variant="ghost" onClick={logout}><LogOut className="size-3.5" /> Déconnexion</Button>
          </div>
        }
      />

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
        <Metric kicker="Requêtes 24 h" value={metrics?.requests_total ?? "—"} />
        <Metric kicker="Local" value={metrics?.requests_local ?? "—"} suffix="sur site" />
        <Metric kicker="Cloud" value={metrics?.requests_cloud ?? "—"} suffix="API" />
        <Metric kicker="Latence local" value={metrics?.avg_latency_ms_local?.toFixed(0) ?? "—"} suffix="ms" />
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-4">
        <Card className="lg:col-span-2">
          <div className="px-5 py-3 rule"><span className="kicker">Latence (20 dernières)</span></div>
          <div className="px-2 py-2 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={seriesTotal}>
                <CartesianGrid stroke="rgb(var(--line))" vertical={false} />
                <XAxis dataKey="t" stroke="rgb(var(--subtle))" fontSize={10} />
                <YAxis stroke="rgb(var(--subtle))" fontSize={10} unit=" ms" />
                <Tooltip contentStyle={{ background: "rgb(var(--paper))", border: "1px solid rgb(var(--line))", fontSize: 12 }} />
                <Line type="monotone" dataKey="latency" stroke="rgb(var(--accent))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <div className="px-5 py-3 rule"><span className="kicker">Répartition local/cloud</span></div>
          <div className="px-2 py-2 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={providerMix} layout="vertical">
                <XAxis type="number" stroke="rgb(var(--subtle))" fontSize={10} />
                <YAxis type="category" dataKey="name" stroke="rgb(var(--subtle))" fontSize={11} width={50} />
                <Tooltip contentStyle={{ background: "rgb(var(--paper))", border: "1px solid rgb(var(--line))", fontSize: 12 }} />
                <Bar dataKey="value" fill="rgb(var(--accent))" radius={[4, 4, 4, 4]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
        <Card>
          <div className="px-5 py-3 rule flex items-center justify-between">
            <span className="kicker">Politiques de routage</span>
            <Badge dot>manuel + recommandation RL</Badge>
          </div>
          <div className="px-5 py-4">
            <div className="flex flex-wrap items-end gap-2 mb-4">
              <div className="w-40">
                <Label>UC</Label>
                <select className="input py-1.5" value={newPolicy.use_case ?? ""} onChange={(e) => setNewPolicy({ ...newPolicy, use_case: e.target.value })}>
                  <option value="UC1_DIAGNOSTIC">UC1</option>
                  <option value="UC2_REPORT">UC2</option>
                  <option value="UC3_PRESCRIPTION">UC3</option>
                </select>
              </div>
              <div className="w-32">
                <Label>Override</Label>
                <select className="input py-1.5" value={newPolicy.override ?? "local"} onChange={(e) => setNewPolicy({ ...newPolicy, override: e.target.value })}>
                  <option value="local">local</option>
                  <option value="cloud">cloud</option>
                </select>
              </div>
              <div className="flex-1 min-w-[160px]">
                <Label>Département</Label>
                <Input value={newPolicy.department ?? ""} onChange={(e) => setNewPolicy({ ...newPolicy, department: e.target.value })} placeholder="cardiologie" />
              </div>
              <Button variant="primary" size="sm" onClick={createPolicy} disabled={busy}><Plus className="size-3.5" /> Ajouter</Button>
            </div>

            <table className="table-sm w-full">
              <thead><tr><th>UC</th><th>Département</th><th>Override</th><th></th></tr></thead>
              <tbody>
                {policies.map((p) => (
                  <tr key={p.id}>
                    <td className="font-mono text-[12px]">{p.use_case}</td>
                    <td className="text-[12px]">{p.department ?? "—"}</td>
                    <td><Badge tone={p.override === "local" ? "accent" : "warn"} dot>{p.override}</Badge></td>
                    <td className="text-right">
                      <button type="button" onClick={() => deletePolicy(p.id)} className="p-1 rounded hover:bg-line/40">
                        <Trash2 className="size-3.5 text-subtle hover:text-danger" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card>
          <div className="px-5 py-3 rule flex items-center gap-2"><Cpu className="size-4" /><span className="kicker">Modèles</span></div>
          <div className="px-5 py-4 space-y-4">
            {models && (
              <>
                <ModelRow label="Local · génération" value={models.local.model} host={models.local.host} />
                <ModelRow label="Local · embeddings" value={models.local.embed_model} host={models.local.host} />
                <ModelRow label={`Cloud · ${models.cloud.provider}`} value={models.cloud.model} host={models.cloud.base_url} />
                <div className="flex items-center gap-2 pt-2">
                  {models.force_local_only && <Badge tone="accent" dot><ShieldCheck className="size-3" /> Force local only</Badge>}
                </div>
              </>
            )}
            <div className="rule pt-3 mt-2">
              <div className="kicker mb-1">RL training</div>
              <p className="text-[11px] text-muted mb-2">Entraîneur heuristique exécuté sur audit + feedback (prépare la transition RL).</p>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="ghost" onClick={runRL}>Lancer entraînement</Button>
                {rlStatus && <Badge dot>{rlStatus}</Badge>}
              </div>
            </div>
          </div>
        </Card>
      </section>

      <section className="mt-4">
        <Card>
          <div className="px-5 py-3 rule flex items-center justify-between gap-4 flex-wrap">
            <h2 className="kicker">Journal d'audit</h2>
            <div className="flex items-center gap-2">
              <select className="input py-1 text-[12px] w-[140px]" value={filterUC} onChange={(e) => updateFilter("uc", e.target.value)}>
                <option value="">Tous les UC</option>
                <option value="UC1_DIAGNOSTIC">UC1</option>
                <option value="UC2_REPORT">UC2</option>
                <option value="UC3_PRESCRIPTION">UC3</option>
                <option value="UC_QA">UC_QA</option>
              </select>
              <select className="input py-1 text-[12px] w-[160px]" value={filterEvent} onChange={(e) => updateFilter("event", e.target.value)}>
                <option value="">Tous les événements</option>
                <option value="llm_call">llm_call</option>
                <option value="admin_policy_change">admin_policy_change</option>
                <option value="rl_train_run">rl_train_run</option>
              </select>
              <Badge tone={chainOk ? "good" : "danger"} dot>chaîne HMAC {chainOk ? "intacte" : "altérée"}</Badge>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="table-sm w-full">
              <thead><tr><th>#</th><th>Date</th><th>Événement</th><th>UC</th><th>Provider</th><th>Modèle</th><th>Règle</th><th className="text-right">Latence</th></tr></thead>
              <tbody>
                {audit.map((r) => (
                  <tr key={r.id}>
                    <td className="font-mono text-[11px] text-subtle">{r.id}</td>
                    <td className="text-[11px]">{new Date(r.created_at).toLocaleString("fr-FR")}</td>
                    <td className="text-[12px]">{r.event_type}</td>
                    <td className="font-mono text-[11px]">{r.use_case ?? "—"}</td>
                    <td className="text-[12px]">{r.provider ?? "—"}</td>
                    <td className="text-[11px] text-muted">{r.model ?? "—"}</td>
                    <td className="font-mono text-[10px] text-subtle">{r.rule ?? "—"}</td>
                    <td className="font-mono text-[11px] text-right tabular-nums">{r.latency_ms != null ? `${r.latency_ms}\u00a0ms` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </div>
  );
}

function Metric({ kicker, value, suffix }: { kicker: string; value: number | string; suffix?: string }) {
  return (
    <Card>
      <div className="px-5 py-4">
        <div className="kicker">{kicker}</div>
        <div className="mt-1.5 flex items-baseline gap-2">
          <span className="display-italic text-[32px] leading-none tabular-nums">{value}</span>
          {suffix && <span className="text-[11px] text-muted">{suffix}</span>}
        </div>
      </div>
    </Card>
  );
}

function ModelRow({ label, value, host }: { label: string; value: string; host?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-line last:border-0 pb-2 last:pb-0">
      <div className="min-w-0">
        <div className="text-[11px] text-muted">{label}</div>
        <div className="font-mono text-[12px] truncate">{value}</div>
      </div>
      {host && <div className="font-mono text-[10px] text-subtle truncate max-w-[180px]">{host}</div>}
    </div>
  );
}

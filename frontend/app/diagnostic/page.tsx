"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Stethoscope, Sparkles, Download, AlertTriangle, Check, X, HelpCircle, Loader2 } from "lucide-react";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Field, Textarea, Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import VoiceInput from "@/components/VoiceInput";
import { api } from "@/lib/api";

type Diagnosis = { condition: string; probability: number; reasoning: string; icd10?: string | null; citations?: string[] };
type UC1Response = {
  diagnoses: Diagnosis[];
  red_flags: string[];
  provider_used: string;
  model_used: string;
  rule: string;
  audit_id: number;
  citations: { id: string; source: string; section: string }[];
  raw_answer: string;
};

export default function DiagnosticPage() {
  const router = useRouter();
  const [symptoms, setSymptoms] = useState("");
  const [patientId, setPatientId] = useState("");
  const [dmpLoading, setDmpLoading] = useState(false);
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [antecedents, setAntecedents] = useState("");
  const [result, setResult] = useState<UC1Response | null>(null);
  const [explainText, setExplainText] = useState("");
  const [explainLoading, setExplainLoading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const body = {
        symptoms,
        patient_context: {
          age: age ? Number(age) : undefined,
          sexe: sex || undefined,
          antecedents: antecedents ? antecedents.split(",").map((s) => s.trim()).filter(Boolean) : [],
        },
        patient_id: patientId || undefined,
      };
      const r = await api.post<UC1Response>("/api/uc1/diagnose", body);
      setResult(r);
    } catch (e: any) {
      setError(e?.message ?? "Échec de la requête");
    } finally {
      setLoading(false);
    }
  };

  const loadDmp = async () => {
    if (!patientId) return;
    setDmpLoading(true);
    try {
      const r = await api.get<{ record: any }>(`/api/dmp/${encodeURIComponent(patientId)}`);
      const rec = r.record || {};
      if (rec.age != null) setAge(String(rec.age));
      if (rec.sexe) setSex(String(rec.sexe));
      if (Array.isArray(rec.antecedents)) setAntecedents(rec.antecedents.join(", "));
    } catch {
      // Keep manual entry if no DMP record.
    } finally {
      setDmpLoading(false);
    }
  };

  const exportToCR = () => {
    if (!result) return;
    const md = [
      `# Aide au diagnostic — export CR`,
      `Patient: ${patientId || "—"}`,
      `Contexte: ${age ? `${age} ans` : ""} ${sex ?? ""} ${antecedents ? `ATCD: ${antecedents}` : ""}`.trim(),
      ``,
      `## Symptômes`, symptoms, ``,
      `## Hypothèses diagnostiques`,
      ...result.diagnoses.map((d, i) => `${i + 1}. **${d.condition}** (p=${d.probability.toFixed(2)})${d.icd10 ? ` — CIM-10 ${d.icd10}` : ""}\n   _${d.reasoning}_`),
      ``,
      result.red_flags?.length ? `## Signaux d'urgence\n${result.red_flags.map((r) => `- ${r}`).join("\n")}` : "",
      ``,
      `## Sources`,
      ...result.citations.map((c) => `- [${c.id}] ${c.source} — ${c.section}`),
      ``,
      `_Modèle: ${result.model_used} · routage: ${result.rule} · audit #${result.audit_id}_`,
    ].filter(Boolean).join("\n");
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem("uc1_export_markdown", md);
    }
    router.push("/report?import=uc1");
  };

  const sendFeedback = async (action: "validate" | "reject" | "explain") => {
    if (!result) return;
    await api.post("/api/uc1/feedback", {
      audit_log_id: result.audit_id,
      use_case: "UC1_DIAGNOSTIC",
      action,
    });
  };

  const explainPair = async () => {
    if (!result || result.diagnoses.length < 2) return;
    const [a, b] = result.diagnoses;
    setExplainLoading(true);
    setExplainText("");
    try {
      const exp = await api.post<{ explanation: string }>("/api/uc1/explain", {
        symptoms,
        option_a: a.condition,
        option_b: b.condition,
        patient_context: {
          age: age ? Number(age) : undefined,
          sexe: sex || undefined,
          antecedents: antecedents ? antecedents.split(",").map((s) => s.trim()).filter(Boolean) : [],
        },
        patient_id: patientId || undefined,
      });
      setExplainText(exp.explanation);
      await sendFeedback("explain");
    } catch (e: any) {
      setExplainText(`Explication indisponible: ${e?.message || "erreur"}`);
    } finally {
      setExplainLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        kicker="UC1 · Aide au diagnostic"
        title={<>Hypothèses <span className="display-italic">différentielles</span> à partir des symptômes.</>}
        description="Saisie texte ou dictée vocale. Le contexte DMP est injecté dans la requête. Retrieval reranké, routé en local par défaut pour protéger les PHI."
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6 mt-8">
        <Card>
          <div className="px-5 py-4 rule flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Stethoscope className="size-4" strokeWidth={1.5} aria-hidden="true" />
              <h2 className="text-[13px] font-medium">Consultation</h2>
            </div>
            <VoiceInput onTranscript={(t) => setSymptoms(t)} />
          </div>
          <div className="px-5 py-5 space-y-5">
            <Field label="Symptômes et examen clinique" hint="Dictée possible">
              <Textarea
                value={symptoms}
                onChange={(e) => setSymptoms(e.target.value)}
                placeholder="Ex : douleur thoracique constrictive avec irradiation bras gauche depuis 45 min, sueurs, dyspnée…"
                rows={6}
              />
            </Field>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <Field label="Patient (ID)">
                  <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="P-001" autoComplete="off" spellCheck={false} />
                </Field>
                <button type="button" onClick={loadDmp} className="text-[11px] text-muted hover:text-ink mt-1" disabled={dmpLoading || !patientId}>
                  {dmpLoading ? "Chargement DMP…" : "Importer depuis DMP"}
                </button>
              </div>
              <Field label="Âge">
                <Input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} placeholder="62" autoComplete="off" />
              </Field>
              <Field label="Sexe">
                <Input value={sex} onChange={(e) => setSex(e.target.value)} placeholder="M / F" autoComplete="off" />
              </Field>
              <div className="col-span-2 md:col-span-1">
                <Field label="ATCD">
                  <Input value={antecedents} onChange={(e) => setAntecedents(e.target.value)} placeholder="HTA, tabagisme" autoComplete="off" />
                </Field>
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <Button variant="primary" onClick={submit} disabled={!symptoms || loading}>
                {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                {loading ? "Analyse en cours…" : "Proposer un différentiel"}
              </Button>
              {result && (
                <Button variant="ghost" onClick={exportToCR}>
                  <Download className="size-3.5" /> Exporter au CR
                </Button>
              )}
            </div>

            {error && (
              <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-[13px] text-danger">
                <strong className="font-medium">{error}.</strong> Vérifiez la connexion au serveur local, puis relancez l'analyse.
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4" aria-live="polite" {...(loading ? { "aria-busy": "true" as const } : {})}>
          <Card>
            <div className="px-5 py-3 rule flex items-center justify-between">
              <h2 className="kicker">Résultats</h2>
              {result && (
                <div className="flex items-center gap-2">
                  <Badge tone="accent" dot>{result.provider_used}</Badge>
                  <span className="font-mono text-[10px] text-subtle">{result.rule}</span>
                </div>
              )}
            </div>
            <div className="px-5 py-4">
              {!result && !loading && (
                <EmptyState
                  icon={Stethoscope}
                  title="Aucune analyse pour l'instant"
                  hint="Renseignez les symptômes, puis lancez l'analyse."
                />
              )}
              {loading && <Skeleton />}
              {result && (
                <div className="space-y-4">
                  {result.red_flags?.length > 0 && (
                    <div className="rounded-md border border-danger/30 bg-danger/5 p-3">
                      <div className="flex items-start gap-2">
                        <AlertTriangle className="size-4 text-danger shrink-0 mt-0.5" strokeWidth={1.5} />
                        <div>
                          <div className="text-[12px] font-medium text-danger">Signaux d'urgence</div>
                          <ul className="mt-1 text-[12px] text-danger/90 space-y-0.5">
                            {result.red_flags.map((f, i) => <li key={i}>· {f}</li>)}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}

                  <ul className="space-y-3">
                    {result.diagnoses.map((d, i) => (
                      <li key={i} className="border-b border-line last:border-0 pb-3 last:pb-0">
                        <div className="flex items-baseline justify-between gap-3">
                          <h3 className="text-[14px] font-medium text-balance" translate="no">{d.condition}</h3>
                          <span className="font-mono text-[12px] text-muted tabular-nums">
                            p={d.probability.toFixed(2)}
                          </span>
                        </div>
                        {d.icd10 && (
                          <div className="mt-0.5 font-mono text-[10px] text-subtle">CIM-10 {d.icd10}</div>
                        )}
                        <p className="mt-1.5 text-[12px] text-muted leading-relaxed text-pretty">
                          {d.reasoning}
                        </p>
                      </li>
                    ))}
                  </ul>

                  <div className="pt-2 flex items-center gap-1.5">
                    <Button size="sm" variant="ghost" onClick={() => sendFeedback("validate")} aria-label="Valider le diagnostic">
                      <Check className="size-3" /> Valider
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => sendFeedback("reject")} aria-label="Rejeter le diagnostic">
                      <X className="size-3" /> Rejeter
                    </Button>
                    <Button size="sm" variant="ghost" onClick={explainPair} aria-label="Comparer les deux diagnostics principaux" disabled={explainLoading || result.diagnoses.length < 2}>
                      <HelpCircle className="size-3" /> Expliquer
                    </Button>
                  </div>

                  {(explainLoading || explainText) && (
                    <div className="rounded-md border border-line p-3">
                      <div className="text-[12px] font-medium mb-1">Pourquoi A plutôt que B ?</div>
                      {explainLoading ? (
                        <div className="text-[12px] text-muted">Comparaison en cours…</div>
                      ) : (
                        <p className="text-[12px] text-muted whitespace-pre-wrap text-pretty">{explainText}</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </Card>

          {result && result.citations?.length > 0 && (
            <Card>
              <div className="px-5 py-3 rule"><span className="kicker">Sources RAG (reranked)</span></div>
              <div className="px-5 py-4">
                <ul className="space-y-2">
                  {result.citations.slice(0, 5).map((c, i) => (
                    <li key={i} className="text-[12px]">
                      <span className="font-mono text-subtle mr-2">[{c.id}]</span>
                      <span className="font-medium">{c.source}</span>
                      {c.section && <span className="text-muted"> — {c.section}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, hint }: { icon: any; title: string; hint: string }) {
  return (
    <div className="py-10 text-center">
      <div className="inline-flex size-10 rounded-lg border border-line items-center justify-center mb-3">
        <Icon className="size-4 text-subtle" strokeWidth={1.5} />
      </div>
      <p className="text-[13px] font-medium text-balance">{title}</p>
      <p className="text-[12px] text-muted mt-1 text-pretty">{hint}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2">
      {[...Array(3)].map((_, i) => (
        <div key={i} className="h-16 rounded-md bg-line/30" />
      ))}
    </div>
  );
}

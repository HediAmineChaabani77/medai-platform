"use client";
import { useState } from "react";
import { Pill, Sparkles, AlertOctagon, AlertTriangle, ShieldCheck, Loader2 } from "lucide-react";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Field, Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge, SeverityBadge } from "@/components/ui/Badge";
import { MedList, type Medication } from "@/components/DrugPicker";
import { api } from "@/lib/api";

type InteractionAlert = {
  type: string;
  severity: "minor" | "moderate" | "major";
  drug_a?: string;
  drug_b?: string;
  mechanism: string;
  note?: string | null;
};

type UC3Response = {
  blocked: boolean;
  max_severity: "minor" | "moderate" | "major" | null;
  alerts: InteractionAlert[];
  explanation: string;
  provider_used: string | null;
  model_used: string | null;
  rule: string | null;
  audit_id: number | null;
  alternatives?: string[];
};

export default function PrescriptionPage() {
  const [newMeds, setNewMeds] = useState<Medication[]>([{ name: "" }]);
  const [currentMeds, setCurrentMeds] = useState<Medication[]>([]);
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [dfg, setDfg] = useState("");
  const [pregnant, setPregnant] = useState(false);
  const [allergies, setAllergies] = useState("");
  const [patientId, setPatientId] = useState("");
  const [dmpLoading, setDmpLoading] = useState(false);
  const [result, setResult] = useState<UC3Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setLoading(true); setError(null); setResult(null);
    try {
      const body = {
        new_medications: newMeds.filter((m) => m.name).map(clean),
        patient: {
          age: age ? Number(age) : undefined,
          sex: sex || undefined,
          allergies: allergies ? allergies.split(",").map((s) => s.trim()).filter(Boolean) : [],
          current_medications: currentMeds.filter((m) => m.name).map(clean),
          pregnant,
          dfg_ml_min: dfg ? Number(dfg) : undefined,
        },
        patient_id: patientId || undefined,
      };
      const r = await fetch((process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001") + "/api/uc3/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      // HTTP 409 means blocked — the payload comes under `detail`.
      setResult(r.status === 409 ? data.detail : data);
    } catch (e: any) {
      setError(e?.message ?? "Échec de la vérification");
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
      if (rec.dfg_ml_min != null) setDfg(String(rec.dfg_ml_min));
      if (Array.isArray(rec.allergies)) setAllergies(rec.allergies.join(", "));
      if (Array.isArray(rec.current_medications)) {
        setCurrentMeds(
          rec.current_medications
            .filter((x: any) => x && x.name)
            .map((x: any) => ({
              name: String(x.name),
              dose: x.dose ? String(x.dose) : undefined,
              frequency: x.frequency ? String(x.frequency) : undefined,
              duration: x.duration ? String(x.duration) : undefined,
              route: x.route ? String(x.route) : undefined,
            }))
        );
      }
      if (typeof rec.pregnant === "boolean") setPregnant(Boolean(rec.pregnant));
    } catch {
      // no-op
    } finally {
      setDmpLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        kicker="UC3 · Vérification d'ordonnance"
        title={<>Sécurité <span className="display-italic">pharmaceutique</span> avant signature.</>}
        description="Recherche sur les 13 594 médicaments BDPM. Interactions, contre-indications, redondance thérapeutique. Routage toujours local."
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-6 mt-8">
        <Card>
          <div className="px-5 py-4 rule flex items-center gap-2">
            <Pill className="size-4" strokeWidth={1.5} aria-hidden="true" />
            <h2 className="text-[13px] font-medium">Nouvelle prescription</h2>
          </div>

          <div className="px-5 py-5 space-y-6">
            <section>
              <div className="kicker mb-2">À prescrire</div>
              <MedList meds={newMeds} onChange={setNewMeds} />
            </section>

            <section>
              <div className="kicker mb-2">Traitement en cours</div>
              <MedList meds={currentMeds} onChange={setCurrentMeds} />
            </section>

            <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <div>
                <Field label="Patient (ID)">
                  <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="P-001" autoComplete="off" spellCheck={false} />
                </Field>
                <button type="button" onClick={loadDmp} className="text-[11px] text-muted hover:text-ink mt-1" disabled={dmpLoading || !patientId}>
                  {dmpLoading ? "Chargement DMP…" : "Importer DMP"}
                </button>
              </div>
              <Field label="Âge">
                <Input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} autoComplete="off" />
              </Field>
              <Field label="Sexe">
                <Input value={sex} onChange={(e) => setSex(e.target.value)} placeholder="M / F" autoComplete="off" />
              </Field>
              <Field label="DFG (mL/min)">
                <Input type="number" inputMode="numeric" value={dfg} onChange={(e) => setDfg(e.target.value)} autoComplete="off" />
              </Field>
              <div>
                <Label>Grossesse</Label>
                <label className="flex items-center gap-2 h-[38px] px-3 border border-line rounded-md cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={pregnant}
                    onChange={(e) => setPregnant(e.target.checked)}
                    className="size-3.5 accent-[rgb(var(--accent))]"
                  />
                  <span className="text-[12px] text-muted">Enceinte</span>
                </label>
              </div>
            </section>

            <section>
              <Field label="Allergies connues (séparées par virgule)">
                <Input value={allergies} onChange={(e) => setAllergies(e.target.value)} placeholder="pénicilline, sulfamides…" spellCheck={false} autoComplete="off" />
              </Field>
            </section>

            <div className="pt-1 flex items-center gap-2">
              <Button variant="primary" onClick={submit} disabled={loading || !newMeds.some((m) => m.name)}>
                {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                {loading ? "Analyse…" : "Vérifier la prescription"}
              </Button>
            </div>

            {error && (
              <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-[13px] text-danger">
                <strong className="font-medium">{error}.</strong> Vérifiez les médicaments saisis, puis relancez la vérification.
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4" aria-live="polite" {...(loading ? { "aria-busy": "true" as const } : {})}>
          <Card>
            <div className="px-5 py-3 rule flex items-center justify-between">
              <h2 className="kicker">Vérification</h2>
              {result && (
                <div className="flex items-center gap-2">
                  <SeverityBadge severity={result.max_severity} />
                  {result.blocked && <Badge tone="danger" dot>bloqué</Badge>}
                </div>
              )}
            </div>
            <div className="px-5 py-4">
              {!result && !loading && (
                <EmptyState />
              )}
              {loading && <Skeleton />}
              {result && (
                <div className="space-y-3">
                  {result.blocked && (
                    <div className="rounded-md border border-danger/30 bg-danger/5 p-3 flex items-start gap-2">
                      <AlertOctagon className="size-4 text-danger shrink-0 mt-0.5" strokeWidth={1.5} />
                      <div>
                        <div className="text-[12px] font-medium text-danger">Prescription bloquée (HTTP 409)</div>
                        <p className="text-[11px] text-danger/90 mt-0.5 text-pretty">
                          Une interaction ou une contre-indication majeure est détectée. Modifiez la prescription ou documentez la dérogation.
                        </p>
                      </div>
                    </div>
                  )}
                  {result.alerts.length === 0 ? (
                    <p className="text-[13px] text-muted text-pretty">Aucune alerte. La prescription ne déclenche pas de signal de sécurité.</p>
                  ) : (
                    <ul className="space-y-2">
                      {result.alerts.map((a, i) => (
                        <li key={i} className="rounded-md border border-line p-3">
                          <div className="flex items-start gap-2">
                            <SeverityIcon severity={a.severity} />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-baseline gap-2 flex-wrap">
                                <span className="text-[13px] font-medium">
                                  {a.drug_a}{a.drug_b && ` + ${a.drug_b}`}
                                </span>
                                <span className="font-mono text-[10px] text-subtle">{a.type}</span>
                              </div>
                              <p className="text-[12px] text-muted mt-0.5 text-pretty">{a.mechanism}</p>
                              {a.note && <p className="text-[11px] text-subtle mt-1">{a.note}</p>}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  )}

                  {result.explanation && (
                    <details className="rounded-md border border-line p-3">
                      <summary className="cursor-pointer text-[12px] font-medium">Explication détaillée (LLM)</summary>
                      <p className="mt-2 text-[12px] text-muted leading-relaxed whitespace-pre-wrap text-pretty">
                        {result.explanation}
                      </p>
                    </details>
                  )}

                  {result.alternatives && result.alternatives.length > 0 && (
                    <div className="rounded-md border border-line p-3">
                      <div className="text-[12px] font-medium">Alternatives suggérées</div>
                      <ul className="mt-1 text-[12px] text-muted space-y-0.5">
                        {result.alternatives.map((alt, i) => <li key={i}>· {alt}</li>)}
                      </ul>
                    </div>
                  )}

                  <div className="pt-1 text-[11px] text-subtle">
                    routage <span className="font-mono">{result.rule ?? "—"}</span>
                    {result.audit_id && <> · audit <span className="font-mono">#{result.audit_id}</span></>}
                  </div>
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function clean(m: Medication): Medication {
  const out: Medication = { name: m.name };
  if (m.dose) out.dose = m.dose;
  if (m.frequency) out.frequency = m.frequency;
  if (m.duration) out.duration = m.duration;
  if (m.route) out.route = m.route;
  if (m.atc) out.atc = m.atc;
  return out;
}

function SeverityIcon({ severity }: { severity: "minor" | "moderate" | "major" }) {
  if (severity === "major") return <AlertOctagon className="size-4 text-danger shrink-0 mt-0.5" strokeWidth={1.5} />;
  if (severity === "moderate") return <AlertTriangle className="size-4 text-warn shrink-0 mt-0.5" strokeWidth={1.5} />;
  return <ShieldCheck className="size-4 text-good shrink-0 mt-0.5" strokeWidth={1.5} />;
}

function EmptyState() {
  return (
    <div className="py-10 text-center">
      <div className="inline-flex size-10 rounded-lg border border-line items-center justify-center mb-3">
        <Pill className="size-4 text-subtle" strokeWidth={1.5} />
      </div>
      <p className="text-[13px] font-medium text-balance">Aucune vérification</p>
      <p className="text-[12px] text-muted mt-1 text-pretty">Ajoutez un médicament à prescrire et lancez la vérification.</p>
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

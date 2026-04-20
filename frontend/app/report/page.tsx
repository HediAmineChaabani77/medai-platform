"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { FileText, Sparkles, Download, Send, ShieldCheck, Loader2 } from "lucide-react";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Field, Textarea, Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import AudioUpload from "@/components/AudioUpload";
import { api } from "@/lib/api";

const TEMPLATES = {
  Consultation: "Consultation de médecine générale\n\nMotif:\n\nAnamnèse:\n\nExamen clinique:\n\nConclusion:\n\nPlan de soins:",
  Hospitalisation: "Compte-rendu d'hospitalisation\n\nMotif d'admission:\n\nATCD:\n\nHistoire de la maladie:\n\nExamens complémentaires:\n\nSynthèse:\n\nTraitement de sortie:\n\nSuivi:",
  Opératoire: "Compte-rendu opératoire\n\nIntervention:\n\nOpérateur:\n\nType d'anesthésie:\n\nDéroulement:\n\nSuites opératoires immédiates:",
  Urgences: "Compte-rendu d'urgences\n\nMotif de consultation:\n\nTri IOA:\n\nExamen clinique:\n\nExamens complémentaires:\n\nDiagnostic:\n\nOrientation:",
} as const;

type Template = keyof typeof TEMPLATES;

type UC2Response = {
  report_type: string;
  markdown: string;
  sections: { title: string; content: string }[];
  signature: string;
  provider_used: string;
  model_used: string;
  rule: string;
  audit_id: number;
};

export default function ReportPage() {
  return (
    <Suspense fallback={null}>
      <ReportPageInner />
    </Suspense>
  );
}

function ReportPageInner() {
  const params = useSearchParams();
  const [reportType, setReportType] = useState<Template>("Consultation");
  const [rawText, setRawText] = useState("");
  const [patientId, setPatientId] = useState("");
  const [physicianKey, setPhysicianKey] = useState("dr-42");
  const [result, setResult] = useState<UC2Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [signed, setSigned] = useState(false);
  const [archiveInfo, setArchiveInfo] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Warn the physician before losing unsaved clinical notes.
  useEffect(() => {
    const dirty = rawText.trim().length > 0 && !result;
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "Notes cliniques non générées. Quitter cette page ?";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [rawText, result]);

  useEffect(() => {
    if (params.get("import") !== "uc1") return;
    if (typeof window === "undefined") return;
    const uc1 = window.sessionStorage.getItem("uc1_export_markdown");
    if (!uc1) return;
    setRawText(uc1);
    window.sessionStorage.removeItem("uc1_export_markdown");
  }, [params]);

  const submit = async () => {
    setLoading(true); setError(null); setResult(null); setSigned(false);
    try {
      const r = await api.post<UC2Response>("/api/uc2/generate", {
        report_type: reportType,
        raw_text: rawText,
        patient_id: patientId || undefined,
        physician_key: physicianKey,
      });
      setResult(r);
    } catch (e: any) {
      setError(e?.message ?? "Échec de la génération");
    } finally {
      setLoading(false);
    }
  };

  const download = () => {
    if (!result) return;
    const blob = new Blob([result.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `CR_${reportType}_${Date.now()}.md`;
    a.click(); URL.revokeObjectURL(url);
  };

  const archiveToDPI = async () => {
    if (!result) return;
    try {
      const r = await api.post<{ archive_id: number; archive_path: string; destination: string }>("/api/uc2/archive", {
        patient_id: patientId || undefined,
        report_type: reportType,
        markdown: result.markdown,
        signature: result.signature,
        signed_by: "dr1",
        destination: "DPI",
      });
      setArchiveInfo(`Archivé #${r.archive_id} (${r.destination})`);
    } catch (e: any) {
      setArchiveInfo(`Échec archivage: ${e?.message || "erreur"}`);
    }
  };

  return (
    <div>
      <PageHeader
        kicker="UC2 · Génération de compte-rendu"
        title={<>Du <span className="display-italic">texte brut</span> au CR structuré, signé, archivable.</>}
        description="Saisie libre, dictée audio ou import de template. Whisper transcrit localement. Signature électronique HMAC et envoi DPI (stub)."
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_440px] gap-6 mt-8">
        <Card>
          <div className="px-5 py-4 rule flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <FileText className="size-4" strokeWidth={1.5} aria-hidden="true" />
              <h2 className="text-[13px] font-medium">Rédaction</h2>
            </div>
            <div className="flex items-center gap-2">
              <Label>Type de CR</Label>
              <select
                aria-label="Type de compte-rendu"
                className="input py-1.5 pr-8"
                value={reportType}
                onChange={(e) => setReportType(e.target.value as Template)}
              >
                {Object.keys(TEMPLATES).map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="px-5 py-5 space-y-5">
            <div className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-line/10 px-4 py-3">
              <span className="kicker">Ingestion</span>
              <AudioUpload onTranscript={(t) => setRawText((prev) => (prev ? prev + "\n" : "") + t)} />
              <div className="w-px h-5 bg-line" />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setRawText(TEMPLATES[reportType])}
                aria-label={`Charger le template ${reportType}`}
              >
                Charger le template
              </Button>
              <label className="btn btn-ghost text-[12px] cursor-pointer">
                Importer fichier texte
                <input
                  type="file"
                  accept=".txt,.md"
                  className="hidden"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (!f) return;
                    const text = await f.text();
                    setRawText(text);
                  }}
                />
              </label>
            </div>

            <Field label="Notes cliniques">
              <Textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                placeholder="Dictez, importez un audio, ou saisissez les notes brutes…"
                rows={12}
              />
            </Field>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Field label="Patient (ID)">
                <Input value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="P-001" autoComplete="off" spellCheck={false} />
              </Field>
              <Field label="Clé médecin (HMAC e-signature)">
                <Input value={physicianKey} onChange={(e) => setPhysicianKey(e.target.value)} autoComplete="off" spellCheck={false} />
              </Field>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button variant="primary" onClick={submit} disabled={!rawText || loading}>
                {loading ? <Loader2 className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}
                {loading ? "Génération…" : "Générer le CR structuré"}
              </Button>
              {result && (
                <>
                  <Button variant="ghost" onClick={download} aria-label="Télécharger le CR"><Download className="size-3.5" /> Télécharger</Button>
                  <Button variant="accent" onClick={() => setSigned(true)} aria-label="Signer électroniquement">
                    <ShieldCheck className="size-3.5" /> {signed ? "Signé" : "Signer"}
                  </Button>
                  <Button variant="ghost" onClick={archiveToDPI} aria-label="Envoyer au DPI">
                    <Send className="size-3.5" /> Envoyer au DPI
                  </Button>
                </>
              )}
            </div>
            {archiveInfo && <div className="text-[12px] text-muted">{archiveInfo}</div>}

            {error && (
              <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-[13px] text-danger">
                <strong className="font-medium">{error}.</strong> Recommencez la génération ou enregistrez vos notes avant de rafraîchir.
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4" aria-live="polite" {...(loading ? { "aria-busy": "true" as const } : {})}>
          <Card>
            <div className="px-5 py-3 rule flex items-center justify-between">
              <h2 className="kicker">Aperçu CR</h2>
              {result && (
                <div className="flex items-center gap-2">
                  {signed && <Badge tone="accent" dot>signé</Badge>}
                  <Badge dot>{result.report_type}</Badge>
                </div>
              )}
            </div>
            <div className="px-5 py-4">
              {!result && !loading && (
                <EmptyState title="Pas de CR généré" hint="Collez vos notes ou importez un audio, puis lancez la génération." />
              )}
              {loading && <Skeleton />}
              {result && (
                <article className="prose prose-sm max-w-none">
                  <div className="space-y-4">
                    {result.sections.map((s, i) => (
                      <section key={i}>
                        <h3 className="font-mono text-[11px] uppercase tracking-wider text-subtle mb-1">
                          {s.title}
                        </h3>
                        <p className="text-[13px] leading-relaxed text-pretty whitespace-pre-wrap">
                          {s.content}
                        </p>
                      </section>
                    ))}
                  </div>
                  <div className="mt-5 pt-3 rule">
                    <div className="font-mono text-[10px] text-subtle">
                      e-sign {result.signature.slice(0, 16)}…
                    </div>
                  </div>
                </article>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="py-10 text-center">
      <div className="inline-flex size-10 rounded-lg border border-line items-center justify-center mb-3">
        <FileText className="size-4 text-subtle" strokeWidth={1.5} />
      </div>
      <p className="text-[13px] font-medium text-balance">{title}</p>
      <p className="text-[12px] text-muted mt-1 text-pretty">{hint}</p>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-2">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-12 rounded-md bg-line/30" />
      ))}
    </div>
  );
}

"use client";
import { useState } from "react";
import { CircleHelp, Sparkles, Loader2, BookOpen } from "lucide-react";
import PageHeader from "@/components/shell/PageHeader";
import { Card } from "@/components/ui/Card";
import { Field, Textarea } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { api } from "@/lib/api";

type QAResponse = {
  answer: string;
  provider_used: string;
  model_used: string;
  rule: string;
  audit_id: number;
  citations?: Array<Record<string, any>>;
};

const EXAMPLES = [
  "What are common symptoms of diabetes?",
  "Quels sont les signes d'alarme d'un AVC ?",
  "How is hypertension managed in adults?",
  "Quand faut-il orienter vers les urgences pour une douleur thoracique ?",
];

export default function QAPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<QAResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async (q?: string) => {
    const text = (q ?? question).trim();
    if (text.length < 3) return;
    if (q) setQuestion(text);
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await api.post<QAResponse>("/api/qa/ask", { question: text });
      setResult(r);
    } catch (e: any) {
      setError(e?.message ?? "Échec de la requête");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        kicker="QA · Questions-réponses médicales"
        title={<>Réponses ancrées sur le <span className="display-italic">corpus indexé</span>.</>}
        description="Un seul jeu de données est utilisé : medical_qa.json. Routage toujours local pour un comportement déterministe. Les réponses citent les extraits utilisés."
      />

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_440px] gap-6 mt-8">
        <Card>
          <div className="px-5 py-4 rule flex items-center gap-2">
            <CircleHelp className="size-4" strokeWidth={1.5} aria-hidden="true" />
            <h2 className="text-[13px] font-medium">Poser une question</h2>
          </div>
          <div className="px-5 py-5 space-y-5">
            <Field label="Question médicale" hint="minimum 3 caractères">
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ex : Quels sont les effets secondaires courants de la metformine ?"
                rows={4}
                spellCheck
                autoComplete="off"
              />
            </Field>

            <div>
              <div className="kicker mb-2">Exemples</div>
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => ask(q)}
                    disabled={loading}
                    className="pill hover:border-ink/40 hover:text-ink transition-colors text-left max-w-full"
                  >
                    <span className="truncate">{q}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="pt-1 flex items-center gap-2">
              <Button variant="primary" onClick={() => ask()} disabled={loading || question.trim().length < 3}>
                {loading ? <Loader2 className="size-3.5 animate-spin" aria-hidden="true" /> : <Sparkles className="size-3.5" aria-hidden="true" />}
                {loading ? "Recherche…" : "Poser la question"}
              </Button>
            </div>

            {error && (
              <div role="alert" className="rounded-md border border-danger/30 bg-danger/5 px-4 py-3 text-[13px] text-danger">
                <strong className="font-medium">{error}.</strong> Vérifiez que le corpus QA est ingéré et que l'IA locale est disponible.
              </div>
            )}
          </div>
        </Card>

        <div className="space-y-4" aria-live="polite" {...(loading ? { "aria-busy": "true" as const } : {})}>
          <Card>
            <div className="px-5 py-3 rule flex items-center justify-between">
              <h2 className="kicker">Réponse</h2>
              {result && (
                <div className="flex items-center gap-2">
                  <Badge tone="accent" dot>{result.provider_used}</Badge>
                  <span className="font-mono text-[10px] text-subtle">{result.rule}</span>
                </div>
              )}
            </div>
            <div className="px-5 py-4">
              {!result && !loading && (
                <EmptyState />
              )}
              {loading && <AnswerSkeleton />}
              {result && (
                <div className="space-y-4">
                  <p className="text-[13px] leading-relaxed text-pretty whitespace-pre-wrap">
                    {result.answer}
                  </p>
                  <div className="pt-2 rule border-b-0 border-t flex items-center gap-3 text-[11px] text-subtle">
                    <span className="font-mono" translate="no">{result.model_used}</span>
                    <span>·</span>
                    <span>audit <span className="font-mono">#{result.audit_id}</span></span>
                  </div>
                </div>
              )}
            </div>
          </Card>

          {result && result.citations && result.citations.length > 0 && (
            <Card>
              <div className="px-5 py-3 rule flex items-center gap-2">
                <BookOpen className="size-4" strokeWidth={1.5} aria-hidden="true" />
                <h2 className="kicker">Sources · medical_qa.json</h2>
              </div>
              <div className="px-5 py-4">
                <ul className="space-y-3">
                  {result.citations.slice(0, 5).map((c, i) => (
                    <li key={i} className="text-[12px] border-b border-line last:border-0 pb-2 last:pb-0">
                      <div className="flex items-baseline gap-2">
                        <span className="font-mono text-subtle">[{String(c.id ?? `SRC${i + 1}`)}]</span>
                        {c.section && <span className="font-medium truncate">{String(c.section)}</span>}
                      </div>
                      {c.source && <div className="text-[11px] text-muted mt-0.5">{String(c.source)}</div>}
                      {c.chunk_id && <div className="text-[10px] font-mono text-subtle mt-0.5" translate="no">{String(c.chunk_id)}</div>}
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

function EmptyState() {
  return (
    <div className="py-10 text-center">
      <div className="inline-flex size-10 rounded-lg border border-line items-center justify-center mb-3">
        <CircleHelp className="size-4 text-subtle" strokeWidth={1.5} aria-hidden="true" />
      </div>
      <p className="text-[13px] font-medium text-balance">Aucune question posée</p>
      <p className="text-[12px] text-muted mt-1 text-pretty">
        Choisissez un exemple ou saisissez votre propre question.
      </p>
    </div>
  );
}

function AnswerSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 rounded bg-line/30 w-11/12" />
      <div className="h-3 rounded bg-line/30 w-10/12" />
      <div className="h-3 rounded bg-line/30 w-8/12" />
    </div>
  );
}

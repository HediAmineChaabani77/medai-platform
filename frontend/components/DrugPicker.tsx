"use client";
import { useEffect, useRef, useState } from "react";
import { Search, Plus, X, Loader2 } from "lucide-react";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";

export type Medication = { name: string; dose?: string; frequency?: string; duration?: string; route?: string; atc?: string };

type DrugHit = { cis: string; name: string; form?: string; routes: string[]; substances: string[] };

export default function DrugPicker({
  value, onChange, label = "Médicament",
}: { value: Medication; onChange: (m: Medication) => void; label?: string }) {
  const [query, setQuery] = useState(value.name);
  const [hits, setHits] = useState<DrugHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    if (!query || query.length < 2) { setHits([]); return; }
    timer.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const r = await api.get<{ results: DrugHit[] }>(`/api/uc3/drug-search?q=${encodeURIComponent(query)}`);
        setHits(r.results);
      } catch { setHits([]); } finally { setLoading(false); }
    }, 180);
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [query]);

  const pick = (h: DrugHit) => {
    onChange({ ...value, name: h.name, route: h.routes[0], atc: value.atc });
    setQuery(h.name);
    setOpen(false);
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-[2fr_1fr_1fr_1fr_1fr] gap-2">
      <div className="relative">
        <Label>{label}</Label>
        <div className="relative">
          <Search className="size-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
          <Input
            value={query}
            onChange={(e) => { setQuery(e.target.value); onChange({ ...value, name: e.target.value }); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 120)}
            placeholder="aspirin, warfarin, amoxicilline..."
            className="pl-9"
          />
          {loading && <Loader2 className="size-3.5 animate-spin absolute right-3 top-1/2 -translate-y-1/2 text-subtle" />}
        </div>
        {open && hits.length > 0 && (
          <div className="absolute z-20 mt-1 w-full surface max-h-80 overflow-auto animate-in">
            <ul className="py-1">
              {hits.map((h) => (
                <li key={h.cis}>
                  <button
                    type="button"
                    onMouseDown={() => pick(h)}
                    className="w-full text-left px-3 py-2 hover:bg-line/40 flex items-start gap-3"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium truncate">{h.name}</div>
                      <div className="text-[11px] text-muted truncate">
                        {h.substances.join(", ") || h.form}
                      </div>
                    </div>
                    <span className="font-mono text-[10px] text-subtle shrink-0">CIS {h.cis}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      <div>
        <Label>Dose</Label>
        <Input value={value.dose ?? ""} onChange={(e) => onChange({ ...value, dose: e.target.value })} placeholder="100 mg" />
      </div>
      <div>
        <Label>Fréquence</Label>
        <Input value={value.frequency ?? ""} onChange={(e) => onChange({ ...value, frequency: e.target.value })} placeholder="1×/j" />
      </div>
      <div>
        <Label>Durée</Label>
        <Input value={value.duration ?? ""} onChange={(e) => onChange({ ...value, duration: e.target.value })} placeholder="7 jours" />
      </div>
      <div>
        <Label>Voie</Label>
        <Input value={value.route ?? ""} onChange={(e) => onChange({ ...value, route: e.target.value })} placeholder="PO" />
      </div>
    </div>
  );
}

export function MedList({
  meds, onChange,
}: { meds: Medication[]; onChange: (m: Medication[]) => void }) {
  return (
    <div className="space-y-3">
      {meds.map((m, i) => (
        <div key={i} className="relative rounded-md border border-line p-3">
          <DrugPicker
            value={m}
            onChange={(nm) => onChange(meds.map((x, j) => (j === i ? nm : x)))}
            label={`Médicament ${i + 1}`}
          />
          <button
            type="button"
            aria-label={`Retirer le médicament ${i + 1}`}
            onClick={() => onChange(meds.filter((_, j) => j !== i))}
            className="absolute top-2 right-2 size-6 inline-flex items-center justify-center rounded hover:bg-line/40"
          >
            <X className="size-3.5 text-subtle" />
          </button>
        </div>
      ))}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onChange([...meds, { name: "" }])}
      >
        <Plus className="size-3.5" /> Ajouter un médicament
      </Button>
    </div>
  );
}

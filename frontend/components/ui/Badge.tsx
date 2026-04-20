import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type Tone = "neutral" | "accent" | "danger" | "warn" | "good";

const toneStyle: Record<Tone, string> = {
  neutral: "text-ink",
  accent: "text-accent border-accent/40 bg-accent/10",
  danger: "text-danger border-danger/40 bg-danger/10",
  warn: "text-warn border-warn/40 bg-warn/10",
  good: "text-good border-good/40 bg-good/10",
};

export function Badge({
  tone = "neutral",
  dot = false,
  className,
  children,
  ...p
}: HTMLAttributes<HTMLSpanElement> & { tone?: Tone; dot?: boolean }) {
  return (
    <span
      className={cn("pill", dot && "pill-dot", toneStyle[tone], className)}
      {...p}
    >
      {children}
    </span>
  );
}

export function SeverityBadge({ severity }: { severity: "minor" | "moderate" | "major" | null | undefined }) {
  if (!severity) return <Badge tone="good" dot>aucune alerte</Badge>;
  if (severity === "minor") return <Badge tone="good" dot>Mineur</Badge>;
  if (severity === "moderate") return <Badge tone="warn" dot>Modéré</Badge>;
  return <Badge tone="danger" dot>Majeur</Badge>;
}

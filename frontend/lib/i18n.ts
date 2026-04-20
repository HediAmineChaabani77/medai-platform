const fr = {
  "app.title": "MedAI Assistant",
  "nav.diagnostic": "UC1 — Aide au diagnostic",
  "nav.report": "UC2 — Compte-rendu",
  "nav.prescription": "UC3 — Ordonnance",
  "nav.admin": "UC4 — Administration",
  "mode.local": "Mode: Local",
  "mode.cloud": "Mode: Cloud",
  "mode.offline": "Mode hors ligne — IA locale activée",
  "diagnostic.symptoms": "Symptômes",
  "diagnostic.context": "Contexte patient (JSON)",
  "diagnostic.submit": "Analyser",
  "diagnostic.redflags": "Signaux d'alerte",
  "report.type": "Type de compte-rendu",
  "report.notes": "Notes brutes",
  "report.submit": "Générer",
  "rx.current": "Traitements en cours",
  "rx.new": "Nouveaux médicaments",
  "rx.submit": "Vérifier",
  "rx.blocked": "PRESCRIPTION BLOQUÉE",
  "admin.metrics": "Métriques",
  "admin.policies": "Règles de routage",
  "admin.audit": "Journal d'audit",
};
const en: Record<string, string> = {
  "mode.offline": "Offline — local AI active",
  "rx.blocked": "PRESCRIPTION BLOCKED",
};
export type Locale = "fr" | "en";
export function t(key: keyof typeof fr, locale: Locale = "fr"): string {
  return (locale === "en" && en[key]) || fr[key] || String(key);
}

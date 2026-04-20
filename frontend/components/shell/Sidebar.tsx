"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Stethoscope, FileText, Pill, Gauge, Home, CircleHelp
} from "lucide-react";
import { cn } from "@/lib/cn";

const nav = [
  { href: "/", label: "Aperçu", icon: Home, group: "principal" },
  { href: "/diagnostic", label: "Aide au diagnostic", icon: Stethoscope, group: "principal", uc: "UC1" },
  { href: "/report", label: "Compte-rendu", icon: FileText, group: "principal", uc: "UC2" },
  { href: "/prescription", label: "Ordonnance", icon: Pill, group: "principal", uc: "UC3" },
  { href: "/admin", label: "Administration", icon: Gauge, group: "système", uc: "UC4" },
  { href: "/qa", label: "QA médicale", icon: CircleHelp, group: "système" },
];

export default function Sidebar() {
  const p = usePathname();

  return (
    <aside aria-label="Navigation principale" className="hidden lg:flex flex-col w-[248px] shrink-0 rule-l border-l-0 border-r border-line bg-paper">
      <div className="px-5 pt-6 pb-4">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="display-italic text-[22px] leading-none">MedAI</span>
          <span className="kicker">Assistant</span>
        </Link>
      </div>

      <div className="px-3 py-2 space-y-6">
        {["principal", "système"].map((g) => (
          <div key={g}>
            <div className="kicker px-3 mb-2">{g}</div>
            <ul className="space-y-1">
              {nav.filter((n) => n.group === g).map((item) => {
                const active = p === item.href || (item.href !== "/" && p?.startsWith(item.href));
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 rounded-md text-[13px] transition-colors",
                        active
                          ? "bg-line/50 text-ink font-medium"
                          : "text-muted hover:text-ink hover:bg-line/30"
                      )}
                    >
                      <Icon className="size-4 shrink-0" strokeWidth={1.5} aria-hidden="true" />
                      <span className="flex-1 truncate">{item.label}</span>
                      {item.uc && (
                        <span className="font-mono text-[10px] text-subtle">{item.uc}</span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="mt-auto px-5 py-4 rule border-t border-b-0">
        <div className="kicker mb-1">Conformité</div>
        <p className="text-[11px] text-muted leading-relaxed">
          Données patient routées en local pour toutes requêtes critiques (HIPAA/RGPD).
        </p>
      </div>
    </aside>
  );
}

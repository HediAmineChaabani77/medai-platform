"use client";
import clsx from "clsx";

export default function ProviderBadge({ provider }: { provider: string | null }) {
  if (!provider) return null;
  const isLocal = provider === "local";
  return (
    <span
      className={clsx(
        "inline-block px-2 py-1 rounded text-xs font-semibold",
        isLocal ? "bg-emerald-100 text-emerald-800" : "bg-indigo-100 text-indigo-800"
      )}
    >
      {isLocal ? "Mode: Local" : "Mode: Cloud"}
    </span>
  );
}

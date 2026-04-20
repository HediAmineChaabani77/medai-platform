import type { ReactNode } from "react";

export default function PageHeader({
  kicker, title, description, actions,
}: {
  kicker?: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="pt-8 pb-6 rule">
      <div className="flex items-start gap-8 flex-wrap">
        <div className="flex-1 min-w-[280px]">
          {kicker && <div className="kicker mb-3">{kicker}</div>}
          <h1 className="title-xl text-balance">{title}</h1>
          {description && <p className="lede mt-3 text-pretty">{description}</p>}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
    </header>
  );
}

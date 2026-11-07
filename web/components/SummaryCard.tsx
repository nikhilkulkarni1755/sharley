import type { ReactNode } from "react";

/** The clear ending of a pipeline or run: what happened, then what to do next. */
export default function SummaryCard({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="panel stack summary" aria-label="Summary">
      {children}
      {actions && <div className="row">{actions}</div>}
    </section>
  );
}

import type { ReactNode } from "react";

type SectionCardProps = {
  title: string;
  description: string;
  badge?: string;
  action?: ReactNode;
  children?: ReactNode;
  className?: string;
};

export function SectionCard({ title, description, badge, action, children, className = "" }: SectionCardProps) {
  return (
    <section className={`card p-6 ${className}`}>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2.5">
            <h2 style={{ color: "#1F2328", fontSize: "16px", fontWeight: 600, margin: 0 }}>{title}</h2>
            {badge && (
              <span className="badge badge-accent">{badge}</span>
            )}
          </div>
          <p style={{ color: "#656D76", fontSize: "12px", marginTop: "4px" }}>{description}</p>
        </div>
        {action && <div>{action}</div>}
      </div>
      {children}
    </section>
  );
}

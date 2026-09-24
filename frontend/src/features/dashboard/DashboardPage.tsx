import { useEffect, useState } from "react";

import { SectionCard } from "../../components/SectionCard";
import { fetchHealth, type ApiHealth } from "../../services/api";
import { appConfig } from "../../services/config";
import type { StageStatus, WorkflowStage } from "../../types/workflow";

type StageDescriptor = {
  key: WorkflowStage;
  label: string;
  description: string;
  status: StageStatus;
};

const stages: StageDescriptor[] = [
  {
    key: "ingestion",
    label: "Ingestion",
    description: "Register daily reports, contractor spreadsheets, and L5/L6 schedules.",
    status: "planned",
  },
  {
    key: "extraction",
    label: "Extraction",
    description: "Convert source files into structured activity observations.",
    status: "planned",
  },
  {
    key: "normalization",
    label: "Normalization",
    description: "Standardize descriptions, units, and status language before matching.",
    status: "planned",
  },
  {
    key: "matching",
    label: "Schedule Linking",
    description: "Map normalized evidence to L5/L6 schedule activities.",
    status: "planned",
  },
  {
    key: "reconciliation",
    label: "Reconciliation",
    description: "Resolve conflicts, assign confidence, and explain proposed actual status.",
    status: "planned",
  },
  {
    key: "planner-review",
    label: "Planner Review",
    description: "Escalate uncertain or conflicting results to a human planner.",
    status: "planned",
  },
];

function statusStyles(status: StageStatus): string {
  if (status === "in-progress") {
    return "bg-ember/15 text-ember";
  }

  if (status === "planned") {
    return "bg-moss/15 text-moss";
  }

  return "bg-slate-200 text-slate";
}

export function DashboardPage() {
  const [health, setHealth] = useState<ApiHealth | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    fetchHealth()
      .then((result) => {
        if (mounted) {
          setHealth(result);
        }
      })
      .catch(() => {
        if (mounted) {
          setHealthError("Backend not reachable yet.");
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <main className="min-h-screen px-6 py-10 text-ink sm:px-10 lg:px-16">
      <div className="mx-auto flex max-w-7xl flex-col gap-8">
        <header className="overflow-hidden rounded-[2rem] border border-white/70 bg-ink px-8 py-10 text-white shadow-panel">
          <p className="text-sm uppercase tracking-[0.25em] text-white/70">Project Controls & Evidence Reconciliation</p>
          <h1 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
            {appConfig.appName}
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-white/80">
            Field reports, contractor spreadsheets, and L5/L6 schedules converge here for explainable
            progress reconciliation and planner review.
          </p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <SectionCard
            title="MVP Workflow"
            description="The product backbone is fixed around extracting progress evidence, linking it to schedule activities, reconciling conflicts, and escalating uncertainty."
          >
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {stages.map((stage) => (
                <article key={stage.key} className="rounded-2xl border border-slate-200 bg-sand p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-base font-semibold text-ink">{stage.label}</h3>
                    <span className={`rounded-full px-3 py-1 text-xs font-medium ${statusStyles(stage.status)}`}>
                      {stage.status}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate">{stage.description}</p>
                </article>
              ))}
            </div>
          </SectionCard>

          <SectionCard
            title="System Status"
            description="This shell does not simulate workflow execution. It only reports actual application wiring available in this phase."
          >
            <div className="space-y-4">
              <div className="rounded-2xl bg-sand p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate">API Base URL</p>
                <p className="mt-2 break-all text-sm font-medium">{appConfig.apiBaseUrl}</p>
              </div>
              <div className="rounded-2xl bg-sand p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate">Health Check</p>
                {health ? (
                  <div className="mt-2 text-sm leading-6">
                    <p>Status: {health.status}</p>
                    <p>Service: {health.app_name}</p>
                    <p>Environment: {health.environment}</p>
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-slate">{healthError ?? "Checking backend connectivity..."}</p>
                )}
              </div>
            </div>
          </SectionCard>
        </div>

        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          <SectionCard
            title="Evidence First"
            description="Every accepted schedule-linked result must remain inspectable back to source evidence."
          />
          <SectionCard
            title="Confidence Controlled"
            description="Auto-accept and planner-review thresholds are designed to be configurable in backend settings."
          />
          <SectionCard
            title="Provider Independent"
            description="AI dependencies are planned behind abstraction layers so business logic stays vendor-neutral."
          />
          <SectionCard
            title="Planner Review"
            description="Uncertain and conflicting cases are intentional workflow outputs, not hidden system failures."
          />
        </div>
      </div>
    </main>
  );
}

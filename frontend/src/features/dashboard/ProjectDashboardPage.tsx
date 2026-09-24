import { useEffect, useMemo, useState } from "react";
import { SectionCard } from "../../components/SectionCard";
import {
  fetchDashboard,
  fetchPlannerReviews,
  resetDemo,
  pasteDprReport,
  uploadEvidenceFile,
  continueToMatchingAndReconciliation,
  fetchExecutionContext,
  fetchSchedulePreview,
  downloadScheduleExport,
  uploadScheduleFile,
  fetchProjectMemorySummary,
  fetchActivityExecutionHistory,
  fetchProjectExecutionRecords,
  fetchSimilarExecutions,
  syncProjectMemory,
  type DashboardData,
  type PlannerReviewContext,
  type ExtractedEventItem,
  type ExecutionContextResponse,
  type ScheduleChangePreviewResponse,
  type ScheduleChangeItem,
  type ProjectPerformanceSummary,
  type ActivityExecutionHistoryResponse,
  type ExecutionRecordResponse,
  type HistoricalReferenceItem,
  type SimilarExecutionSearchResponse,
} from "../../services/api";
import { PlannerReviewPage } from "../planner-review/PlannerReviewPage";

export type View = "schedule" | "memory" | "reconciliation" | "overview" | "activities" | "conflicts" | "evidence" | "audit" | "reviews";

const views: Array<[View, string]> = [
  ["schedule", "Schedule Bridge"],
  ["memory", "Execution Memory"],
  ["reconciliation", "Reconciliation Center"],
  ["overview", "Project Overview"],
  ["activities", "Activity Explorer"],
  ["conflicts", "Conflict Center"],
  ["evidence", "Evidence Viewer"],
  ["audit", "Audit Trail"],
  ["reviews", "Planner Review"],
];


const pretty = (v: unknown) => String(v ?? "—").replaceAll("_", " ");

const fmtDate = (v: unknown) => {
  if (!v) return "—";
  const d = new Date(String(v));
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
};

const fmtDateTime = (v: unknown) => {
  if (!v) return "—";
  const d = new Date(String(v));
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) + ", " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
};

function fmtStatus(v: unknown): string {
  const str = String(v ?? "not_started").toLowerCase().replace(/[-_]/g, " ");
  if (str.includes("complete")) return "Completed";
  if (str.includes("progress")) return "In Progress";
  if (str.includes("not started")) return "Not Started";
  if (str.includes("delayed")) return "Delayed";
  if (str.includes("review")) return "Needs Review";
  return pretty(v);
}

function badgeClass(value: string) {
  const v = value.toLowerCase();
  if (v.includes("conflict") || v.includes("review") || v.includes("reject") || v.includes("stale") || v.includes("delayed"))
    return "badge badge-attention";
  if (v.includes("complete") || v.includes("accept") || v.includes("linked") || v.includes("matched") || v.includes("ok") || v.includes("supporting"))
    return "badge badge-success";
  if (v.includes("progress") || v.includes("active") || v.includes("ongoing"))
    return "badge badge-accent";
  return "badge badge-default";
}

function Badge({ value, className = "" }: { value: unknown; className?: string }) {
  const label = fmtStatus(value);
  return <span className={`${badgeClass(label)} ${className}`}>{label}</span>;
}

function Spinner() {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "#fff", border: "1px solid #D0D7DE", borderRadius: 12, padding: "64px 32px", textAlign: "center" }}>
      <div style={{ width: 32, height: 32, borderRadius: "50%", border: "2px solid #0D9488", borderTopColor: "transparent", animation: "spin 0.8s linear infinite" }} />
      <p style={{ marginTop: 16, fontWeight: 600, color: "#1F2328", fontSize: 14 }}>Synchronizing schedule baseline & reconciling evidence…</p>
      <p style={{ marginTop: 4, color: "#656D76", fontSize: 12 }}>CognitiveProgress Project Controls Engine</p>
    </div>
  );
}

function ErrorBox({ msg, onRetry, onReset }: { msg: string; onRetry?: () => void; onReset?: () => void }) {
  const isNotFound = msg.toLowerCase().includes("not found") || msg.includes("404");
  return (
    <div style={{ background: "#FFEBE9", border: "1px solid #FF9EA0", borderRadius: 10, padding: "20px 24px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
      <div>
        <p style={{ color: "#CF222E", fontWeight: 700, fontSize: 14, margin: "0 0 4px" }}>System Notice</p>
        <p style={{ color: "#CF222E", fontSize: 13, margin: 0 }}>{msg}</p>
        {isNotFound && (
          <p style={{ color: "#656D76", fontSize: 12, margin: "6px 0 0" }}>
            The demonstration project baseline is not yet seeded in the current database. Click below to initialize the benchmark project.
          </p>
        )}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {isNotFound && onReset && (
          <button onClick={onReset} style={{ background: "#0D9488", color: "#FFFFFF", border: "none", borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            Initialize Baseline
          </button>
        )}
        {onRetry && (
          <button onClick={onRetry} style={{ background: "#CF222E", color: "#FFFFFF", border: "none", borderRadius: 6, padding: "8px 16px", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

function EmptyState({ title = "No records available", description = "No operational records found for this project context." }: { title?: string; description?: string }) {
  return (
    <div style={{ background: "#fff", border: "1px dashed #D0D7DE", borderRadius: 12, padding: "48px 32px", textAlign: "center" }}>
      <p style={{ fontWeight: 600, color: "#1F2328", fontSize: 15, margin: "0 0 6px" }}>{title}</p>
      <p style={{ color: "#656D76", fontSize: 13, margin: 0 }}>{description}</p>
    </div>
  );
}

function State({ loading, error, empty, onRetry, onReset, children }: { loading: boolean; error: string | null; empty: boolean; onRetry?: () => void; onReset?: () => void; children: React.ReactNode }) {
  if (loading) return <Spinner />;
  if (error) return <ErrorBox msg={error} onRetry={onRetry} onReset={onReset} />;
  if (empty) return <EmptyState />;
  return <>{children}</>;
}

function getSourceDocInfo(name: string, type: string) {
  const lower = (name || "").toLowerCase();
  if (lower.includes("supervisor")) return { title: "Daily Site Supervision Report", subtitle: "Unit 3 Piping Workfront", typeName: "Daily Site Report" };
  if (lower.includes("contractor")) return { title: "Subcontractor Progress Return", subtitle: "Mechanical & Piping Package", typeName: "Subcontractor Return" };
  if (lower.includes("site_diary")) return { title: "Resident Engineer Site Diary", subtitle: "Unit 3 Field Observations", typeName: "Site Diary Log" };
  if (lower.includes("high_confidence")) return { title: "Substation Quality & Inspection Report", subtitle: "Electrical Transformer Foundation", typeName: "Quality Inspection Record" };
  if (lower.includes("ambiguous")) return { title: "Electrical Installation Daily Log", subtitle: "Unit 2 Cable Tray Workfront", typeName: "Workfront Daily Log" };
  if (lower.includes("unmatched")) return { title: "Site Infrastructure & Logistics Log", subtitle: "Laydown Area Workfront", typeName: "Logistics Log" };
  if (lower.includes("dependency_conflict")) return { title: "Field Daily Progress Report", subtitle: "Unit 3 Piping & Hydrotesting", typeName: "Daily Site Report" };
  if (lower.includes("delay_cause")) return { title: "Resident Engineer Daily Log", subtitle: "Unit 3 NDT & Hydrotest Front", typeName: "Site Diary Log" };
  return { title: name, subtitle: pretty(type), typeName: pretty(type) };
}

const DEFAULT_PROJECT_ID = "26122000-0000-0000-0000-000000000001";
const DEFAULT_PROJECT_DISPLAY_NAME = "PRJ-2026-SYN01 · Oil & Gas Infrastructure Project (Synthetic Demo)";

export interface ProjectDashboardPageProps {
  initialView?: View;
  onOpenMethodology?: () => void;
}

export function ProjectDashboardPage({ initialView = "reconciliation", onOpenMethodology }: ProjectDashboardPageProps = {}) {
  const [projectId, setProjectId] = useState(DEFAULT_PROJECT_ID);
  const [projectName, setProjectName] = useState(DEFAULT_PROJECT_DISPLAY_NAME);
  const [data, setData] = useState<DashboardData | null>(null);
  const [reviews, setReviews] = useState<PlannerReviewContext[]>([]);
  const [view, setView] = useState<View>(initialView);
  const [selectedReviewId, setSelectedReviewId] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showIdSelector, setShowIdSelector] = useState(false);
  const [showMethodology, setShowMethodology] = useState(false);
  const [selectedActivity, setSelectedActivity] = useState<any | null>(null);

  async function load(targetId?: string) {
    const id = (targetId ?? projectId).trim();
    if (!id) { setError("Please specify a valid Project Identifier."); return; }
    setLoading(true); setError(null);
    try {
      const [dashboard, queue] = await Promise.all([fetchDashboard(id), fetchPlannerReviews(id)]);
      setData(dashboard); setReviews(queue);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load project schedule data.");
    } finally { setLoading(false); }
  }

  async function resetBaseline() {
    setLoading(true); setError(null); setNotice(null);
    try {
      const demo = await resetDemo();
      setProjectId(demo.project_id);
      setProjectName(demo.project_name || DEFAULT_PROJECT_DISPLAY_NAME);
      const [dashboard, queue] = await Promise.all([fetchDashboard(demo.project_id), fetchPlannerReviews(demo.project_id)]);
      setData(dashboard); setReviews(queue); setView("reconciliation");
      setNotice("Synthetic demonstration baseline re-initialized: 10 WBS L5/L6 activities across Civil, Piping, Electrical, and Instrumentation disciplines synchronized with 8 evidence sources.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to reset benchmark project baseline.");
    } finally { setLoading(false); }
  }

  useEffect(() => { load(DEFAULT_PROJECT_ID); }, []);

  const activityName = useMemo(() => new Map((data?.activities ?? []).map((a) => [a.activity_id, a.external_activity_id])), [data]);
  const activityMap = useMemo(() => new Map((data?.activities ?? []).map((a) => [a.activity_id, a])), [data]);

  function navigateToReview(reviewId?: string) {
    setSelectedReviewId(reviewId);
    setView("reviews");
  }

  return (
    <div style={{ minHeight: "100vh", background: "#F6F8FA", color: "#1F2328" }}>

      {/* ─── ENTERPRISE HEADER ───────────────────────────────── */}
      <header style={{ background: "#0D1117", borderBottom: "1px solid #30363D", color: "#F0F6FC" }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", padding: "16px 24px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
            
            {/* Branding & Subtitle */}
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div style={{ width: 38, height: 38, borderRadius: 9, background: "linear-gradient(135deg, #0D9488 0%, #14B8A6 100%)", display: "flex", alignItems: "center", justifyContent: "center", color: "#FFFFFF", fontWeight: 900, fontSize: 18, boxShadow: "0 2px 8px rgba(13,148,136,0.3)" }}>
                CP
              </div>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#F0F6FC", letterSpacing: "-0.02em" }}>
                    CognitiveProgress
                  </h1>
                  <span style={{ background: "rgba(13,148,136,0.15)", border: "1px solid rgba(13,148,136,0.35)", borderRadius: 12, padding: "2px 8px", fontSize: 10, fontWeight: 700, color: "#2DD4BF", letterSpacing: "0.04em" }}>
                    Enterprise Controls
                  </span>
                </div>
                <p style={{ margin: "2px 0 0", fontSize: 12, color: "#8B949E" }}>
                  Project Controls & Evidence Reconciliation Platform
                </p>
              </div>
            </div>

            {/* Project Context & Global Actions */}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
              
              {/* Project Badge / Switcher */}
              <div style={{ display: "flex", alignItems: "center", background: "#161B22", border: "1px solid #30363D", borderRadius: 8, padding: "4px 10px", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#2DD4BF", display: "inline-block" }} />
                <span style={{ fontSize: 12, fontWeight: 600, color: "#F0F6FC" }}>
                  {projectName}
                </span>
                <button
                  onClick={() => setShowIdSelector(!showIdSelector)}
                  style={{ background: "none", border: "none", color: "#8B949E", cursor: "pointer", fontSize: 11, padding: "2px 4px" }}
                  title="Switch or view internal Project UUID"
                >
                  ⚙
                </button>
              </div>

              {/* Sync Schedule Button */}
              <button
                onClick={() => load()}
                style={{ background: "#21262D", border: "1px solid #30363D", borderRadius: 8, padding: "7px 14px", color: "#F0F6FC", fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, transition: "all 0.15s" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#30363D")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "#21262D")}
              >
                <span>↻</span> Refresh Data
              </button>

              {/* Reset to Benchmark Button */}
              <button
                onClick={resetBaseline}
                style={{ background: "#0D9488", border: "1px solid #0F766E", borderRadius: 8, padding: "7px 14px", color: "#FFFFFF", fontSize: 12, fontWeight: 600, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, transition: "all 0.15s" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "#0F766E")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "#0D9488")}
                title="Re-synchronize benchmark activities, multi-source evidence, and planner queue"
              >
                Reset Baseline
              </button>

              {/* Methodology Guide Modal Button */}
              <button
                onClick={() => {
                  if (onOpenMethodology) {
                    onOpenMethodology();
                  } else {
                    setShowMethodology(true);
                  }
                }}
                style={{ background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: 8, padding: "7px 12px", color: "#E6EDF3", fontSize: 12, fontWeight: 500, cursor: "pointer" }}
                onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.12)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.06)")}
              >
                Methodology
              </button>

              {/* User Persona Chip */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 8, borderLeft: "1px solid #30363D" }}>
                <div style={{ width: 28, height: 28, borderRadius: "50%", background: "#238636", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700 }}>
                  LP
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#F0F6FC" }}>Lead Planner</span>
                  <span style={{ fontSize: 10, color: "#8B949E" }}>Controls & Actuation</span>
                </div>
              </div>

            </div>
          </div>

          {/* Project ID drawer (technical details) */}
          {showIdSelector && (
            <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid #21262D", display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 11, color: "#8B949E" }}>Internal Project UUID:</span>
              <input
                style={{ background: "#161B22", border: "1px solid #30363D", borderRadius: 6, padding: "5px 10px", color: "#F0F6FC", fontSize: 11, fontFamily: "ui-monospace, monospace", minWidth: 320 }}
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                placeholder="UUID"
              />
              <button
                onClick={() => load()}
                style={{ background: "#21262D", border: "1px solid #30363D", borderRadius: 6, padding: "5px 12px", color: "#F0F6FC", fontSize: 11, cursor: "pointer" }}
              >
                Load UUID
              </button>
            </div>
          )}
        </div>
      </header>

      {/* ─── MAIN WORKSPACE ─────────────────────────────────── */}
      <main style={{ maxWidth: 1440, margin: "0 auto", padding: "20px 24px" }}>

        {/* Operational Notice Banner */}
        {notice && (
          <div style={{ background: "#DAFBE1", border: "1px solid #82E9A6", borderRadius: 8, padding: "10px 16px", marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ color: "#1A7F37", fontSize: 12, fontWeight: 500 }}>{notice}</span>
            <button onClick={() => setNotice(null)} style={{ background: "none", border: "none", color: "#1A7F37", fontWeight: 700, cursor: "pointer", fontSize: 12 }}>✕</button>
          </div>
        )}

        {/* Primary Navigation Tabs */}
        <nav style={{ display: "flex", gap: 6, marginBottom: 20, overflowX: "auto", paddingBottom: 4 }}>
          {views.map(([key, label]) => {
            const isActive = view === key;
            return (
              <button
                key={key}
                onClick={() => setView(key)}
                style={{
                  whiteSpace: "nowrap", borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600, cursor: "pointer", border: "1px solid", transition: "all 0.15s ease",
                  background: isActive ? "#1F2328" : "#FFFFFF",
                  color: isActive ? "#FFFFFF" : "#656D76",
                  borderColor: isActive ? "#1F2328" : "#D0D7DE",
                  display: "flex", alignItems: "center", gap: 6,
                  boxShadow: isActive ? "0 1px 3px rgba(31,35,40,0.12)" : "none",
                }}
                onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "#8C959F"; e.currentTarget.style.color = "#1F2328"; }}}
                onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "#D0D7DE"; e.currentTarget.style.color = "#656D76"; }}}
              >
                {label}
                {key === "reviews" && reviews.length > 0 && (
                  <span style={{ background: isActive ? "#F0A30A" : "#FFF8C5", color: isActive ? "#fff" : "#9A6700", borderRadius: 20, padding: "1px 8px", fontSize: 11, fontWeight: 700 }}>
                    {reviews.length}
                  </span>
                )}
                {key === "conflicts" && data?.conflicts && data.conflicts.length > 0 && (
                  <span style={{ background: isActive ? "#CF222E" : "#FFEBE9", color: isActive ? "#fff" : "#CF222E", borderRadius: 20, padding: "1px 8px", fontSize: 11, fontWeight: 700 }}>
                    {data.conflicts.length}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* View States */}
        <State loading={loading} error={error} empty={!data} onRetry={() => load()} onReset={resetBaseline}>
          {data && (
            <>
              {view === "schedule" && <ScheduleBridge projectId={projectId} onNavigateToReview={navigateToReview} />}
              {view === "memory" && <ExecutionMemoryView projectId={projectId} onSelectActivity={(a) => setSelectedActivity(a)} onOpenReview={navigateToReview} />}
              {view === "reconciliation" && <Reconciliation data={data} reviews={reviews} onOpenReview={navigateToReview} onSelectActivity={(a) => setSelectedActivity(a)} />}

              {view === "overview" && <Overview data={data} />}
              {view === "activities" && <Activities data={data} onSelectActivity={(a) => setSelectedActivity(a)} />}
              {view === "conflicts" && <Conflicts data={data} onOpenReview={navigateToReview} />}
              {view === "evidence" && <Evidence data={data} projectId={projectId} onRefresh={() => load(projectId)} onNavigateToReconciliation={() => setView("reconciliation")} />}
              {view === "audit" && <Audit data={data} names={activityName} />}
              {view === "reviews" && <PlannerReviews reviews={reviews} projectId={projectId} initialReviewId={selectedReviewId} onAction={() => load(projectId)} />}
            </>
          )}
        </State>

        {/* Activity Details Drawer / Modal */}
        {selectedActivity && data && (
          <ActivityDetailsModal
            activity={selectedActivity}
            data={data}
            projectId={projectId}
            onClose={() => setSelectedActivity(null)}
            onOpenReview={navigateToReview}
            onSelectActivity={(a) => setSelectedActivity(a)}
          />
        )}

        {/* System Methodology Modal */}
        {showMethodology && (
          <MethodologyModal onClose={() => setShowMethodology(false)} />
        )}
      </main>
    </div>
  );
}

// ─── SCHEDULE BRIDGE & EXPORT ───────────────────────────────────────────────
function ScheduleBridge({ projectId, onNavigateToReview }: { projectId: string; onNavigateToReview: (id?: string) => void }) {
  const [preview, setPreview] = useState<ScheduleChangePreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "verified" | "review" | "unchanged">("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Schedule Import State
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importVersion, setImportVersion] = useState("rev-05");
  const [isImporting, setIsImporting] = useState(false);

  // Export State
  const [exportingFormat, setExportingFormat] = useState<"csv" | "xlsx" | null>(null);

  async function loadPreview() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchSchedulePreview(projectId);
      setPreview(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load schedule change preview.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPreview();
  }, [projectId]);

  async function handleImportSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!importFile) {
      setError("Please choose a CSV or XLSX schedule file to import.");
      return;
    }
    setIsImporting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await uploadScheduleFile(projectId, importFile, importVersion);
      setNotice(`Schedule imported: ${res.records_imported} activities synchronized into baseline.`);
      setImportFile(null);
      await loadPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Schedule import failed.");
    } finally {
      setIsImporting(false);
    }
  }

  async function handleExport(format: "csv" | "xlsx") {
    setExportingFormat(format);
    setError(null);
    try {
      await downloadScheduleExport(projectId, format);
      setNotice(`Verified schedule successfully exported as ${format.toUpperCase()}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to export schedule as ${format.toUpperCase()}.`);
    } finally {
      setExportingFormat(null);
    }
  }

  const filteredChanges = useMemo(() => {
    if (!preview) return [];
    return preview.changes.filter((item) => {
      if (filter === "verified" && item.decision !== "VERIFIED") return false;
      if (filter === "review" && item.decision !== "PLANNER_REVIEW" && item.decision !== "CONFLICT" && item.decision !== "REJECTED") return false;
      if (filter === "unchanged" && item.decision !== "UNCHANGED") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesId = item.external_activity_id.toLowerCase().includes(q);
        const matchesName = item.activity_name.toLowerCase().includes(q);
        const matchesDisc = (item.discipline || "").toLowerCase().includes(q);
        if (!matchesId && !matchesName && !matchesDisc) return false;
      }
      return true;
    });
  }, [preview, filter, searchQuery]);

  const verifiedCount = useMemo(() => preview?.changes.filter((c) => c.decision === "VERIFIED").length ?? 0, [preview]);
  const reviewCount = useMemo(() => preview?.changes.filter((c) => c.decision === "PLANNER_REVIEW" || c.decision === "CONFLICT" || c.decision === "REJECTED").length ?? 0, [preview]);
  const unchangedCount = useMemo(() => preview?.changes.filter((c) => c.decision === "UNCHANGED").length ?? 0, [preview]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Workflow Stepper Banner */}
      <div style={{ background: "#0D1117", border: "1px solid #30363D", borderRadius: 12, padding: "16px 20px", color: "#F0F6FC" }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#2DD4BF", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
          CognitiveProgress · Planning-to-Execution Schedule Bridge
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, fontSize: 12, fontWeight: 600 }}>
          <span style={{ color: "#F0F6FC" }}>Schedule Import (L5/L6)</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#F0F6FC" }}>Field DPR Evidence</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#F0F6FC" }}>L5/L6 Matching</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#F0F6FC" }}>Reconciliation</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#E3B341" }}>Temporal / Dependency Gate</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#2DD4BF" }}>Verified Actuals</span>
          <span style={{ color: "#8B949E" }}>→</span>
          <span style={{ color: "#3FB950" }}>Exportable Schedule</span>
        </div>
      </div>

      {notice && (
        <div style={{ background: "#DAFBE1", border: "1px solid #82E9A6", borderRadius: 8, padding: "10px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ color: "#1A7F37", fontSize: 13, fontWeight: 600 }}>✓ {notice}</span>
          <button onClick={() => setNotice(null)} style={{ background: "none", border: "none", color: "#1A7F37", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>✕</button>
        </div>
      )}

      {error && <ErrorBox msg={error} onRetry={() => loadPreview()} />}

      {/* Schedule Import Card */}
      <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px", boxShadow: "0 1px 3px rgba(31,35,40,0.04)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#1F2328" }}>Import L5/L6 Schedule Baseline</h3>
            <p style={{ margin: "3px 0 0", fontSize: 12, color: "#656D76" }}>
              Import realistic schedule extracts (CSV or XLSX) with Activity ID, Description, WBS, Predecessors, and Baseline Actuals.
            </p>
          </div>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#0969DA", background: "#DDF4FF", border: "1px solid #54AEFF", padding: "3px 10px", borderRadius: 12 }}>
            CSV / XLSX Supported
          </span>
        </div>
        <form onSubmit={handleImportSchedule} style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setImportFile(e.target.files?.[0] || null)}
            style={{ fontSize: 12, border: "1px solid #D0D7DE", borderRadius: 6, padding: "6px 10px", background: "#F6F8FA", color: "#1F2328", cursor: "pointer" }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#656D76", fontWeight: 600 }}>Schedule Version:</span>
            <input
              type="text"
              value={importVersion}
              onChange={(e) => setImportVersion(e.target.value)}
              placeholder="e.g. rev-05"
              style={{ fontSize: 12, border: "1px solid #D0D7DE", borderRadius: 6, padding: "6px 10px", width: 110 }}
            />
          </div>
          <button
            type="submit"
            disabled={isImporting || !importFile}
            style={{
              background: isImporting || !importFile ? "#8C959F" : "#1F2328",
              color: "#FFFFFF", border: "none", borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 700,
              cursor: isImporting || !importFile ? "not-allowed" : "pointer",
            }}
          >
            {isImporting ? "Importing Schedule..." : "Upload & Synchronize Schedule"}
          </button>
        </form>
      </div>

      {/* Summary KPI Cards */}
      {preview && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
          <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#656D76", textTransform: "uppercase" }}>Evaluated</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#1F2328", marginTop: 4 }}>{preview.summary.activities_evaluated}</div>
            <div style={{ fontSize: 11, color: "#8C959F", marginTop: 2 }}>L5/L6 Schedule Baseline</div>
          </div>
          <div style={{ background: "#FFFFFF", border: "1px solid #A7F3D0", borderRadius: 10, padding: "14px 18px", borderTop: "3px solid #059669" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#065F46", textTransform: "uppercase" }}>Verified Updates</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#059669", marginTop: 4 }}>{preview.summary.verified_updates}</div>
            <div style={{ fontSize: 11, color: "#047857", marginTop: 2 }}>Included in Export</div>
          </div>
          <div style={{ background: "#FFFFFF", border: "1px solid #FDE68A", borderRadius: 10, padding: "14px 18px", borderTop: "3px solid #D97706" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#92400E", textTransform: "uppercase" }}>Planner Review</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#D97706", marginTop: 4 }}>{preview.summary.planner_review}</div>
            <div style={{ fontSize: 11, color: "#B45309", marginTop: 2 }}>Excluded Until Approved</div>
          </div>
          <div style={{ background: "#FFFFFF", border: "1px solid #FECACA", borderRadius: 10, padding: "14px 18px", borderTop: "3px solid #DC2626" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#991B1B", textTransform: "uppercase" }}>Conflicts</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#DC2626", marginTop: 4 }}>{preview.summary.conflicts}</div>
            <div style={{ fontSize: 11, color: "#B91C1C", marginTop: 2 }}>Safety Gate Blocked</div>
          </div>
          <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>Rejected</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#64748B", marginTop: 4 }}>{preview.summary.rejected}</div>
            <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 2 }}>Withheld</div>
          </div>
          <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 10, padding: "14px 18px" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>Unchanged</div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#1F2328", marginTop: 4 }}>{preview.summary.unchanged}</div>
            <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 2 }}>Baseline Intact</div>
          </div>
        </div>
      )}

      {/* Verified Schedule Export Action Bar */}
      <div style={{ background: "#0D1117", border: "1px solid #30363D", borderRadius: 12, padding: "20px 24px", color: "#F0F6FC", display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
            <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#F0F6FC" }}>Verified Schedule Export</h3>
            <span style={{ background: "rgba(13,148,136,0.2)", border: "1px solid #0D9488", color: "#2DD4BF", fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 12 }}>
              Safety Gate Authoritative
            </span>
          </div>
          <p style={{ margin: 0, fontSize: 12, color: "#8B949E", maxWidth: 660 }}>
            Only verified / approved actual dates and progress appear in the export file. Unverified events, pending planner reviews, and dependency conflicts are strictly withheld to guarantee schedule integrity.
          </p>
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#F0883E", fontWeight: 600 }}>
            <span>ℹ</span>
            <span>P6 XML deferred; verified schedule export available through CSV/XLSX.</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            onClick={() => handleExport("csv")}
            disabled={exportingFormat !== null}
            style={{
              background: "#238636", color: "#FFFFFF", border: "1px solid rgba(240,246,252,0.15)", borderRadius: 8, padding: "10px 20px",
              fontSize: 13, fontWeight: 700, cursor: exportingFormat ? "not-allowed" : "pointer",
            }}
          >
            {exportingFormat === "csv" ? "Generating CSV..." : "Export CSV"}
          </button>
          <button
            onClick={() => handleExport("xlsx")}
            disabled={exportingFormat !== null}
            style={{
              background: "#0D9488", color: "#FFFFFF", border: "1px solid rgba(240,246,252,0.15)", borderRadius: 8, padding: "10px 20px",
              fontSize: 13, fontWeight: 700, cursor: exportingFormat ? "not-allowed" : "pointer",
            }}
          >
            {exportingFormat === "xlsx" ? "Generating XLSX..." : "Export XLSX"}
          </button>
        </div>
      </div>

      {/* Schedule Change Preview Card */}
      <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#1F2328" }}>Schedule Change Preview</h3>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "#656D76" }}>
              Deterministic evaluation of schedule updates, provenance, confidence, and temporal validation.
            </p>
          </div>
          {/* Search box */}
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ID or Activity..."
            style={{ fontSize: 12, border: "1px solid #D0D7DE", borderRadius: 6, padding: "6px 12px", width: 220 }}
          />
        </div>

        {/* Filter Pills */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 16 }}>
          <button
            onClick={() => setFilter("all")}
            style={{
              borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
              background: filter === "all" ? "#1F2328" : "#FFFFFF",
              color: filter === "all" ? "#FFFFFF" : "#656D76",
              borderColor: filter === "all" ? "#1F2328" : "#D0D7DE",
            }}
          >
            All Items ({preview?.changes.length ?? 0})
          </button>
          <button
            onClick={() => setFilter("verified")}
            style={{
              borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
              background: filter === "verified" ? "#059669" : "#FFFFFF",
              color: filter === "verified" ? "#FFFFFF" : "#059669",
              borderColor: filter === "verified" ? "#059669" : "#A7F3D0",
            }}
          >
            Verified Updates ({verifiedCount})
          </button>
          <button
            onClick={() => setFilter("review")}
            style={{
              borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
              background: filter === "review" ? "#D97706" : "#FFFFFF",
              color: filter === "review" ? "#FFFFFF" : "#D97706",
              borderColor: filter === "review" ? "#D97706" : "#FDE68A",
            }}
          >
            Review & Conflicts ({reviewCount})
          </button>
          <button
            onClick={() => setFilter("unchanged")}
            style={{
              borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
              background: filter === "unchanged" ? "#475569" : "#FFFFFF",
              color: filter === "unchanged" ? "#FFFFFF" : "#475569",
              borderColor: filter === "unchanged" ? "#475569" : "#CBD5E1",
            }}
          >
            Unchanged ({unchangedCount})
          </button>
        </div>

        {/* Change Preview Table */}
        {loading ? (
          <Spinner />
        ) : filteredChanges.length === 0 ? (
          <EmptyState title="No matching schedule records" description="No schedule items match the current filter or search criteria." />
        ) : (
          <div style={{ overflowX: "auto", border: "1px solid #D0D7DE", borderRadius: 8 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
              <thead style={{ background: "#F6F8FA", borderBottom: "1px solid #D0D7DE" }}>
                <tr>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Activity ID</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Activity Name & Discipline</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Field</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Old Value</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>New Value</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Evidence</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Match</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Temporal</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Decision</th>
                  <th style={{ padding: "10px 12px", fontWeight: 700, color: "#1F2328" }}>Audit / Source</th>
                </tr>
              </thead>
              <tbody>
                {filteredChanges.map((change, idx) => {
                  const isVerified = change.decision === "VERIFIED";
                  const isReview = change.decision === "PLANNER_REVIEW";
                  const isConflict = change.decision === "CONFLICT";
                  const isRejected = change.decision === "REJECTED";

                  let badgeBg = "#F1F5F9";
                  let badgeColor = "#475569";
                  let badgeBorder = "#CBD5E1";
                  if (isVerified) {
                    badgeBg = "#ECFDF5"; badgeColor = "#059669"; badgeBorder = "#A7F3D0";
                  } else if (isReview) {
                    badgeBg = "#FFFBEB"; badgeColor = "#D97706"; badgeBorder = "#FDE68A";
                  } else if (isConflict || isRejected) {
                    badgeBg = "#FEF2F2"; badgeColor = "#DC2626"; badgeBorder = "#FECACA";
                  }

                  return (
                    <tr key={`${change.activity_id}-${change.field}-${idx}`} style={{ borderBottom: "1px solid #E1E4E8", background: isVerified ? "#F0FDF4" : (isConflict ? "#FFF5F5" : "#FFFFFF") }}>
                      <td style={{ padding: "10px 12px", fontWeight: 700, fontFamily: "ui-monospace, monospace" }}>
                        {change.external_activity_id}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ fontWeight: 600, color: "#1F2328" }}>{change.activity_name}</div>
                        <div style={{ fontSize: 11, color: "#656D76" }}>
                          {[change.discipline, change.location].filter(Boolean).join(" · ") || "General"}
                        </div>
                      </td>
                      <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1F2328" }}>
                        {change.field}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#656D76", fontFamily: "ui-monospace, monospace" }}>
                        {change.old_value}
                      </td>
                      <td style={{ padding: "10px 12px", fontWeight: 700, color: isVerified ? "#059669" : "#1F2328", fontFamily: "ui-monospace, monospace" }}>
                        {change.new_value}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#1F2328", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={change.source_evidence}>
                        {change.source_evidence}
                      </td>
                      <td style={{ padding: "10px 12px", color: "#656D76" }}>
                        {change.match_confidence !== null ? `${Math.round(change.match_confidence * 100)}%` : "—"}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                          background: change.temporal_status === "VALID" ? "#ECFDF5" : "#FEF2F2",
                          color: change.temporal_status === "VALID" ? "#059669" : "#DC2626",
                          border: `1px solid ${change.temporal_status === "VALID" ? "#A7F3D0" : "#FECACA"}`
                        }}>
                          {change.temporal_status}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 10,
                          background: badgeBg, color: badgeColor, border: `1px solid ${badgeBorder}`
                        }}>
                          {change.decision}
                        </span>
                        {isReview && (
                          <button
                            onClick={() => onNavigateToReview()}
                            style={{ display: "block", marginTop: 4, background: "none", border: "none", padding: 0, color: "#0969DA", fontSize: 11, cursor: "pointer", textDecoration: "underline" }}
                          >
                            Review in Queue →
                          </button>
                        )}
                      </td>
                      <td style={{ padding: "10px 12px", fontSize: 11, color: "#656D76", maxWidth: 180 }}>
                        <div style={{ fontWeight: 600, color: "#24292F" }}>{change.decision_source}</div>
                        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={change.rationale}>
                          {change.rationale}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── EXECUTION MEMORY & INSTITUTIONAL KNOWLEDGE ─────────────────────────────
function ExecutionMemoryView({
  projectId,
  onSelectActivity,
  onOpenReview,
}: {
  projectId: string;
  onSelectActivity?: (act: any) => void;
  onOpenReview?: (id?: string) => void;
}) {
  const [summary, setSummary] = useState<ProjectPerformanceSummary | null>(null);
  const [records, setRecords] = useState<ExecutionRecordResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Inspector & selection
  const [selectedActivityId, setSelectedActivityId] = useState<string | null>(null);
  const [activityHistory, setActivityHistory] = useState<ActivityExecutionHistoryResponse | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Filters
  const [disciplineFilter, setDisciplineFilter] = useState<string>("all");
  const [deviationFilter, setDeviationFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Similar historical reference search
  const [similarQuery, setSimilarQuery] = useState("hydrotest");
  const [similarResults, setSimilarResults] = useState<HistoricalReferenceItem[]>([]);
  const [similarLoading, setSimilarLoading] = useState(false);

  async function loadMemoryData() {
    setLoading(true);
    setError(null);
    try {
      const [sum, recs] = await Promise.all([
        fetchProjectMemorySummary(projectId),
        fetchProjectExecutionRecords(projectId),
      ]);
      setSummary(sum);
      setRecords(recs);
      if (recs.length > 0 && !selectedActivityId) {
        setSelectedActivityId(recs[0].activity_id);
        loadActivityHistory(recs[0].activity_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load execution memory.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSyncMemory() {
    setSyncing(true);
    setError(null);
    setNotice(null);
    try {
      const updated = await syncProjectMemory(projectId);
      setNotice(`Execution memory synchronized: ${updated.length} records compiled into institutional knowledge.`);
      await loadMemoryData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to synchronize execution memory.");
    } finally {
      setSyncing(false);
    }
  }

  async function loadActivityHistory(actId: string) {
    setSelectedActivityId(actId);
    setLoadingHistory(true);
    try {
      const hist = await fetchActivityExecutionHistory(projectId, actId);
      setActivityHistory(hist);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingHistory(false);
    }
  }

  async function handleSearchSimilar(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!similarQuery.trim()) return;
    setSimilarLoading(true);
    try {
      const res = await fetchSimilarExecutions(projectId, similarQuery);
      setSimilarResults(res.results);
    } catch (err) {
      console.error(err);
    } finally {
      setSimilarLoading(false);
    }
  }

  useEffect(() => {
    loadMemoryData();
    handleSearchSimilar();
  }, [projectId]);

  const filteredRecords = useMemo(() => {
    return records.filter((r) => {
      if (disciplineFilter !== "all" && r.discipline?.toLowerCase() !== disciplineFilter.toLowerCase()) {
        return false;
      }
      if (deviationFilter !== "all" && r.deviation_type !== deviationFilter) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchId = r.external_activity_id.toLowerCase().includes(q);
        const matchName = r.activity_name.toLowerCase().includes(q);
        const matchCause = (r.delay_cause || "").toLowerCase().includes(q);
        if (!matchId && !matchName && !matchCause) return false;
      }
      return true;
    });
  }, [records, disciplineFilter, deviationFilter, searchQuery]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* ─── HEADER & ACTIONS ────────────────────────────────────────── */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ background: "#EDE9FE", border: "1px solid #C4B5FD", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#5B21B6", textTransform: "uppercase" }}>
              SIH26122 Core Memory
            </span>
            <span style={{ fontSize: 12, color: "#656D76" }}>Institutional Project Knowledge Repository</span>
          </div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Execution Memory</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76", maxWidth: 740 }}>
            Preserves actual project execution knowledge: durations, deterministic variances, contractor performance, and verified delay causes with complete evidence provenance. Zero cause fabrication.
          </p>
        </div>

        <button
          onClick={handleSyncMemory}
          disabled={syncing}
          style={{
            display: "flex", alignItems: "center", gap: 8, borderRadius: 8, padding: "8px 16px", fontSize: 13, fontWeight: 600,
            cursor: syncing ? "not-allowed" : "pointer", background: "#7C3AED", color: "#FFFFFF", border: "none",
            boxShadow: "0 1px 3px rgba(124, 58, 237, 0.2)",
          }}
        >
          {syncing ? "Compiling Memory…" : "Sync Execution Memory"}
        </button>
      </div>

      {notice && (
        <div style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", borderRadius: 8, padding: "10px 16px", color: "#065F46", fontSize: 12, fontWeight: 600 }}>
          {notice}
        </div>
      )}
      {error && (
        <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "10px 16px", color: "#991B1B", fontSize: 12, fontWeight: 600 }}>
          {error}
        </div>
      )}

      {/* ─── PROJECT PERFORMANCE KPI CARDS ────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 14 }}>
        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#656D76", fontWeight: 600, textTransform: "uppercase" }}>Activities Completed</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#1F2328", marginTop: 4 }}>
            {summary?.completed_activities ?? "—"} <span style={{ fontSize: 13, color: "#656D76", fontWeight: 500 }}>/ {summary?.total_activities ?? "—"}</span>
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #A7F3D0", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#059669", fontWeight: 600, textTransform: "uppercase" }}>On Time / Early</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#059669", marginTop: 4 }}>
            {summary?.on_time_activities ?? "—"}
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #FDE68A", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#D97706", fontWeight: 600, textTransform: "uppercase" }}>Late / Extended</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#D97706", marginTop: 4 }}>
            {summary?.late_activities ?? "—"}
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #FECACA", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#DC2626", fontWeight: 600, textTransform: "uppercase" }}>Conflicts Blocked</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: "#DC2626", marginTop: 4 }}>
            {summary?.conflict_count ?? "—"}
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#656D76", fontWeight: 600, textTransform: "uppercase" }}>Avg Planned Duration</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "#1F2328", marginTop: 4 }}>
            {summary?.average_planned_duration_days != null ? `${summary.average_planned_duration_days} days` : "—"}
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#656D76", fontWeight: 600, textTransform: "uppercase" }}>Avg Actual Duration</div>
          <div style={{ fontSize: 24, fontWeight: 800, color: "#1F2328", marginTop: 4 }}>
            {summary?.average_actual_duration_days != null ? `${summary.average_actual_duration_days} days` : "—"}
          </div>
        </div>

        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, padding: "16px 20px" }}>
          <div style={{ fontSize: 12, color: "#656D76", fontWeight: 600, textTransform: "uppercase" }}>Average Variance</div>
          <div
            style={{
              fontSize: 24, fontWeight: 800, marginTop: 4,
              color: (summary?.average_variance_days || 0) > 0 ? "#DC2626" : (summary?.average_variance_days || 0) < 0 ? "#059669" : "#1F2328",
            }}
          >
            {summary?.average_variance_days != null ? `${summary.average_variance_days > 0 ? "+" : ""}${summary.average_variance_days} days` : "—"}
          </div>
        </div>
      </div>

      {/* ─── DELAY CAUSES & DISCIPLINE / CONTRACTOR PERFORMANCE ──────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        {/* Top Recorded Delay Causes Card */}
        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
          <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 700, color: "#1F2328" }}>Top Recorded Delay Causes</h3>
          <p style={{ margin: "0 0 16px", fontSize: 12, color: "#656D76" }}>
            Extracted strictly from explicit DPR evidence statements. No causes fabricated.
          </p>

          {summary?.top_delay_causes.length === 0 ? (
            <div style={{ color: "#656D76", fontSize: 13, fontStyle: "italic", padding: "16px 0" }}>
              No explicit delay causes reported in current project evidence.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {summary?.top_delay_causes.map((c) => (
                <div key={c.category} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#F6F8FA", border: "1px solid #E1E4E8", borderRadius: 8, padding: "10px 14px" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ background: "#FEF3C7", color: "#92400E", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700 }}>
                        {c.category}
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 600, color: "#1F2328" }}>
                        {c.sample_causes.length > 0 ? c.sample_causes.join(", ") : "Recorded delay"}
                      </span>
                    </div>
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 800, color: "#92400E", background: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: 12, padding: "2px 10px" }}>
                    {c.count} {c.count === 1 ? "occurrence" : "occurrences"}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Discipline & Contractor Performance */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
            <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 700, color: "#1F2328" }}>Discipline Performance</h3>
            <p style={{ margin: "0 0 14px", fontSize: 12, color: "#656D76" }}>Schedule variance breakdown by engineering discipline.</p>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 10 }}>
              {summary?.discipline_performance.map((d) => (
                <div key={d.discipline} style={{ background: "#F6F8FA", border: "1px solid #E1E4E8", borderRadius: 8, padding: "12px 14px" }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#1F2328" }}>{d.discipline}</div>
                  <div style={{ fontSize: 11, color: "#656D76", marginTop: 2 }}>{d.completed_activities} / {d.total_activities} completed</div>
                  <div style={{ marginTop: 8, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 11, color: "#656D76" }}>Avg Variance:</span>
                    <span
                      style={{
                        fontSize: 12, fontWeight: 700,
                        color: (d.average_variance_days || 0) > 0 ? "#DC2626" : (d.average_variance_days || 0) < 0 ? "#059669" : "#1F2328",
                      }}
                    >
                      {d.average_variance_days != null ? `${d.average_variance_days > 0 ? "+" : ""}${d.average_variance_days}d` : "—"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Contractor Performance */}
          <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
            <h3 style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 700, color: "#1F2328" }}>Contractor Execution Performance</h3>
            <p style={{ margin: "0 0 14px", fontSize: 12, color: "#656D76" }}>Aggregated from field returns where contractor was explicitly reported.</p>

            {summary?.contractor_performance.length === 0 ? (
              <div style={{ color: "#656D76", fontSize: 12, fontStyle: "italic" }}>No specific contractors reported in field returns.</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #E1E4E8", color: "#656D76", textAlign: "left" }}>
                    <th style={{ padding: "6px 8px" }}>Contractor</th>
                    <th style={{ padding: "6px 8px" }}>Activities</th>
                    <th style={{ padding: "6px 8px" }}>Delayed</th>
                    <th style={{ padding: "6px 8px", textAlign: "right" }}>Avg Variance</th>
                  </tr>
                </thead>
                <tbody>
                  {summary?.contractor_performance.map((c) => (
                    <tr key={c.contractor} style={{ borderBottom: "1px solid #F0F2F5" }}>
                      <td style={{ padding: "8px 8px", fontWeight: 600, color: "#1F2328" }}>{c.contractor}</td>
                      <td style={{ padding: "8px 8px", color: "#656D76" }}>{c.completed_activities} / {c.total_activities}</td>
                      <td style={{ padding: "8px 8px", color: c.delayed_count > 0 ? "#D97706" : "#656D76" }}>{c.delayed_count}</td>
                      <td style={{ padding: "8px 8px", textAlign: "right", fontWeight: 700, color: (c.average_variance_days || 0) > 0 ? "#DC2626" : "#059669" }}>
                        {c.average_variance_days != null ? `${c.average_variance_days > 0 ? "+" : ""}${c.average_variance_days}d` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* ─── ACTIVITY EXECUTION HISTORY & EVIDENCE INSPECTOR ─────────── */}
      <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#1F2328" }}>Activity Execution Memory & Audit Trace</h3>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "#656D76" }}>
              Select any activity to inspect verified duration, baseline variance, deviations, delay causes, and planner actions.
            </p>
          </div>

          {/* Search box */}
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Filter by ID, description, cause…"
            style={{ fontSize: 12, border: "1px solid #D0D7DE", borderRadius: 6, padding: "6px 12px", width: 240 }}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 20 }}>
          {/* Records Table */}
          <div style={{ overflowX: "auto", border: "1px solid #E1E4E8", borderRadius: 8 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
              <thead style={{ background: "#F6F8FA", borderBottom: "1px solid #D0D7DE" }}>
                <tr>
                  <th style={{ padding: "10px 12px", fontWeight: 600 }}>Activity</th>
                  <th style={{ padding: "10px 12px", fontWeight: 600 }}>Discipline</th>
                  <th style={{ padding: "10px 12px", fontWeight: 600 }}>Duration (P/A)</th>
                  <th style={{ padding: "10px 12px", fontWeight: 600 }}>Variance</th>
                  <th style={{ padding: "10px 12px", fontWeight: 600 }}>Deviation</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((r) => {
                  const isSelected = selectedActivityId === r.activity_id;
                  const varianceLabel = r.variance_days != null ? `${r.variance_days > 0 ? "+" : ""}${r.variance_days}d` : "—";
                  const pDur = r.planned_duration_days != null ? `${r.planned_duration_days}d` : "—";
                  const aDur = r.actual_duration_days != null ? `${r.actual_duration_days}d` : "—";

                  let devBadgeColor = "#E1E4E8";
                  let devTextColor = "#24292F";
                  if (r.deviation_type === "ON_TIME" || r.deviation_type === "EARLY") {
                    devBadgeColor = "#D1FAE5"; devTextColor = "#065F46";
                  } else if (r.deviation_type === "LATE" || r.deviation_type === "EXTENDED") {
                    devBadgeColor = "#FEF3C7"; devTextColor = "#92400E";
                  } else if (r.deviation_type === "CONFLICT") {
                    devBadgeColor = "#FEE2E2"; devTextColor = "#991B1B";
                  }

                  return (
                    <tr
                      key={r.record_id}
                      onClick={() => loadActivityHistory(r.activity_id)}
                      style={{
                        cursor: "pointer",
                        borderBottom: "1px solid #F0F2F5",
                        background: isSelected ? "#F5F3FF" : "transparent",
                        transition: "background 0.15s ease",
                      }}
                    >
                      <td style={{ padding: "10px 12px" }}>
                        <div style={{ fontWeight: 700, color: "#1F2328" }}>{r.external_activity_id}</div>
                        <div style={{ fontSize: 11, color: "#656D76", maxWidth: 180, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                          {r.activity_name}
                        </div>
                      </td>
                      <td style={{ padding: "10px 12px", color: "#656D76" }}>{r.discipline || "—"}</td>
                      <td style={{ padding: "10px 12px", color: "#24292F", fontFamily: "monospace" }}>
                        {pDur} / {aDur}
                      </td>
                      <td
                        style={{
                          padding: "10px 12px", fontWeight: 700, fontFamily: "monospace",
                          color: (r.variance_days || 0) > 0 ? "#DC2626" : (r.variance_days || 0) < 0 ? "#059669" : "#656D76",
                        }}
                      >
                        {varianceLabel}
                      </td>
                      <td style={{ padding: "10px 12px" }}>
                        <span style={{ background: devBadgeColor, color: devTextColor, padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 700 }}>
                          {r.deviation_type}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Activity Inspector Card */}
          <div style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 18 }}>
            {loadingHistory ? (
              <div style={{ textAlign: "center", padding: "40px 0", color: "#656D76" }}>Loading activity history…</div>
            ) : activityHistory ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                <div style={{ borderBottom: "1px solid #E2E8F0", paddingBottom: 10 }}>
                  <div style={{ fontSize: 11, color: "#7C3AED", fontWeight: 700, textTransform: "uppercase" }}>Activity History</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: "#0F172A", marginTop: 2 }}>{activityHistory.external_activity_id} · {activityHistory.activity_name}</div>
                  <div style={{ fontSize: 12, color: "#64748B", marginTop: 2 }}>
                    Discipline: <strong>{activityHistory.discipline || "—"}</strong> · Contractor: <strong>{activityHistory.contractor || "UNKNOWN"}</strong> · Location: <strong>{activityHistory.location || "—"}</strong>
                  </div>
                </div>

                {/* Plan vs Actual Dates & Durations */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: 12 }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#64748B", textTransform: "uppercase" }}>Baseline Plan</div>
                    <div style={{ fontSize: 12, color: "#0F172A", marginTop: 2 }}>Start: <strong>{fmtDate(activityHistory.planned_start)}</strong></div>
                    <div style={{ fontSize: 12, color: "#0F172A" }}>Finish: <strong>{fmtDate(activityHistory.planned_finish)}</strong></div>
                    <div style={{ fontSize: 12, color: "#0F172A", marginTop: 2 }}>Duration: <strong>{activityHistory.planned_duration_days != null ? `${activityHistory.planned_duration_days} days` : "—"}</strong></div>
                  </div>

                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#0D9488", textTransform: "uppercase" }}>Verified Actuals</div>
                    <div style={{ fontSize: 12, color: "#0F172A", marginTop: 2 }}>Start: <strong>{fmtDate(activityHistory.actual_start)}</strong></div>
                    <div style={{ fontSize: 12, color: "#0F172A" }}>Finish: <strong>{fmtDate(activityHistory.actual_end)}</strong></div>
                    <div style={{ fontSize: 12, color: "#0F172A", marginTop: 2 }}>
                      Duration: <strong>{activityHistory.actual_duration_days != null ? `${activityHistory.actual_duration_days} days` : "—"}</strong>
                    </div>
                  </div>
                </div>

                {/* Variance Display */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: "8px 12px" }}>
                  <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Deterministic Schedule Variance:</span>
                  <span
                    style={{
                      fontSize: 14, fontWeight: 800,
                      color: (activityHistory.variance_days || 0) > 0 ? "#DC2626" : (activityHistory.variance_days || 0) < 0 ? "#059669" : "#0F172A",
                    }}
                  >
                    {activityHistory.variance_days != null ? `${activityHistory.variance_days > 0 ? "+" : ""}${activityHistory.variance_days} days` : "UNKNOWN (Missing Actual End)"}
                  </span>
                </div>

                {/* Recorded Deviations */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Recorded Deviations</div>
                  {activityHistory.recorded_deviations.length === 0 ? (
                    <div style={{ fontSize: 12, color: "#059669" }}>✓ No baseline deviations recorded. Execution aligned with schedule.</div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                      {activityHistory.recorded_deviations.map((d, idx) => (
                        <div key={idx} style={{ fontSize: 12, color: "#92400E", background: "#FEF3C7", padding: "4px 8px", borderRadius: 4, fontWeight: 500 }}>
                          ⚠ {d}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Recorded Delay Cause & Provenance */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Recorded Cause & Provenance</div>
                  <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: "10px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 12, fontWeight: 700, color: "#0F172A" }}>
                        {activityHistory.recorded_cause || "UNKNOWN"}
                      </span>
                      {activityHistory.delay_category && (
                        <span style={{ background: "#EDE9FE", color: "#6D28D9", padding: "1px 6px", borderRadius: 4, fontSize: 10, fontWeight: 700 }}>
                          {activityHistory.delay_category}
                        </span>
                      )}
                    </div>
                    {activityHistory.cause_source_reference && (
                      <div style={{ fontSize: 11, color: "#64748B", marginTop: 4 }}>
                        Source Citation: <code>{activityHistory.cause_source_reference}</code>
                      </div>
                    )}
                    {activityHistory.cause_confidence != null && (
                      <div style={{ fontSize: 11, color: "#64748B" }}>
                        Confidence Score: <strong>{(activityHistory.cause_confidence * 100).toFixed(0)}%</strong>
                      </div>
                    )}
                  </div>
                </div>

                {/* Execution Evidence Sources */}
                <div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Execution Evidence Citations</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {activityHistory.execution_evidence_citations.map((cite) => (
                      <span key={cite} style={{ background: "#E2E8F0", color: "#334155", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                        📄 {cite}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Planner Actions / Overrides */}
                {activityHistory.planner_decisions.length > 0 && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#475569", textTransform: "uppercase", marginBottom: 4 }}>Planner Review History</div>
                    {activityHistory.planner_decisions.map((p, idx) => (
                      <div key={idx} style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: "8px 10px", fontSize: 11, color: "#334155" }}>
                        <div><strong>{p.reviewer}</strong>: {p.reviewer_decision.toUpperCase()}</div>
                        <div style={{ color: "#64748B", marginTop: 2 }}>{p.reviewer_comment}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div style={{ textAlign: "center", padding: "40px 0", color: "#656D76" }}>Select an activity to view history.</div>
            )}
          </div>
        </div>
      </div>

      {/* ─── FUTURE PLANNING REFERENCE (SIMILAR EXECUTIONS) ─────────── */}
      <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "20px 24px" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 16, marginBottom: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ background: "#FEF3C7", border: "1px solid #FCD34D", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#92400E", textTransform: "uppercase" }}>
                Institutional Memory Reference
              </span>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#DC2626" }}>HISTORICAL REFERENCE ONLY — NOT A PREDICTION</span>
            </div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "#1F2328" }}>Similar Completed Historical Activities</h3>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76", maxWidth: 740 }}>
              Queries past completed work across projects with semantic embedding similarity to provide benchmark durations, variances, and recorded delay causes for future planning reference.
            </p>
          </div>

          <form onSubmit={handleSearchSimilar} style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={similarQuery}
              onChange={(e) => setSimilarQuery(e.target.value)}
              placeholder="Search historical activity (e.g., hydrotest)…"
              style={{ fontSize: 12, border: "1px solid #D0D7DE", borderRadius: 6, padding: "6px 12px", width: 280 }}
            />
            <button
              type="submit"
              disabled={similarLoading}
              style={{ background: "#24292F", color: "#FFFFFF", border: "none", borderRadius: 6, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
            >
              {similarLoading ? "Searching…" : "Retrieve Reference"}
            </button>
          </form>
        </div>

        {similarResults.length === 0 ? (
          <div style={{ background: "#F6F8FA", border: "1px dashed #D0D7DE", borderRadius: 8, padding: "24px", textAlign: "center", color: "#656D76", fontSize: 13 }}>
            No matching completed historical activities found for query: "<strong>{similarQuery}</strong>".
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 14 }}>
            {similarResults.map((item, idx) => (
              <div key={idx} style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 8, padding: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{item.activity_name}</div>
                    <div style={{ fontSize: 11, color: "#64748B" }}>Project: {item.project_name} · {item.discipline || "—"}</div>
                  </div>
                  <span style={{ background: "#E2E8F0", color: "#475569", borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 700 }}>
                    {(item.similarity_score * 100).toFixed(0)}% match
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: 8, fontSize: 11 }}>
                  <div>
                    <span style={{ color: "#64748B" }}>Plan:</span> <strong>{item.planned_duration_days != null ? `${item.planned_duration_days}d` : "—"}</strong>
                  </div>
                  <div>
                    <span style={{ color: "#64748B" }}>Actual:</span> <strong>{item.actual_duration_days != null ? `${item.actual_duration_days}d` : "—"}</strong>
                  </div>
                  <div>
                    <span style={{ color: "#64748B" }}>Variance:</span>{" "}
                    <strong style={{ color: (item.variance_days || 0) > 0 ? "#DC2626" : "#059669" }}>
                      {item.variance_days != null ? `${item.variance_days > 0 ? "+" : ""}${item.variance_days}d` : "—"}
                    </strong>
                  </div>
                </div>

                {item.delay_cause && (
                  <div style={{ fontSize: 11, color: "#92400E", background: "#FEF3C7", padding: "4px 8px", borderRadius: 4 }}>
                    Recorded Cause: <strong>{item.delay_cause}</strong> {item.delay_category ? `(${item.delay_category})` : ""}
                  </div>
                )}
                {item.evidence_reference && (
                  <div style={{ fontSize: 10, color: "#64748B" }}>Evidence: {item.evidence_reference}</div>
                )}

                <div style={{ fontSize: 9, color: "#94A3B8", fontWeight: 600, borderTop: "1px solid #F1F5F9", paddingTop: 4 }}>
                  {item.disclaimer}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── RECONCILIATION CENTER ────────────────────────────────────────────────────

function Reconciliation({ data, reviews, onOpenReview, onSelectActivity }: { data: DashboardData; reviews: PlannerReviewContext[]; onOpenReview: (id?: string) => void; onSelectActivity?: (act: any) => void }) {
  const [filter, setFilter] = useState<"all" | "conflict" | "auto" | "review">("all");
  const actMap = useMemo(() => new Map(data.activities.map((a) => [a.activity_id, a])), [data]);
  const revMap = useMemo(() => new Map(reviews.map((r) => [r.current_activity.activity_id, r])), [reviews]);

  const filtered = useMemo(() => data.reconciliations.filter((item) => {
    const hasConflict = Boolean(item.conflicting_evidence?.length);
    if (filter === "conflict") return hasConflict;
    if (filter === "auto") return item.decision === "auto_accept";
    if (filter === "review") return item.decision === "planner_review";
    return true;
  }), [data.reconciliations, filter]);

  const chips: Array<["all" | "conflict" | "auto" | "review", string]> = [
    ["all", `All Records (${data.reconciliations.length})`],
    ["conflict", `Discrepancies (${data.reconciliations.filter((r) => r.conflicting_evidence?.length).length})`],
    ["auto", `Auto-Accepted (${data.reconciliations.filter((r) => r.decision === "auto_accept").length})`],
    ["review", `Pending Review (${data.reconciliations.filter((r) => r.decision === "planner_review").length})`],
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      
      {/* Section Header & Summary */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#0D4F4A", textTransform: "uppercase" }}>
              Reconciliation Summary
            </span>
            <span style={{ fontSize: 12, color: "#656D76" }}>
              Project: {DEFAULT_PROJECT_DISPLAY_NAME}
            </span>
          </div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Reconciliation Center</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76", maxWidth: 640 }}>
            Synthesizes multi-source daily field logs against WBS schedule baselines, resolving variance through source reliability and temporal freshness weighting.
          </p>
        </div>

        {/* Filter Chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {chips.map(([key, label]) => (
            <button key={key} onClick={() => setFilter(key)}
              style={{ borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid", transition: "all 0.15s",
                background: filter === key ? "#1F2328" : "#FFFFFF", color: filter === key ? "#FFFFFF" : "#656D76", borderColor: filter === key ? "#1F2328" : "#D0D7DE" }}
              onMouseEnter={(e) => { if (filter !== key) e.currentTarget.style.borderColor = "#8C959F"; }}
              onMouseLeave={(e) => { if (filter !== key) e.currentTarget.style.borderColor = "#D0D7DE"; }}
            >{label}</button>
          ))}
        </div>
      </div>

      {/* Operational Pipeline Tracker */}
      <OperationalPipeline linkedCount={data.pipeline.length} />

      {/* Reconciliation Cards */}
      {filtered.length === 0 ? <EmptyState title="No reconciliation records" description="No activities match the selected filter criteria." /> : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(560px, 1fr))", gap: 20 }}>
          {filtered.map((item) => {
            const act = actMap.get(item.activity_id);
            const rev = revMap.get(item.activity_id);
            const hasConflict = Boolean(item.conflicting_evidence?.length);
            const isAuto = item.decision === "auto_accept";
            const isReview = item.decision === "planner_review";

            return (
              <article key={item.reconciliation_id} style={{ background: "#FFFFFF", border: `1px solid ${isReview ? "#EAC54F" : "#D0D7DE"}`, borderRadius: 12, padding: 22, boxShadow: "0 1px 3px rgba(31,35,40,0.06)", display: "flex", flexDirection: "column", gap: 16 }}>

                {/* Activity header */}
                <div style={{ borderBottom: "1px solid #EAEEF2", paddingBottom: 14 }}>
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                      <code style={{ background: "#1F2328", color: "#F0F6FC", borderRadius: 6, padding: "3px 8px", fontSize: 12, fontWeight: 700 }}>
                        {act?.external_activity_id ?? item.activity_id.slice(0, 8)}
                      </code>
                      <span style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600, color: "#656D76" }}>WBS L{act?.level ?? 5}</span>
                      {act?.discipline && <span style={{ background: "#DFF0FF", border: "1px solid #54AEFF", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 600, color: "#0969DA" }}>{act.discipline}</span>}
                      {act?.location && <span style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 6, padding: "2px 8px", fontSize: 11, color: "#656D76" }}>{act.location}</span>}
                    </div>
                    <Badge value={isAuto ? "Completed" : isReview ? "Needs Review" : "No Action"} />
                  </div>
                  <h3 style={{ margin: "10px 0 0", fontSize: 16, fontWeight: 700, color: "#1F2328" }}>{act?.description ?? "Schedule Activity"}</h3>

                  {/* Baseline vs Reconciled Grid */}
                  <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 12 }}>
                    {[
                      ["Planned Schedule", `${fmtDate(act?.planned_start)} → ${fmtDate(act?.planned_finish)}`],
                      ["Baseline State", `${fmtStatus(act?.status)} (${act?.progress ?? 0}%)`],
                      ["Reconciled Target", `${fmtStatus(item.status)} (${item.progress ?? "—"}%)`],
                    ].map(([label, val]) => (
                      <div key={label}>
                        <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F", marginBottom: 3 }}>{label}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#1F2328" }}>{val}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Conflict Notice */}
                {hasConflict && (
                  <div style={{ background: "#FFF8C5", border: "1px solid #EAC54F", borderRadius: 8, padding: "10px 14px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#9A6700", textTransform: "uppercase", letterSpacing: 0.5 }}>⚠ Multi-Source Variance Detected</span>
                      <span style={{ background: "#FFF8C5", border: "1px solid #EAC54F", borderRadius: 20, padding: "1px 8px", fontSize: 11, fontWeight: 700, color: "#9A6700" }}>
                        {item.conflicting_evidence.length} source{item.conflicting_evidence.length > 1 ? "s" : ""}
                      </span>
                    </div>
                    <p style={{ margin: "5px 0 0", fontSize: 12, color: "#7A5300" }}>
                      Contradictory progress claims detected between field reports. Synthesized via reliability weighting and decay.
                    </p>
                  </div>
                )}

                {/* Reconciliation Engine Rationale */}
                <div style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 10, padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, paddingBottom: 8, borderBottom: "1px solid #CCFBF1" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#0D4F4A" }}>
                      Reconciliation Analysis
                    </span>
                    <span style={{ background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 20, padding: "2px 10px", fontSize: 11, fontWeight: 700, color: "#0D4F4A" }}>
                      Reconciliation Confidence: {Math.round(item.confidence * 100)}%
                    </span>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: "#1F2328", lineHeight: 1.6 }}>{item.explanation}</p>
                  {item.recommended_action && (
                    <div style={{ marginTop: 10, background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 6, padding: "8px 12px", fontSize: 12, color: "#0D4F4A" }}>
                      <strong>Recommended: </strong>{item.recommended_action}
                    </div>
                  )}
                </div>

                {/* Compact Schedule Validation Section */}
                <ScheduleValidationSection rec={item} activity={act} onOpenReview={() => onOpenReview(rev?.review_id)} />

                {/* Multi-Source Evidence List */}
                {([...item.supporting_evidence, ...item.conflicting_evidence]).length > 0 && (
                  <div>
                    <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                      Evidence Records ({item.supporting_evidence.length + item.conflicting_evidence.length})
                    </p>
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {[...item.supporting_evidence, ...item.conflicting_evidence].map((ev) => {
                        const isConf = item.conflicting_evidence.some((c: any) => c.observation_id === ev.observation_id);
                        const doc = getSourceDocInfo(ev.source_name, ev.source_type);
                        return (
                          <div key={ev.observation_id} style={{ background: isConf ? "#FFF8C5" : "#F6F8FA", border: `1px solid ${isConf ? "#EAC54F" : "#EAEEF2"}`, borderRadius: 8, padding: "8px 12px", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                            <div>
                              <span style={{ fontWeight: 700, fontSize: 12, color: "#1F2328" }}>{doc.title}</span>
                              <span style={{ fontSize: 11, color: "#656D76", marginLeft: 6 }}>({doc.typeName})</span>
                              <br />
                              <span style={{ fontSize: 12, color: "#1F2328" }}>{fmtStatus(ev.status)}{ev.progress != null ? ` · ${ev.progress}%` : ""}</span>
                            </div>
                            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                              {ev.reliability_score != null && (
                                <span style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#656D76", fontFamily: "ui-monospace, monospace" }}>
                                  {Math.round(ev.reliability_score * 100)}% source reliability
                                </span>
                              )}
                              {ev.freshness_score != null && (
                                <span style={{ fontSize: 11, color: "#8C959F", fontFamily: "ui-monospace, monospace" }}>
                                  {Math.round(ev.freshness_score * 100)}% freshness
                                </span>
                              )}
                              <Badge value={isConf ? "Needs Review" : "Completed"} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Card Footer */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid #EAEEF2" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <code style={{ fontSize: 11, color: "#8C959F" }}>
                      Record #REC-{item.reconciliation_id.slice(0, 6).toUpperCase()}
                    </code>
                    {act && onSelectActivity && (
                      <button
                        onClick={() => onSelectActivity(act)}
                        style={{
                          background: "#F6F8FA",
                          border: "1px solid #D0D7DE",
                          borderRadius: 6,
                          padding: "3px 10px",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "#24292F",
                          cursor: "pointer",
                        }}
                        title="Inspect immediate execution context, dependencies & field evidence"
                      >
                        Execution Context →
                      </button>
                    )}
                  </div>
                  {isReview && rev && (
                    <button onClick={() => onOpenReview(rev.review_id)}
                      style={{ background: "#9A6700", border: "none", borderRadius: 8, padding: "7px 16px", color: "#FFF8C5", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
                      onMouseEnter={(e) => { e.currentTarget.style.background = "#7A5300"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.background = "#9A6700"; }}
                    >Open in Planner Review Queue →</button>
                  )}
                  {isAuto && <span style={{ fontSize: 12, fontWeight: 600, color: "#1A7F37" }}>✓ Schedule baseline auto-actuated</span>}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── OPERATIONAL PIPELINE TRACKER ────────────────────────────────────────────
function OperationalPipeline({ linkedCount }: { linkedCount: number }) {
  const steps = [
    ["1", "Ingestion", "Field documents"],
    ["2", "Extraction", "Attributes & progress"],
    ["3", "Normalization", "Taxonomy & WBS"],
    ["4", "Schedule Match", "L5/L6 activities"],
    ["5", "Conflict Detect", "Cross-source check"],
    ["6", "Reconciliation", "Reliability weighting"],
    ["7", "Safety Gate", "Validation threshold"],
    ["8", "Schedule Update", "Planner review / sync"],
  ];

  return (
    <div className="card-flat" style={{ padding: "16px 20px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, paddingBottom: 8, borderBottom: "1px solid #EAEEF2" }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76" }}>
          Reconciliation Workflow Stages
        </span>
        <span style={{ fontSize: 12, fontWeight: 600, color: "#0D9488" }}>
          {linkedCount} active field observations tracked
        </span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
        {steps.map(([num, label, sub]) => (
          <div key={label} className="pipeline-step" style={{ padding: 10, textAlign: "center" }}>
            <span style={{ display: "flex", width: 22, height: 22, alignItems: "center", justifyContent: "center", borderRadius: "50%", background: "#1F2328", color: "#fff", fontSize: 10, fontWeight: 700, margin: "0 auto 6px" }}>{num}</span>
            <p style={{ margin: "0 0 2px", fontSize: 11, fontWeight: 700, color: "#1F2328", lineHeight: 1.3 }}>{label}</p>
            <p style={{ margin: 0, fontSize: 10, color: "#8C959F" }}>{sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── OVERVIEW ─────────────────────────────────────────────────────────────────
function Overview({ data }: { data: DashboardData }) {
  const o = data.overview;
  
  // Compute discipline breakdown from actual activities
  const disciplines = useMemo(() => {
    const counts: Record<string, { total: number; completed: number; progressSum: number }> = {};
    for (const a of data.activities) {
      const disc = a.discipline || "General";
      if (!counts[disc]) counts[disc] = { total: 0, completed: 0, progressSum: 0 };
      counts[disc].total += 1;
      if (a.status === "completed") counts[disc].completed += 1;
      counts[disc].progressSum += a.progress || 0;
    }
    return Object.entries(counts).map(([name, s]) => ({
      name,
      total: s.total,
      completed: s.completed,
      avgProgress: Math.round(s.progressSum / s.total),
    }));
  }, [data.activities]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ background: "#DFF0FF", border: "1px solid #54AEFF", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#0969DA", textTransform: "uppercase" }}>
            Project Controls
          </span>
          <span style={{ fontSize: 12, color: "#656D76" }}>{DEFAULT_PROJECT_DISPLAY_NAME}</span>
        </div>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Project Overview & Schedule Health</h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
          Reconciled actual progress compared against scheduled baseline dates and variance thresholds.
        </p>
      </div>

      {/* Primary KPI Tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
        {[
          { label: "Actual Progress", value: `${o.overall_progress}%`, sub: `Planned: ${o.planned_progress}%`, accent: "#0D9488" },
          { label: "Schedule Variance", value: `${o.planned_vs_actual_delta > 0 ? "+" : ""}${o.planned_vs_actual_delta}%`, sub: o.planned_vs_actual_delta >= 0 ? "Ahead of baseline" : "Behind planned finish", accent: o.planned_vs_actual_delta >= 0 ? "#1A7F37" : "#CF222E" },
          { label: "Completed", value: `${o.completed_activities} / ${o.total_activities}`, sub: "Activities finished", accent: "#0969DA" },
          { label: "In Progress", value: o.ongoing_activities, sub: "Active workfronts", accent: "#0969DA" },
          { label: "Delayed Activities", value: o.delayed_activities, sub: "Past planned finish date", accent: "#9A6700" },
          { label: "High Risk / Exceptions", value: o.high_risk_activities, sub: `${o.conflicts} conflicts · ${o.planner_reviews} reviews`, accent: "#CF222E" },
        ].map(({ label, value, sub, accent }) => (
          <div key={label} style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderTop: `3px solid ${accent}`, borderRadius: 10, padding: "14px 16px", boxShadow: "0 1px 3px rgba(31,35,40,0.05)" }}>
            <p style={{ margin: "0 0 6px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>{label}</p>
            <p style={{ margin: "0 0 4px", fontSize: 24, fontWeight: 700, color: "#1F2328", fontFamily: "ui-monospace, monospace" }}>{value}</p>
            <p style={{ margin: 0, fontSize: 11, color: "#656D76" }}>{sub}</p>
          </div>
        ))}
      </div>

      {/* Schedule Health Baseline Comparison */}
      <SectionCard title="Schedule Baseline vs. Actual Progress" description="Cross-discipline progress tracking based on multi-source verified evidence.">
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {[
            { label: "Actual Reconciled Progress", value: o.overall_progress, color: "#0D9488" },
            { label: "Planned Baseline Progress", value: o.planned_progress, color: "#1F2328" },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 12, fontWeight: 600, color: "#1F2328" }}>
                <span>{label}</span>
                <span style={{ fontFamily: "ui-monospace, monospace", color }}>{value}%</span>
              </div>
              <div className="progress-bar">
                <div className={`progress-bar-fill ${color === "#0D9488" ? "progress-bar-fill-teal" : "progress-bar-fill-dark"}`} style={{ width: `${Math.min(100, value)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {/* Discipline Progress Distribution */}
      <SectionCard title="Package Breakdown by Discipline" description="Calculated directly from active WBS activity states.">
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
          {disciplines.map((d) => (
            <div key={d.name} style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 13, color: "#1F2328" }}>{d.name}</span>
                <span style={{ fontSize: 12, fontWeight: 700, color: "#0D9488" }}>{d.avgProgress}%</span>
              </div>
              <p style={{ margin: "0 0 8px", fontSize: 11, color: "#656D76" }}>{d.completed} of {d.total} completed</p>
              <div className="progress-bar" style={{ height: 6 }}>
                <div className="progress-bar-fill progress-bar-fill-teal" style={{ width: `${d.avgProgress}%` }} />
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

// ─── ACTIVITY EXPLORER ────────────────────────────────────────────────────────
function Activities({ data, onSelectActivity }: { data: DashboardData; onSelectActivity: (act: any) => void }) {
  const [search, setSearch] = useState("");
  const [disciplineFilter, setDisciplineFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortCol, setSortCol] = useState<string>("external_activity_id");
  const [sortAsc, setSortAsc] = useState(true);

  const disciplines = useMemo(() => {
    const set = new Set(data.activities.map((a) => a.discipline).filter(Boolean));
    return ["all", ...Array.from(set)];
  }, [data.activities]);

  const filtered = useMemo(() => {
    return data.activities.filter((a) => {
      const q = search.toLowerCase().trim();
      const matchesSearch = !q || (
        a.external_activity_id.toLowerCase().includes(q) ||
        a.description.toLowerCase().includes(q) ||
        (a.location && a.location.toLowerCase().includes(q)) ||
        (a.discipline && a.discipline.toLowerCase().includes(q))
      );
      const matchesDisc = disciplineFilter === "all" || a.discipline === disciplineFilter;
      const matchesStatus = statusFilter === "all" || a.status === statusFilter || (statusFilter === "conflict" && a.evidence_status === "conflict");
      return matchesSearch && matchesDisc && matchesStatus;
    }).sort((a, b) => {
      let va = a[sortCol];
      let vb = b[sortCol];
      if (va == null) va = "";
      if (vb == null) vb = "";
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [data.activities, search, disciplineFilter, statusFilter, sortCol, sortAsc]);

  function handleSort(col: string) {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(true); }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      
      {/* Title & Controls */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Schedule Activity Explorer</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
            L5/L6 project activities. Click any row to inspect schedule timeline, linked evidence, and audit history.
          </p>
        </div>
        
        {/* Search Input */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 8, padding: "7px 12px", fontSize: 12, minWidth: 220, outline: "none" }}
            placeholder="Search activity, description, location…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 8, padding: "7px 12px", fontSize: 12, color: "#1F2328", outline: "none" }}
            value={disciplineFilter}
            onChange={(e) => setDisciplineFilter(e.target.value)}
          >
            <option value="all">All Disciplines</option>
            {disciplines.filter((d) => d !== "all").map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
          <select
            style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 8, padding: "7px 12px", fontSize: 12, color: "#1F2328", outline: "none" }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="in_progress">In Progress</option>
            <option value="completed">Completed</option>
            <option value="not_started">Not Started</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: "auto", background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 10, boxShadow: "0 1px 3px rgba(31,35,40,0.06)" }}>
        <table style={{ width: "100%", minWidth: 960, borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#F6F8FA", borderBottom: "1px solid #D0D7DE" }}>
              {[
                ["external_activity_id", "Activity ID"],
                ["level", "WBS"],
                ["discipline", "Discipline"],
                ["description", "Description"],
                ["planned_finish", "Planned Dates"],
                ["actual_end", "Actual Dates"],
                ["progress", "Reconciled Progress"],
                ["status", "Status"],
                ["confidence", "Reconciliation Conf."],
                ["evidence_status", "Evidence"],
              ].map(([key, label]) => (
                <th
                  key={key}
                  onClick={() => handleSort(key)}
                  style={{ padding: "10px 14px", textAlign: "left", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76", cursor: "pointer", userSelect: "none" }}
                >
                  {label} {sortCol === key ? (sortAsc ? "▲" : "▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody style={{ background: "#FFFFFF" }}>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={10} style={{ padding: 32, textAlign: "center", color: "#8C959F" }}>
                  No activities matching current filter.
                </td>
              </tr>
            ) : filtered.map((a) => (
              <tr key={a.activity_id}
                onClick={() => onSelectActivity(a)}
                style={{ borderBottom: "1px solid #EAEEF2", cursor: "pointer", transition: "background 0.1s" }}
                onMouseEnter={(e) => { e.currentTarget.style.background = "#F6F8FA"; }}
                onMouseLeave={(e) => { e.currentTarget.style.background = "#FFFFFF"; }}
                title="Click to view detailed activity timeline, evidence, and audit history"
              >
                <td style={{ padding: "10px 14px", fontFamily: "ui-monospace, monospace", fontWeight: 700, fontSize: 12, color: "#1F2328" }}>{a.external_activity_id}</td>
                <td style={{ padding: "10px 14px", fontSize: 12, fontWeight: 600, color: "#656D76" }}>L{a.level ?? 5}</td>
                <td style={{ padding: "10px 14px", fontSize: 12, color: "#656D76" }}>{a.discipline ?? "—"}</td>
                <td style={{ padding: "10px 14px", fontSize: 12, color: "#1F2328", maxWidth: 240 }}>{a.description}</td>
                <td style={{ padding: "10px 14px", fontSize: 11, color: "#656D76" }}>{fmtDate(a.planned_start)} → {fmtDate(a.planned_finish)}</td>
                <td style={{ padding: "10px 14px", fontSize: 11, color: "#656D76" }}>{fmtDate(a.actual_start)} → {fmtDate(a.actual_end)}</td>
                <td style={{ padding: "10px 14px", fontFamily: "ui-monospace, monospace", fontWeight: 700, fontSize: 12, color: "#1F2328" }}>{a.progress == null ? "—" : `${a.progress}%`}</td>
                <td style={{ padding: "10px 14px" }}><Badge value={a.status} /></td>
                <td style={{ padding: "10px 14px", fontFamily: "ui-monospace, monospace", fontSize: 12, color: "#656D76" }}>{a.confidence == null ? "—" : `${Math.round(a.confidence * 100)}%`}</td>
                <td style={{ padding: "10px 14px" }}><Badge value={a.evidence_status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ margin: 0, fontSize: 11, color: "#8C959F" }}>
        Showing {filtered.length} of {data.activities.length} activities in current schedule baseline.
      </p>
    </div>
  );
}

// ─── CONFLICT CENTER ──────────────────────────────────────────────────────────
function Conflicts({ data, onOpenReview }: { data: DashboardData; onOpenReview: () => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <span style={{ background: "#FFEBE9", border: "1px solid #FF9EA0", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#CF222E", textTransform: "uppercase" }}>
              Exception Management
            </span>
            <span style={{ fontSize: 12, color: "#656D76" }}>{data.conflicts.length} active discrepancy</span>
          </div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Conflict & Discrepancy Center</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
            Field report contradictions requiring planner verification before schedule baseline actuation.
          </p>
        </div>
        <button onClick={onOpenReview} style={{ background: "#1F2328", border: "none", borderRadius: 8, padding: "8px 16px", color: "#FFFFFF", fontSize: 12, fontWeight: 700, cursor: "pointer" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "#0D1117"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "#1F2328"; }}
        >Open in Planner Review Queue →</button>
      </div>

      {data.conflicts.length === 0 ? (
        <EmptyState title="No discrepancies detected" description="All reported evidence across field sources is currently consistent with schedule baselines." />
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {data.conflicts.map((c) => (
            <div key={c.conflict_id} className="card-flat" style={{ padding: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, paddingBottom: 10, borderBottom: "1px solid #EAEEF2" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <code style={{ background: "#1F2328", color: "#F0F6FC", borderRadius: 6, padding: "3px 8px", fontSize: 12, fontWeight: 700 }}>
                      {c.activity}
                    </code>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#9A6700" }}>{pretty(c.conflict_type)}</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: "#1F2328" }}>{c.sources}</p>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <Badge value={c.severity} />
                  <Badge value={c.resolution_status} />
                </div>
              </div>

              {/* Reported states breakdown */}
              <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 14, marginBottom: 12 }}>
                <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>
                  Multi-Source Variance Breakdown
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 8 }}>
                  <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#1F2328" }}>Contractor Daily Return</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, fontWeight: 600, color: "#0969DA" }}>80% · In Progress</p>
                    <span style={{ fontSize: 10, color: "#8C959F" }}>Reliability: 75% · 06 Sep 2026</span>
                  </div>
                  <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#1F2328" }}>Resident Engineer Site Diary</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, fontWeight: 600, color: "#9A6700" }}>55% · In Progress</p>
                    <span style={{ fontSize: 10, color: "#8C959F" }}>Reliability: 85% · 06 Sep 2026, 5:00 PM</span>
                  </div>
                  <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: 10 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#1F2328" }}>Daily Site Supervision Report</span>
                    <p style={{ margin: "4px 0 0", fontSize: 13, fontWeight: 600, color: "#1A7F37" }}>100% · Completed</p>
                    <span style={{ fontSize: 10, color: "#8C959F" }}>Reliability: 90% · 06 Sep 2026, 8:00 AM</span>
                  </div>
                </div>
              </div>

              {/* Action bar */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 12, color: "#656D76" }}>
                  <strong>Safety Recommendation: </strong>Planner verification required before schedule actuation.
                </span>
                <button onClick={onOpenReview} style={{ background: "none", border: "none", color: "#0D9488", fontSize: 12, fontWeight: 700, cursor: "pointer", textDecoration: "underline" }}>
                  Resolve in Review Queue →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── EVIDENCE VIEWER & PROGRESS CAPTURE ──────────────────────────────────────────
function Evidence({
  data,
  projectId,
  onRefresh,
  onNavigateToReconciliation,
}: {
  data: DashboardData;
  projectId: string;
  onRefresh?: () => void;
  onNavigateToReconciliation?: () => void;
}) {
  const [inputMode, setInputMode] = useState<"paste" | "upload">("paste");
  const [pastedText, setPastedText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState("daily_report");
  const [isProcessing, setIsProcessing] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [extractedEvents, setExtractedEvents] = useState<ExtractedEventItem[]>([]);
  const [canContinue, setCanContinue] = useState(false);

  async function handleExtractProgress() {
    setIsProcessing(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      if (inputMode === "paste") {
        if (!pastedText.trim()) {
          setErrorMessage("Please paste natural-language DPR or field report text.");
          setIsProcessing(false);
          return;
        }
        const result = await pasteDprReport(projectId, pastedText.trim(), "pasted_dpr_report.txt", sourceType, true);
        setExtractedEvents(result.extracted_events);
        setStatusMessage(`Successfully extracted ${result.extracted_events.length} structured event(s) from field report.`);
        setCanContinue(true);
      } else {
        if (!selectedFile) {
          setErrorMessage("Please select a file to upload (TXT, PDF, CSV, or XLSX).");
          setIsProcessing(false);
          return;
        }
        await uploadEvidenceFile(projectId, selectedFile, sourceType);
        setStatusMessage(`File uploaded and structured events extracted.`);
        setCanContinue(true);
      }
      if (onRefresh) onRefresh();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to process field report.");
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleContinueToMatching() {
    setIsProcessing(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const result = await continueToMatchingAndReconciliation(projectId);
      setStatusMessage(`Matched ${result.matched_count} observation(s) and reconciled ${result.reconciled_count} activity(ies).`);
      setCanContinue(false);
      if (onRefresh) onRefresh();
      if (onNavigateToReconciliation) onNavigateToReconciliation();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to complete matching and reconciliation.");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ─── CAPTURE PROGRESS SECTION ──────────────────────── */}
      <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: 22, boxShadow: "0 1px 3px rgba(31,35,40,0.06)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16, borderBottom: "1px solid #EAEEF2", paddingBottom: 12 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <span style={{ background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#0D4F4A", textTransform: "uppercase" }}>
                Field Ingestion
              </span>
              <span style={{ fontSize: 12, color: "#656D76" }}>CognitiveProgress Natural-Language Intake</span>
            </div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#1F2328" }}>Capture Progress</h3>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
              Ingest natural-language Daily Progress Reports (DPRs), supervisor notes, or field returns without rigid formatting.
            </p>
          </div>

          {/* Mode Switcher */}
          <div style={{ display: "flex", gap: 6 }}>
            <button
              onClick={() => setInputMode("paste")}
              style={{
                borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
                background: inputMode === "paste" ? "#1F2328" : "#FFFFFF",
                color: inputMode === "paste" ? "#FFFFFF" : "#656D76",
                borderColor: inputMode === "paste" ? "#1F2328" : "#D0D7DE",
              }}
            >
              Paste Field Report
            </button>
            <button
              onClick={() => setInputMode("upload")}
              style={{
                borderRadius: 8, padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
                background: inputMode === "upload" ? "#1F2328" : "#FFFFFF",
                color: inputMode === "upload" ? "#FFFFFF" : "#656D76",
                borderColor: inputMode === "upload" ? "#1F2328" : "#D0D7DE",
              }}
            >
              Upload File
            </button>
          </div>
        </div>

        {/* Source Type Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#1F2328" }}>Source Type:</label>
          <select
            value={sourceType}
            onChange={(e) => setSourceType(e.target.value)}
            style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: "5px 10px", fontSize: 12, color: "#1F2328" }}
          >
            <option value="daily_report">Daily Site Supervision Report</option>
            <option value="site_diary">Resident Engineer Site Diary</option>
            <option value="contractor_spreadsheet">Subcontractor Return (Spreadsheet / CSV)</option>
            <option value="discipline_spreadsheet">Discipline Progress Return</option>
          </select>
        </div>

        {inputMode === "paste" ? (
          <div>
            <textarea
              rows={4}
              placeholder="E.g. Piping crew completed erection of the 24-inch line in Unit 3 at approximately 4:30 PM. Hydrotest preparation has started."
              value={pastedText}
              onChange={(e) => setPastedText(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box", background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 8, padding: "10px 12px", fontSize: 13, color: "#1F2328", fontFamily: "inherit", outline: "none" }}
            />
            {/* Quick Natural-Language Field Report Presets */}
            <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, color: "#656D76", fontWeight: 600 }}>Quick Field Presets:</span>
              {[
                ["Line 24-XX erection started today.", "daily_report"],
                ["Valve installation finished yesterday.", "daily_report"],
                ["Hydrotest preparation started on September 10.", "daily_report"],
                ["Foundation excavation completed and rebar fixing started.", "daily_report"],
              ].map(([sample, sType], idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => {
                    setPastedText(sample);
                    setSourceType(sType);
                  }}
                  style={{
                    background: "#F6F8FA",
                    border: "1px solid #D0D7DE",
                    borderRadius: 6,
                    padding: "3px 8px",
                    fontSize: 11,
                    color: "#0969DA",
                    cursor: "pointer",
                    fontFamily: "inherit",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "#EAEEF2")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "#F6F8FA")}
                >
                  "{sample}"
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ background: "#F6F8FA", border: "1px dashed #D0D7DE", borderRadius: 8, padding: 20, textAlign: "center" }}>
            <input
              type="file"
              accept=".txt,.pdf,.csv,.xlsx"
              onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
              style={{ fontSize: 12 }}
            />
            <p style={{ margin: "8px 0 0", fontSize: 11, color: "#656D76" }}>
              Supported formats: TXT, text-based PDF, XLSX, CSV
            </p>
          </div>
        )}

        {/* Action Button */}
        <div style={{ marginTop: 14, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            {statusMessage && <span style={{ color: "#1A7F37", fontSize: 12, fontWeight: 600 }}>✓ {statusMessage}</span>}
            {errorMessage && <span style={{ color: "#CF222E", fontSize: 12, fontWeight: 600 }}>⚠ {errorMessage}</span>}
          </div>
          <button
            onClick={handleExtractProgress}
            disabled={isProcessing}
            style={{
              background: "#0D9488", border: "none", borderRadius: 8, padding: "8px 18px", color: "#FFFFFF", fontSize: 13, fontWeight: 700, cursor: isProcessing ? "not-allowed" : "pointer", opacity: isProcessing ? 0.7 : 1,
            }}
          >
            {isProcessing ? "Processing…" : "Extract Progress"}
          </button>
        </div>

        {/* Extracted Events Display */}
        {extractedEvents.length > 0 && (
          <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid #EAEEF2" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1F2328" }}>
                EXTRACTED EVENTS ({extractedEvents.length})
              </h4>
              <button
                onClick={handleContinueToMatching}
                disabled={isProcessing}
                style={{
                  background: "#1F2328", border: "none", borderRadius: 8, padding: "7px 16px", color: "#FFFFFF", fontSize: 12, fontWeight: 700, cursor: isProcessing ? "not-allowed" : "pointer",
                }}
              >
                Continue to Matching & Reconciliation →
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 10 }}>
              {extractedEvents.map((ev, idx) => (
                <div key={ev.observation_id || idx} style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 8, padding: 12 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                    <span style={{ fontSize: 13, fontWeight: 700, color: "#1F2328" }}>{ev.activity_description}</span>
                    <span style={{ background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 12, padding: "1px 6px", fontSize: 10, fontWeight: 700, color: "#0D4F4A" }}>
                      {Math.round(ev.confidence * 100)}% conf
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: "#656D76", display: "flex", flexDirection: "column", gap: 2 }}>
                    <div><strong>Discipline:</strong> {ev.discipline || "General"} · <strong>Location:</strong> {ev.location || "Site Wide"}{ev.contractor ? ` · Contractor: ${ev.contractor}` : ""}{ev.equipment_or_tag ? ` · Tag: ${ev.equipment_or_tag}` : ""}</div>
                    <div><strong>Status:</strong> <span style={{ textTransform: "capitalize", fontWeight: 600, color: "#1F2328" }}>{fmtStatus(ev.status)}</span>{ev.progress != null ? ` · ${ev.progress}%` : ""}{ev.actual_start ? ` · Start: ${ev.actual_start}` : ""}{ev.actual_end ? ` · Finish: ${ev.actual_end}` : ""}</div>
                    {ev.notes && <div><strong>Context:</strong> {ev.notes}</div>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ─── INGESTED FIELD EVIDENCE LIST ─────────────────── */}
      <div>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Evidence Ingestion & Document Viewer</h2>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
          Field documentation, subcontractor progress returns, and site diaries ingested into the reconciliation pipeline.
        </p>
      </div>

      {/* Unmatched / Discovered Activities Banner (SIH26122 Requirement B) */}
      {(() => {
        const unmatchedItems: Array<{ evidenceName: string; timestamp: string; obs: any }> = [];
        data.evidence.forEach((e) => {
          (e.interpretations || []).forEach((i: any) => {
            if (i.match_outcome === "no_match") {
              unmatchedItems.push({ evidenceName: e.source_name, timestamp: e.source_timestamp, obs: i });
            }
          });
        });
        if (unmatchedItems.length === 0) return null;
        return (
          <div style={{ background: "#F8FAFC", border: "1px solid #CBD5E1", borderRadius: 12, padding: 18, boxShadow: "0 1px 3px rgba(31,35,40,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ background: "#F1F5F9", border: "1px solid #94A3B8", borderRadius: 12, padding: "3px 10px", fontSize: 11, fontWeight: 700, color: "#334155" }}>
                  UNMATCHED FIELD EVIDENCE ({unmatchedItems.length})
                </span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>
                  Deterministic Safety Gate: Quarantined from Schedule Actuation
                </span>
              </div>
              <span style={{ background: "#ECFDF5", border: "1px solid #A7F3D0", color: "#065F46", borderRadius: 12, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>
                Preserved in Institutional Memory
              </span>
            </div>
            <p style={{ margin: "0 0 12px", fontSize: 12, color: "#475569", lineHeight: 1.5 }}>
              Field observations that cannot be safely linked to an existing L5/L6 baseline activity are <strong>never silently dropped</strong>.
              They are preserved with full provenance, timestamps, and raw text so planners can review them for potential scope addition or site service tracking.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {unmatchedItems.map((item, idx) => (
                <div key={idx} style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8, padding: 12, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, fontSize: 13, color: "#0F172A" }}>"{item.obs.activity}"</span>
                      <span style={{ background: "#F1F5F9", color: "#64748B", borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 600 }}>
                        {item.obs.discipline || "Site Services"} · {item.obs.location || "General"}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "#64748B" }}>
                      Source: <strong>{item.evidenceName}</strong> · Reported State: {fmtStatus(item.obs.status)} ({item.obs.progress ?? 0}%) · {fmtDateTime(item.timestamp)}
                    </div>
                  </div>
                  <span style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#991B1B", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 700 }}>
                    Unmatched / New Activity Candidate
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      })()}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(480px, 1fr))", gap: 16 }}>
        {data.evidence.map((e) => {
          const doc = getSourceDocInfo(e.source_name, e.source_type);
          return (
            <div key={e.evidence_id} className="card-flat" style={{ padding: 20 }}>
              
              {/* Document Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12, paddingBottom: 10, borderBottom: "1px solid #EAEEF2" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#1F2328" }}>{doc.title}</h3>
                  <p style={{ margin: "3px 0 0", fontSize: 11, color: "#656D76" }}>
                    {doc.subtitle} · Captured: {fmtDateTime(e.source_timestamp)}
                  </p>
                </div>
                <span className="badge badge-accent">{e.interpretations?.length || 0} observations</span>
              </div>

              {/* Extracted Observations */}
              <div>
                <p style={{ margin: "0 0 6px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                  Extracted Observations
                </p>
                {e.interpretations?.map((i: any) => (
                  <div key={i.observation_id} style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: "10px 12px", marginBottom: 8 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 700, fontSize: 13, color: "#1F2328" }}>{i.activity}</span>
                      <span style={{ background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 20, padding: "1px 8px", fontSize: 11, fontWeight: 700, color: "#0D4F4A" }}>
                        {Math.round((i.confidence || 0) * 100)}% extraction confidence
                      </span>
                    </div>
                    <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
                      Reported State: <strong style={{ color: "#1F2328" }}>{fmtStatus(i.status)}</strong>{i.progress != null ? ` · ${i.progress}%` : ""}
                    </p>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                      {i.match_outcome === "matched" && (
                        <span style={{ background: "#DCFCE7", border: "1px solid #86EFAC", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 700, color: "#166534" }}>
                          ✓ Linked to {i.matched_activity || "Schedule Baseline"} {i.best_score != null ? `(${Math.round(i.best_score * 100)}% match)` : ""}
                        </span>
                      )}
                      {i.match_outcome === "ambiguous" && (
                        <span style={{ background: "#FEF9C3", border: "1px solid #FDE047", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 700, color: "#854D0E" }}>
                          ⚠ Ambiguous Candidates ({i.candidates_count || 2} candidates) · Quarantined to Planner Review
                        </span>
                      )}
                      {i.match_outcome === "no_match" && (
                        <span style={{ background: "#F1F5F9", border: "1px solid #CBD5E1", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 700, color: "#475569" }}>
                          🔍 Unmatched / New Activity Candidate · Quarantined
                        </span>
                      )}
                      {i.discipline && (
                        <span style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 4, padding: "2px 6px", fontSize: 10, color: "#656D76" }}>
                          {i.discipline}
                        </span>
                      )}
                      {i.contractor && (
                        <span style={{ background: "#FEF3C7", borderRadius: 4, padding: "2px 6px", fontSize: 10, fontWeight: 600, color: "#92400E" }}>
                          {i.contractor}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Collapsible Raw Source */}
              {e.raw_text && (
                <details style={{ marginTop: 12 }}>
                  <summary style={{ fontSize: 11, fontWeight: 700, color: "#656D76", cursor: "pointer", userSelect: "none" }}>
                    View source record / raw document
                  </summary>
                  <pre style={{ marginTop: 8, background: "#1F2328", color: "#F0F6FC", borderRadius: 8, padding: 12, fontSize: 11, fontFamily: "ui-monospace, monospace", maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap" }}>
                    {e.raw_text}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── AUDIT TRAIL ──────────────────────────────────────────────────────────────
function Audit({ data, names }: { data: DashboardData; names: Map<string, string> }) {
  const [filterAction, setFilterAction] = useState("all");

  const filtered = useMemo(() => {
    if (filterAction === "all") return data.audit_trail;
    return data.audit_trail.filter((a) => a.action.toLowerCase().includes(filterAction));
  }, [data.audit_trail, filterAction]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#1F2328" }}>Enterprise Audit Trail</h2>
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>
            Immutable ledger of every automated reconciliation, discrepancy detection, planner decision, and schedule actuation.
          </p>
        </div>

        {/* Filter */}
        <div style={{ display: "flex", gap: 6 }}>
          {[
            ["all", "All Events"],
            ["update", "Schedule Updates"],
            ["review", "Planner Reviews"],
            ["reconciliation", "Reconciliations"],
          ].map(([key, label]) => (
            <button key={key} onClick={() => setFilterAction(key)}
              style={{ borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", border: "1px solid",
                background: filterAction === key ? "#1F2328" : "#FFFFFF", color: filterAction === key ? "#FFFFFF" : "#656D76", borderColor: filterAction === key ? "#1F2328" : "#D0D7DE" }}
            >{label}</button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map((a, index) => {
          const actCode = names.get(a.entity_id);
          return (
            <div key={a.audit_id || index} className="card-flat" style={{ padding: 16 }}>
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", marginBottom: 8, paddingBottom: 8, borderBottom: "1px solid #EAEEF2", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Badge value={a.action} />
                  <span style={{ fontSize: 12, fontWeight: 700, color: "#1F2328" }}>
                    Audit Event #EV-{String(a.audit_id).slice(0, 6).toUpperCase()}
                  </span>
                  {actCode && (
                    <span style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 4, padding: "2px 6px", fontSize: 11, fontWeight: 700, color: "#656D76" }}>
                      Activity: {actCode}
                    </span>
                  )}
                </div>
                <span style={{ fontSize: 11, color: "#8C959F" }}>
                  {fmtDateTime(a.created_at)} · Actor: <strong>{a.actor}</strong>
                </span>
              </div>
              
              {a.explanation && (
                <p style={{ margin: "0 0 10px", fontSize: 12, color: "#1F2328", lineHeight: 1.6 }}>{a.explanation}</p>
              )}

              {/* Formatted State Before vs After */}
              {(a.before_value || a.after_value) && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
                  <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 10 }}>
                    <p style={{ margin: "0 0 4px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>State Before</p>
                    {a.before_value ? (
                      <div style={{ fontSize: 11, color: "#1F2328" }}>
                        {Object.entries(a.before_value).map(([k, v]) => (
                          <div key={k} style={{ marginBottom: 2 }}><strong>{pretty(k)}:</strong> {pretty(v)}</div>
                        ))}
                      </div>
                    ) : <span style={{ fontSize: 11, color: "#8C959F" }}>Baseline initiation</span>}
                  </div>
                  <div style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 8, padding: 10 }}>
                    <p style={{ margin: "0 0 4px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#0D4F4A" }}>State After</p>
                    {a.after_value ? (
                      <div style={{ fontSize: 11, color: "#0D4F4A" }}>
                        {Object.entries(a.after_value).map(([k, v]) => (
                          <div key={k} style={{ marginBottom: 2 }}><strong>{pretty(k)}:</strong> {pretty(v)}</div>
                        ))}
                      </div>
                    ) : <span style={{ fontSize: 11, color: "#8C959F" }}>No change</span>}
                  </div>
                </div>
              )}

              {/* Collapsible Technical Details */}
              <details style={{ marginTop: 6 }}>
                <summary style={{ fontSize: 10, fontWeight: 700, color: "#8C959F", cursor: "pointer", userSelect: "none" }}>
                  View technical audit details (JSON payload)
                </summary>
                <pre style={{ marginTop: 6, background: "#1F2328", color: "#F0F6FC", borderRadius: 6, padding: 8, fontSize: 10, fontFamily: "ui-monospace, monospace", overflow: "auto", maxHeight: 120 }}>
                  {JSON.stringify({ entity_type: a.entity_type, entity_id: a.entity_id, before: a.before_value, after: a.after_value }, null, 2)}
                </pre>
              </details>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── PLANNER REVIEWS WRAPPER ──────────────────────────────────────────────────
function PlannerReviews({ reviews, projectId, initialReviewId, onAction }: { reviews: PlannerReviewContext[]; projectId: string; initialReviewId?: string; onAction: () => void }) {
  return (
    <PlannerReviewPage initialProjectId={projectId} initialReviewId={initialReviewId} onAction={onAction} />
  );
}

// ─── EXECUTION CONTEXT PANEL (PHASE 3) ─────────────────────────────────────────
function ExecutionContextSection({
  projectId,
  activityId,
  data,
  onNavigateActivity,
}: {
  projectId: string;
  activityId: string;
  data: DashboardData;
  onNavigateActivity: (act: any) => void;
}) {
  const [context, setContext] = useState<ExecutionContextResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchExecutionContext(projectId, activityId)
      .then((res) => {
        if (!cancelled) {
          setContext(res);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || "Failed to load execution context.");
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, activityId]);

  if (loading) {
    return (
      <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 14, marginBottom: 16 }}>
        <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#656D76" }}>
          Execution Evidence Graph
        </span>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: "#8C959F" }}>Loading immediate execution context & field evidence...</p>
      </div>
    );
  }

  if (error || !context) {
    return null;
  }

  return (
    <div style={{ background: "#F8FAFC", border: "1px solid #CBD5E1", borderRadius: 8, padding: 16, marginBottom: 16 }}>
      {/* Title */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, borderBottom: "1px solid #E2E8F0", paddingBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#0284C7" }} />
          <span style={{ fontSize: 12, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.5, color: "#0F172A" }}>
            Execution Context & Evidence Graph
          </span>
        </div>
        <span style={{ fontSize: 11, color: "#64748B", fontWeight: 600 }}>
          {context.execution_events.length} Linked Event{context.execution_events.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Dependencies Context (Predecessors / Successors) */}
      <div style={{ marginBottom: 14 }}>
        <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#64748B", marginBottom: 6 }}>
          Schedule Dependencies (Execution Order)
        </span>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          {/* Predecessors */}
          <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: "8px 10px" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#475569", display: "block", marginBottom: 4 }}>
              ← Predecessors ({context.predecessors.length})
            </span>
            {context.predecessors.length === 0 ? (
              <span style={{ fontSize: 11, color: "#94A3B8" }}>No predecessor constraints (root activity)</span>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {context.predecessors.map((p) => {
                  const targetAct = data.activities.find((a) => a.activity_id === p.activity_id);
                  return (
                    <div
                      key={p.dependency_id}
                      onClick={() => targetAct && onNavigateActivity(targetAct)}
                      style={{
                        fontSize: 11,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        background: "#F1F5F9",
                        padding: "4px 8px",
                        borderRadius: 4,
                        cursor: targetAct ? "pointer" : "default",
                      }}
                      title={targetAct ? "Click to inspect predecessor execution context" : undefined}
                    >
                      <span style={{ fontWeight: 600, color: "#0F172A" }}>
                        {p.external_activity_id} · <span style={{ fontWeight: 400, color: "#475569" }}>{p.description}</span>
                      </span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: p.status === "completed" ? "#15803D" : "#B45309" }}>
                        {p.status.toUpperCase()}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Successors */}
          <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: "8px 10px" }}>
            <span style={{ fontSize: 10, fontWeight: 700, color: "#475569", display: "block", marginBottom: 4 }}>
              → Successors ({context.successors.length})
            </span>
            {context.successors.length === 0 ? (
              <span style={{ fontSize: 11, color: "#94A3B8" }}>No successor dependencies</span>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {context.successors.map((s) => {
                  const targetAct = data.activities.find((a) => a.activity_id === s.activity_id);
                  return (
                    <div
                      key={s.dependency_id}
                      onClick={() => targetAct && onNavigateActivity(targetAct)}
                      style={{
                        fontSize: 11,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        background: "#F1F5F9",
                        padding: "4px 8px",
                        borderRadius: 4,
                        cursor: targetAct ? "pointer" : "default",
                      }}
                      title={targetAct ? "Click to inspect successor execution context" : undefined}
                    >
                      <span style={{ fontWeight: 600, color: "#0F172A" }}>
                        {s.external_activity_id} · <span style={{ fontWeight: 400, color: "#475569" }}>{s.description}</span>
                      </span>
                      <span style={{ fontSize: 10, fontWeight: 700, color: s.status === "completed" ? "#15803D" : "#B45309" }}>
                        {s.status.toUpperCase()}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Field Execution Events */}
      <div style={{ marginBottom: 14 }}>
        <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#64748B", marginBottom: 6 }}>
          Field Execution Events & Evidence
        </span>
        {context.execution_events.length === 0 ? (
          <p style={{ margin: 0, fontSize: 11, color: "#94A3B8", fontStyle: "italic" }}>
            No field evidence or execution events matched to this activity.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {context.execution_events.map((ev) => (
              <div
                key={ev.event_id}
                style={{
                  background: "#FFFFFF",
                  border: `1px solid ${ev.is_conflicting ? "#FCA5A5" : ev.match_outcome === "ambiguous" ? "#FDE047" : "#E2E8F0"}`,
                  borderRadius: 6,
                  padding: 10,
                }}
              >
                {/* Event header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#0F172A" }}>
                      {fmtDate(ev.source_timestamp)}
                    </span>
                    {ev.discipline && (
                      <span style={{ background: "#E0F2FE", color: "#0369A1", borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 600 }}>
                        {ev.discipline}
                      </span>
                    )}
                    {ev.location && (
                      <span style={{ background: "#F1F5F9", color: "#475569", borderRadius: 4, padding: "1px 6px", fontSize: 10 }}>
                        {ev.location}
                      </span>
                    )}
                    {ev.contractor && (
                      <span style={{ background: "#FEF3C7", color: "#92400E", borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 600 }}>
                        Contractor: {ev.contractor}
                      </span>
                    )}
                  </div>
                  <div style={{ display: "flex", gap: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, background: "#F1F5F9", color: "#334155", borderRadius: 4, padding: "2px 6px" }}>
                      Match: {ev.match_score != null ? `${Math.round(ev.match_score * 100)}%` : "—"}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 700,
                        borderRadius: 4,
                        padding: "2px 6px",
                        background: ev.reconciliation_decision === "auto_accept" ? "#DCFCE7" : ev.is_conflicting ? "#FEE2E2" : "#FEF9C3",
                        color: ev.reconciliation_decision === "auto_accept" ? "#166534" : ev.is_conflicting ? "#991B1B" : "#854D0E",
                      }}
                    >
                      {ev.reconciliation_decision === "auto_accept" ? "VERIFIED" : ev.is_conflicting ? "CONFLICT" : "REVIEW"}
                    </span>
                  </div>
                </div>

                {/* Field description vs Plan activity */}
                <div style={{ fontSize: 12, color: "#1E293B", fontWeight: 600, marginBottom: 4 }}>
                  "{ev.field_description}"
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10, color: "#64748B" }}>
                  <span>
                    Evidence: <strong>{ev.source_name}</strong> ({pretty(ev.source_type)})
                  </span>
                  <span>
                    Reported State: <strong>{fmtStatus(ev.status)}</strong> {ev.progress != null ? `(${ev.progress}%)` : ""}
                  </span>
                </div>

                {/* Multiple Candidates Notice */}
                {ev.candidates.length > 1 && (
                  <div style={{ marginTop: 8, background: "#FFFBEB", border: "1px solid #FCD34D", borderRadius: 4, padding: "6px 8px" }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: "#92400E", display: "block", marginBottom: 4 }}>
                      ⚠ Candidate Matches ({ev.candidates.length}):
                    </span>
                    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      {ev.candidates.map((cand) => (
                        <div key={cand.activity_id} style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#78350F" }}>
                          <span>
                            <strong>{cand.external_activity_id}:</strong> {cand.description}
                          </span>
                          <span>{Math.round(cand.final_score * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Execution Provenance Trace */}
      {context.provenance.length > 0 && (
        <div style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 6, padding: 10 }}>
          <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#475569", marginBottom: 6 }}>
            Deterministic Provenance Trace (Actual Dates & Scope)
          </span>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {context.provenance.map((prov, i) => (
              <div key={i} style={{ fontSize: 11, color: "#334155", background: "#F8FAFC", padding: "6px 8px", borderRadius: 4, borderLeft: "3px solid #0284C7" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                  <span style={{ fontWeight: 700, color: "#0F172A" }}>
                    {pretty(prov.field).toUpperCase()}: {prov.value}
                  </span>
                  <span style={{ fontSize: 10, color: "#64748B" }}>
                    Source: {prov.source_name}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 11, color: "#475569" }}>{prov.rationale}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── ACTIVITY DETAILS MODAL ───────────────────────────────────────────────────
function ActivityDetailsModal({
  activity,
  data,
  projectId,
  onClose,
  onOpenReview,
  onSelectActivity,
}: {
  activity: any;
  data: DashboardData;
  projectId: string;
  onClose: () => void;
  onOpenReview: (revId?: string) => void;
  onSelectActivity: (act: any) => void;
}) {
  const rec = data.reconciliations.find((r) => r.activity_id === activity.activity_id);
  const conflicts = data.conflicts.filter((c) => c.activity_id === activity.activity_id);
  const auditEvents = data.audit_trail.filter((a) => a.entity_id === activity.activity_id);

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#FFFFFF", borderRadius: 12, maxWidth: 760, width: "100%", maxHeight: "90vh", overflowY: "auto", padding: 24, boxShadow: "0 10px 30px rgba(0,0,0,0.25)" }}>
        
        {/* Modal Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid #EAEEF2", paddingBottom: 16, marginBottom: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <code style={{ background: "#1F2328", color: "#F0F6FC", borderRadius: 6, padding: "3px 8px", fontSize: 13, fontWeight: 700 }}>
                {activity.external_activity_id}
              </code>
              <Badge value={activity.status} />
              <span style={{ fontSize: 12, color: "#656D76" }}>WBS Level {activity.level ?? 5} · {activity.discipline}</span>
            </div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#1F2328" }}>{activity.description}</h3>
            {activity.location && <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>Location: {activity.location}</p>}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "#656D76" }}>✕</button>
        </div>

        {/* Schedule Dates & Progress */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: 12, marginBottom: 16 }}>
          <div>
            <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>Planned Finish</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#1F2328" }}>{fmtDate(activity.planned_finish)}</span>
          </div>
          <div>
            <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>Actual End</span>
            <span style={{ fontSize: 12, fontWeight: 600, color: "#1F2328" }}>{fmtDate(activity.actual_end)}</span>
          </div>
          <div>
            <span style={{ display: "block", fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>Reconciled Progress</span>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#0D9488" }}>{activity.progress == null ? "—" : `${activity.progress}%`}</span>
          </div>
        </div>

        {/* Phase 3 Execution Evidence Graph Panel */}
        <ExecutionContextSection
          projectId={projectId}
          activityId={activity.activity_id}
          data={data}
          onNavigateActivity={onSelectActivity}
        />

        {/* Reconciliation Synthesis */}
        {rec && (
          <div style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 8, padding: 14, marginBottom: 16 }}>
            <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#0D4F4A" }}>Reconciliation Rationale ({Math.round(rec.confidence * 100)}% confidence)</span>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#1F2328", lineHeight: 1.6 }}>{rec.explanation}</p>
          </div>
        )}

        {/* Schedule Validation */}
        <div style={{ marginBottom: 16 }}>
          <ScheduleValidationSection rec={rec} activity={activity} onOpenReview={() => { onClose(); onOpenReview(); }} />
        </div>

        {/* Active Conflicts */}
        {conflicts.length > 0 && (
          <div style={{ background: "#FFF8C5", border: "1px solid #EAC54F", borderRadius: 8, padding: 14, marginBottom: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#9A6700" }}>⚠ Discrepancy Active</span>
              <button onClick={() => { onClose(); onOpenReview(); }} style={{ background: "#9A6700", border: "none", borderRadius: 6, padding: "4px 10px", color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer" }}>
                Review in Queue →
              </button>
            </div>
            {conflicts.map((c) => (
              <p key={c.conflict_id} style={{ margin: "6px 0 0", fontSize: 12, color: "#7A5300" }}>{c.sources}</p>
            ))}
          </div>
        )}

        {/* Audit Trail for this activity */}
        {auditEvents.length > 0 && (
          <div>
            <p style={{ margin: "0 0 8px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8C959F" }}>Activity Audit Events ({auditEvents.length})</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {auditEvents.map((a, i) => (
                <div key={a.audit_id || i} style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 6, padding: "8px 10px", fontSize: 11 }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong>{pretty(a.action)}</strong>
                    <span style={{ color: "#8C959F" }}>{fmtDateTime(a.created_at)} · {a.actor}</span>
                  </div>
                  {a.explanation && <p style={{ margin: "4px 0 0", color: "#656D76" }}>{a.explanation}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginTop: 20, textAlign: "right" }}>
          <button onClick={onClose} style={{ background: "#1F2328", color: "#FFFFFF", border: "none", borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── SYSTEM METHODOLOGY MODAL ─────────────────────────────────────────────────
function MethodologyModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15, 23, 42, 0.6)", zIndex: 100, display: "flex", alignItems: "center", justifyContent: "center", padding: 20 }}>
      <div style={{ background: "#FFFFFF", borderRadius: 12, maxWidth: 740, width: "100%", maxHeight: "90vh", overflowY: "auto", padding: 28, boxShadow: "0 10px 30px rgba(0,0,0,0.25)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #EAEEF2", paddingBottom: 14, marginBottom: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#1F2328" }}>System Methodology & Architecture</h3>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "#656D76" }}>CognitiveProgress multi-source evidence reconciliation process</p>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", fontSize: 18, cursor: "pointer", color: "#656D76" }}>✕</button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14, fontSize: 13, color: "#1F2328", lineHeight: 1.6 }}>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>1. Multi-Source Evidence Ingestion</h4>
            <p style={{ margin: 0 }}>Captures daily site diaries, contractor returns, supervisor logs, and inspection sheets without imposing rigid templates on field staff.</p>
          </div>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>2. Semantic WBS Schedule Matching</h4>
            <p style={{ margin: 0 }}>Uses domain-tuned embeddings to map unstructured observations to standard Level 5/6 activities in Primavera P6 or MS Project.</p>
          </div>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>3. Discrepancy & Conflict Detection</h4>
            <p style={{ margin: 0 }}>Identifies contradictions in progress and completion status between different contractors and inspection agents on the same workfront.</p>
          </div>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>4. Reliability & Freshness Weighted Synthesis</h4>
            <p style={{ margin: 0 }}>Applies historical reliability scores and temporal freshness decay to synthesize a justified target progress percentage with quantifiable confidence.</p>
          </div>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>5. Safety Gate & Planner Review</h4>
            <p style={{ margin: 0 }}>Decisions exceeding 0.70 confidence threshold with consistent evidence auto-actuate to the schedule baseline. Conflicting claims are escalated to the planner review queue.</p>
          </div>
          <div>
            <h4 style={{ margin: "0 0 4px", fontSize: 14, color: "#0D9488" }}>6. Immutable Audit Trail</h4>
            <p style={{ margin: 0 }}>Every extraction, state transformation, and planner override is permanently recorded with full before-and-after diffs for audit compliance.</p>
          </div>
        </div>

        <div style={{ marginTop: 24, textAlign: "right", borderTop: "1px solid #EAEEF2", paddingTop: 14 }}>
          <button onClick={onClose} style={{ background: "#1F2328", color: "#FFFFFF", border: "none", borderRadius: 6, padding: "8px 18px", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── SCHEDULE VALIDATION SECTION ──────────────────────────────────────────────
function ScheduleValidationSection({
  rec,
  activity,
  onOpenReview,
}: {
  rec?: any;
  activity?: any;
  onOpenReview?: () => void;
}) {
  const status: string = rec?.dependency_status || "VALID";
  const details: any[] = rec?.dependency_details || [];
  const conflicts = details.filter((d) => d.status === "CONFLICT");
  const warnings = details.filter((d) => d.status === "WARNING");

  const isConflict = status === "CONFLICT";
  const isWarning = status === "WARNING";
  const isUnknown = status === "UNKNOWN";

  return (
    <div
      style={{
        background: isConflict ? "#FFEBE9" : isWarning ? "#FFF8C5" : "#F6F8FA",
        border: `1px solid ${isConflict ? "#FF8182" : isWarning ? "#EAC54F" : "#D0D7DE"}`,
        borderRadius: 8,
        padding: "12px 14px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            textTransform: "uppercase",
            letterSpacing: 0.5,
            color: isConflict ? "#CF222E" : isWarning ? "#9A6700" : "#1A7F37",
          }}
        >
          Schedule Validation
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 700,
            color: isConflict ? "#CF222E" : isWarning ? "#9A6700" : isUnknown ? "#656D76" : "#1A7F37",
          }}
        >
          {status === "VALID" && "✓ Dependency sequence consistent"}
          {isWarning && "⚠ Dependency warning"}
          {isConflict && "✕ Dependency conflict"}
          {isUnknown && "ℹ Dependency status unknown (dates unavailable)"}
        </span>
      </div>

      {conflicts.map((conf, idx) => (
        <div
          key={idx}
          style={{
            marginTop: 10,
            paddingTop: 10,
            borderTop: "1px dashed rgba(207, 34, 46, 0.3)",
            fontSize: 12,
            color: "#1F2328",
          }}
        >
          <div style={{ fontWeight: 700, color: "#1F2328", marginBottom: 6 }}>
            {conf.successor_activity_name || activity?.description || "Activity"} ({conf.successor_activity_id || activity?.external_activity_id})
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11, color: "#57606A", marginBottom: 6, background: "#FFFFFF", padding: 8, borderRadius: 6, border: "1px solid #FFCECB" }}>
            <div>
              <span style={{ color: "#8C959F", display: "block" }}>Predecessor:</span>
              <strong>{conf.predecessor_activity_name || "Predecessor"} ({conf.predecessor_activity_id})</strong>
            </div>
            <div>
              <span style={{ color: "#8C959F", display: "block" }}>Result:</span>
              <span style={{ color: "#CF222E", fontWeight: 700 }}>CONFLICT</span>
            </div>
            <div>
              <span style={{ color: "#8C959F", display: "block" }}>Reported start:</span>
              <strong>{conf.relevant_actual_start || "—"}</strong>
            </div>
            <div>
              <span style={{ color: "#8C959F", display: "block" }}>Predecessor completion:</span>
              <strong>{conf.relevant_actual_end || "—"}</strong>
            </div>
          </div>
          <p style={{ margin: "4px 0 8px", fontSize: 11, color: "#82071E", fontStyle: "italic" }}>
            {conf.reason}
          </p>
          {onOpenReview && (
            <button
              onClick={onOpenReview}
              style={{
                background: "#CF222E",
                color: "#FFFFFF",
                border: "none",
                borderRadius: 6,
                padding: "5px 12px",
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Send to Planner Review →
            </button>
          )}
        </div>
      ))}

      {isWarning && warnings.map((warn, idx) => (
        <div key={idx} style={{ marginTop: 6, fontSize: 11, color: "#7A5300" }}>
          <strong>Predecessor {warn.predecessor_activity_id}:</strong> {warn.reason}
        </div>
      ))}

      {isUnknown && details.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 11, color: "#656D76" }}>
          {details[0].reason || "Dependency exists, but required actual dates are unavailable."}
        </div>
      )}
    </div>
  );
}

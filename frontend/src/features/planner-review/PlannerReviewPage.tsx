import { useEffect, useState } from "react";
import { actOnPlannerReview, fetchPlannerReviews, type PlannerReviewContext } from "../../services/api";

const pretty = (v: unknown) => String(v ?? "—").replaceAll("_", " ");
const fmt = (v: unknown) => v ? new Date(String(v)).toLocaleDateString("en-GB") : "—";

export function PlannerReviewPage({
  initialProjectId,
  initialReviewId,
  onAction,
}: {
  initialProjectId?: string;
  initialReviewId?: string;
  onAction?: () => void;
} = {}) {
  const [projectId, setProjectId] = useState(initialProjectId || "26122000-0000-0000-0000-000000000001");
  const [reviews, setReviews] = useState<PlannerReviewContext[]>([]);
  const [selected, setSelected] = useState<PlannerReviewContext | null>(null);
  const [reviewer, setReviewer] = useState("Lead Planner (Piping & Civil)");
  const [comment, setComment] = useState("");
  const [progressOverride, setProgressOverride] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  async function load(targetId?: string, preferredId?: string) {
    const id = (targetId ?? projectId).trim();
    if (!id) return;
    try {
      const loaded = await fetchPlannerReviews(id);
      setReviews(loaded);
      const pref = preferredId ? loaded.find((r) => r.review_id === preferredId) : null;
      const keep = selected ? loaded.find((r) => r.review_id === selected.review_id) : null;
      setSelected(pref ?? keep ?? loaded[0] ?? null);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to load reviews.");
    }
  }

  useEffect(() => {
    if (initialProjectId && initialProjectId !== projectId) setProjectId(initialProjectId);
  }, [initialProjectId]);

  useEffect(() => {
    if (projectId.trim()) load(projectId.trim(), initialReviewId);
  }, [projectId, initialReviewId]);

  async function act(action: "approve" | "reject" | "modify" | "select_activity" | "comment", selectedActivityId?: string) {
    if (!selected || !reviewer.trim()) { setError("Enter the reviewer name."); return; }
    setError(null); setSuccessMsg(null);
    try {
      const updated = await actOnPlannerReview(projectId, selected.review_id, {
        action, reviewer: reviewer.trim(),
        comment: comment.trim() || null,
        progress: progressOverride.trim() ? Number(progressOverride.trim()) : null,
        selected_activity_id: selectedActivityId ?? null,
      });
      setSelected(updated);
      setReviews((items) => items.map((r) => (r.review_id === updated.review_id ? updated : r)));
      setSuccessMsg(`Decision "${action.toUpperCase()}" recorded. Schedule actuation applied.`);
      onAction?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Planner action failed.");
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%", background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 8,
    padding: "8px 12px", fontSize: 13, color: "#1F2328", outline: "none", boxSizing: "border-box",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>

      {/* ── Header ── */}
      <div style={{ background: "#0D1117", border: "1px solid #30363D", borderRadius: 12, padding: "20px 24px", color: "#F0F6FC" }}>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
          <div>
            <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
              <span style={{ background: "rgba(13,148,136,0.15)", border: "1px solid rgba(13,148,136,0.4)", borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, color: "#2DD4BF" }}>
                Schedule Update Controls
              </span>
              <span style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.4)", borderRadius: 20, padding: "3px 10px", fontSize: 11, fontWeight: 600, color: "#A5B4FC" }}>
                Authorized Review
              </span>
            </div>
            <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, color: "#F0F6FC" }}>Planner Review Queue</h2>
            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#8B949E", lineHeight: 1.5, maxWidth: 600 }}>
              Operational exceptions requiring human verification before schedule baseline actuation.
            </p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ background: "#21262D", border: "1px solid #30363D", borderRadius: 8, padding: "8px 16px", display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: reviews.filter((r) => r.reviewer_decision === "pending").length > 0 ? "#F0A30A" : "#1A7F37", display: "inline-block" }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "#F0F6FC" }}>
                {reviews.filter((r) => r.reviewer_decision === "pending").length} Pending Decisions
              </span>
            </div>
            <button
              onClick={() => load(projectId)}
              style={{ background: "#21262D", border: "1px solid #30363D", borderRadius: 8, padding: "8px 14px", color: "#F0F6FC", fontSize: 12, fontWeight: 600, cursor: "pointer" }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "#30363D")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "#21262D")}
            >
              Refresh Queue
            </button>
          </div>
        </div>
      </div>

      {/* ── Error / Success ── */}
      {error && (
        <div style={{ background: "#FFEBE9", border: "1px solid #FF9EA0", borderRadius: 8, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ color: "#CF222E", fontSize: 13, fontWeight: 600 }}>{error}</span>
          <button onClick={() => setError(null)} style={{ background: "none", border: "none", color: "#CF222E", cursor: "pointer", fontWeight: 700 }}>✕</button>
        </div>
      )}
      {successMsg && (
        <div style={{ background: "#DAFBE1", border: "1px solid #82E9A6", borderRadius: 8, padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ color: "#1A7F37", fontSize: 13, fontWeight: 600 }}>✓ {successMsg}</span>
          <button onClick={() => setSuccessMsg(null)} style={{ background: "none", border: "none", color: "#1A7F37", cursor: "pointer", fontWeight: 700 }}>✕</button>
        </div>
      )}

      {/* ── Content Area: Empty State vs Split Layout ── */}
      {reviews.length === 0 ? (
        <div style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: "48px 32px", textAlign: "center", boxShadow: "0 1px 3px rgba(31,35,40,0.05)" }}>
          <div style={{ width: 48, height: 48, borderRadius: "50%", background: "#DAFBE1", border: "2px solid #82E9A6", color: "#1A7F37", display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", fontSize: 24, fontWeight: 700 }}>
            ✓
          </div>
          <h3 style={{ margin: "0 0 8px", fontSize: 18, fontWeight: 700, color: "#1F2328" }}>
            No Pending Planner Decisions
          </h3>
          <p style={{ margin: "0 auto 24px", fontSize: 13, color: "#656D76", maxWidth: 540, lineHeight: 1.6 }}>
            All field observations and reported discrepancies for the active project have been reconciled.
            No manual planner intervention is currently required.
          </p>

          {/* Operational summary cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 16, maxWidth: 840, margin: "0 auto 28px", textAlign: "left" }}>
            <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 10, padding: "14px 16px" }}>
              <span style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8C959F", marginBottom: 4 }}>Baseline Status</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#1A7F37" }}>Synchronized & Current</span>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>Schedule updates applied via automated safety thresholds.</p>
            </div>
            <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 10, padding: "14px 16px" }}>
              <span style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8C959F", marginBottom: 4 }}>Safety Verification</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#0969DA" }}>Active Gate (0.70 Confidence)</span>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>Discrepancies exceeding variance tolerance are automatically routed here.</p>
            </div>
            <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 10, padding: "14px 16px" }}>
              <span style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: "#8C959F", marginBottom: 4 }}>Evidence Monitoring</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: "#1F2328" }}>Continuous Ingestion</span>
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "#656D76" }}>Listening for new daily reports, contractor returns, and site diaries.</p>
            </div>
          </div>

          <button
            onClick={() => load(projectId)}
            style={{ background: "#1F2328", border: "none", borderRadius: 8, padding: "10px 20px", color: "#FFFFFF", fontSize: 13, fontWeight: 600, cursor: "pointer" }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#0D1117")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#1F2328")}
          >
            Re-check Queue Status
          </button>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 20, alignItems: "start" }}>

          {/* Left: Queue items */}
          <section>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                Review Queue ({reviews.length})
              </span>
              <span style={{ fontSize: 11, color: "#656D76" }}>
                {reviews.filter((r) => r.reviewer_decision === "pending").length} action required
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {reviews.map((rev) => {
                const isSelected = selected?.review_id === rev.review_id;
                const isPending = rev.reviewer_decision === "pending";
                return (
                  <button
                    key={rev.review_id}
                    onClick={() => { setSelected(rev); setError(null); setSuccessMsg(null); }}
                    style={{
                      width: "100%", textAlign: "left", borderRadius: 10, padding: 14, cursor: "pointer",
                      background: "#FFFFFF",
                      border: `1px solid ${isSelected ? "#0D9488" : "#D0D7DE"}`,
                      boxShadow: isSelected ? "0 0 0 2px rgba(13,148,136,0.2)" : "0 1px 3px rgba(31,35,40,0.04)",
                      transition: "all 0.15s",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontFamily: "ui-monospace, monospace", fontWeight: 700, fontSize: 13, color: "#1F2328" }}>
                        {rev.current_activity.external_activity_id}
                      </span>
                      <span style={{
                        borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 700,
                        background: isPending ? "#FFF8C5" : "#DAFBE1",
                        color: isPending ? "#9A6700" : "#1A7F37",
                        border: `1px solid ${isPending ? "#EAC54F" : "#82E9A6"}`,
                      }}>
                        {pretty(rev.reviewer_decision)}
                      </span>
                    </div>
                    <p style={{ margin: "0 0 8px", fontSize: 12, color: "#656D76", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {rev.current_activity.description}
                    </p>
                    <div style={{ display: "flex", justifyContent: "space-between", paddingTop: 8, borderTop: "1px solid #EAEEF2", fontSize: 11, color: "#8C959F" }}>
                      <span>Reconciled: <strong style={{ color: "#1F2328" }}>{pretty(rev.proposed_reconciliation.reconciled_status)}{rev.proposed_reconciliation.reconciled_progress != null ? ` (${rev.proposed_reconciliation.reconciled_progress}%)` : ""}</strong></span>
                      <span style={{ fontFamily: "ui-monospace, monospace", fontWeight: 700, color: "#0D9488" }}>{Math.round(rev.proposed_reconciliation.confidence * 100)}% conf</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          {/* Right: Selected item workspace */}
          {selected ? (
            <section style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 12, padding: 24, display: "flex", flexDirection: "column", gap: 20, boxShadow: "0 1px 3px rgba(31,35,40,0.05)" }}>

              {/* Activity Header */}
              <div style={{ borderBottom: "1px solid #EAEEF2", paddingBottom: 16 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
                  <code style={{ background: "#1F2328", color: "#F0F6FC", borderRadius: 6, padding: "3px 8px", fontSize: 12, fontWeight: 700 }}>
                    {selected.current_activity.external_activity_id}
                  </code>
                  <span style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 600, color: "#656D76" }}>
                    Schedule Exception Review
                  </span>
                  <span style={{ background: "#FFF8C5", border: "1px solid #EAC54F", borderRadius: 6, padding: "3px 8px", fontSize: 11, fontWeight: 700, color: "#9A6700" }}>
                    Multi-Source Variance Flagged
                  </span>
                </div>
                <h3 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700, color: "#1F2328" }}>{selected.current_activity.description}</h3>
                <p style={{ margin: 0, fontSize: 12, color: "#656D76" }}>{selected.reason}</p>
              </div>

              {/* Dependency / Temporal Conflict Callout (Deterministic Safety Gate) */}
              {selected.proposed_reconciliation.dependency_status === "CONFLICT" && (
                <div style={{ background: "#FEF2F2", border: "1px solid #FCA5A5", borderRadius: 10, padding: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ background: "#DC2626", color: "#FFFFFF", borderRadius: 4, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>
                      DEPENDENCY CONFLICT
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: "#991B1B" }}>
                      Predecessor Execution Order Violated — Safe Gate Blocked
                    </span>
                  </div>
                  <p style={{ margin: "0 0 6px", fontSize: 12, color: "#7F1D1D" }}>
                    Deterministic temporal validation determined this activity cannot proceed or start because one or more predecessor activities have not finished or satisfied finish-to-start constraints.
                  </p>
                  {selected.proposed_reconciliation.dependency_details && selected.proposed_reconciliation.dependency_details.length > 0 && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6, paddingTop: 6, borderTop: "1px solid #FEE2E2" }}>
                      {selected.proposed_reconciliation.dependency_details.map((d, idx) => (
                        <div key={idx} style={{ fontSize: 11, color: "#991B1B", fontFamily: "ui-monospace, monospace" }}>
                          ⚠ <strong>Rule {d.rule}:</strong> {d.reason || `Predecessor ${d.predecessor_activity_id} constraint violated.`}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Step 1: Baseline vs Proposed */}
              <div>
                <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                  Schedule Baseline vs. Reconciled Recommendation
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 10, padding: 14 }}>
                    <p style={{ margin: "0 0 8px", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>Active Baseline</p>
                    <p style={{ margin: "0 0 6px", fontSize: 18, fontWeight: 700, color: "#1F2328" }}>
                      {pretty(selected.current_activity.status)} · {selected.current_activity.actual_progress ?? "0"}%
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 11, color: "#656D76" }}>
                      <div><span style={{ display: "block", color: "#8C959F", fontSize: 10, textTransform: "uppercase", marginBottom: 2 }}>Actual Start</span>{fmt(selected.current_activity.actual_start)}</div>
                      <div><span style={{ display: "block", color: "#8C959F", fontSize: 10, textTransform: "uppercase", marginBottom: 2 }}>Actual Finish</span>{fmt(selected.current_activity.actual_end)}</div>
                    </div>
                  </div>
                  <div style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 10, padding: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <p style={{ margin: 0, fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#0D4F4A" }}>Reconciled Recommendation</p>
                      <span style={{ background: "#0D9488", color: "#fff", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 700 }}>
                        {Math.round(selected.proposed_reconciliation.confidence * 100)}% confidence
                      </span>
                    </div>
                    <p style={{ margin: "0 0 6px", fontSize: 18, fontWeight: 700, color: "#0D4F4A" }}>
                      {pretty(selected.proposed_reconciliation.reconciled_status)} · {selected.proposed_reconciliation.reconciled_progress ?? "—"}%
                    </p>
                    <p style={{ margin: 0, fontSize: 12, color: "#656D76" }}>Synthesized from source reliability, freshness decay, and schedule context.</p>
                  </div>
                </div>
              </div>

              {/* Step 2: Field Evidence Table */}
              <div>
                <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                  Field Evidence & Source Reliability
                </p>
                <div style={{ overflowX: "auto", border: "1px solid #D0D7DE", borderRadius: 10 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr style={{ background: "#F6F8FA", borderBottom: "1px solid #D0D7DE" }}>
                        {["Source", "Reported Progress", "Source Reliability", "Freshness", "State"].map((h) => (
                          <th key={h} style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76" }}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {[...selected.supporting_evidence, ...selected.conflicting_evidence].map((ev) => {
                        const isConf = selected.conflicting_evidence.some((c: any) => c.observation_id === ev.observation_id);
                        return (
                          <tr key={ev.observation_id} style={{ background: isConf ? "#FFFBEF" : "#FFFFFF", borderBottom: "1px solid #EAEEF2" }}>
                            <td style={{ padding: "10px 12px" }}>
                              <span style={{ fontWeight: 700, color: "#1F2328" }}>{ev.source_name}</span>
                              <span style={{ fontSize: 11, color: "#8C959F", marginLeft: 4 }}>({pretty(ev.source_type)})</span>
                            </td>
                            <td style={{ padding: "10px 12px", fontWeight: 600, color: "#1F2328" }}>
                              {pretty(ev.status)}{ev.progress != null ? ` (${ev.progress}%)` : ""}
                            </td>
                            <td style={{ padding: "10px 12px" }}>
                              {ev.reliability_score != null
                                ? <code style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 4, padding: "2px 6px", fontSize: 12, fontWeight: 700, color: "#656D76" }}>{Math.round(ev.reliability_score * 100)}%</code>
                                : "—"}
                            </td>
                            <td style={{ padding: "10px 12px", fontSize: 12, color: "#656D76", fontFamily: "ui-monospace, monospace" }}>
                              {ev.freshness_score != null ? `${Math.round(ev.freshness_score * 100)}% (${fmt(ev.source_timestamp)})` : fmt(ev.source_timestamp)}
                            </td>
                            <td style={{ padding: "10px 12px" }}>
                              {isConf
                                ? <span style={{ background: "#FFF8C5", border: "1px solid #EAC54F", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#9A6700" }}>{ev.is_stale ? "Stale" : "Contradictory"}</span>
                                : <span style={{ background: "#DAFBE1", border: "1px solid #82E9A6", borderRadius: 20, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#1A7F37" }}>Supporting</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Step 3: Reconciliation Rationale */}
              <div>
                <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                  Reconciliation Analysis & Recommendation
                </p>
                <div style={{ background: "#F0FDFA", border: "1px solid #5EEAD4", borderRadius: 10, padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingBottom: 10, borderBottom: "1px solid #CCFBF1", marginBottom: 12 }}>
                    <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#0D4F4A" }}>Reconciliation Engine Rationale</span>
                    <span style={{ fontSize: 12, color: "#656D76" }}>Safety-gate verified</span>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: "#1F2328", lineHeight: 1.7 }}>{selected.proposed_reconciliation.explanation}</p>
                  {selected.proposed_reconciliation.recommended_action && (
                    <div style={{ marginTop: 12, background: "#CCFBF1", border: "1px solid #5EEAD4", borderRadius: 8, padding: "8px 12px" }}>
                      <span style={{ fontSize: 12, color: "#0D4F4A" }}><strong>Recommended Action: </strong>{selected.proposed_reconciliation.recommended_action}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Step 4: Candidate Redirection (if multiple matches) */}
              {selected.match_candidates.length > 1 && (
                <div>
                  <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                    Candidate Activity Mapping
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    {selected.match_candidates.map((cand) => (
                      <div key={cand.activity_id} style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 10, padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
                        <div style={{ display: "flex", justifyContent: "space-between" }}>
                          <code style={{ fontWeight: 700, fontSize: 12, color: "#1F2328" }}>{cand.external_activity_id}</code>
                          <code style={{ background: "#FFFFFF", border: "1px solid #D0D7DE", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700, color: "#656D76" }}>{Math.round(cand.final_score * 100)}% match</code>
                        </div>
                        <p style={{ margin: 0, fontSize: 12, color: "#656D76" }}>{cand.description}</p>
                        <button disabled={selected.reviewer_decision !== "pending"} onClick={() => act("select_activity", cand.activity_id)}
                          style={{ background: "#1F2328", border: "none", borderRadius: 8, padding: "7px 12px", color: "#FFFFFF", fontSize: 12, fontWeight: 600, cursor: "pointer", opacity: selected.reviewer_decision !== "pending" ? 0.5 : 1 }}>
                          Redirect to this activity
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Step 5: Planner Decision & Schedule Actuation */}
              <div style={{ borderTop: "1px solid #EAEEF2", paddingTop: 20 }}>
                <p style={{ margin: "0 0 14px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                  Planner Decision & Schedule Actuation
                </p>
                {selected.reviewer_decision !== "pending" ? (
                  <div style={{ background: "#DAFBE1", border: "1px solid #82E9A6", borderRadius: 10, padding: 16 }}>
                    <p style={{ margin: "0 0 4px", fontWeight: 700, color: "#1A7F37", fontSize: 14 }}>
                      ✓ Decision Recorded: <strong>{selected.reviewer_decision.toUpperCase()}</strong> by {selected.reviewer || "Lead Planner"}
                    </p>
                    {selected.reviewer_comment && <p style={{ margin: "4px 0 0", fontSize: 12, color: "#1A7F37", fontStyle: "italic" }}>"{selected.reviewer_comment}"</p>}
                    <p style={{ margin: "8px 0 0", fontSize: 12, color: "#1A7F37" }}>Schedule actuation complete. Project schedule baseline updated per planner authorization.</p>
                  </div>
                ) : (
                  <div style={{ background: "#F6F8FA", border: "1px solid #D0D7DE", borderRadius: 10, padding: 16, display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                      <div>
                        <label style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76", marginBottom: 6 }}>Planner Name / Authorization</label>
                        <input style={inputStyle} value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="e.g. Lead Planner" />
                      </div>
                      <div>
                        <label style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76", marginBottom: 6 }}>Override Progress (%)</label>
                        <input style={inputStyle} value={progressOverride} onChange={(e) => setProgressOverride(e.target.value)} placeholder="Leave blank to accept recommended" />
                      </div>
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#656D76", marginBottom: 6 }}>Decision Rationale / Notes</label>
                      <input style={inputStyle} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Document basis for approval, modification, or rejection" />
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                      {([
                        ["approve", "Approve & Update Baseline", "#1A7F37", "#DAFBE1", "#82E9A6"],
                        ["modify", "Modify with Override", "#0969DA", "#DFF0FF", "#54AEFF"],
                        ["reject", "Reject Recommendation", "#CF222E", "#FFEBE9", "#FF9EA0"],
                        ["comment", "Add Comment Only", "#656D76", "#FFFFFF", "#D0D7DE"],
                      ] as const).map(([action, label, color, bg, border]) => (
                        <button key={action} onClick={() => act(action as any)}
                          style={{ background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: "9px 18px", color: color, fontSize: 13, fontWeight: 700, cursor: "pointer", transition: "opacity 0.15s" }}
                          onMouseEnter={(e) => { e.currentTarget.style.opacity = "0.8"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.opacity = "1"; }}
                        >{label}</button>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Step 6: Audit History */}
              {selected.audit_history.length > 0 && (
                <div style={{ borderTop: "1px solid #EAEEF2", paddingTop: 16 }}>
                  <p style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.5, color: "#8C959F" }}>
                    Decision Audit Log ({selected.audit_history.length} events)
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {selected.audit_history.map((ev, index) => (
                      <div key={ev.audit_id || index} style={{ background: "#F6F8FA", border: "1px solid #EAEEF2", borderRadius: 8, padding: "10px 14px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: "#1F2328" }}>{pretty(ev.action)}</span>
                          <span style={{ fontSize: 11, color: "#8C959F", fontFamily: "ui-monospace, monospace" }}>{new Date(ev.created_at).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })} · {ev.actor}</span>
                        </div>
                        {ev.explanation && <p style={{ margin: 0, fontSize: 12, color: "#656D76" }}>{ev.explanation}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          ) : (
            <div style={{ display: "flex", height: 400, alignItems: "center", justifyContent: "center", background: "#FFFFFF", border: "1px dashed #D0D7DE", borderRadius: 12, color: "#8C959F", fontSize: 13, textAlign: "center", padding: 32 }}>
              Select an item from the queue on the left to inspect evidence and record a decision.
            </div>
          )}
        </div>
      )}
    </div>
  );
}

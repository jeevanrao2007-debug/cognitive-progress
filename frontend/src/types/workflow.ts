export type WorkflowStage =
  | "ingestion"
  | "extraction"
  | "normalization"
  | "matching"
  | "reconciliation"
  | "planner-review";

export type StageStatus = "planned" | "in-progress" | "not-implemented";

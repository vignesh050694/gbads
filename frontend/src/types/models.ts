export type CloneStatus = "PENDING" | "CLONING" | "DONE" | "FAILED";

export type FeatureStatus =
  | "INTERCEPTING"
  | "AWAITING_CLARIFICATION"
  | "AWAITING_METRIC_APPROVAL"
  | "RUNNING"
  | "DONE"
  | "PARTIAL"
  | "CANCELLED";

export interface UserProfile {
  id: string;
  github_username: string;
  github_email?: string;
  avatar_url?: string;
}

export interface DetectedStack {
  language?: string;
  frameworks?: string[];
  databases?: string[];
  queues?: string[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  detected_stack?: DetectedStack;
}

export interface RepoInfo {
  id: string;
  github_url: string;
  repo_name: string;
  clone_status: CloneStatus;
  default_branch?: string;
  cloned_at?: string;
}

export interface FeatureSummary {
  id: string;
  title: string;
  status: FeatureStatus;
  feature_branch?: string;
}

export interface PlannedTestCategory {
  count: number;
  examples?: string[];
}

export interface BenchmarkPlan {
  metric: string;
  formula: string;
  target: string;
  total_planned: number;
  planned_test_cases: Record<string, PlannedTestCategory>;
  real_infra_testing?: boolean;
  infra_services?: string[];
  infra_note?: string;
  estimated_seconds_per_iteration?: number;
}

export interface ModuleSpec {
  clarifying_questions?: string[];
}

export interface FeatureDetail extends FeatureSummary {
  project_id?: string;
  session_id?: string;
  benchmark_plan?: BenchmarkPlan;
  module_spec?: ModuleSpec;
}

export interface ProjectDetail {
  id: string;
  name: string;
  description?: string;
  status?: string;
  detected_stack?: DetectedStack;
  generated_compose?: boolean;
  repos: RepoInfo[];
  features?: FeatureSummary[];
}

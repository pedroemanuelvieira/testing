// Tipos partilhados com a API do backend (FastAPI).

export type Dict = Record<string, any>;

export interface Area {
  id: string; name: string; icon: string; color: string; description: string;
  kpis: string[]; typical_sources: string[]; stakeholders: string[]; decisions: string[]; risks: string[];
  use_cases?: number;
}

export interface ProblemType {
  id: string; name: string; short: string; description: string; learning: string; training_agent: string;
  primary_metric: string; metrics: string[]; default_models: string[]; guide?: string; terms: string[];
}

export interface UseCase {
  id: string; name: string; area: string; areas: string[]; problem_type: string; maturity: string; summary: string;
  business_question: string; decision: string; unit: string;
  target: { column?: string | null; definition: string; positive_class?: any };
  horizon: string; typical_features: string[]; data_requirements: string[]; demo: Dict;
  recommended_models: { model: string; why: string }[];
  metrics: { primary: string; secondary: string[]; business: string };
  profile: Dict; business_costs?: { cost_fp: number; cost_fn: number; benefit_tp: number; note: string } | null;
  pitfalls: string[];
  powerbi_output?: { table: string; columns: string[]; visuals: string[]; measures: { name: string; dax: string }[] } | null;
  ai_act_risk: string; sensitive_attributes: string[]; terms: string[];
  models?: (ModelSpec & { why: string })[]; glossary?: Term[];
}

export interface Hyperparameter {
  name: string; label: string; type: "int" | "float" | "choice" | "bool"; default: any; min?: number | null;
  max?: number | null; log: boolean; choices: any[]; importance: "alta" | "média" | "baixa"; description: string;
  increase: string; decrease: string; search: Dict; term?: string | null;
}

export interface ModelSpec {
  id: string; name: string; family: string; tasks: string[]; library: string; description: string; how_it_works: string;
  strengths: string[]; weaknesses: string[]; when_to_use: string; interpretability: number; speed: number;
  needs_scaling: boolean; handles_missing: boolean; handles_categorical: boolean; hyperparameters: Hyperparameter[];
  available?: boolean;
}

export interface Term {
  id: string; term: string; en: string; category: string; level: string; short: string; definition: string;
  example: string; formula: string; pitfalls: string[]; related: string[]; steps: string[];
  related_terms?: Term[]; used_in_steps?: WorkflowStep[]; used_by_models?: { id: string; name: string; param: string }[];
  use_cases?: { id: string; name: string }[];
}

export interface GlossaryCategory { id: string; name: string; icon: string; description: string; count?: number }

export interface WorkflowStep {
  id: string; order: number; title: string; agent: string; agent_name?: string; objective: string; why: string;
  how: string[]; checklist: string[]; mistakes: string[]; terms: string[]; outputs: string[];
}

export interface Guide {
  id: string; title: string; audience: string; duration: string; problem_type?: string | null; summary: string;
  sections: { title: string; content: string; terms: string[] }[];
}

export interface AgentCard {
  id: string; name: string; component: string; role: string; description: string; icon: string; step?: string | null;
  problem_types: string[]; capabilities: string[]; inputs: string[]; outputs: string[];
  params: { name: string; label: string; type: string; choices?: string[] }[]; requires_data: boolean;
}

export interface Insight { level: "info" | "success" | "warning" | "critical"; title: string; detail: string; terms: string[] }

export interface Block { type: string; title?: string; description?: string; terms?: string[]; [k: string]: any }

export interface AgentResult {
  run_id: string; agent_id: string; project_id?: string; title: string; summary: string; status: string;
  insights: Insight[]; recommendations: string[]; blocks: Block[]; outputs: Dict; next_step?: string | null;
  terms: string[]; params: Dict; created_at: string; duration_ms: number;
}

export interface Job {
  id: string; kind: string; project_id?: string; status: "queued" | "running" | "done" | "error"; progress: number;
  message: string; log: { t: string; p: number; msg: string }[]; result?: any; error?: string | null;
  created_at: string; started_at?: string; finished_at?: string;
}

export interface DataSource {
  connector_id: string; workspace_id?: string | null; dataset_id?: string | null; table?: string | null;
  query?: string | null; columns?: string[] | null; filters: Dict[]; top?: number | null;
}

export interface Project {
  id: string; name: string; description: string; area_id?: string | null; use_case_id?: string | null; problem_type: string;
  source?: DataSource | null; data_info: Dict; target?: string | null; positive_class?: any; time_column?: string | null;
  id_columns: string[]; excluded_columns: string[]; features: string[]; series_columns: string[];
  value_column?: string | null; aggregation: string; freq?: string | null; horizon?: number | null;
  transaction_column?: string | null; item_column?: string | null; label_column?: string | null;
  column_roles: Record<string, string>; feature_plan: Dict; selected_models: string[];
  model_params: Record<string, Dict>; params_locked: string[]; tuning: { enabled: boolean; n_iter: number; method: string };
  cv_folds: number; business_costs: Record<string, number>; goal: string; champion_version_id?: string | null;
  production_version_id?: string | null; steps: Record<string, { status: string; run_id?: string; updated_at?: string }>;
  latest_runs: Record<string, string>; created_at: string; updated_at: string;
}

export interface ProjectStep { id: string; order: number; title: string; agent_id: string; agent_name: string; status: string; run_id?: string | null }

export interface ProjectView {
  project: Project; steps: ProjectStep[]; progress: number; champion: Dict | null; use_case: UseCase | null;
  has_data: boolean; jobs: Job[];
}

export interface ProjectSummary {
  id: string; name: string; use_case_id?: string; use_case_name?: string; area_id?: string; problem_type: string;
  progress: number; updated_at: string; created_at: string; rows?: number; champion_version_id?: string;
  production_version_id?: string;
}

export interface Connector {
  id: string; name: string; kind: string; description?: string; capabilities: string[]; default?: boolean;
  status: string; error?: string; target?: string; methods?: Dict;
}

export interface Meta {
  version: string; knowledge: Record<string, number>; connectors: Connector[]; default_connector: string;
  assistant: { mode: "llm" | "offline"; detail: string; model?: string | null };
  libraries: Record<string, boolean>; optuna: boolean; max_rows: number;
}

export interface ParamDetail extends Hyperparameter {
  value: any; changed: boolean; reason: string;
}

export interface Assessment {
  complexity: number; overfit_risk: number; overfit_level: string; underfit_risk: number; underfit_level: string;
  training_cost: number; training_cost_level: string; explanation: string;
}

export interface Recommendation {
  model_id: string; model_name: string; goal: string; goal_description: string; params: Dict; details: ParamDetail[];
  notes: string[]; profile: Dict; assessment: Assessment; search_space?: Dict;
}

export interface ValidationIssue { level: "error" | "warning" | "info"; param?: string | null; message: string; term?: string | null }

export interface Validation { model_id: string; valid: boolean; issues: ValidationIssue[]; params: Dict; assessment: Assessment }

export interface ChatMessage {
  role: "user" | "assistant"; text: string; ts?: string; mode?: string;
  tools?: { name: string; input: Dict; error?: boolean }[];
  sources?: { terms: { id: string; term: string; short: string }[]; use_cases: { id: string; name: string }[] };
}

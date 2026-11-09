export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type Classification = 'validated' | 'observed' | 'inferred' | 'theoretical'

export interface AuthStatus {
  token_required: boolean
  mode: 'local' | 'demo'
  read_only: boolean
  admin_token_supported: boolean
}
export interface Service {
  id: string
  name: string
  name_ar: string
  criticality: number
  rto_hours: number
  description: string
  description_ar: string
}
export interface AttackScenario {
  id: string
  name: string
  name_ar: string
  compromised: string[]
  description: string
  description_ar: string
  active?: boolean
}

export interface Asset {
  segment?: string | null
  id: string
  name: string
  name_ar: string
  type: string
  criticality: number
  exposure: string
  compromised: boolean
  description: string
  description_ar: string
  controls: string[]
}
export interface Relationship {
  id: string
  source: string
  target: string
  type: string
  privilege: string
  evidence: string
  legitimate_use: string | null
  legitimate_use_ar: string | null
  business_critical: boolean
  mfa_required: boolean
  disabled: boolean
  evidence_source?: string
  collected_at?: string | null
  confidence?: 'low' | 'medium' | 'high' | null
  validation?: string
  rationale?: string | null
  rationale_ar?: string | null
  supports_services?: string[]
  recovery_hours?: number | null
}
export interface EnvMeta {
  config_hash?: string
  config_is_default?: boolean
  hash: string
  is_sample: boolean
  can_undo: boolean
  history_depth: number
  synthetic: boolean
  recommendations_partial: boolean
  paths_truncated: boolean
}
export interface AiStatus {
  enabled: boolean
  provider: string | null
  reason: string
}
export interface SimRecord {
  id: number
  time: string
  env_hash: string
  actions: SimAction[]
  risk_reduction_pct: number
  paths_before: number
  paths_after: number
  current_environment: boolean
}
export interface Environment {
  name: string
  name_ar?: string
  synthetic: boolean
  assets: Asset[]
  relationships: Relationship[]
  services?: Service[]
  attack_scenarios?: AttackScenario[]
}

export interface Factor {
  code: string
  value: number
  detail: Record<string, unknown>
}
export interface AttackPath {
  id: string
  source: string
  target: string
  nodes: string[]
  relationship_ids: string[]
  score: number
  severity: Severity
  classification: Classification
  factors: Factor[]
  weakest_hop?: { relationship_id: string; weight: number; reasons: string[] }
  drivers?: string[]
  steps: {
    relationship_id: string; from: string; to: string; type: string; privilege: string; evidence: string
    confidence?: string; evidence_source?: string; validation?: string
  }[]
}
export interface Finding {
  id: string
  kind: 'attack_path' | 'unjustified_access'
  severity: Severity
  path_id?: string
  target?: string
  score?: number
  classification?: string
  relationship_id?: string
  source?: string
  privilege?: string
}
export interface Summary {
  total_assets: number
  critical_assets: number
  attack_paths: number
  paths_truncated: boolean
  compromised_sensitive_assets?: string[]
  validated_paths: number
  max_path_score: number
  total_path_score: number
  posture_score: number
  evidence_distribution?: Record<Classification, number>
  severity_distribution: Record<Severity, number>
}
export interface Analysis {
  paths: AttackPath[]
  findings: Finding[]
  summary: Summary
}

export type SimAction =
  | { kind: 'remove_relationship'; relationship_id: string }
  | { kind: 'disable_relationship'; relationship_id: string }
  | { kind: 'reduce_privilege'; relationship_id: string; to: 'read' }
  | { kind: 'apply_mfa'; asset_id: string }
  | { kind: 'apply_segmentation'; asset_id: string }

export interface Impact {
  relationship_id: string
  source: string
  target: string
  action: string
  level: string
  legitimate_use: string | null
  legitimate_use_ar: string | null
  business_critical: boolean
  reversible: boolean
}
export interface OperationalImpact {
  level: string
  affected_relationships: Impact[]
  affected_assets: string[]
  lost_access: { identity: string; asset: string }[]
  fully_reversible: boolean
}
export interface SimResult {
  actions: SimAction[]
  before: Summary
  after: Summary
  risk_reduction_pct: number
  path_score_reduction_pct: number
  paths_eliminated: string[]
  paths_mitigated: string[]
  paths_remaining: string[]
  before_paths?: AttackPath[]
  after_paths: AttackPath[]
  record_id?: number | null
  ephemeral?: boolean
  recorded_at?: string | null
  env_hash?: string
  current_environment?: boolean
  residual_risks: {
    path_id: string
    target: string
    score: number
    severity: Severity
    score_before: number
    classification: string
    reasons: { code: string }[]
  }[]
  operational_impact: OperationalImpact
  note: string
}
export interface Recommendation {
  id: string
  action: SimAction
  risk_reduction_pct: number
  path_score_reduction_pct: number
  paths_eliminated: number
  paths_mitigated: number
  paths_remaining: number
  operational_impact: OperationalImpact
  disruption_cost: number
  priority: number
  tradeoff: string
  requires_human_approval: boolean
}
export interface Activity {
  time: string
  kind: string
  [k: string]: unknown
}
export interface Explanation {
  evidence: { route: string[]; score?: number }
  template_explanation: string
  ai_explanation: string | null
  ai_status: string
  notice: string
}

/* ---------------------------------------------------------------- decision intelligence */
export interface ScoringConfig {
  evidence_observed: number
  evidence_inferred: number
  evidence_theoretical: number
  privilege_read: number
  privilege_write: number
  mfa_factor: number
  length_penalty: number
  exposure_bonus: number
}
export interface ScoringConfigResponse {
  config: ScoringConfig
  defaults: ScoringConfig
  hash: string
  is_default: boolean
  notice: string
}
export interface SensitivityResult {
  trials: number
  spread: number
  seed: number
  posture: { baseline: number; min: number; max: number }
  paths: { id: string; rank: number; baseline: number; min: number; max: number; median: number; rank_min: number; rank_max: number; severity_can_change: boolean; indicator: 'low' | 'medium' | 'high' }[]
  recommendations: { id: string; baseline_rank: number; rank_min: number | null; rank_max: number | null; presence_pct: number; top1_pct: number; top3_pct: number; stability: 'stable' | 'moderate' | 'sensitive' }[]
  parameters: { name: string; baseline: number; low_value: number; high_value: number; posture_at_low: number; posture_at_high: number; posture_swing: number; top_recommendation_changes: boolean }[]
  top_recommendation_unchanged_pct: number
  highest_path_unchanged_pct: number
  not_a_probability: boolean
  note: string
}
export interface ServiceEffect {
  service_id: string; name: string; name_ar: string; criticality: number; rto_hours: number
  effect: 'interrupted' | 'degraded' | 'friction'; relationships: string[]
  recovery: 'rollback' | 'reprovision' | 'unknown'; recovery_hours: number | null
  rto_status: 'within' | 'exceeds' | 'unknown' | 'not_applicable'
}
export interface Plan {
  id: string
  strategy: string
  also_strategies?: string[]
  actions: SimAction[]
  metrics: {
    paths_before: number; paths_after: number; paths_eliminated: number; paths_mitigated: number
    posture_before: number; posture_after: number; posture_reduction_pct: number
    max_residual_score: number; residual_validated: number
  }
  residual_top: { path_id: string; nodes: string[]; target: string; score: number; severity: Severity; classification: Classification }[]
  operational: { level: string; affected_assets: string[]; lost_access: number; fully_reversible: boolean; touches_business_critical: boolean; affected_relationships: string[] }
  business: {
    services: ServiceEffect[]; business_impact_index: number; services_interrupted: number
    critical_services_interrupted: number; rto_exceeded: number; rto_unknown: number; services_declared: number
  }
  disruption_cost: number
  effort: number
  approvals: { role: string; why: string[] }[]
  objectives: number[]
  pareto: { optimal: boolean; dominated_by: string[] }
  summary: { en: string; ar: string }
  requires_human_approval: boolean
}
export interface PlansResponse {
  plans: Plan[]
  objectives: string[]
  suggested_plan_id: string | null
  suggestion_rule: string
  optimality_claim: string
  partial: boolean
}
export interface EvidenceRow {
  id: string; source: string; target: string; type: string; privilege: string; evidence: Classification
  confidence: string; evidence_source: string; collected_at: string | null; age_days: number | null; stale: boolean
  validation: string; rationale: string | null; rationale_ar: string | null; disabled: boolean; attack_paths_through: number
}
export interface EvidenceOverview {
  relationships: EvidenceRow[]
  summary: {
    total: number; by_evidence: Record<string, number>; by_validation: Record<string, number>; by_source: Record<string, number>
    undated: number; stale: number; stale_after_days: number; on_attack_paths: number; weak_on_paths: number
  }
  honesty: { synthetic: boolean; real_world_validated: number; declared_not_verified: boolean }
}
export interface ServiceDependency extends Service {
  access_requirements: { relationship_id: string; source: string; target: string; type: string; privilege: string; legitimate_use: string | null; legitimate_use_ar: string | null; business_critical: boolean; disabled: boolean; attack_paths_through: number; recovery_hours: number | null }[]
  exposed_dependencies: number
}
export interface RecExplanation {
  id: string
  confidence: { level: 'high' | 'medium' | 'low'; reasons: string[]; strong_evidence_share: number; is_probability: boolean }
  questions: { key: string; question: { en: string; ar: string }; answer: { en: string; ar: string } }[]
}

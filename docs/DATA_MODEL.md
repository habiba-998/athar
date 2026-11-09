# Data model

Defined in `backend/app/models.py` (Pydantic v2, `extra="forbid"`).

**Asset**: `id` (`^[a-z0-9][a-z0-9_-]{0,63}$`), `name`, `name_ar`, `type` (user, service_account, group, server, database, cloud, control), `criticality` 1–5, `exposure` (internet/internal/restricted), `compromised`, `description(_ar)`, `controls[]` (ids of control assets).

**Relationship**: `id`, `source`, `target`, `type` (member_of, can_login, admin_access, read_access, write_access, trusts, has_credentials, network_access, assumes_role, protects), `privilege` (none/read/write/admin), `evidence` (**validated / inferred / theoretical**, all synthetic in this MVP), `legitimate_use(_ar)`, `business_critical`, `mfa_required`, `disabled`.

**Environment**: `name`, optional `name_ar` (UI falls back to `name`), `synthetic: true` (literal; non-synthetic files are rejected), `assets` (≤ 500), `relationships` (≤ 5000).

## Consistency rules (checked on every import and edit)
- unique asset ids and relationship ids
- every relationship endpoint exists; no self-loops
- at most one relationship per ordered asset pair
- `protects` may only originate from a `control` asset, and control assets may only use `protects`
- a control cannot be a relationship target and cannot be `compromised`
- every id in `asset.controls` must be an existing `control` asset
- deleting an asset cascades its relationships (the UI shows how many) and removes it from other assets' `controls`

## Simulation request
1–20 actions, discriminated by `kind`: `remove_relationship`, `disable_relationship`, `reduce_privilege` (to `read`), `apply_mfa` (asset), `apply_segmentation` (asset). Unknown kinds and extra fields are rejected.

## Stored records (SQLite)
- `activity(id, ts, kind, detail)` — environment loaded/imported/reset/undo, asset and relationship edits, analysis, simulation runs, explanations
- `simulations(id, ts, env_hash, actions, result)` — `result` holds before/after summaries, **before and after paths with their score factors and per-step evidence labels**, residual risks and operational impact
- `explanations(id, ts, kind, ref, lang, evidence, template_text, ai_text, ai_status, env_hash)`
- `kv(key, value)` — the current environment as JSON

## Evidence levels
| level | meaning | weight in score |
|---|---|---|
| validated | exploitability confirmed — **within the synthetic data**, not by real testing | 1.0 |
| inferred | derived from configuration; unconfirmed | 0.7 |
| theoretical | reachable on paper only | 0.4 |

A path is `validated` only if every hop is validated; any theoretical hop makes it `theoretical`.

## Analysis summary (selected fields)
`attack_paths`, `validated_paths`, `severity_distribution`, `max_path_score`, `total_path_score`, `posture_score` (mean worst path per *scored* sensitive asset), `paths_truncated`, and **`compromised_sensitive_assets`**: ids of sensitive assets that are themselves marked compromised. They have no attack path, are excluded from the posture mean, and are surfaced as a warning (audit finding F1). Environment metadata additionally reports `recommendations_partial`.

## Scenarios
`scenarios/acme-sample.json` and `scenarios/harbor-logistics.json` (generated from `backend/app/data/*.py`; a test fails if they drift). See `scenarios/README.md`.

## Sample environment
`data/demo.py`: 15 assets + 1 control, 20 relationships — a phished employee, web portal, application server, jump host, backup server, customer and HR databases, a cloud backup role and archive, and a secrets vault. Yields 20 attack paths (5 fully validated).


## Added fields (advanced-intelligence sprint)

All additions are optional with defaults, so older environment files still import.

| Object | Field | Meaning |
|---|---|---|
| Asset | `type: identity_provider` | SSO / directory-style identity asset; counts as a sensitive target when criticality >= 4 |
| Asset | `segment` | Network zone label (descriptive) |
| Relationship | `evidence` now also `observed` | Seen directly in a data source, not independently validated |
| Relationship | `evidence_source`, `collected_at`, `confidence`, `validation`, `rationale`, `rationale_ar` | Provenance, all **declared** by the data author. `validation` is `none` or `synthetic_exercise`; `real_world` is rejected |
| Relationship | `supports_services`, `recovery_hours` | Business services that rely on the access, and the declared time to re-provision it |
| Environment | `services[]` | `id`, `name`, `name_ar`, `criticality` 1-5, `rto_hours`, descriptions |
| Environment | `attack_scenarios[]` | Named assumed-breach starting points (`compromised[]` asset ids, non-control) |
| ScoringConfig (server-side) | `evidence_observed/inferred/theoretical`, `privilege_read/write`, `mfa_factor`, `length_penalty`, `exposure_bonus` | Heuristic weights; `validated`, `admin`, `none` are fixed at 1 |

Integrity rules added: unique service and scenario ids; relationships may only reference declared services; scenarios may only reference existing non-control assets.

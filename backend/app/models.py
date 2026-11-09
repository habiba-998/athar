"""ATHAR domain model (Pydantic v2).

All identifiers are restricted to a safe charset so they can be echoed in
API responses and used as graph keys without injection risk.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SafeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
ShortText = Annotated[str, StringConstraints(max_length=200)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetType(str, Enum):
    user = "user"
    service_account = "service_account"
    group = "group"
    server = "server"
    database = "database"
    cloud = "cloud"
    identity_provider = "identity_provider"  # SSO / directory: a high-value identity asset
    control = "control"  # security control (display only, never traversed)


class Exposure(str, Enum):
    internet = "internet"
    internal = "internal"
    restricted = "restricted"


class RelType(str, Enum):
    member_of = "member_of"
    can_login = "can_login"
    admin_access = "admin_access"
    read_access = "read_access"
    write_access = "write_access"
    trusts = "trusts"
    has_credentials = "has_credentials"
    network_access = "network_access"
    assumes_role = "assumes_role"
    protects = "protects"  # control -> asset; informational, not traversable


class Privilege(str, Enum):
    none = "none"
    read = "read"
    write = "write"
    admin = "admin"


class Evidence(str, Enum):
    """How strongly a relationship is supported. DECLARED by the data author; ATHAR never verifies or upgrades it.

    Strength order (weakest link decides a path's class): theoretical < inferred < observed < validated.
    In this MVP every environment is synthetic, so none of these can mean real-world validation.
    """

    validated = "validated"      # exploitability independently confirmed (synthetic exercise in this MVP)
    observed = "observed"        # seen directly in a data source (configuration export, telemetry) but not independently validated
    inferred = "inferred"        # derived indirectly from other data
    theoretical = "theoretical"  # reachable on paper only


EVIDENCE_RANK = {Evidence.theoretical: 0, Evidence.inferred: 1, Evidence.observed: 2, Evidence.validated: 3}
DEFAULT_CONFIDENCE = {Evidence.validated: "high", Evidence.observed: "high", Evidence.inferred: "medium", Evidence.theoretical: "low"}


class Asset(Strict):
    id: SafeId
    name: ShortText
    name_ar: ShortText
    type: AssetType
    criticality: int = Field(ge=1, le=5, default=1)
    exposure: Exposure = Exposure.internal
    compromised: bool = False
    description: ShortText = ""
    description_ar: ShortText = ""
    controls: list[SafeId] = Field(default_factory=list, max_length=10)
    segment: SafeId | None = None  # network zone label (e.g. dmz, corp, data); descriptive, used for filtering


class Service(Strict):
    """A business service that depends on relationships (used to estimate business impact of a change)."""

    id: SafeId
    name: ShortText
    name_ar: ShortText
    criticality: int = Field(ge=1, le=5, default=3)
    rto_hours: float = Field(ge=0.0, le=720.0, default=24.0)  # recovery time objective: how long an outage is tolerable
    description: ShortText = ""
    description_ar: ShortText = ""


class AttackScenario(Strict):
    """A named assumed-breach starting point set. Activating it only changes which assets are marked compromised."""

    id: SafeId
    name: ShortText
    name_ar: ShortText
    compromised: list[SafeId] = Field(min_length=1, max_length=20)
    description: ShortText = ""
    description_ar: ShortText = ""


class Relationship(Strict):
    id: SafeId
    source: SafeId
    target: SafeId
    type: RelType
    privilege: Privilege = Privilege.none
    evidence: Evidence = Evidence.inferred
    # Operational context used to estimate side effects of removing the edge.
    legitimate_use: ShortText | None = None
    legitimate_use_ar: ShortText | None = None
    business_critical: bool = False
    # Mitigation state (set by simulation controls or the editor).
    mfa_required: bool = False
    # Disabled relationships stay in the data (reversible, auditable) but are not traversable.
    disabled: bool = False
    # ---- provenance: where this relationship comes from and how far it can be trusted (all declared, never verified)
    evidence_source: ShortText = "unspecified"      # e.g. "synthetic:scenario-author", "iam-export", "scanner:<name>"
    collected_at: datetime | None = None
    confidence: Literal["low", "medium", "high"] | None = None   # None => derived from the evidence level
    validation: Literal["none", "synthetic_exercise", "real_world"] = "none"
    rationale: ShortText | None = None           # why the relationship exists
    rationale_ar: ShortText | None = None
    # ---- business context
    supports_services: list[SafeId] = Field(default_factory=list, max_length=10)
    recovery_hours: float | None = Field(default=None, ge=0.0, le=720.0)  # time to restore this access if it must be re-provisioned

    @property
    def effective_confidence(self) -> str:
        return self.confidence or DEFAULT_CONFIDENCE[self.evidence]


class Environment(Strict):
    name: ShortText
    name_ar: ShortText = ""  # optional; the UI falls back to `name` when empty
    synthetic: Literal[True] = True
    assets: list[Asset] = Field(max_length=500)
    relationships: list[Relationship] = Field(max_length=5000)
    services: list[Service] = Field(default_factory=list, max_length=100)
    attack_scenarios: list[AttackScenario] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def _check_integrity(self) -> "Environment":
        ids = [a.id for a in self.assets]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate asset id")
        known = set(ids)
        service_ids = [s.id for s in self.services]
        if len(service_ids) != len(set(service_ids)):
            raise ValueError("duplicate service id")
        scenario_ids = [s.id for s in self.attack_scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("duplicate attack scenario id")
        non_control = {a.id for a in self.assets if a.type is not AssetType.control}
        for sc in self.attack_scenarios:
            for aid in sc.compromised:
                if aid not in non_control:
                    raise ValueError(f"attack scenario {sc.id} references unknown or control asset {aid}")
        controls = {a.id for a in self.assets if a.type is AssetType.control}
        for a in self.assets:
            if a.type is AssetType.control and a.compromised:
                raise ValueError(f"control {a.id} cannot be compromised")
            for c in a.controls:
                if c not in controls:
                    raise ValueError(f"asset {a.id} references unknown control {c}")
        rel_ids: set[str] = set()
        pairs: set[tuple[str, str]] = set()
        for r in self.relationships:
            if r.id in rel_ids:
                raise ValueError(f"duplicate relationship id {r.id}")
            rel_ids.add(r.id)
            if r.source not in known or r.target not in known:
                raise ValueError(f"relationship {r.id} references unknown asset")
            if r.validation == "real_world":
                # Honesty rule: a synthetic environment can never carry real-world validation.
                raise ValueError(f"relationship {r.id}: real-world validation cannot be recorded in a synthetic environment")
            for sid in r.supports_services:
                if sid not in set(service_ids):
                    raise ValueError(f"relationship {r.id} references unknown service {sid}")
            if r.source == r.target:
                raise ValueError(f"relationship {r.id} is a self-loop")
            if (r.type is RelType.protects) != (r.source in controls):
                raise ValueError(f"relationship {r.id}: only control assets may be the source of 'protects' "
                                 "and control assets may only use 'protects'")
            if r.target in controls:
                raise ValueError(f"relationship {r.id}: a control cannot be a relationship target")
            if (r.source, r.target) in pairs:
                raise ValueError("only one relationship per ordered asset pair is supported")
            pairs.add((r.source, r.target))
        return self

    def asset(self, asset_id: str) -> Asset:
        for a in self.assets:
            if a.id == asset_id:
                return a
        raise KeyError(asset_id)


# ---------------------------------------------------------------- scoring configuration


class ScoringConfig(Strict):
    """The tunable assumptions of the heuristic score. NOT calibrated, NOT probabilities.

    `validated` (evidence) and `admin` / `none` (privilege) are fixed at 1.0 as the anchors of the scale.
    Frozen (hashable) so weight tables can be cached per configuration.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_observed: float = Field(default=0.85, ge=0.05, le=1.0)
    evidence_inferred: float = Field(default=0.70, ge=0.05, le=1.0)
    evidence_theoretical: float = Field(default=0.40, ge=0.05, le=1.0)
    privilege_read: float = Field(default=0.70, ge=0.05, le=1.0)
    privilege_write: float = Field(default=0.85, ge=0.05, le=1.0)
    mfa_factor: float = Field(default=0.35, ge=0.05, le=1.0)
    length_penalty: float = Field(default=0.10, ge=0.0, le=0.5)
    exposure_bonus: float = Field(default=1.10, ge=1.0, le=1.5)

    @model_validator(mode="after")
    def _ordered(self) -> "ScoringConfig":
        if not (self.evidence_theoretical <= self.evidence_inferred <= self.evidence_observed <= 1.0):
            raise ValueError("evidence weights must satisfy theoretical <= inferred <= observed <= 1.0")
        if not (self.privilege_read <= self.privilege_write <= 1.0):
            raise ValueError("privilege weights must satisfy read <= write <= 1.0")
        return self

    def evidence_weights(self) -> dict[Evidence, float]:
        return {Evidence.validated: 1.0, Evidence.observed: self.evidence_observed,
                Evidence.inferred: self.evidence_inferred, Evidence.theoretical: self.evidence_theoretical}

    def privilege_weights(self) -> dict[Privilege, float]:
        return {Privilege.none: 1.0, Privilege.read: self.privilege_read, Privilege.write: self.privilege_write, Privilege.admin: 1.0}


# ---------------------------------------------------------------- simulation


class RemoveRelationship(Strict):
    kind: Literal["remove_relationship"] = "remove_relationship"
    relationship_id: SafeId


class ReducePrivilege(Strict):
    kind: Literal["reduce_privilege"] = "reduce_privilege"
    relationship_id: SafeId
    to: Literal["read"] = "read"


class DisableRelationship(Strict):
    """Temporarily disable a relationship: it stays in the data (reversible) but is not traversable."""

    kind: Literal["disable_relationship"] = "disable_relationship"
    relationship_id: SafeId


class ApplyMfa(Strict):
    """Require MFA on login/credential relationships into an asset."""

    kind: Literal["apply_mfa"] = "apply_mfa"
    asset_id: SafeId


class ApplySegmentation(Strict):
    """Block network_access relationships into an asset."""

    kind: Literal["apply_segmentation"] = "apply_segmentation"
    asset_id: SafeId


SimAction = Annotated[
    RemoveRelationship | DisableRelationship | ReducePrivilege | ApplyMfa | ApplySegmentation,
    Field(discriminator="kind"),
]


class SimulationRequest(Strict):
    actions: list[SimAction] = Field(min_length=1, max_length=20)


class ExplainRequest(Strict):
    kind: Literal["path", "recommendation"]
    id: ShortText
    lang: Literal["en", "ar"] = "en"

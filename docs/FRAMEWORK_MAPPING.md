# Mapping ATHAR to cybersecurity frameworks

**ATHAR is not certified against, compliant with, or an implementation of any framework below.** This document says which framework concepts ATHAR's features *help reason about*, so a reviewer can place the tool in context. It uses framework vocabulary for communication only.

Identifier note: the identifiers below were checked against **ATT&CK Enterprise v20.1** (released 13 Oct 2026) and **NIST CSF 2.0** on 2026-11-09. Technique, tactic and mitigation IDs and names change between ATT&CK versions (the tactic list of T1078 already changed: it now includes *Stealth* (TA0005) where older versions list *Defense Evasion*), so **confirm each ID against the current release (attack.mitre.org, csrc.nist.gov) before publishing or submitting.** The mapping is illustrative either way.

## 1. MITRE ATT&CK (Enterprise)

ATHAR does **not** detect, emulate or test ATT&CK techniques. It models *access relationships*; an attacker traversing a relationship would plausibly use a technique like the one named. The mapping is illustrative.

### Relationship types → techniques an attacker might use to traverse them

| ATHAR relationship | Plausible ATT&CK technique(s) | Tactic(s) |
|---|---|---|
| `can_login` | T1078 Valid Accounts; T1021 Remote Services | Initial Access / Persistence / Privilege Escalation / Stealth (T1078, v20.1; *Defense Evasion* in older versions); Lateral Movement (T1021) |
| `admin_access` | T1078 Valid Accounts (privileged use) | Privilege Escalation, Lateral Movement |
| `has_credentials` (credentials stored on or reachable from the source) | T1552 Unsecured Credentials; T1003 OS Credential Dumping (e.g. a directory server) | Credential Access |
| `assumes_role` | T1078.004 Cloud Accounts | Privilege Escalation, Persistence |
| `network_access` | T1021 Remote Services | Lateral Movement |
| `trusts` | T1199 Trusted Relationship | Initial Access |
| `member_of` | no technique of its own (ATT&CK has none for inherited group rights); access via T1078 | – |
| `read_access` on data stores | T1213 Data from Information Repositories; T1530 Data from Cloud Storage | Collection |
| `write_access` on data stores | T1565 Data Manipulation | Impact |
| Assumed starting points | internet-facing portal: T1190 Exploit Public-Facing Application; phished account: T1566 Phishing then T1078 | Initial Access |

### ATHAR simulation actions → ATT&CK mitigations

| ATHAR action | ATT&CK mitigation (conceptual match) |
|---|---|
| `remove_relationship`, `disable_relationship` (revoke stale or excessive access) | M1018 User Account Management; M1026 Privileged Account Management |
| `reduce_privilege` | M1026 Privileged Account Management; M1018 User Account Management |
| `apply_mfa` | M1032 Multi-factor Authentication |
| `apply_segmentation` | M1030 Network Segmentation |
| "Recorded legitimate use" findings | M1047 Audit (reviewing access) |

### What ATHAR does not cover in ATT&CK
Detection and telemetry, execution and persistence techniques, defence evasion, exfiltration channels, and any technique that depends on a vulnerability or on attacker tooling. ATHAR has no notion of technique difficulty, prevalence or detection.

## 2. NIST Cybersecurity Framework 2.0

ATHAR supports *analysis for* these CSF 2.0 categories; it does not perform the activities and cannot demonstrate that an organisation does.

| CSF 2.0 function / category | How ATHAR relates |
|---|---|
| **ID.AM** Asset Management | The environment model (assets, relationships, criticality, exposure); JSON import/export. It is only as complete as the data supplied. |
| **ID.RA** Risk Assessment | Attack-path discovery and a transparent, reproducible prioritisation index with documented assumptions. It does not estimate likelihood or loss. |
| **PR.AA** Identity Management, Authentication, and Access Control | Finds excessive or unjustified access, evaluates privilege reduction and MFA as what-if changes. |
| **PR.IR** Technology Infrastructure Resilience | What-if network segmentation. |
| **GV.RM** Risk Management Strategy | Makes trade-offs explicit (security benefit vs operational impact vs reversibility) and records decisions in an audit trail. It does not set strategy or risk appetite. |
| DE (Detect), RS (Respond), RC (Recover) | **Not addressed.** |

## 3. Least privilege

| Principle | ATHAR feature | Limit |
|---|---|---|
| Grant only the access that is needed | "Access with no recorded justification" finding (privileged or sensitive-reaching relationships without a stated use); `reduce_privilege`; `remove` / reversible `disable`; the simulation shows which legitimate access would be lost | "Needed" is whatever the data author recorded. ATHAR sees no usage logs, so it cannot tell whether access is actually used. |

## 4. Zero Trust (NIST SP 800-207 concepts)

| Zero Trust idea | ATHAR relation | Limit |
|---|---|---|
| Assume breach | Analysis starts from assumed-compromised assets | The assumption is an input. |
| Least-privilege access | see §3 | |
| Micro-segmentation | `apply_segmentation` what-if | Models removal of network paths only. |
| Explicit verification of every access (e.g. MFA) | `apply_mfa` what-if (modelled as a 0.35 factor) | The factor is an assumption. |
| Continuous evaluation, policy engines, telemetry | **Not addressed** | |

## 4b. NIST SP 800-207 tenets and ATHAR (what each tenet would need beyond ATHAR)

SP 800-207 states seven tenets (resources, secure communication, per-session access, dynamic policy, asset posture monitoring, dynamic authentication, and continuous data collection). ATHAR touches **none of them operationally**: it is an offline reasoning tool over a model. It supports *analysis of* tenet 3 (per-session, least-privilege access) and tenet 4 (policy decisions that depend on state) only in the sense that it shows which standing relationships would remain after a change.

## 4c. Evidence classes are not a framework

The four evidence classes (validated, observed, inferred, theoretical) are ATHAR's own vocabulary. They are **declared by the data author** and weighted in the heuristic score; they are not ATT&CK, CSF or any standard's confidence scale, and "validated" never means validated in the real world in this MVP (the model rejects a `real_world` validation on synthetic data).

## 5. Attack-path analysis (background)

Reasoning over graphs of reachability to find chains of access is an established idea (attack graphs: Phillips and Swiler, 1998; Sheyner et al., 2002; and identity attack-path tooling in common use). ATHAR applies the idea to an editable synthetic model. It claims no algorithmic novelty; see `PRODUCT_OVERVIEW.md` for what it does contribute and `CLAIMS.md` for what is verified.

## 6. References (primary sources)

- MITRE ATT&CK Enterprise v20.1, attack.mitre.org (techniques T1078, T1021, T1552, T1003, T1199, T1213, T1530, T1565, T1190, T1566; mitigations M1018, M1026, M1030, M1032, M1047).
- NIST Cybersecurity Framework 2.0 (NIST CSWP 29, 2024): functions GV, ID, PR, DE, RS, RC; categories ID.AM, ID.RA, PR.AA, PR.IR, GV.RM.
- NIST SP 800-207, *Zero Trust Architecture* (2020): the seven tenets of zero trust.
- NIST Computer Security Resource Center glossary: *least privilege*.
- O. Sheyner, J. Haines, S. Jha, R. Lippmann, J. M. Wing, "Automated Generation and Analysis of Attack Graphs", IEEE Symposium on Security and Privacy, 2002, pp. 273-284.
- C. Phillips and L. P. Swiler, "A Graph-Based System for Network-Vulnerability Analysis", New Security Paradigms Workshop, 1998, pp. 71-79.

None of these documents endorses ATHAR, and ATHAR makes no compliance or certification claim against any of them.

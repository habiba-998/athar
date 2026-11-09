# ATHAR: product overview

**See the attack before it happens. Predict. Simulate. Prevent.**

ATHAR is a working prototype of a defensive tool that answers a question security teams struggle to answer with lists of findings: *"If this account or system were compromised, what could the attacker reach, which single change would cut the most routes, and what would that change break?"*

It runs entirely on **synthetic data**. It does not scan, exploit, or change anything. "Predict" in the tagline means *show the routes an attacker could take through modelled access*, not forecast attacks: ATHAR contains no trained model and makes no probability claims.

## What it does

1. **Models an enterprise as a graph.** Users, service accounts, groups, servers, databases, cloud resources and security controls, joined by directed relationships (can log in, administer, read/write, hold credentials, trust, assume a role, network reach). Each relationship carries a privilege level, an evidence level (validated / inferred / theoretical), whether it has a recorded legitimate use, and whether the business depends on it. Environments can be edited in the UI or imported as validated JSON.
2. **Finds attack paths.** From the assets assumed compromised, it enumerates every route (up to 6 hops) to sensitive assets, and scores each with a transparent formula whose factors are shown next to the score.
3. **Simulates defences on an isolated copy.** Remove a permission, disable it reversibly, reduce a privilege, require MFA, or segment the network. The result shows paths eliminated, paths that remain and why, the exact assets affected, legitimate access that would be lost, and whether the change can be reverted. The live environment is never modified.
4. **Recommends actions, explainably.** Each candidate is simulated and ranked by benefit against operational disruption. Every recommendation requires human approval; ATHAR never executes anything.
5. **Keeps evidence, calculation and narration apart.** Optional AI text is a separate, labelled block that cannot create findings or change a number, and is off by default.
6. **Keeps an audit trail.** Every simulation (with its full before/after paths and score factors), explanation and edit is stored locally with a timestamp.
7. **Speaks English and Arabic**, with correct RTL layout, in a phone-usable interface.

## The problem

Security data is usually organised *by finding*: this host has that weakness, this account has that permission. Attackers move *along relationships*: a phished helpdesk account, a stale bastion login, credentials on a build server, an over-privileged deploy role. Defenders then face two hard questions that lists don't answer:

- **Which of these thousand things actually connects to something that matters?**
- **If I remove this access, what do I gain, and who can no longer do their job?**

ATHAR makes both questions computable and shows the working.

## How it differs from vulnerability scanners

| | Vulnerability scanner | ATHAR |
|---|---|---|
| Question answered | "What is weak on this host?" | "What can a compromised identity *reach*, and what cuts those routes?" |
| Unit of analysis | A host or software flaw | A chain of access relationships |
| Needs a vulnerability to matter? | Yes | No. Excess privilege, stale access and stored credentials create paths with no CVE at all |
| Output | A prioritised list of findings | Routes, a ranked list of *changes*, and the measured effect of each |
| "What if?" | Not offered | Core: isolated simulation with operational impact and reversibility |
| Evidence | Detected from the target | Declared in the model (this MVP: synthetic), kept visibly separate from calculations |

They are **complementary**, not substitutes. A scanner could supply the evidence levels that ATHAR currently takes as declared inputs. ATHAR also does not claim to outperform mature attack-path-management, identity-security or breach-simulation products; none was tested against it.

## Why simulation is the point

A list of recommendations is cheap; the hard part is *trust*. ATHAR's recommendations are not asserted, they are **demonstrated**: each one is applied to a copy of the model and the engine reports what changes. That makes the trade-off visible *before* anything is touched: in the Harbor scenario a single change removes 37 of 42 paths with no legitimate access lost, while the next-best reduction touches business-critical access and is flagged high impact. It also surfaces the uncomfortable remainder: the residual risk that exists because the business needs the connection.

## What is novel here (stated carefully)

ATHAR does **not** claim a new algorithm: attack graphs and identity attack-path analysis are established ideas. Its contribution in this prototype is the *combination*, implemented end to end and tested:

- deterministic, reproducible scoring whose every factor is exposed, with the sensitivity of its own weights published;
- what-if simulation that is isolated by construction, reports legitimate-access side effects and reversibility, and is validated against an independent oracle;
- a hard separation between declared evidence, computed results and optional AI narration;
- honest handling of incompleteness (truncation and partial-recommendation flags) and of residual risk (a business-safe plan that is allowed to fail to reach zero);
- first-class Arabic and English, RTL included.

## Maturity

| | |
|---|---|
| Stage | Working MVP / research prototype |
| Data | Synthetic only |
| Users | Single user on one machine (loopback, optional shared token) |
| Validated | Internal correctness and reproducibility (see `TECHNICAL_VALIDATION.md`, `CLAIMS.md`) |
| Not validated | Usefulness on real environments; scoring weights against real incidents; usability with real analysts |

## Documents

[Technical validation](TECHNICAL_VALIDATION.md) · [Evaluation](EVALUATION.md) · [Framework mapping](FRAMEWORK_MAPPING.md) · [Threat model](THREAT_MODEL.md) · [Claims register](CLAIMS.md) · [Competition demo](COMPETITION_DEMO.md) · [Architecture](ARCHITECTURE.md) · [Security](SECURITY.md) · [Remaining work](REMAINING_WORK.md)

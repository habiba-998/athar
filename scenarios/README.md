# Synthetic scenarios

Importable through **Environment → Import JSON**. Everything in these files is invented: no real organisation, person, host, credential or vulnerability.

| File | Contents | Starting points (assumed, not findings) |
|---|---|---|
| `acme-sample.json` | The default demo: 16 assets (incl. 1 control), 20 relationships | a phished employee |
| `harbor-logistics.json` | A fictional logistics company: 34 assets, 55 relationships. 7 identities at different privilege levels (helpdesk, HR, developer, finance, DBA, IT admin, executive), 3 service accounts, 4 groups, 8 servers, 4 databases, 4 cloud resources, 4 security controls | a phished helpdesk analyst; an internet-facing portal assumed exploitable |
| `meridian-enterprise.json` | **Digital twin** used in the competition demo: 46 assets (6 controls), 66 relationships, an SSO identity provider, a directory, privileged and service accounts, servers, 5 databases, cloud resources, network segments, 7 business services with recovery objectives, and per-relationship provenance (source, date, confidence, validation) | four selectable scenarios: phished helpdesk analyst + exploitable portal (default), compromised vendor account, portal only, developer account misuse |

Expected results (pinned by `backend/tests/test_scenarios.py`): Harbor has 42 attack paths (12 validated, 5 critical), posture 67.3, highest path 88.0; removing `r02` (the helpdesk group's admin login to the jump host) leaves 5 paths and posture 22.8 with low impact.

Meridian (pinned by `tests/test_scenarios.py`, `docs/evaluation/MERIDIAN.md`): 71 attack paths, posture 66.2, highest path 80.0; evidence classes 1 validated / 22 observed / 44 inferred / 4 theoretical; none is real-world validated.

The JSON is generated from `backend/app/data/*.py` by `python scripts/export_scenarios.py`; a test fails if the files drift from their builders. To make your own, export the current environment from the UI, edit it, and import it back. The file must declare `"synthetic": true`, and every relationship must reference existing assets.

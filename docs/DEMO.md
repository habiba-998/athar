# Short demo script (≈ 6 minutes, sample environment)

> For the full competition presentation with the Harbor scenario, residual-risk discussion and measured results, use [COMPETITION_DEMO.md](COMPETITION_DEMO.md).

**Before you start** (do this once, a few minutes earlier)
1. Start both servers (see README). Open http://localhost:5173.
2. *Environment* tab → **Load sample** (guarantees the known starting point). Check the header chips: **Synthetic data**, **AI narration: off**.
3. Optional: browser zoom 100%, window ≥ 1280 px wide. Keep a phone or a 375 px browser window ready for step 8.

**Say up front (20 s):** "Everything you see is synthetic. ATHAR never touches real systems or changes anything; scores are a reproducible heuristic, not a probability, and there is no trained model."

## 1. The picture (45 s) — Dashboard
The page opens on the **most dangerous attack path**, drawn as a route trace: red dot = compromised start, diamond = sensitive target, and the line style says how well each hop is supported (solid = validated, dashed = inferred, dotted = theoretical). Then: 15 assets, 7 critical, **20 attack paths, 5 fully validated**, posture index 54.8, the assets at risk ranked by their worst path, and findings split into *Act now* and *Review*. "Every number is computed live by the API from the graph."

## 2. How an attacker gets in (75 s) — Attack graph
1. Click **Open path in graph** (or pick the top path in the list). The graph isolates that path as a readable column; the side panel shows the relationship sequence with evidence tags and the score factors. Untick **Show only selected path** to see it in the context of the whole graph, tick it again to return.
2. Click **Explain this path**: *Evidence (deterministic)*, the template explanation, and a separate dashed block **"AI-generated narration (not evidence)"** which says AI is off. "Findings never depend on AI."
3. Select the *Jump Host* path and click the edge *Sara can log in to Jump Host*: **admin** privilege and **no recorded legitimate use**. Open *Evidence levels* to show that "validated" means validated within the synthetic data.

## 3. Defend: remove the excess (90 s) — Simulation
1. Action **Remove permission**, target *Sara can log in Jump Host* → **Add to queue** → **Run simulation**.
2. **20 → 11 paths, 9 eliminated** (large Before/After blocks, severity bars and a change column), summed score −46.3%, impact **Low**, "exactly affected assets": *Sara*, *Jump Host*. Each eliminated path is drawn as a route trace with a scissors mark on the hop that was cut; the graph shows the removed edge in red. The percentages carry a note that they describe ATHAR's scores, not the likelihood of an attack.
3. **Residual risks**: routes through the portal and app server still reach the Customer Database. "Those links are business-critical, so removing them would hurt the business — that is the honest remainder."
4. Show the original is untouched: *Attack graph* tab still lists all 20 paths.

## 4. Reversible vs irreversible (45 s)
Reset, then queue **Disable relationship (reversible)** on the same edge and run. Same security effect, but the panel says **"Every change in this simulation can be reverted"** while *Remove* said **Not reversible**. Use **Undo last change** once.

## 5. Side effects (45 s)
Queue **Remove permission** on *Omar (HR) read access HR Database*. Impact **High**, and **Legitimate access lost: Omar (HR) → HR Database**. "ATHAR shows what you would break, not just what you would fix."

## 6. Recommendations and audit (45 s)
*Recommendations*: each action was simulated; show priority, trade-off and "Requires human approval". Click **Simulate this** on one. Back in *Simulation*, show **Saved simulation runs** with timestamps; restart-proof, and an old run warns if the environment changed.

## 7. Your own environment (45 s) — Environment
Use the **Assets / Relationships** tabs and the search box. **Export JSON**, then on *Relationships* **Disable** one and watch the dashboard recompute. Click **Add relationship**, leave the ID empty and press **Save** (inline validation), then choose the same asset as source and target: the server rejects it with the reason ("self-loop") and nothing changes. **Delete** shows a confirmation dialog that says how many relationships go with it. **Undo last edit**, then **Load sample**.

## 8. Arabic and phone (45 s)
Click **العربية**: full RTL, mirrored graph and route traces, Arabic explanations, Latin digits, Arabic typeface. Switch to a 375 px window: the tabs become a bottom bar, forms are 44 px touch targets, and selecting a path shows it as a readable top-down column.

## If something goes wrong
- *"Could not reach the ATHAR API"*: start the backend (Terminal 1) and press **Retry**.
- State looks odd: *Environment* → **Load sample**, then reload the page.
- Never enable the AI during the demo unless you have tested your key beforehand; the demo is complete without it.

## Questions you should expect (honest answers)
- *Is there a machine-learning model?* No. Deterministic graph analysis; AI only narrates.
- *Are the "validated" paths real?* They are validated within synthetic data only.
- *Could it run on a real network?* Not as built: no data ingestion, no real authentication; see Known limitations in README and docs/SECURITY.md.
- *Does it scale?* Up to the stated caps; see the measured table in docs/ARCHITECTURE.md.

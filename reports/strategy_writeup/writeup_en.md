# Grim v22 — A Deterministic Hierarchical Control Policy for Marnie's Grimmsnarl ex

**Team:** 可抽奖的冰棒 — Pokémon TCG AI Battle Challenge, Strategy Category
**Corresponding simulation submission:** frozen archive `grim_v22_final` (SHA-256 `599e19ae…`), active in both final slots.

---

## 1. Summary

We win by refusing luck. Our deck converts a one-shot, coin-free evolution trigger — Marnie's Grimmsnarl ex's *Punk Up*, which attaches up to five basic Darkness energy from the deck — into the largest deterministic energy swing in the card pool. Our agent, a purely rule-based hierarchical policy of about 7,600 lines, converts that energy lead into prize cards through bench sniping (*Shadow Bullet*), damage-counter manipulation (Munkidori), and passive spread pressure (Froslass). The policy contains no randomness, no neural component, and no coin-flip-dependent card, and every returned action passes hard validation — we observed zero faults in every local evaluation leg and in all 40 live submissions. The measurement discipline around it — a calibrated noise floor, byte-identical frozen archives, isolated opponent runners, and pre-registered negative results — is our main claim to originality. The submission converged to a final rating of 830.9, rank 874 of 6,807 teams (top ≈12.8%).

## 2. Deck construction

### 2.1 Game plan: engine, control, consistency

The 60-card list is built on three mutually reinforcing axes.

| Role | Card | Count |
|---|---|---|
| Engine | Marnie's Impidimp / Marnie's Morgrem / Marnie's Grimmsnarl ex (646/647/648) | 4 / 3 / 3 |
| Control | Munkidori (112) · Snorunt (860) · Froslass (104) | 4 / 2 / 2 |
| Energy | Basic Darkness (7) | 10 |
| Consistency | Buddy-Buddy Poffin (1086) ×4 · Rare Candy (1079) ×3 · Spikemuth Gym (1259) ×4 · Team Rocket's Petrel (1219) ×4 · Lillie's Determination (1227) ×4 · Poké Pad (1152) ×4 · Dawn (1231) ×1 · Pokégear 3.0 (1122) ×1 | 25 |
| Disruption / recovery | Night Stretcher (1097) ×3 · Boss's Orders (1182) ×2 · Unfair Stamp (1080, ACE SPEC) ×1 · Tool Scrapper (1137) ×1 | 7 |

**Engine.** *Punk Up* fires when Grimmsnarl ex evolves from hand: attach up to five basic Darkness energy from the deck to any Marnie's Pokémon. No coin, no discard, no once-per-game lottery — a guaranteed five-energy swing that the rest of the deck is built to reach quickly: four Buddy-Buddy Poffin fetch two ≤70-HP basics (Impidimp or Snorunt) on turn one, three Rare Candy skip Morgrem, Spikemuth Gym grants a Marnie's-Pokémon search per turn, and Dawn fetches a Basic, a Stage 1 and a Stage 2 in a single supporter. With only ten energy in the list, *Punk Up* effectively ends the attachment game on its activation turn.

**Control.** The energy lead is converted by two abilities. Munkidori's *Adrena Brain* (with Darkness attached, once per turn) moves up to three damage counters from our board to the opponent's board — simultaneously healing our attackers and finishing benched targets that attacks cannot reach. Froslass's *Icy Curtain* places a damage counter on every Ability Pokémon on both sides at each Pokémon Check. It is symmetric on paper and asymmetric in practice: our key ability fires once per game (Punk Up), while the dominant meta engines — Alakazam ability loops, opposing Grimmsnarl — depend on repeatable once-per-turn abilities and pay the tax every turn. Shadow Bullet's fixed 30 bench damage (weakness and resistance ignored on the bench) then converts the accumulated spread into knockouts over stall walls. Two Boss's Orders break stall boards that refuse to engage.

**Disruption.** Unfair Stamp converts our first knockout into asymmetric hand disruption; Tool Scrapper answers ability-bearing tools; Night Stretcher sustains the engine through forced knockouts.

### 2.2 Design rule: no luck

Every coin-flip card in the pool was rejected on principle, and no special energy with variance-based effects was adopted. All 60 slots are either engine pieces or tutors for engine pieces. This is deck-level determinism matching the agent-level determinism below — the direct answer to the "robustness against luck" axis.

### 2.3 Deck search discipline

Card changes were decided by single-card greedy hill-climbing under a joint fitness (mirror win rate + first-player win rate), screened at n=1000 and confirmed at n=4000, then gated by three-seed experiments classified STRONG / MARGINAL / REGRESS by Wilson lower bounds. Changes inside the noise band were rejected and recorded, not shipped. Directions that failed this process — an extra router layer (v28/v29) and a retreat-pivot build — were closed with the same evidence standard (see §4).

## 3. Agent design

### 3.1 Five layers over a validated fallback

The policy is a strict hierarchy; each layer may only replace the choice of the layer below, and every layer must answer "why did this decision exist?" from its own trace.

**Layer 0 — validated fallback (~2,500 lines).** Its only contract is legality: correct action count, valid indices, no duplicates. Any exception, malformed option, or unknown engine context silently degrades to this layer, so there is structurally no code path that can emit an invalid action.

**Layer 1 — processing queue + turn DAG.** Committed jobs (evolution, attack setup, board repair) are enqueued and executed through an explicit dependency DAG that may first complete a missing prerequisite — attaching the promised energy before executing the attack node — instead of blindly executing the queue head.

**Layer 2 — deadline ledger.** A resource ledger (Dark energy, attachment rights, supporter-per-turn, stadium, Boss counts) drives lexicographic deadline scheduling: each candidate action carries a deadline class, and the most urgent executable job wins. This replaced a fixed priority list, which we found unable to express "attach now, the attack window closes next turn."

**Layer 3 — continuity scheduler with strategic memory.** Turn-objective inference classifies the current turn (establish control body / prize conversion / passive pressure campaign); phase inference detects openings such as an opponent Active already in prize-conversion range. Memory persists commitments *within* a game only — cross-game state is reset at every episode boundary, verified by replay audits of live episodes with zero mismatches.

**Layer 4 — guard policies.** Twenty-three narrow guards, each born from a diagnosed replay failure and each a surgical override with a documented trigger: stall guards against Boss's Orders on damaged basics, preservation guards for energized Impidimp/Morgrem, promotion guards for damaged or low-HP Munkidori, attachment guards protecting pre-ability and pre-attack energy placement, lethal-guards for Shadow Bullet double-KO math, and match-up-specific guards for Alakazam and Zoroark boards. Each guard's reason is recorded in the decision ledger — the policy is a set of named, motivated overrides, not a heuristic soup.

**Engine alignment.** Every rule is written against observed simulator behavior, not printed card text; where the two disagreed, the simulator won. This eliminated an entire class of "correct by the rules, wrong in the engine" bugs.

### 3.2 Why rules, not learned models

We did not skip machine learning; we measured it and closed it with thresholds. Behavior cloning of our own policy produced a student whose fidelity ceiling (0.75–0.80) made every rollout it produced unreliable, so it was closed. A residual RL line failed to beat the rule baseline on the gate and was closed. A one-ply search variant with rule-based rollout evaluation was implemented and deferred — its live evidence never exceeded the frozen archive. Each negative result is pre-registered, gated, and kept: they explain *why* the final agent is rules-only, which we believe is more credible than any algorithm claim.

**Not over-specialized.** Single-archetype is a deliberate deck-axis choice — deep, not broad. The policy itself is not tuned against one imagined opponent: the four-leg head-to-head battery in §5 spans four distinct opponent families (Alakazam ability loops, our own pivot build, a full Grim control list, a match-up router), and the live pool matched the agent against a diverse field at an opponent mean of 812. The breadth claim is measured, not assumed.

## 4. Evaluation methodology

**Noise floor.** The native engine exposes no shuffle seed; same-seed reruns are independent batches, not replays. We calibrated the cross-process noise band at roughly ±2.2 percentage points and treat any smaller difference as non-evidence. All win rates in this report carry Wilson 95% intervals and batch sizes.

**Exact archives.** Every candidate was frozen as a byte-identical submission archive (two independent packings, identical SHA-256), re-unpacked, and re-verified against its manifest; the *unpacked* artifact — not the source tree — was the object tested and submitted.

**Isolated runners.** Candidates shared the top-level package name `policies`; a naive head-to-head runner let opponents share module state. We built per-candidate module isolation and invalidated earlier pooled results — two runner artifacts that would have manufactured false conclusions were found and fixed this way.

**Decision example — v22 vs v29.** A more elaborate state-router variant (v29) was re-judged after its first elimination was questioned: merged decisive head-to-head 208–175 (54.3%, Wilson 95% ≈ 49.3–59.2%) still spans 50%, and v29 carried an extra routing layer plus uncovered legs. We kept the simpler v22 rather than shipping on non-significance. The same standard removed our own longest-running line: the Mega Lucario build that had carried the team for weeks was set aside when the Grimmsnarl build measured better on both live and local gates. The discipline has to be able to kill our own favorites, or it proves nothing.

**Live-read discipline.** Early public scores of different submission instances are not one robot's time series; we compare only episodes attributed by submission ID, corrected for opponent mean strength via implied-rating inversion, and we never chased instantaneous score spikes.

**One boundary, drawn precisely.** What we eliminate is *strategy-layer* luck: actions produced by deterministic rules, no coin cards, no random components. *Game-layer* variance from shuffles and draws remains — we do not claim to have removed it; we bound it with the noise discipline above instead of pretending it away.

## 5. Results

**Local (exact final archive, n=64 per leg, zero faults in every leg):** vs Alakazam 79.7% (51–13); vs our retreat-pivot baseline 65.6% (42–22); vs a full Grimmsnarl v1 control list 60.9% (39–25); vs a match-up router 59.4% (38–26). Self-play smoke (n=8) produced zero candidate or opponent faults.

**Live.** Across 40 completed submissions, zero runtime errors. The final two active slots were the same frozen archive, a controlled best-of-latest-2 decision. The headline number: the final locked rating is **830.9**, rank **874 of 6,807** (top ≈12.8%, public leaderboard 2026-09-01). The mature reference `55539446` (`grim_v22_final`) carried the team score; the duplicate slot `55547740` settled at 798.1.

## 6. Discussion

Honest limits: the *deck* is deliberately single-archetype and tuned against a snapshot meta — the *policy* is not over-specialized, with breadth across four opponent families evidenced in §3.2; the control plan loses races that end before the engine turn; and Froslass's tax is double-edged if the meta shifts to ability-free lists. What we would fund next is already measured as ingredients: a match-up router over this policy plus the deferred search variant with opponent-archetype detection. The barrier that kept them out — live evidence exceeding the frozen archive under the same noise discipline — is exactly the process we recommend as this project's main export.

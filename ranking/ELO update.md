# ELO weighting update

## Problem statement
You want an Elo-like system for dance competitions where each dancer has a solo rating r_i, couples compete as pairs, and pair outcomes update solo ratings. Key requirements: simple rules, origin-independence (ratings have no fixed zero), protect high-rated professionals from being excessively penalized when dancing many heats with weak amateurs, and use the same weighting for pair fusion and update propagation.

## Executive summary
- Use a single, simple, origin-independent share rule for each couple: reserve a fixed base share for each partner (20%), split the remaining 60% by an origin-independent exponential function of the rating difference so the weaker partner receives most of the remainder. This yields per-pair shares s_a,s_b in (0.2,0.8) that sum to 1.
- Use the same shares to compute pair rating: R_pair = s_a·R_a + s_b·R_b.
- Compute pair expected score with Elo formula and update pair rating by Δ_pair = K*(S − E).
- Propagate Δ_pair to individuals using the same shares: R_a += s_a·Δ_pair, R_b += s_b·Δ_pair.
- This is simple, symmetric, origin-independent, stable, and gives built-in protection for the stronger partner without many special-case rules.

## Discussion
- Why origin-independence matters: additive shifts to all ratings (e.g., anchoring at 1500) should not change weight splits; using functions of the rating difference (|d|) or ratios of exponentials accomplishes this.
- Share function families considered:
  - Logistic/exponential: smooth, probabilistic interpretation, controlled by scale C (e.g., 400).
  - Power/rational: more aggressive, tunable tail behavior via exponent p.
  - Linear ratio w_A = R_B/(R_A+R_B): simple but not origin-independent.
- Protection for pros:
  - Built into the chosen share rule (weaker partner gets most remainder), avoiding complex per-case rules.
  - Alternative protections considered (caps, asymmetric rules, conditional protection) were discarded in favor of simplicity.
- Consistency: using the same shares for pair fusion and propagation keeps the model coherent (pair rating reflects how updates are split).
- Stability: deterministic analysis shows the system is stable — shares change slowly as ratings move, updates are bounded, and pros decline much less than amateurs for the same negative match result.
- Tuning knobs:
  - K (pair update magnitude): controls overall volatility (e.g., 10–30 typical; higher for new dancers).
  - C (scale for exponent): controls how quickly shares move toward extremes (400 aligns with Elo sensitivity).
  - base (minimum per-partner share): sets minimum protection; 0.20 was your chosen value.
  - Alternative: use power instead of exponential if you want sharper transfer to the weaker partner (but requires careful tuning).

### Pros
- Simple and deterministic: one clear formula (base + exponential split) — easy to implement and explain.
- Origin-independent: weights depend only on rating differences, not absolute scale.
- Built-in pro protection: stronger partner is guaranteed a minimum share (e.g., 20%) and the weaker partner absorbs most of the remainder.
- Consistent fusion/propagation: same shares used for pair rating and for splitting updates — avoids internal inconsistency.
- Stable dynamics: shares change slowly as ratings move; per-match individual updates are bounded.
- Tunable with few knobs: base, C (scale), and K; no many corner-case rules required.
- Interpretable extremes: when gap → large, shares → (base, 1−base) (e.g., 0.2/0.8).

### Cons
- Bias against the strong partner: intentional protection can under-update a genuinely declining pro (may mask true drops).
- Slower correction for overperforming amateurs: amateurs may take longer to be pulled down if protection skews updates away from pros, potentially inflating pair ratings transiently.
- Choice of base and C matters: poor choices can either overprotect pros (too large base/small C) or fail to protect them (too small base/large C); requires tuning.
- Not probabilistically optimal: splitting updates by heuristic shares departs from a full likelihood-based inference that would jointly estimate solos and fusion parameters.
- Potential long-term drift: without periodic batch re-estimation or anchors, asymmetric continuous updates might slowly bias absolute scale (can be mitigated by anchoring mean or occasional MLE refit).
- Edge cases with many mixed partnerships: strong dancers who mostly partner weak amateurs may accumulate biased histories unless new-dancer learning rates / periodic refits used.
- Less data-efficient than hierarchical/Bayesian methods: when many dancers have few matches, principled shrinkage models perform better at recovering true solo skills.

## Concrete proposal (simple, implementable)
1) Share computation (symmetric protection)
   - d = R_a − R_b
   - base = 0.20, rem = 1 − 2·base (0.60)
   - s = exp(|d| / C) with C = 400 (default)
   - If d == 0: s_a = s_b = 0.5
   - If d > 0 (A stronger):
     - s_a = base + rem * (1 / (1 + s))
     - s_b = 1 − s_a
   - If d < 0 (A weaker):
     - s_a = base + rem * (s / (1 + s))
     - s_b = 1 − s_a

2) Pair rating and Elo update
   - R_pair_ab = s_a·R_a + s_b·R_b
   - R_pair_cd = s_c·R_c + s_d·R_d
   - E_ab = 1 / (1 + 10^{(R_cd − R_ab)/400})
   - Δ_pair = K * (S_ab − E_ab)  (S_ab ∈ {0,0.5,1} or normalized score)

3) Propagation
   - R_a += s_a * Δ_pair
   - R_b += s_b * Δ_pair
   - R_c += s_c * (−Δ_pair)
   - R_d += s_d * (−Δ_pair)

4) Defaults and notes
   - Defaults: K = 20, C = 400, base = 0.20.
   - New dancers: use higher K for faster learning (e.g., 30–40).
   - Optionally cap per-individual Δ to avoid extreme single-match swings.
   - Periodic batch re-estimation (MLE/Bayesian) can correct slow drift, but is optional.

   Below is a concise A vs B-style test plan you can run (simulation + real-data backtests) to validate and choose weighting methods.

## Validation
- Compare two candidate methods (A and B) on accuracy, stability, responsiveness, and protection of pros.
- Here A = existing method and B is the new proposal

### Overview
- Method A: baseline (e.g., logistic or proportional split).
- Method B: your proposed symmetric-protection split (base=0.20, exponential remainder with C=400).
- Repeat experiments on synthetic data (where true solo skills are known) and on held-out real match data (couples-only).

1) Metrics (compute for every trial)
- MAE_solo(t): mean absolute error between estimated r_i and true r_i over time (synthetic).
- RMSE_pair: RMSE between predicted pair strengths and true pair strengths (synthetic).
- Log-loss / Brier score on held-out match outcomes (both synthetic & real).
- Rank correlation (Spearman) between predicted pair ratings and observed pair win rates.
- Pro-protection bias: average Δ per-match for top-decile dancers when paired with bottom-decile partners (should be small).
- Responsiveness (learn speed): number of matches until MAE drops below threshold for novices.
- Stability: variance of rating changes for top-decile dancers over N matches.
- Calibration: group predicted win probabilities into bins and compare observed win rates.
- False-drift test: long-run drift of mean rating (monitor inflation).

2) Synthetic-data experiments
A) Generate population
- N_dancers = 2000 (tunable).
- True r_i ~ Normal(1500, 200) with pro tail: randomly label ~5% as pros with +300 mean shift.
- Simulate partnerships:
  - ProAm pairs (30% of matches)
  - Balanced pairs (40%)
  - Random mixes (30%)
- Pair fusion true function f_true (choose one): harmonic or a blended parametric form (e.g., α·min + (1−α)·max with α=0.6).
- Match noise: sample match outcome with P(ab beats cd) = logistic((R_ab_true − R_cd_true)/s) with s=400. Add judge noise by flipping outcome with small prob or sampling continuous scores.

B) Experimental protocol
- Simulate M matches (e.g., 200k) over time; record sequentially.
- Online mode: feed matches in chronological order and update ratings incrementally using each method.
- Batch mode: at intervals (after 1k, 10k, 50k matches) compute batch-MLE baseline to compare.
- Repeat for multiple seeds (≥20) for confidence.

C) Measure metrics over time
- Plot MAE_solo(t), RMSE_pair(t), log-loss(t).
- Compute pro-protection bias by selecting pros and measuring average per-match negative Δ when paired with weak partners.
- Report averages ± std across seeds.

3) Real-data backtest (if you have historical matches)
A) Data split
- Train on initial window (e.g., first 80% chronologically), test on last 20%.
- Alternatively: rolling-window evaluation.

B) Protocol
- Run online updates on training set for each method.
- Predict probabilities for test matches; compute log-loss, Brier, calibration, and rank correlation with observed placements.
- Identify a set of established pros and compute stability (mean Δ per-match) when they danced many heats with low-rated partners; also inspect any cases where pro rating drops below their frequent amateurs.

4) Specific A vs B comparisons to report
- Accuracy: final MAE_solo & RMSE_pair (synthetic).
- Predictive skill: test-set log-loss (real & synthetic).
- Protection: average negative Δ for pros in ProAm matches (absolute and relative).
- Responsiveness: time-to-converge for novices (matches to reach within ±X points of true).
- Volatility: standard deviation of per-match Δ for top-decile dancers.
- Calibration plots & reliability diagrams.
- Edge-case behavior: proportion of pros that end below their frequent amateurs after N matches.

5) Decision rules (pick winner)
- If Method B yields significantly lower pro negative Δ while MAE_solo and log-loss are within 5% of A → prefer B (protect pros).
- If B protects pros but increases MAE_solo or log-loss >10% → consider hybrid or adjust base/C/K.
- If both comparable on metrics → pick simpler method or the one with better calibration.

6) Parameter sweeps
- For each method sweep K ∈ {10,20,30}, C ∈ {200,400,800}, base ∈ {0.1,0.2,0.3}, p (if power) ∈ {1,2,3}.
- For each setting, run shorter simulations (e.g., 20 seeds) and record metrics; present heatmaps for MAE and pro-bias trade-off.

7) Practical checks & sanity tests
- Conservation test: verify shares sum to 1 and per-match Δ_pair distribution reasonable.
- Stability test: run 10k matches between two fixed-difference pairs and confirm no runaway divergence.
- Sensitivity to sparse data: pick dancers with ≤5 matches and check shrinkage toward prior.

8) Implementation notes
- Use vectorized simulation (NumPy) or PyTorch to parallelize.
- Store per-dancer match counts to optionally vary K for newcomers.
- Seed random generators and fix simulation config for reproducibility.

9) Deliverables you should produce
- Scripts to run simulations + parameter sweeps.
- A summary table: method × metric (mean ± std).
- Plots: MAE_solo over time, log-loss over time, calibration curves, pro Δ distributions.
- Short recommendation based on decision rules above.

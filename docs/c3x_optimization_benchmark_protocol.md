# C3X Knowledge-Informed MFBO Benchmark Protocol

## Scientific question

Does frozen one-dimensional film-cooling knowledge reduce the number of
paper-grid CFD design evaluations required to find a strong feasible design,
beyond the reduction already obtained by standard coarse/paper MFBO?

`N_HF` means the cumulative number of converged paper-grid design evaluations.
It does not mean Fluent nonlinear iterations within one CFD case. Every paper
evaluation used for initialization, calibration, recovery, or optimization is
counted.

## Information hierarchy

| Level | Information source | Optimization role |
| --- | --- | --- |
| L1 | one-dimensional correlation and Sellers row superposition | frozen knowledge prior |
| L2 | 1.96M coarse CFD | numerical low fidelity |
| L3 | 3.78M paper CFD | high-fidelity objective |
| Audit | 6.43M fine CFD | finalist verification only |

The fine result is never returned to an acquisition function.

## Required methods

| ID | Method | L1 knowledge | Coarse CFD | Paper CFD |
| --- | --- | --- | --- | --- |
| RND | random or Latin-hypercube search | no | no | yes |
| SFBO | standard single-fidelity BO | no | no | yes |
| MFBO | standard multi-fidelity BO | no | yes | yes |
| PI-SFBO | prior-informed single-fidelity ablation | yes | no | yes |
| PI-MFBO | proposed method | yes | yes | yes |
| WRONG | deliberately misspecified-prior ablation | wrong | yes | yes |

The primary comparison is MFBO versus PI-MFBO. SFBO quantifies the benefit of
coarse CFD; PI-SFBO separates prior benefit from cross-fidelity benefit; WRONG
tests robustness rather than expected performance.

## Fairness controls

- Use identical design variables, bounds, geometry gate, objective mask,
  constraints, candidate pool, convergence gate, and failure policy.
- Use paired random seeds and the same initial paper designs for every method.
- Give MFBO and PI-MFBO the same initial and maximum coarse/paper budgets.
- Count the five-design ranking/calibration pilot in `N_HF` if its paper data are
  used to train an optimizer. Do not present those observations as free data.
- Freeze L1 equations, coefficients, and uncertainty before viewing benchmark
  outcomes. Literature or a declared calibration subset may be used; final-test
  paper values may not be used to tune the prior.
- Cache identical deterministic CFD design/fidelity pairs across methods, but
  charge their nominal evaluation cost to every algorithm that requests them.
- Use at least five paired seeds; ten is preferred if the CFD budget permits.
- Give every method the same number of fine-grid finalist audits, performed only
  after all paper-level decisions are frozen.

## Surrogates

Standard MFBO uses coarse and paper data without the physics mean:

```text
f3(x) = rho32 f2(x) + delta3(x)
```

The proposed method uses:

```text
m1(x) = frozen one-dimensional knowledge
f2(x) = rho21 m1(x) + delta2(x)
f3(x) = rho32 f2(x) + delta3(x)
```

The acquisition selects only CFD evaluations at L2 or L3. L1 is deterministic
and globally available, so repeatedly "querying" it is not counted as useful
optimization work.

## Endpoints

Primary endpoint:

- median `N_HF` required to reach a frozen fraction of the best paper-level
  improvement over baseline, with paired confidence intervals.

Secondary endpoints:

- best feasible paper objective versus `N_HF`;
- reference simple regret versus `N_HF`;
- probability of reaching the target within the paper budget;
- area under the best-so-far curve;
- equivalent paper cost including coarse evaluations;
- failed CFD count and wall-clock/core-hour cost;
- fine-grid objective of an equal number of finalists from each method.

The reference best must be described as the best paper result observed across
the complete benchmark unless an independent dense reference is available. It
must not be called the global optimum.

## Current implementation gap

The existing controller, ledger, UI, geometry gate, physics prior, and command
adapter are reusable. The current residual GP with fidelity as one input is a
bootstrap implementation, not the final comparator. Before production runs:

1. implement the hierarchical coarse-to-paper surrogate and its zero-prior
   switch;
2. expose fixed, removed, and wrong-prior modes without changing CFD data;
3. validate the implemented fidelity-specific NASA coarse/paper evaluator on a
   completed perturbed-design trial;
4. implement a benchmark runner with paired seeds and strict cost accounting;
5. replace bootstrap EI-per-cost with the frozen standard MFBO acquisition used
   by both MFBO and PI-MFBO, differing only in the L1 knowledge model.

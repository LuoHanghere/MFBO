# C3X Physics-Informed Optimization Framework

## 1. Scope and current boundary

The framework closes the engineering loop around the existing C3X automation:

```text
design x -> geometry gate -> CAD -> mesh -> Fluent setup/solve -> postprocess
         -> result contract -> persistent ledger -> surrogate update -> next x
```

The controller, database, physics prior, constrained cost-aware BO policy,
desktop monitor, and NASA coarse/paper production evaluator are implemented.
The eight-dimensional geometry-to-result loop has completed multiple real CFD
trials. The current standard-MFBO ledger is finishing its frozen startup design
before acquisition-driven proposals begin.

This distinction matters:

- **Automation readiness** means every stage has a parameterized command and a
  machine-readable artifact.
- **Optimization readiness** additionally requires a frozen objective mask,
  accepted constraints, repeatable L1/L2 values, measured costs, and a robust
  failure policy.
- **Publication readiness** requires grid/fidelity validation, repeated random
  seeds, baselines and ablations. A working UI is not evidence for the method.

## 2. Optimization problem

The active optimization uses the eight-dimensional design

\[
x=(s_{SS1},s_{SS2},s_{PS1},s_{PS2},\alpha_{SS},\alpha_{PS},D,N_z).
\]

Here \(s\) is normalized surface arc length, \(\alpha\) is streamwise
injection angle, \(D\) is the shared downstream-row diameter, and \(N_z\) is
the integer number of holes per row over the `14.85 mm` periodic span. The
current bounds are `0.85--1.10 mm` and four to seven holes. The spacing is

\[
\frac{p}{D}=\frac{14.85}{N_zD}.
\]

The primary problem is

\[
\begin{aligned}
\max_x\quad & f(x)=\bar\eta_A(x),\\
\text{s.t.}\quad
& r_m(x)=\dot m_c(x)/\dot m_{c,0}\le 1.001,\\
& x\in\mathcal X_{geom}.
\end{aligned}
\]

The protected area \(A\) must be frozen before production. The current candidate
is the pressure and suction surface downstream of each first variable row. The
complete-vane mean remains a diagnostic, not the optimization target, because
fixed leading-edge cooling dilutes sensitivity to downstream rows.

### 2.1 Hard and probabilistic constraints

Cheap deterministic geometry conditions belong in \(\mathcal X_{geom}\) and are
rejected before CFD. They include bounds, row order, minimum row separation,
hole/plenum clearance, a connected fluid body, and exact periodic topology. They
must not be represented by an arbitrary objective penalty.

Quantities only known after CFD use probabilistic constraints. The frozen first
benchmark constrains coolant mass only; pressure loss remains a recorded
diagnostic because its L2/L3 definition has not yet shown acceptable agreement.
Define the active margin

\[
g_m(x)=1.001-r_m(x).
\]

Positive values are feasible. Independent GP models give

\[
P_f(x)=\Phi\!\left(\frac{\mu_{g_m}}{\sigma_{g_m}}\right).
\]

Mesh and solver failures are separately recorded. The current policy suppresses
the neighborhood of failed designs. The production method should replace this
distance heuristic with a Bernoulli GP feasibility classifier after enough
failures exist to identify a boundary.

## 3. Correlation-informed prior

### 3.1 Single-row model

For row \(i\), the low-order downstream effectiveness is

\[
\eta_i(s)=
\frac{c_0 A_\alpha}
{1+c_1\left[\frac{(s-s_i)L_s}{M s_e}\right]^{c_2}},
\quad s\ge s_i,
\]

where \(L_s\) is surface arc length, \(M\) is the blowing-ratio parameter, and

\[
s_e=\frac{\pi D^2/4}{p}=\frac{\pi D}{4(p/D)}
\]

is the equivalent slot width. The current angle factor is a deliberately smooth
regularizer around the baseline-relevant optimum,

\[
A_\alpha=\exp\left[-\left(\frac{\alpha-\alpha_*}{\sigma_\alpha}\right)^2\right],
\]

with \(\alpha_*=35^\circ\) on the suction side and \(30^\circ\) on the pressure
side. It is not claimed as a universal physical law; its role and sensitivity
must be tested in the wrong-prior ablation.

### 3.2 Multiple-row superposition

Rows on each surface are combined using the Sellers complement product:

\[
\eta_{surface}(s)=1-\prod_i[1-\eta_i(s)].
\]

The prior mean is the protected-region arc integral followed by a suction/
pressure weighted combination:

\[
m_{phys}(x;\theta)=w_s\bar\eta_{SS}(x;\theta)
 +(1-w_s)\bar\eta_{PS}(x;\theta).
\]

The initial parameter vector is

\[
\theta=(c_0,c_1,c_2,M,\sigma_\alpha,w_s)
       =(0.68,0.22,0.82,1.0,18^\circ,0.56).
\]

These values initialize a prior; they are not fitted conclusions. Production
work must calibrate them from literature and baseline/DoE data, preserve their
uncertainty, and report the calibration set separately from optimization tests.

### 3.3 Residual GP

The surrogate does not force CFD to follow the correlation. It decomposes

\[
f(x,\ell)=m_{phys}(x;\theta)+r(x,\ell),
\]

and places the GP on the discrepancy:

\[
r\sim\mathcal{GP}(\mu_r,k_{5/2}^{ARD}).
\]

Thus unlimited data can override a poor prior. The benefit appears only when
the residual is smoother or smaller than the raw response. This must be tested
by comparing normalized signal ranges and cross-validated errors for
\(f\) and \(f-m_{phys}\).

The current exact GP standardizes only the residual and learns ARD length scales
and observation noise by marginal likelihood. It is appropriate for the first
tens to low hundreds of evaluations. Jitter and bounded length scales protect
the online controller against nearly duplicated samples.

## 4. Information and fidelity model

The proposed production study has three information levels, but only two CFD
mesh fidelities:

| Level | Source | Role | Initial relative cost |
|---|---|---|---:|
| L1 | one-dimensional correlation + Sellers row superposition | frozen prior knowledge | 0.001 |
| L2 | coarse CFD | low-cost exploration and feasibility | 0.20 |
| L3 | paper CFD | high-fidelity optimization target | 1.00 |

The fine mesh is an independent numerical audit for the baseline and selected
finalists. It is not an optimization fidelity and is never fed back into the
acquisition loop. This keeps the scientific question focused on whether prior
knowledge reduces the number of paper-grid design evaluations.

Relative CFD costs are placeholders until wall-clock or core-hour measurements
are collected. They must then be estimated as robust medians including geometry,
meshing, retries, solve, and postprocessing rather than solver time alone. The
L1 correlation is deterministic and globally available; its nominal cost only
prevents numerical division by zero and is not counted as a CFD evaluation.

The implemented bootstrap model treats normalized fidelity \(\ell\) as an extra
GP coordinate. This permits immediate testing of persistence and closed-loop
behavior with sparse data. It is not the final paper model.

The proposed knowledge-informed production model is hierarchical residual
co-Kriging:

\[
m_1(x)=m_{phys}(x;\theta),
\]

\[
f_2(x)=\rho_{21}m_1(x)+\delta_2(x),\qquad
f_3(x)=\rho_{32}f_2(x)+\delta_3(x),
\]

where each discrepancy `delta_j` has its own GP. L3/paper observations are
intentionally sparse because reducing their count is the primary outcome.

The standard-MFBO comparator uses the identical L2/L3 CFD data and acquisition
budget but removes `m_1`:

\[
f_3(x)=\rho_{32}f_2(x)+\delta_3(x).
\]

This separation is mandatory. Treating fine CFD as L3 would test mesh count,
not whether one-dimensional prior knowledge reduces expensive evaluations.

Before enabling it, evaluate the frozen L1 model and a baseline-plus-four paired
coarse/paper pilot, then grow the paired CFD calibration set only as required.
Use rank correlation, linear \(R^2\), residual
structure, top-k overlap, perturbation-sign agreement, and optimum-order
preservation. Audit the baseline and the same number of final candidates from
each optimizer on the fine mesh. A single high Pearson correlation is
insufficient. If
the mapping is strongly nonlinear or changes across the space, use NARGP

\[
f_2(x)=g[x,f_1(x)]
\]

or redefine L1 so it preserves the same physics as L2.

## 5. Acquisition policy

### 5.1 Implemented support-preserving prior policy

After a paired coarse/paper baseline anchor and a coarse Latin-hypercube startup,
each CFD fidelity is scored by constrained expected improvement per equivalent
paper-grid cost. L1 is deterministic and globally available; it is not inserted
as a same-scale CFD observation. Its raw correlation is anchored to the declared
paper-grid baseline:

\[
m_{phys}(x)=y_{3,0}+s_m[m_{raw}(x)-m_{raw}(x_0)].
\]

The residual GP is trained only on L2/L3 data. Prior and residual uncertainty
are combined for acquisition as

\[
\sigma_f^2=\sigma_\delta^2+\sigma_{prior}^2,
\]

where the configured prior uncertainty grows with normalized distance from the
baseline and decays as L3 observations accumulate. The PI variant multiplies
the otherwise shared acquisition by an annealed piBO-style weight:

\[
w_\pi(x,t)=w_{min}+(1-w_{min})
\exp\{\beta_t[z_\pi(x)-\max z_\pi]\},\qquad w_{min}>0.
\]

Thus no candidate is assigned zero support, and \(w_\pi\to1\) as \(\beta_t\to0\).
This is an operational protection against a wrong prior, not yet a formal
no-regret proof. The complete bootstrap acquisition is

\[
a(x,\ell)=
\frac{w_\pi(x,t)[EI(x,\ell)+\kappa\sigma_f(x,\ell)]P_f(x,\ell)
      P_{run}(x,\ell)}{\lambda_\ell}.
\]

For maximization,

\[
EI=(\mu-f^+)\Phi(z)+\sigma\phi(z),\qquad
z=\frac{\mu-f^+}{\sigma}.
\]

Standard MFBO sets `physics_prior.enabled=false`, which gives
\(m_{phys}=0\), \(\sigma_{prior}=0\), and \(w_\pi=1\). The small
\(\kappa\sigma\) term avoids a brittle zero-EI controller during early
model mismatch. \(P_{run}\) is currently a smooth exclusion around failed
designs. Sobol candidates are generated in the unit hypercube, decoded, rounded
for integer variables, passed through hard geometry constraints, and checked
against duplicate design/fidelity pairs.

The first benchmark treats coolant mass-flow consistency as the only optimizer
hard constraint. Total-pressure loss remains in every result contract as a
diagnostic; its current mesh sensitivity does not justify a `5%` rejection
threshold. A later study may promote it to a frozen constraint or a second
objective after its definition and fidelity behavior are qualified.

### 5.2 Final paper policy

The frozen target is constrained, cost-aware multi-fidelity knowledge gradient:

\[
(x^*,\ell^*)=\arg\max_{x,\ell}
\frac{KG(x,\ell)P_f(x,\ell)}{\lambda_\ell}.
\]

MFKG values the expected increase in the best posterior decision after observing
a design at a chosen fidelity. This is preferable to simply dividing EI by cost
when a cheap observation can change beliefs about many expensive candidates.
The controller API deliberately separates proposal from evaluation so the
bootstrap policy can be replaced by BoTorch `qMultiFidelityKnowledgeGradient`
without changing storage, UI or CFD execution.

Required comparisons are:

1. random/LHS search evaluated on paper CFD;
2. single-fidelity BO using paper CFD only;
3. standard MFBO using coarse + paper CFD without L1 knowledge;
4. the proposed knowledge-informed MFBO using L1 + coarse + paper;
5. a knowledge-informed single-fidelity ablation using L1 + paper;
6. fixed, removed, and deliberately wrong-prior ablations.

All methods use the same design bounds, initial paper anchors, candidate pool,
random seeds, convergence gates, and maximum paper-evaluation budget. The main
abscissa is cumulative paper-grid design evaluations `N_HF`, not Fluent solver
iterations. Report best-so-far paper objective, simple regret, paper evaluations
to reach a frozen target, success probability, and equivalent paper cost over at
least five independent seeds. Fine-grid results are reported afterward as an
equal-count audit and never used to choose the next design.

## 6. Persistence and state semantics

`ExperimentStore` uses SQLite WAL mode. Every trial records:

- exact decoded design and fidelity;
- proposal source and posterior diagnostics;
- pending/running/completed/failed state;
- objective, constraints and auxiliary metrics;
- relative cost, run directory, timestamps and traceback;
- append-only human-readable events.

On restart, a trial left in `running` is marked failed rather than silently
rerun. This prevents duplicated expensive jobs. A future scheduler adapter may
reconcile remote job IDs before making that decision.

Pause means **finish the current external trial, then stop scheduling**. Stop has
the same safety rule and returns the controller to idle. Killing Fluent midway
can corrupt artifacts and leak license state, so force termination is not an
ordinary UI action.

## 7. Evaluator contract

The demo evaluator provides a deterministic synthetic discrepancy and exercises
the entire loop without Fluent. A production command evaluator runs configured
stages and requires each trial directory to end with `result.json`:

```json
{
  "objective": 0.4631,
  "constraints": {
    "coolant_mass_ratio": 0.997,
    "loss_ratio": 1.013
  },
  "metrics": {
    "mass_imbalance_kg_s": 7.3e-7,
    "wall_y_plus_p95": 0.94,
    "iterations": 387,
    "converged": true
  }
}
```

The production pipeline must fail the trial instead of writing an objective if
geometry, mesh quality, mass balance, convergence, temperature sanity or output
completeness gates fail. Numerical failure is information about feasibility; it
must never be disguised as a very poor but valid objective.

Three consecutive failures open a controller circuit breaker. This prevents a
shared fault such as license checkout, invalid template CAD, or a broken Fluent
installation from generating an unlimited series of failed trials.

## 8. Desktop monitor

Launch with:

```powershell
.\.venv\python.exe scripts\run_optimization_ui.py
```

The UI shows controller state, equivalent L2 budget, current trial, best feasible
objective, convergence history, trial table, event stream and selected design.
It can start/resume, pause, stop scheduling and open an archived trial directory.
The interface intentionally does not expose GP hyperparameters or CFD settings;
those are versioned configuration, not knobs to change during a run.

For a headless demo:

```powershell
.\.venv\python.exe scripts\run_optimization.py
```

Delete neither the SQLite database nor completed trial directories to restart.
Use a new database/run root for a new experimental seed or method. Mixing method
changes into one ledger destroys provenance.

## 9. Gates before production optimization

1. Restore a legitimate Fluent 2024 R2-compatible license and verify independent
   mesh and solver feature checkout.
2. Finish the paper-grid baseline and accept convergence, mass balance, wall
   \(y^+\), temperature bounds and mesh hot-cell diagnostics.
3. Freeze the protected-area mask and baseline objective/constraints.
4. Generate 8--12 geometry-only designs and measure hard-gate failure modes.
5. Run the initial L1 DoE; measure actual end-to-end cost and repeatability.
6. Pair 15--20 selected designs at L1/L2; diagnose fidelity correlation.
7. Calibrate the prior only on declared calibration data; freeze it before the
   comparative optimization experiment.
8. Replace bootstrap cEI with MFKG and validate all algorithms on the synthetic
   plant and an offline surrogate before spending the formal CFD budget.

## 10. Coarse screening campaign

The first live campaign uses `configs/c3x_optimization_coarse.yaml`. It varies
only four row positions and two injection angles while fixing `D=0.99 mm` and
five holes per span period. This isolates optimizer behavior before introducing
coolant-area and integer topology changes.

The accepted periodic-v2 coarse baseline is imported as trial 1 with protected-
area `eta_bar=0.4889209`. Four reproducible LHS candidates have passed the same
coupled plenum-clearance gate used by the CAD builder. Each new trial rebuilds
CAD and the coarse mesh; the baseline mesh is not deformed or reused for changed
hole geometry. The live campaign remains idle until Fluent v242 can check out a
compatible license.

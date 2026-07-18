# NASA 44344 Multi-Fidelity Ranking Pilot

## Purpose

This pilot calibrates the three information levels used by the proposed method:
L1 low-order film-cooling knowledge, L2 coarse CFD, and L3 paper CFD. It also
tests whether the two CFD meshes order the same controlled geometry changes
before a long optimization campaign. It is not an optimization result.

## Frozen design set

The machine-readable source is
`runs/optimization/nasa_ranking_pilot/controlled_candidates.json`. All five
designs pass the coupled plenum/hole geometry gate.

| ID | Controlled change from baseline | Geometry gate | Minimum cavity clearance (mm) |
| --- | --- | --- | ---: |
| BASELINE | none | pass | 0.852 |
| SS_ROWS_DOWN | SS1 and SS2 `s/s0` +0.008 | pass | 0.852 |
| SS_ANGLE_STEEP | suction angle +5 deg | pass | 0.852 |
| PS_ROWS_DOWN | PS1 and PS2 `s/s0` +0.008 | pass | 0.929 |
| PS_ANGLE_STEEP | pressure angle +5 deg | pass | 1.124 |

Diameter (`0.99 mm`), span count (`5`), plenums, leading-edge cooling, inlet
and outlet geometry, periodic boundaries, mainstream conditions, and prescribed
NASA coolant mass flows remain fixed.

## Evaluation matrix

- L1/knowledge: evaluate the frozen one-dimensional correlation and Sellers
  superposition for all five designs at negligible cost.
- L2/coarse: evaluate all five designs.
- L3/paper: evaluate all five designs with the same design IDs.
- Fine mesh: retain the completed baseline and audit selected final designs; it
  is not an optimization fidelity.

Use the frozen thermal stopping rule from `c3x_nasa_validation_protocol.md`.
Do not compare a thermally unconverged L1 value against a converged L2 value.

## Acceptance gate

Report protected-area eta and the same feasibility diagnostics for every CFD
pair. Accept coarse CFD for optimization screening only if:

- Spearman rank correlation across the five coarse/paper pairs is at least `0.9`;
- the sign of all four baseline-to-perturbation eta changes agrees between
  coarse and paper;
- top-2 overlap is nonzero and the best coarse design has acceptably small paper
  regret;
- mass-flow, convergence, and geometry gates pass for every compared design.

The diagnostic total-pressure difference is recorded but is not a publication
constraint until its normalization and grid behavior are frozen.

The L1 knowledge source is assessed separately by comparing raw CFD variation
against residual variation after subtracting the frozen correlation. Its value
is established only by the later optimizer ablation, not by requiring the
correlation to match paper CFD pointwise.

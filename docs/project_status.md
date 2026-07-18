# C3X MFBO Project Status

Status frozen on 2026-07-18.

## Geometry

The complete vane contains nine cooling rows. Five NASA leading-edge rows are
fixed in the CAD template. Four downstream rows are parameterized: two suction
rows (`SS1`, `SS2`) and two pressure rows (`PS1`, `PS2`). Each downstream row
uses the same diameter and integer number of holes over the `14.85 mm`
periodic span.

The active eight-dimensional design vector is

```text
(SS1_s, SS2_s, PS1_s, PS2_s,
 suction_angle_deg, pressure_angle_deg,
 diameter_mm, span_count)
```

with `diameter_mm` in `[0.85, 1.10]` and `span_count` in `{4, 5, 6, 7}`.
The geometry gate enforces row ordering, separation, plenum clearance, and
integer periodic topology before CFD is launched.

## Automated Pipeline

The production path is operational end to end:

1. Decode and screen an 8D design.
2. Generate the fixed-leading-edge plus parameterized-downstream SCDOC.
3. Generate an L2 coarse or L3 paper mesh through native CAD import.
4. Apply measured NASA coolant mass flow and the frozen solver settings.
5. Export pressure, temperature, cooling effectiveness, mass balance, and y+.
6. Validate the strict `result.json` contract and record the SQLite trial.
7. Save the hole-layout, cooling map, and baseline-difference projections.

The fine mesh is excluded from optimizer training and retained as an external
audit fidelity.

## Validation State

- Aerodynamic pressure alignment is accepted for the declared NASA quantities.
- L2/L3/fine protected effectiveness remains mesh sensitive and is treated as
  a multi-fidelity response, not a grid-independent scalar.
- L2 and L3 are the optimizer fidelities; L1 is low-order film-cooling
  knowledge used only by PI-MFBO.
- Coolant mass flow is imposed and checked. Pressure loss remains diagnostic
  until its cross-fidelity definition is stabilized.
- Current L2 startup trials have continuity residuals near `4e-3` and vane-wall
  `y+` p95 near `8.5`.

## Standard MFBO Ledger

Configuration: `configs/c3x_nasa_standard_mfbo_8d.yaml`.

- Completed trials: `13`.
- Completed L2 trials: `10`.
- Completed L3 trials: `3`, forming three exact L2/L3 pairs.
- Failed trials: `0`.
- Used budget: `5.0 / 16.5` equivalent L3 evaluations.
- Required L2 startup count: `18`; eight L2 startup evaluations remain.

The four new span-count-stratified L2 points produced protected-area
effectiveness values of `0.60550`, `0.67824`, `0.71853`, and `0.74902` for
`N=4,5,6,7`, respectively. The accepted coarse baseline is `0.68221`. Because
all eight variables differ between these space-filling points, this sequence
is descriptive and is not yet a causal hole-count result.

After the remaining eight L2 startup evaluations, the next proposal is the
first `standard_constrained_ei` step: the optimizer will jointly select the 8D
design and L2/L3 fidelity. Existing L3 pairs all lie on the inherited
`diameter=0.99 mm`, `span_count=5` slice. At least two new paired L3 checks near
the released diameter/count extremes are recommended before making a strong
publication claim about the learned L2-to-L3 relationship.

## Immediate Next Actions

1. Complete the remaining eight stratified L2 startup evaluations.
2. Quantify objective stability between solver checkpoints and replace the
   fixed 1800-iteration rule only if the monitored objective supports it.
3. Add two 8D L2/L3 calibration pairs spanning the released diameter/count
   variables.
4. Execute the first acquisition-driven standard-MFBO steps with the prior off.
5. Freeze identical initial data, costs, budgets, and seeds for standard MFBO,
   PI-MFBO, paper-only BO, and ablation comparisons.

## Repository Data Boundary

Git includes source, tests, configuration, documentation, and small JSON result
records. Fluent `.cas/.dat/.msh` files, CAD/Workbench binaries, transcripts,
SQLite ledgers, and large face-level CSV exports remain local.

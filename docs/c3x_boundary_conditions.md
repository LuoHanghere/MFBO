# C3X Boundary Conditions

## Recommended Baseline

Use NASA CR-182133 run 44344 for the first quantitative validation. It is the
Hylton condition reproduced in Kumar et al.: `Pt1=285.13 kPa`, `Tt1=701 K`,
`Ma1=0.17`, `Ma2=0.89`, `Re2=2.03e6`, and inlet turbulence intensity `6.5%`.
With zero Fluent operating pressure, the inferred ideal-gas pressure-outlet
value is `170416.542 Pa`.

NASA Table VI-B gives the resolved-plenum total conditions:

| Plenum | Pc/Pt | Tc/Tg | Tc [K] | Full-vane mdot [kg/s] | 14.85 mm mdot [kg/s] |
|---|---:|---:|---:|---:|---:|
| Suction | 1.051 | 0.85 | 595.85 | 0.01340 | 0.0026114 |
| Leading edge | 1.048 | 0.86 | 602.86 | 0.00638 | 0.0012433 |
| Pressure | 1.050 | 0.83 | 581.83 | 0.00752 | 0.0014655 |

The periodic-slice mass flows are monitoring targets, scaled by
`14.85/76.20`; pressure and temperature remain the imposed inlet conditions.

## Kumar Parametric Point

Kumar et al. specify mainstream pressure `285130 Pa`, mainstream temperature
`1773 K`, coolant temperature `773 K`, and coolant/mainstream pressure ratio
`1.15`. Their solver is steady RANS with ideal-gas air, realizable k-epsilon,
SIMPLE coupling, flow residual `1e-5`, energy residual `1e-8`, and `y+<1`.
Their grid study uses `2.0M`, `3.5M`, and `4.5M` cells and selects `3.5M`.

The same paper also states a temperature ratio of `3`, which conflicts with
the explicit temperatures (`1773/773=2.294`). Automated runs therefore use
the dimensional temperatures unless a ratio-3 sensitivity is explicitly
requested.

## Thermal Wall Mode

Use adiabatic no-slip walls for film-effectiveness optimization. NASA heat
transfer validation is a separate workflow: Table VI reports only the
arc-weighted average `Tw/Tg=0.79` for run 44344, while the local wall
temperature distribution is needed for a defensible Stanton/HTC comparison.

Sources: NASA CR-182133 PDF pages 30-34 (report pages 26-30), and Kumar et al.
PDF pages 3-7 (book pages 20-24).

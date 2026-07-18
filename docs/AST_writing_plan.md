# AST manuscript writing plan

Working target: *Aerospace Science and Technology* (AST), Elsevier.

Project working title:
Correlation-informed multi-fidelity Bayesian optimization for film-cooling hole layout on a C3X turbine vane

Status of this document:
This is a drafting and execution plan, not a claim that all results already exist. Result-dependent statements are written as placeholders until CFD, BO, validation, and ablation data are available.

## 1. Journal constraints to build into the draft

Official AST Guide for Authors source:
https://www.sciencedirect.com/journal/aerospace-science-and-technology/publish/guide-for-authors

AST fit:
- The journal scope explicitly includes aerospace research with applications related to aircraft, launchers, propulsion, fluid dynamics, turbomachinery, test facilities, and complex system engineering.
- Our manuscript should frame the contribution as an aerospace/turbomachinery design-method paper, not as a pure heat-transfer mechanism paper.

Submission and review format:
- AST uses double-anonymized peer review.
- Prepare two separate files:
  - Title page: title, authors, affiliations, corresponding author details, acknowledgements, competing-interest statement if not submitted separately.
  - Anonymized manuscript: main manuscript, references, tables, and figures, with no author names, affiliations, acknowledgements, self-identifying file names, or self-identifying wording.
- Word submissions must use editable `.doc` or `.docx` source files and single-column layout.

Front matter:
- Abstract: maximum 250 words; standalone; no references unless essential.
- Keywords: 1 to 7 English keywords.
- Highlights: 3 to 5 bullets, submitted as a separate editable file; each bullet maximum 85 characters including spaces.

Article structure:
- Numbered sections are required or strongly expected: 1, 1.1, 1.1.1, etc.
- Do not number the abstract.
- Use section numbers when cross-referencing.
- Theory/calculation sections should connect theoretical background to practical implementation.
- Appendices are labelled A, B, etc.; equations, figures, and tables in appendices use A.1, B.1 numbering patterns.

Figures, tables, equations:
- Equations must be editable text, numbered consecutively, and cited in the text.
- Tables must be editable text, cited in the text, numbered consecutively, and include captions.
- Figures must be cited in the text, numbered by order of appearance, and supplied as separate files with clear names.
- Figure captions need a short title plus explanatory description.
- Prefer vector figures such as EPS or PDF for line drawings; raster images must meet Elsevier resolution requirements.
- Do not use generative AI tools to create or alter manuscript figures.

Data, code, declarations:
- AST requires a data availability statement at submission.
- Research data should be deposited and linked where possible, or a clear reason must be stated if data/code cannot be shared.
- CRediT author contribution roles are required for corresponding authors.
- Funding sources and sponsor roles must be disclosed.
- Competing interests must be declared.
- Generative AI use in manuscript preparation must be declared if used beyond basic grammar/spelling/reference tools.

References:
- Initial submission can use any consistent style if complete, but AST reference style uses numbered citations in square brackets.
- The draft should use numbered references from the beginning to avoid late-stage citation churn.
- DOI links are recommended where available.
- Every in-text citation must appear in the reference list and vice versa.

## 2. Core positioning for AST

Main claim:
Classical film-cooling correlations and Sellers superposition can be used as a physics-based GP prior mean inside a multi-fidelity Bayesian optimization workflow, reducing the number of expensive high-fidelity CFD evaluations needed to improve C3X film-cooling effectiveness.

What AST should care about:
- Aerospace/turbomachinery relevance: turbine vane film cooling is directly within propulsion and turbomachinery.
- Methodological value: the method reduces high-cost CFD budget in design optimization.
- Engineering credibility: C3X validation and L1/L2 fidelity diagnostics prevent the method from looking like a toy BO exercise.
- Reproducibility: automated CAD, meshing, solving, post-processing, and BO bookkeeping are part of the contribution.

What not to overclaim:
- Do not claim new film-cooling physics as the primary contribution in Paper 1.
- Do not claim LES-level truth if the optimization loop is RANS-based.
- Do not claim robust superiority before wrong-prior and multiple-seed tests exist.

## 3. Draft architecture

### Title options

Preferred:
Correlation-informed multi-fidelity Bayesian optimization for film-cooling hole layout on a C3X turbine vane

Shorter alternative:
Physics-prior multi-fidelity Bayesian optimization of C3X turbine-vane film cooling

More method-focused alternative:
A correlation-informed Bayesian optimization framework for sample-efficient turbine-vane film-cooling design

### Abstract skeleton

Write last. Keep under 250 words.

Sentence roles:
1. Problem: Film-cooling layout optimization needs expensive CFD and black-box BO ignores established correlations.
2. Method: We use film-cooling correlations and Sellers superposition as a GP prior mean, with learnable prior coefficients.
3. Multi-fidelity layer: L1 correlation knowledge, L2 coarse RANS, L3 paper-quality RANS, and cost-aware acquisition; fine RANS is an external audit.
4. Case: C3X turbine vane, validated against no-film and film-cooled reference data.
5. Results: Insert paper-grid evaluation reduction, final effectiveness improvement, constraint behavior, and prior-mismatch robustness.
6. Conclusion: The framework makes physics-informed BO practical for aerospace cooling design.

Required placeholders:
- `[RESULT: validation error against C3X no-film data]`
- `[RESULT: validation error against C3X film-cooled baseline]`
- `[RESULT: L1/L2 correlation and cost ratio]`
- `[RESULT: equivalent L2 reduction vs vanilla BO]`
- `[RESULT: final improvement in eta_bar and pressure-loss change]`

### Highlights draft

Each final bullet must be <=85 characters including spaces.

Current draft candidates:
- Film-cooling correlations define a Gaussian-process prior mean.
- Multi-fidelity BO jointly selects C3X designs and CFD fidelity.
- Learnable prior coefficients improve robustness to correlation bias.
- Cost-aware acquisition reduces equivalent high-fidelity CFD calls.
- C3X validation links optimization gains to turbine-vane cooling.

These need final character-count checks before submission.

### Keywords

Candidate keywords:
- Film cooling
- Bayesian optimization
- Multi-fidelity CFD
- Gaussian process
- Turbine vane
- Physics-informed surrogate
- C3X

## 4. Section-by-section writing plan

### 1. Introduction

Goal:
Explain why this is an aerospace design problem and why a physics-informed BO workflow is needed.

Planned content:
- Gas-turbine vane thermal protection requires efficient coolant use.
- Film-cooling hole layout optimization is expensive because each design needs CAD, mesh, CFD solve, and post-processing.
- Black-box BO reduces evaluations but starts from a weak prior.
- Film-cooling has decades of empirical knowledge: row correlations, blowing-ratio trends, Sellers-type superposition.
- Gap: these correlations are rarely formalized as Bayesian priors in an online multi-fidelity optimization workflow for realistic turbine-vane CFD.
- Contribution list:
  1. correlation-informed GP prior mean for film-cooling effectiveness;
  2. learnable prior coefficients and prior-mismatch robustness tests;
  3. cost-aware multi-fidelity BO with L1-knowledge/L2-coarse/L3-paper hierarchy;
  4. automated C3X CAD-mesh-solve-postprocess workflow;
  5. validation and sample-efficiency evidence on a turbine-vane case.

Do not write:
- Do not present final numerical superiority until result figures exist.

### 2. Related work

Suggested subsections:
- 2.1 Film-cooling design and optimization
- 2.2 Bayesian optimization for expensive aerospace CFD
- 2.3 Multi-fidelity surrogate modeling and acquisition
- 2.4 Prior-guided and physics-informed Bayesian optimization

Core contrast:
- Existing film-cooling optimization often focuses on final performance or offline surrogate accuracy.
- Existing prior-guided BO is often demonstrated on synthetic, hyperparameter, or generic benchmark tasks.
- Our angle is engineering-prior construction from film-cooling correlations plus real CFD fidelity scheduling.

### 3. Problem formulation

Suggested subsections:
- 3.1 C3X vane film-cooling layout variables
- 3.2 Objective and constraints
- 3.3 Fidelity hierarchy and cost model

Equations:
- Area-averaged adiabatic effectiveness: eta_bar.
- Coolant mass-flow constraint.
- Pressure-loss soft constraint.
- Equivalent high-fidelity cost metric.

Required table:
Table 1. Design variables, ranges, and feasibility constraints.

### 4. Correlation-informed Bayesian surrogate

Suggested subsections:
- 4.1 Film-cooling correlation prior
- 4.2 Sellers superposition for multiple rows
- 4.3 GP residual model with learnable prior coefficients
- 4.4 Prior-mismatch model for robustness evaluation

Main logic:
The GP learns residuals between CFD and the physics prior, rather than learning the full response from a zero mean.

Required equations:
- Single-row effectiveness correlation.
- Sellers total effectiveness.
- GP model with m_phys(x; theta).
- MAP estimation for prior coefficients and kernel hyperparameters.

Required figure:
Fig. 1. Workflow schematic: design vector -> physics prior -> GP residual -> acquisition -> CFD -> update.

### 5. Multi-fidelity optimization framework

Suggested subsections:
- 5.1 L1/L2/L3 information models
- 5.2 Co-Kriging or NARGP fidelity coupling
- 5.3 Cost-aware acquisition function
- 5.4 Constraint and failure handling
- 5.5 Algorithm summary

Required table:
Table 2. Information levels, CFD mesh targets, approximate cost, and role.

Required algorithm block:
Algorithm 1. Correlation-informed multi-fidelity BO loop.

Decision rule:
If L2/L3 correlation is high enough, couple coarse and paper CFD.
If not, retain the L1 prior but run single-fidelity paper-grid BO.

### 6. CFD case setup and validation protocol

Suggested subsections:
- 6.1 C3X geometry and operating conditions
- 6.2 Automated CAD and mesh generation
- 6.3 Solver settings and convergence criteria
- 6.4 No-film validation
- 6.5 Film-cooled baseline validation
- 6.6 Grid and fidelity diagnostics

Required figures:
- Fig. 2. C3X computational domain and film-row layout.
- Fig. 3. No-film validation: surface pressure or heat-transfer comparison.
- Fig. 4. Film-cooled baseline validation: effectiveness or wall-temperature comparison.

Required tables:
- Table 3. Boundary conditions and operating conditions.
- Table 4. Mesh/fidelity diagnostics and computational cost.

### 7. Optimization experiment design

Suggested subsections:
- 7.1 Compared algorithms
- 7.2 Initial design and random seeds
- 7.3 Evaluation metrics
- 7.4 Ablation and robustness tests

Algorithm columns:
- Random or LHS baseline.
- Vanilla BO: L2-only, zero-mean GP.
- MFBO: L1/L2, zero-mean multi-fidelity surrogate.
- piBO baseline: acquisition-layer prior.
- Ours: correlation-informed prior mean + MFBO.
- Ours without learnable theta.
- Ours with wrong prior.

Metrics:
- Best-so-far eta_bar versus equivalent L2 cost.
- Equivalent L2 evaluations to reach target improvement.
- Final design eta_bar, pressure loss, coolant flow.
- Prior-mismatch performance retention.
- Mesh/solver failure rate and handling.

### 8. Results

Write only after data exist.

Required result figures:
- Fig. 5. L1 versus L2 response correlation and cost ratio.
- Fig. 6. Best-so-far eta_bar versus equivalent L2 evaluations.
- Fig. 7. Ablation: zero mean, fixed prior, learnable prior, wrong prior.
- Fig. 8. Final optimized layout versus baseline.
- Fig. 9. Surface effectiveness contours for baseline and optimized design.

Minimum result package for AST submission:
- At least 3 to 5 random seeds for the main comparisons.
- One validated C3X baseline.
- One final L2 confirmation of the selected optimum.
- One prior-mismatch robustness experiment.
- Clear cost accounting in equivalent L2 units.

### 9. Discussion

Suggested subsections:
- 9.1 Why the prior helps when correlations are imperfect
- 9.2 When multi-fidelity coupling helps or fails
- 9.3 Engineering implications for turbine-vane cooling design
- 9.4 Limitations

Limitations to state honestly:
- RANS-based optimization is not a substitute for high-fidelity turbulence-resolved heat-transfer truth.
- The current study uses C3X and may need transfer tests for other vane families.
- Correlation quality controls early BO acceleration.
- The framework optimizes the chosen objective; robust multi-condition design is future work unless completed.

### 10. Conclusions

Conclusion should be short and result-driven.

Template:
- We developed ...
- On C3X, validation showed ...
- The method reduced equivalent L2 evaluations by ...
- Ablations showed ...
- The framework provides ...

Avoid:
- Vague phrases like "promising" without numbers.
- Introducing new limitations or new methods not discussed earlier.

### Back matter

Required sections:
- CRediT authorship contribution statement.
- Declaration of generative AI and AI-assisted technologies, if applicable.
- Declaration of competing interest.
- Funding.
- Data availability statement.
- Acknowledgements only in title page for double-anonymized review.
- References.

## 5. Figure and table production checklist

Figure naming:
- Figure_1_Workflow.pdf
- Figure_2_C3X_domain_layout.pdf
- Figure_3_NoFilm_validation.pdf
- Figure_4_FilmBaseline_validation.pdf
- Figure_5_L1_L2_correlation.pdf
- Figure_6_BO_convergence.pdf
- Figure_7_Ablation_prior.pdf
- Figure_8_Optimized_layout.pdf
- Figure_9_Effectiveness_contours.png

Table naming:
- Table 1. Design variables and bounds.
- Table 2. Fidelity hierarchy.
- Table 3. CFD operating conditions.
- Table 4. Mesh and cost diagnostics.
- Table 5. BO algorithm settings.
- Table 6. Final performance comparison.

AST figure rules to remember:
- Cite every figure in text before or at first appearance.
- Number in appearance order.
- Keep figure text minimal and legible.
- Prefer vector format for line plots.
- Do not use generative AI to create or alter scientific artwork.

## 6. Data required before the Results section can be written

Validation data:
- No-film C3X baseline compared with experimental surface pressure or heat-transfer data.
- Film-cooled baseline compared with available C3X film-cooling data.
- Mesh independence or at least L1/L2 mesh-diagnostic evidence.

Multi-fidelity diagnostics:
- L1/L2 paired data for 15 to 20 designs.
- Pearson/Spearman correlation.
- Cost ratio in measured wall time or core-hours.
- Decision: AR(1), NARGP, or single-fidelity fallback.

BO data:
- Initial DoE size and seed definitions.
- Best-so-far curves for each algorithm.
- Equivalent L2 cost accounting.
- Final design verification at L2.
- Failure log: CAD, mesh, solver convergence, constraint violation.

Ablation data:
- Fixed prior versus learnable prior.
- Correct prior versus deliberately perturbed prior.
- Prior-as-mean versus acquisition-layer prior, if piBO is implemented.

## 7. Writing sequence

Recommended order:
1. Finalize title, contribution statement, and section outline.
2. Write Sections 1 to 5 from the current method plan.
3. Build all table shells and figure placeholders.
4. Write Section 6 from current CFD pipeline details, marking validation results as placeholders.
5. Write Section 7 as a pre-registered experiment matrix.
6. Run the validation and BO experiments.
7. Fill Section 8 with figures and numbers.
8. Write Discussion and Conclusions after result interpretation stabilizes.
9. Write abstract and highlights last.
10. Run citation, anonymity, data availability, and declaration checks.

## 8. Desk-reject risk control

Before submission, check:
- Does the paper contain author-identifying text in the anonymized manuscript?
- Does the abstract contain unsupported numerical claims?
- Are results strong enough for AST, not just a workflow description?
- Are all figures cited and named logically?
- Are tables editable and not duplicated by prose?
- Are references complete and consistently numbered?
- Is the data availability statement specific?
- Does the manuscript explain why this is an aerospace/turbomachinery contribution?

Minimum threshold for a serious AST first submission:
- Demonstrated validation against C3X reference data.
- Demonstrated sample-efficiency gain over at least one strong BO baseline.
- Honest prior-mismatch robustness result.
- Complete method reproducibility details.
- Clear aerospace design relevance.

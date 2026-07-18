# Section 1 — Introduction (AST draft)

> Draft of the manuscript Introduction for *Aerospace Science and Technology* (double-anonymized).
> Status: method/positioning prose is final-form; all numerical claims are `[RESULT: ...]` placeholders until data exist.
> Anonymity: no author names, affiliations, or "in our previous work" phrasing. Citation style: numbered, square brackets.
> Reference numbers are global across the manuscript and shared with `AST_section4_correlation_informed_surrogate.md`. The master list at the bottom of this file is provisional and must be completed with DOIs and full bibliographic detail, then verified, before submission.

---

## 1. Introduction

First-stage turbine vanes operate in a gas stream hotter than the melting point of the alloy, and film cooling is the primary mechanism that keeps the metal within structural limits while preserving cycle efficiency [1]. The vane surface is protected by rows of discrete holes that inject coolant into the boundary layer; the resulting adiabatic effectiveness depends strongly on hole position, diameter, spanwise pitch, injection angle, and the interaction between successive rows [1]. Because every percent of coolant diverted from the core flow penalizes thermodynamic performance, the engineering objective is to maximize surface protection for a fixed coolant budget. Improving a film-cooling layout is therefore a constrained design-optimization problem of direct relevance to aerospace propulsion.

Evaluating a candidate layout is expensive. Each design requires geometry construction, mesh generation, a converged Reynolds-averaged Navier–Stokes (RANS) solution, and post-processing to extract area-averaged effectiveness and aerodynamic loss. A single high-fidelity evaluation on a realistic vane can take hours to a day of wall-clock time on a workstation-class machine, which limits a design study to tens of high-fidelity evaluations. The cost of the objective, rather than the dimensionality of the design space, is the binding constraint on what can be optimized in practice.

Bayesian optimization (BO) is the established response to expensive black-box objectives [7,8,9]. A Gaussian-process (GP) surrogate models the objective and its uncertainty, and an acquisition function proposes the next design by balancing exploration against exploitation [10]. BO has been applied to turbine film-cooling and related thermal-design problems, including data-driven layout optimization for endwall and blade cooling [19,20]. In the standard formulation, however, the GP is given a zero prior mean, which encodes the assumption that nothing is known about the response before data are collected. For film cooling this assumption discards a large body of established engineering knowledge.

Film-cooling effectiveness has been studied for six decades, and that knowledge is already expressed in compact mathematical form. Single-row effectiveness follows well-characterized decay correlations in the streamwise direction as a function of blowing ratio and hole geometry [4,5], and the combined effect of several rows is captured by the Sellers superposition model [6]. These correlations are not exact on a curved, pressure-loaded vane surface, where row coupling, curvature, and transition shift the response, but they reproduce the dominant trend of the objective at negligible cost. They are precisely the kind of structured prior knowledge that a zero-mean surrogate ignores.

A separate line of work injects user beliefs about the location of the optimum into BO. πBO multiplies the acquisition function by a user-supplied density and anneals its weight over iterations, retaining a no-regret guarantee [15]; ColaBO reshapes the GP posterior with a prior over the optimizer or the objective [16]; BOPrO places a prior on the location of the optimum [17]. These methods are powerful, but they have been demonstrated mainly on synthetic benchmarks and hyperparameter-tuning tasks, and they treat the prior as an abstract belief to be supplied by the user. They do not address how an engineering prior should be *constructed* from domain correlations, nor how such a prior behaves inside a realistic, CFD-in-the-loop optimization with heterogeneous evaluation cost.

This is the gap addressed here. Classical film-cooling correlations and the Sellers superposition model are formalized as a parametric, learnable prior mean of the GP surrogate, so that the surrogate models only the residual between CFD and the physics prior. Domain knowledge enters at the surrogate-mean layer, where it is incorporated through the Bayesian posterior and is automatically dominated by data as observations accumulate, rather than at the acquisition layer, where it must be annealed away by a hand-tuned schedule [15]. The acquisition function is then left in a standard, cost-aware multi-fidelity form. Separating *where the prior enters* (the surrogate mean) from *how the next evaluation is chosen* (the acquisition) keeps both the prior injection principled and the convergence behavior intact, and it makes the method straightforward to state and to reproduce.

The framework is organized around three information levels. A one-dimensional correlation and Sellers superposition model defines L1 and supplies structured prior knowledge at negligible cost. Coarse RANS defines L2, while the paper-quality RANS mesh defines L3 and is the high-fidelity optimization target. A still finer mesh is used only to audit selected final designs and is not fed back into the optimization. Whether L2 and L3 are coupled through a multi-fidelity surrogate is decided from a measured correlation diagnostic before production optimization, so that the L1 prior contribution stands on its own even when coarse-to-paper coupling is not warranted. The case study is the NASA C3X turbine vane, for which public geometry and experimental data exist for both no-film [2] and film-cooled [3] configurations, enabling a two-step validation of the CFD setup before optimization.

The contributions of this paper are:

1. **Correlation-informed prior construction.** A method for turning classical single-row film-cooling correlations [4,5] and Sellers superposition [6] into a parametric prior mean for a GP surrogate of area-averaged effectiveness, so that the surrogate learns a smaller, smoother residual rather than the full response.
2. **Learnable, robustness-tested prior.** The prior coefficients are estimated jointly with the kernel hyperparameters by maximum a posteriori, and a controlled prior-mismatch study quantifies how the method behaves when the correlation prior is deliberately wrong.
3. **Cost-aware multi-fidelity optimization with a diagnosed information hierarchy.** An L1-knowledge/L2-coarse/L3-paper hierarchy with a cost-aware acquisition function that jointly selects the design and CFD fidelity, and a pre-optimization diagnostic that decides whether L2-L3 coupling is used.
4. **An automated turbine-vane evaluation workflow.** A reproducible CAD-to-mesh-to-solve-to-post-process pipeline for the C3X vane that returns structured failure records, so that geometry, meshing, and convergence failures are handled as part of the optimization rather than aborting it.
5. **Validation and sample-efficiency evidence.** Two-step validation against C3X reference data [2,3] and a comparison of the equivalent high-fidelity evaluation budget required by the proposed method and by standard BO baselines.

Consistent with the scope of a first paper, the contribution is methodological. No new film-cooling physics is claimed, the optimization is RANS-based and is not presented as a substitute for turbulence-resolved heat-transfer truth, and any performance gain is reported only after multiple-seed and prior-mismatch tests. `[RESULT: headline sample-efficiency and effectiveness figures, inserted only after the experiments of Sections 7–8.]`

The remainder of the paper is organized as follows. Section 2 reviews film-cooling optimization, Bayesian optimization for expensive CFD, multi-fidelity surrogate modeling, and prior-guided BO. Section 3 defines the design variables, objective, constraints, and the equivalent-cost metric. Section 4 develops the correlation-informed surrogate. Section 5 presents the cost-aware multi-fidelity optimization framework. Section 6 describes the C3X case setup and the validation protocol. Section 7 defines the optimization experiment matrix, and Section 8 reports the results. Sections 9 and 10 discuss the findings and conclude.

---

## References (master list — provisional, complete DOIs and verify before submission)

[1] R. S. Bunker, A review of shaped hole turbine film-cooling technology, ASME Journal of Heat Transfer, 2005.

[2] L. D. Hylton et al., Analytical and experimental evaluation of the heat transfer distribution over the surfaces of turbine vanes, NASA CR-168015, 1983.

[3] L. D. Hylton et al., The effects of leading edge and downstream film cooling on turbine vane heat transfer, NASA CR-182133, 1988.

[4] R. J. Goldstein, Film cooling, Advances in Heat Transfer, 1971.

[5] M. Baldauf, M. Scheurlen, A. Schulz, S. Wittig, Correlation of film-cooling effectiveness from thermographic measurements at enginelike conditions, ASME Journal of Turbomachinery, 2002.

[6] J. P. Sellers, Gaseous film cooling with multiple injection stations, AIAA Journal, 1963.

[7] D. R. Jones, M. Schonlau, W. J. Welch, Efficient global optimization of expensive black-box functions, Journal of Global Optimization, 1998.

[8] B. Shahriari, K. Swersky, Z. Wang, R. P. Adams, N. de Freitas, Taking the human out of the loop: a review of Bayesian optimization, Proceedings of the IEEE, 2016.

[9] P. I. Frazier, A tutorial on Bayesian optimization, arXiv:1807.02811, 2018.

[10] C. E. Rasmussen, C. K. I. Williams, Gaussian Processes for Machine Learning, MIT Press, 2006.

[11] A. I. J. Forrester, A. Sóbester, A. J. Keane, Multi-fidelity optimization via surrogate modelling, Proceedings of the Royal Society A, 2007.

[12] M. C. Kennedy, A. O'Hagan, Predicting the output from a complex computer code when fast approximations are available, Biometrika, 2000.

[13] P. Perdikaris, M. Raissi, A. Damianou, N. D. Lawrence, G. E. Karniadakis, Nonlinear information fusion algorithms for data-efficient multi-fidelity modelling, Proceedings of the Royal Society A, 2017.

[14] J. Wu, S. Toscano-Palmerin, P. I. Frazier, M. Poloczek, Practical multi-fidelity Bayesian optimization for hyperparameter tuning, UAI, 2020.

[15] C. Hvarfner, D. Stoll, A. Souza, M. Lindauer, F. Hutter, L. Nardi, πBO: augmenting acquisition functions with user beliefs for Bayesian optimization, ICLR, 2022.

[16] C. Hvarfner, F. Hutter, L. Nardi, A general framework for user-guided Bayesian optimization (ColaBO), ICLR, 2024.

[17] A. Souza et al., Bayesian optimization with a prior for the optimum, ECML PKDD, 2021.

[18] M. Balandat et al., BoTorch: a framework for efficient Monte-Carlo Bayesian optimization, NeurIPS, 2020.

[19] [Li et al., 2025] Efficient layout optimization of endwall film-cooling holes for a turbine blade, Journal of Shanghai Jiao Tong University, 2025. *(verify exact title/translation and bibliographic detail)*

[20] [Wang et al., 2024] Data-driven framework for prediction and optimization of gas turbine blade film cooling, Physics of Fluids, 2024. *(verify exact title and authors)*

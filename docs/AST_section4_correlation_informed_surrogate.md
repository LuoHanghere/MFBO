# Section 4 — Correlation-informed Bayesian surrogate (AST draft)

> Draft of the manuscript method section for *Aerospace Science and Technology* (double-anonymized).
> Status: equation-level method is final-form and does not depend on results; no `[RESULT: ...]` placeholders are needed in this section.
> Equation numbers are local to this section (4.x) and must be made globally consecutive when the full manuscript is assembled (AST requires consecutively numbered, in-text-cited equations).
> Reference numbers are global and shared with `AST_section1_introduction.md`; see the master list in that file.
> Note for finalization: the streamwise normalization in Eq. (4.3)–(4.4) is written in the standard equivalent-slot-width form; confirm the exact scaling and coefficient definitions against the chosen correlation references [4,5] before submission, and keep the symbol table in the Nomenclature consistent with this section.

---

## 4. Correlation-informed Bayesian surrogate

The objective of the optimization is the area-averaged adiabatic film-cooling effectiveness over the protected vane surface. The local adiabatic effectiveness is

\[
\eta_{aw} = \frac{T_{aw} - T_\infty}{T_c - T_\infty},
\tag{4.1}
\]

where \(T_{aw}\) is the adiabatic wall temperature, \(T_\infty\) the local hot-gas temperature, and \(T_c\) the coolant temperature, so that \(\eta_{aw}=1\) for a fully protected surface and \(\eta_{aw}=0\) for an unprotected one. The scalar objective is the area average over the protected region \(A\),

\[
\bar{\eta}(x) = \frac{1}{A}\int_A \eta_{aw}\,\mathrm{d}A,
\tag{4.2}
\]

with \(x\) the nondimensional design vector defined in Section 3. A high-fidelity evaluation of \(\bar{\eta}(x)\) requires a converged RANS solution and is the expensive operation the surrogate is built to economize.

A standard GP surrogate models \(\bar{\eta}(x)\) with a zero prior mean and therefore must learn the entire response from samples. The approach taken here replaces the zero mean with a physics-based mean derived from film-cooling correlations, so that the GP models only the discrepancy between CFD and the correlation prediction. Section 4.1 constructs the single-row correlation, Section 4.2 combines rows by superposition, Section 4.3 defines the residual GP and the learnable prior, Section 4.4 establishes the lossless property that motivates placing the prior at the mean, and Section 4.5 defines the controlled prior-mismatch model used for the robustness study.

### 4.1 Single-row effectiveness correlation

For a single row \(i\), the spanwise-averaged streamwise decay of effectiveness is represented by a parametric correlation of the classical form [4,5],

\[
\eta_{\mathrm{row},i}(s) = \frac{c_0}{1 + c_1\left(\dfrac{s - s_{\mathrm{hole},i}}{M_i\, s_{e,i}}\right)^{c_2}},
\qquad s \ge s_{\mathrm{hole},i},
\tag{4.3}
\]

where \(s\) is the surface arc-length coordinate, \(s_{\mathrm{hole},i}\) the row location, \(M_i\) the blowing ratio, and \(\theta = (c_0, c_1, c_2)\) the correlation coefficients. The grouping \((s - s_{\mathrm{hole},i})/(M_i s_{e,i})\) is the standard blowing-scaled streamwise distance, and \(s_{e,i}\) is the equivalent slot width of the row, defined from the open injection area per unit span,

\[
s_{e,i} = \frac{\pi D_i^2 / 4}{p_i},
\tag{4.4}
\]

with \(D_i\) the hole diameter and \(p_i\) the spanwise pitch. Upstream of the row, \(\eta_{\mathrm{row},i}(s)=0\) for \(s < s_{\mathrm{hole},i}\). The dependence of \(\eta_{\mathrm{row},i}\) on injection angle \(\alpha_i\) and compound angle \(\beta_i\) enters through the effective blowing scaling and the coefficients; for the baseline these are absorbed into \(\theta\), and angle-resolved coefficients are noted as an extension. Initial values of \(\theta\) are taken from the literature correlation [5] and are refined from data as described in Section 4.3.

### 4.2 Multi-row superposition

The combined effectiveness of \(N_{\mathrm{row}}\) rows is obtained from the Sellers superposition model [6], which treats each downstream row as acting on the gas already cooled by the rows upstream,

\[
\eta_{\mathrm{total}}(s) = 1 - \prod_{i=1}^{N_{\mathrm{row}}}\bigl(1 - \eta_{\mathrm{row},i}(s)\bigr).
\tag{4.5}
\]

Integrating Eq. (4.5) over the protected surface gives the correlation estimate of the area-averaged objective, which defines the physics prior mean,

\[
m_{\mathrm{phys}}(x;\theta) = \bar{\eta}_{\mathrm{corr}}(x) = \frac{1}{A}\int_A \eta_{\mathrm{total}}(s)\,\mathrm{d}A.
\tag{4.6}
\]

Equation (4.6) is a deterministic function of the design vector \(x\) and the coefficients \(\theta\), and it is evaluated in negligible time relative to a RANS solution. It constitutes the negligible-cost knowledge level L1 of the framework (Section 5).

### 4.3 Residual Gaussian process with a learnable prior

The objective is modeled as a Gaussian process with the physics prior as its mean,

\[
f(x) \sim \mathcal{GP}\bigl(m_{\mathrm{phys}}(x;\theta),\, k(x,x')\bigr),
\tag{4.7}
\]

which is equivalent to modeling the response as the prior plus a zero-mean residual process,

\[
f(x) = m_{\mathrm{phys}}(x;\theta) + r(x),
\qquad r \sim \mathcal{GP}(0,\, k).
\tag{4.8}
\]

The GP therefore represents the residual \(r(x) = f_{\mathrm{CFD}}(x) - m_{\mathrm{phys}}(x;\theta)\), which collects the physics not captured by the correlation: row coupling beyond simple superposition, surface curvature, streamwise pressure gradient, and shifts in transition location. This residual is smaller in magnitude and smoother than the full response, so fewer samples are needed to model it to a given accuracy.

The covariance is an anisotropic Matérn-5/2 kernel,

\[
k(x,x') = \sigma_f^2\left(1 + \sqrt{5}\,\rho + \tfrac{5}{3}\rho^2\right)\exp\!\bigl(-\sqrt{5}\,\rho\bigr),
\qquad
\rho = \sqrt{\sum_{d=1}^{D}\frac{(x_d - x_d')^2}{\ell_d^2}},
\tag{4.9}
\]

with signal variance \(\sigma_f^2\) and per-dimension length scales \(\ell_d\) (automatic relevance determination). The Matérn-5/2 form is twice differentiable, which suits engineering responses better than the infinitely smooth squared-exponential kernel, and the per-dimension length scales let the surrogate learn the relative importance of each design variable [10].

The correlation coefficients are not fixed at their literature values. Because correlations fitted on flat plates are expected to be biased on a curved, loaded vane, \(\theta\) is treated as learnable and estimated jointly with the kernel hyperparameters \(\phi = (\sigma_f^2, \{\ell_d\}, \sigma_n^2)\) by maximum a posteriori,

\[
(\hat{\theta}, \hat{\phi}) = \arg\max_{\theta,\phi}\;\Bigl[\log p(\mathbf{y}\mid \mathbf{X}, \theta, \phi) + \log p(\theta)\Bigr],
\tag{4.10}
\]

where \(\mathbf{X}, \mathbf{y}\) are the observed designs and effectiveness values, \(\sigma_n^2\) is a small homoscedastic noise term that absorbs discretization and convergence residuals, and \(p(\theta)\) is a weakly informative Gaussian prior centered on the literature coefficients,

\[
p(\theta) = \mathcal{N}\bigl(\theta;\, \theta_{\mathrm{lit}},\, \Sigma_\theta\bigr).
\tag{4.11}
\]

Equation (4.10) yields a data-calibrated physics prior: the correlation supplies the trend, and the data adjust its coefficients within the range allowed by \(\Sigma_\theta\). The fixed-coefficient variant, obtained by holding \(\theta = \theta_{\mathrm{lit}}\), is retained as an ablation (Section 7) to isolate the value of learnability.

### 4.4 Why the prior is lossless at the mean

Placing the prior at the GP mean is principled in a specific sense: it accelerates the search when the prior is informative and does not damage asymptotic performance when the prior is wrong. As observations accumulate, the GP posterior mean near observed designs is governed by the data, and the prior mean \(m_{\mathrm{phys}}\) is recovered only away from the data. With a universal kernel the surrogate remains a consistent estimator of the response regardless of the mean function, so the prior cannot bias the limit [10].

Two regimes follow. When the prior is accurate, the residual in Eq. (4.8) is small and its hyperparameters are easy to estimate, which gives a large early reduction in the number of evaluations needed. When the prior is inaccurate, the residual is large but is still modeled by the GP, and the asymptotic behavior is unchanged. This differs from injecting the prior into the acquisition function, where the prior is multiplied in and then annealed by a hand-tuned schedule, so that informative content is actively discarded over iterations [15]. By keeping the prior at the surrogate mean and leaving the acquisition function in standard form (Section 5), prior injection and search policy are decoupled: the prior enters through the Bayesian posterior and is dominated by data automatically, while convergence rests on the standard guarantees of the acquisition function.

### 4.5 Controlled prior-mismatch model

The robustness claim is tested by deliberately corrupting the prior and measuring the effect on optimization. A mismatched coefficient vector is generated by a multiplicative perturbation of the literature values,

\[
\theta_{\mathrm{wrong}} = \theta_{\mathrm{lit}} \odot (\mathbf{1} + \boldsymbol{\delta}),
\qquad \delta_j \in [-\delta_{\max}, +\delta_{\max}],
\tag{4.12}
\]

with \(\odot\) the elementwise product and \(\delta_{\max}\) a prescribed mismatch level (for example \(0.5\)). A stronger corruption replaces the superposition rule of Eq. (4.5) with an additive combination, which violates the physical assumption that downstream rows act on already-cooled gas. The prior-mismatch experiment compares three configurations under the same evaluation budget: the correct prior, the corrupted prior of Eq. (4.12), and a zero-mean surrogate. The reported quantity is the retained performance relative to the zero-mean baseline, which measures whether a wrong prior degrades gracefully rather than catastrophically. `[The synthetic-function and pseudo-CFD versions of this experiment are defined in Section 7; this subsection defines only the prior-corruption model.]`

The placement of the prior mean within the multi-fidelity surrogate — on the low-fidelity model or on the inter-fidelity residual — is a separate design choice and is treated in Section 5, together with the diagnostic that decides whether multi-fidelity coupling is used.

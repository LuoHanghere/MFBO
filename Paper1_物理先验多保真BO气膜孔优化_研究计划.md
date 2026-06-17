# Paper 1 研究计划：物理先验融入的多保真贝叶斯优化用于涡轮导叶多排气膜孔排布

> 版本：v1.0（2026-06-12）
> 定位：方法主线论文（目标期刊：Aerospace Science and Technology / Energy / Structural and Multidisciplinary Optimization / Applied Thermal Engineering）
> 核心 story：**把气膜冷却 60 年积累的经验关联式与叠加模型形式化为贝叶斯先验，在多保真框架下量化"能比黑盒 BO 节省多少高成本 CFD"**

---

## 1. 论文定位

### 1.1 一句话贡献声明（写给审稿人看的）

> We propose a correlation-informed multi-fidelity Bayesian optimization framework, in which classical film-cooling correlations and the Sellers superposition model serve as a physics-based prior mean of the Gaussian-process surrogate, and a cost-aware acquisition function jointly selects the design point and fidelity level. On a film-cooled linear turbine vane cascade, the framework reaches the same cooling-effectiveness improvement as standard (multi-fidelity) BO with **X% fewer equivalent high-fidelity CFD evaluations**, and degrades gracefully when the prior is deliberately mis-specified.

三个贡献点（缺一不可）：

1. **Correlation-as-prior**：经验关联式 + Sellers 叠加作为 GP 先验均值，GP 只学习 CFD 与关联式之间的残差（方法贡献）；
2. **多保真 + cost-aware 采集**：关联式（秒级）/粗 RANS（小时级）/细 RANS（十小时级）三档保真联合调度（框架贡献）；
3. **先验失配鲁棒性 + 等效 HF 评估次数对比**：系统的消融实验证明先验对了加速、错了不崩（实验贡献，也是审稿人最关心的）。

### 1.2 与现有工作的差异化（Related Work 怎么写）

| 已有工作 | 它们做了什么 | 我们的差异 |
|---|---|---|
| 上交 2025（端壁气膜孔 BO） | 黑盒 BO + 代理模型，单保真 | 我们注入物理先验 + 多保真，报告样本效率而非仅最终性能 |
| PoF 2024（多排孔 cGAN 代理） | 大样本离线代理 + 进化搜索 | 我们是小样本在线 BO，目标是**少算 CFD** 而非建全局代理 |
| πBO (ICLR 2022) / ColaBO (2024) | 先验注入方法，仅在超参优化等 toy 问题验证 | 我们给出**工程先验的构造方法**（关联式→先验），并在真实 CFD 上验证 |
| DLR / arXiv 2503.17977 多保真叶型优化 | RANS+LES 多保真，纯气动 | 我们做气膜冷却（LF 与 HF 偏差更系统、更适合讲多保真 story），且加入第三档"零成本"关联式保真 |

---

## 2. 基准叶型选择（待你最终拍板）

要求：直叶型（等截面拉伸，便于参数化建模与自动网格）、本身带气膜孔排布、有公开几何与实验数据。

### 候选对比

| 候选 | 类型 | 气膜孔情况 | 公开数据 | 评价 |
|---|---|---|---|---|
| **NASA C3X 导叶（气膜冷却版）** ★主推 | 直叶栅，等截面 | 前缘喷淋 + 叶身排孔（Hylton et al. 1988, NASA CR-182133） | 叶型坐标、壁温/换热系数实验数据齐全（含无气膜的 1983 基准 CR-168015） | 实验数据可直接验证 CFD 设置，审稿人认可度最高；几何公开、文献基数大 |
| GE-E3 第一级导叶 | 环形设计，常被简化为直叶栅 | 多排全覆盖气膜布局（NASA CR-168289） | 几何与冷却布局公开，但叶栅实验数据细节少 | 多排耦合 story 更强，但"简化为直叶栅"会被质疑；适合做第二算例 |
| AGTB-B1（德国联邦国防军大学） | 直叶栅 | 前缘双排气膜 | 有实验数据 | 排数少，多排耦合 story 弱 |
| LS-89 + 自构造孔排 | 直叶栅 | 无原生孔，需自构造 | 气动/传热数据极全但无气膜 | 已放弃（你的判断正确） |

### 建议

**主算例用 C3X 气膜冷却构型**：
- 用 1983 无气膜实验数据做 CFD 验证第一步（外换热系数分布），用 1988 气膜数据做验证第二步（带气膜的壁面换热/温度）——两步验证写进论文，堵住"RANS 预测气膜可信吗"的质疑；
- 优化时以原始排布为 baseline 设计，优化孔位/角度/间距，**"相对公开基准构型的提升"比"相对随意初始构型的提升"有说服力得多**；
- 若时间允许，GE-E3 简化直叶栅作为第二算例，证明方法可迁移（对 SMO/AST 这类期刊是显著加分项）。

> **行动项**：先把 NASA CR-168015 与 CR-182133 两份报告下载通读，确认气膜孔排布参数表和实验工况表（出口马赫数、Re、来流湍流度、吹风比/质量流量比范围）。

---

## 3. 优化问题定义

### 3.1 设计变量（建议 12–18 维起步）

以 3–4 排叶身气膜孔为优化对象（前缘喷淋固定不动，避免几何破碎和网格失败率飙升）：

| 每排变量 | 符号 | 范围建议 | 备注 |
|---|---|---|---|
| 弧长位置 | \(s_i/C\) | 围绕 baseline ±15% 弧长 | 排序约束 \(s_1 < s_2 < s_3\)，避免排交叉 |
| 孔径 | \(D_i\) | 0.8–1.5 mm（依 C3X 实际尺度定） | 可先固定，第二轮再放开 |
| 展向间距 | \(p_i/D_i\) | 3–8 | |
| 流向入射角 | \(\alpha_i\) | 25°–50° | |
| 复合角 | \(\beta_i\) | 0°–45° | 可先固定为 0 |

**维度策略**：第一轮只放开（孔位、间距、入射角）×3 排 = 9 维，跑通全流程；第二轮加孔径与复合角到 15–18 维。不要一开始就上 30 维。

### 3.2 目标函数

主目标（单目标主线）：

\[
\max_{x}\; \bar{\eta}(x) = \frac{1}{A}\int_A \eta_{aw}\, dA, \qquad \eta_{aw} = \frac{T_{aw} - T_\infty}{T_c - T_\infty}
\]

其中 \(A\) 为叶身被保护区域（建议取吸力面或压力面从第一排孔至尾缘的面域，论文中明确定义）。

### 3.3 约束

\[
\text{s.t.}\quad \dot{m}_c(x) \le \dot{m}_{c,\,baseline}, \qquad \zeta(x) \le \zeta_{baseline}\,(1+\epsilon)
\]

- 冷气总流量不超过 baseline（用约束而非目标，保持单目标主线干净）；
- 总压损失系数 \(\zeta\) 允许小幅放宽（\(\epsilon \approx 2\%\)），用 constrained EI 处理；
- 几何可行性约束（孔不重叠、不越过尾缘）在参数化层硬编码，不进优化器。

多目标版本（\(\bar\eta\) vs \(\dot m_c\) 的 Pareto 前沿，qNEHVI）留作论文的扩展小节或 Paper 3。

---

## 4. 方法框架（核心章节）

### 4.1 物理先验均值 GP（主方法）

标准 GP 用零均值；我们用关联式驱动的物理均值：

\[
f(x) \sim \mathcal{GP}\big(m_{\text{phys}}(x;\theta),\; k_{\text{Matérn-5/2}}(x, x')\big)
\]

\(m_{\text{phys}}\) 的构造分两层：

**第一层：单排效率关联式。** 经典横向平均效率衰减形式（Goldstein/Baldauf 族）：

\[
\eta_{\text{row}}(s; M, D, p, \alpha) = \frac{c_0}{1 + c_1 \left( \dfrac{s - s_{\text{hole}}}{M\, s_e} \right)^{c_2}}, \qquad s_e = \frac{\pi D^2 / 4}{p \cdot D}\text{（等效缝宽）}
\]

系数 \(\theta = (c_0, c_1, c_2)\) 取文献初值，并允许随 GP 超参一起做 MAP 估计（**可学习的物理先验**——这是比固定先验更稳健的一个小创新点，值得在论文里单独消融）。

**第二层：Sellers 叠加模型组合多排：**

\[
\eta_{\text{total}}(s) = 1 - \prod_{i=1}^{N_{\text{row}}}\big(1 - \eta_{\text{row},i}(s)\big)
\]

面积分后得到 \(m_{\text{phys}}(x;\theta) = \bar\eta_{\text{corr}}(x)\)。

**直觉**：GP 不再从零学 \(\bar\eta(x)\)，只学 CFD 与关联式的残差 \(f(x) - m_{\text{phys}}(x)\)。残差主要来自排间耦合与曲率/压力梯度效应，比原函数光滑、量级小，少量样本即可拟合。

### 4.2 多保真结构

三档保真：

| 档位 | 模型 | 单次成本 | 角色 |
|---|---|---|---|
| L0 | 关联式 + Sellers 叠加 | < 1 s | 先验均值 / 最低保真 |
| L1 | 粗网格 RANS（约 300–500 万网格，壁函数 y+≈30，SST） | 0.5–2 h | 探索主力 |
| L2 | 细网格 RANS（1500–2500 万网格，y+≈1，SST + γ-Reθ 转捩） | 8–24 h | 关键决策点 |

L1↔L2 用 Kennedy–O'Hagan 自回归 co-Kriging：

\[
f_{L2}(x) = \rho\, f_{L1}(x) + \delta(x), \qquad \delta \sim \mathcal{GP}(m_{\text{phys}}, k_\delta)
\]

**注意**：物理先验均值挂在 \(\delta\) 或挂在 \(f_{L1}\) 上是两种设计，建议都实现、用消融实验比较（又一个小贡献点）。若发现 L1/L2 相关性是非线性的（分离区、激波附近常见），切换 NARGP：

\[
f_{L2}(x) = g\big(x, f_{L1}(x)\big), \quad g \sim \mathcal{GP}
\]

### 4.3 采集函数

> 详细的采集函数对比、"无损"三层含义与选择论证见配套文档 `Paper1_方法学深入_先验构造_采集函数_代理模型.md` 第二部分。以下为冻结后的默认方案。

**主采集函数：Multi-Fidelity Knowledge Gradient（MFKG）**。理由：在"无损/原则化注入先验 + 保留收敛"的要求下，先验注入已放在代理模型层（先验均值 GP），采集函数只需选有保证、多保真原生、工程实现省的形式；MFKG（BoTorch `qMultiFidelityKnowledgeGradient`）API 直接、噪声/多保真友好，优先于实现更重的 MES（MES 作进阶对照，在便宜层级消融）。

**Cost-aware 联合选点与选保真**：

\[
(x^*, \ell^*) = \arg\max_{x,\,\ell \in \{L1, L2\}} \frac{\alpha_{\text{MFKG}}(x, \ell)}{\lambda_\ell}
\]

\(\lambda_\ell\) 用实测核时。约束按"**冷气量硬约束、总压损失软约束**"处理，用 constrained 形式乘可行概率：

\[
\alpha_c(x,\ell) = \alpha_{\text{MFKG}}(x,\ell) \cdot \Pr\big(\dot m_c(x) \le \dot m_{c,\text{base}}\big)\cdot \Pr\big(\zeta(x) \le \zeta_{\text{base}}(1+\epsilon)\big)
\]

冷气量约束的可行概率阈值设高（硬约束），总压损失放宽量 \(\epsilon\approx 2\%\)（软约束）。

### 4.4 对比基线（实验矩阵的列）

| 算法 | 说明 |
|---|---|
| Random / LHS | 下界基线 |
| Vanilla BO（单保真 L2，零均值 GP，EI） | 标准黑盒基线 |
| MFBO（co-Kriging + MFKG，零均值） | 证明"多保真有用" |
| πBO（单保真，\(\alpha \cdot \pi(x)^{\beta/n}\)，\(\pi\) 由关联式构造） | 唯一实现的"采集层先验"对照，证明"先验进代理模型优于人为衰减"；ColaBO 仅在 Related Work 定性讨论 |
| **Ours**（物理均值 GP + 多保真 + MFKG cost-aware） | 主方法 |
| Ours w/o learnable θ | 消融：固定先验 vs 可学习先验（θ 仅放开三系数 \(c_0,c_1,c_2\)） |
| Ours with wrong prior | 鲁棒性：故意把关联式系数扰动 ±50% / 用错误叠加假设 |

每个算法 **至少 5 个随机种子重复**（初始 DoE 不同），报告均值 ± 标准差。这是方法期刊的硬要求，预算要提前留出来。

### 4.5 评价指标

1. **Best-so-far \(\bar\eta\) vs 累计计算成本（核时）曲线**——主图；
2. **等效 L2 评估次数**：达到目标提升（如 baseline +5%）所需的 \(N_{L2} + \sum \lambda_{L1}/\lambda_{L2} \cdot N_{L1}\)——摘要里的那个数字；
3. 最终最优构型相对 C3X baseline 的 \(\Delta\bar\eta\)、\(\Delta\zeta\)、冷气量；
4. 先验失配场景下相对 vanilla BO 的性能保持率。

---

## 5. 仿真与自动化 pipeline（最大工程风险，前 2 个月专攻）

### 5.1 你的硬件下的保真档位现实评估

单节点服务器（多颗至强 + 200 GB 内存，估计 64–128 核）：

- **L1 粗 RANS（300–500 万网格）**：内存 ~30–50 GB，0.5–2 h/case，✅ 无压力，可两个 case 并行；
- **L2 细 RANS（1500–2500 万）**：内存 ~120–180 GB，8–24 h/case，✅ 可行但同时只能跑一个，**这决定了 L2 总预算大约 30–60 次/学期**——实验矩阵必须按这个量级设计；
- **壁面解析 LES**：带气膜的叶栅在实验 Re 下需 \(O(10^8)\) 网格 + 数月墙钟时间，❌ 单节点不现实。

**LES 的正确用法**：不做优化循环内保真档，只对**最终最优构型和 baseline 各做一次**展向窄周期段（取一个孔距周期）的 SBES/WMLES 验证（约 3000–6000 万网格，可压缩到 2–4 周），作为论文的可信度背书。这一条写进论文的 validation 章节，比把 LES 塞进优化循环划算得多。

### 5.2 自动化链路（全部 Python 驱动）

```
design vector x
   │
   ├─ [几何] SpaceClaim 脚本（Python API / journal）：
   │     拉伸 C3X 截面 → 布尔减去圆柱孔阵 → 冷气腔/供气 plenum
   │     失败检测：孔重叠、穿透尾缘 → 直接返回惩罚值，不进 CFD
   │
   ├─ [网格] Fluent Meshing watertight 工作流（TUI 脚本或 PyFluent）：
   │     poly-hexcore + 孔区 BOI 加密 + 边界层棱柱层
   │     L1: y+≈30, 5 层；L2: y+≈1, 20+ 层
   │     质量门槛：skewness/orthogonality 不达标 → 自动重试一次 → 仍失败则标记
   │
   ├─ [求解] PyFluent（Fluent 2024R1 原生支持）：
   │     批处理求解 + 收敛监控（残差 + η 面均值滑动窗口平稳判据）
   │     发散自动检测 → 降 CFL 重试一次
   │
   ├─ [后处理] PyFluent / Python：提取 η̄、ζ、ṁc → 写入结果数据库（sqlite/csv）
   │
   └─ [优化器] BoTorch/GPyTorch：
         自定义 Mean Module = m_phys(x;θ)（θ 注册为可训练参数）
         SingleTaskMultiFidelityGP / 自定义 co-Kriging + qMFKG
```

工程细节提醒：

- **几何参数化用"弧长坐标"而非笛卡尔坐标**定义孔位，排序约束天然好处理；
- **网格失败率是隐形杀手**：预期 5–15% 的设计点会网格失败，BO 框架要支持"失败点作为分类约束"（feasibility GP）或惩罚回退，论文里如实报告失败率；
- 收敛判据不要只看残差，**面均 η 的滑动平均稳定性**才是该问题的可靠判据；
- 每个 case 的网格/设置/结果全部归档（设计向量哈希命名），这是后面 Paper 2 机理分析的原材料。

### 5.3 CFD 验证步骤（写进论文 §Validation）

1. 无气膜 C3X（CR-168015 工况）：外表面换热系数分布 vs 实验，网格无关性三套网格（GCI 指数）；
2. 带气膜 C3X（CR-182133 某工况）：带膜壁面温度/换热 vs 实验，L1 与 L2 都要算——**L1 的系统性偏差曲线本身就是论文图**（它正是多保真框架要利用/修正的对象）；
3. 转捩模型开关的影响单独测一次（C3X 表面转捩对换热分布影响显著）。

### 5.4 算法验证阶梯（防止"高成本试错"的核心机制）

> 原则：**叶片上的正式 BO 是"演出"不是"排练"。** 算法的正确性与几何无关；随几何变化的只有两个量——先验质量、L1/L2 相关性——而这两个量都可以在跑任何正式 BO 之前用小代价实测。试错全部下放到零成本/低成本层级。

**第 0 级：合成函数（零成本，算法调试主战场）**
用 Sellers 叠加 + 关联式构造"合成气膜冷却问题"：原始关联式当真值 \(f_{HF}\)，系数扰动 ±30–50% 的版本当 \(f_{LF}\) 和先验。维度、排序约束、先验失配程度与真实问题同构，但零 CFD 成本。全部算法、全部消融、全部种子在这里跑通（可重复数千次）。πBO/ColaBO 原文的验证也是这个套路，论文附录直接放这部分结果。

**第 1 级：离线代理当真值（真实叶片物理，零边际成本）**
在 C3X 上一次性跑 60–80 点 LHS 的 L1 粗 RANS（总成本约百核时·天内），拟合高精度插值模型（GP/NN），把它当"免费伪 CFD"调试完整 BO 闭环——物理是真实叶栅的（曲率、压力梯度、排间耦合都在），调用成本为零。这批样本零浪费：后续复用为正式 BO 的初始 DoE、L1/L2 标定的候选点、Paper 2 的流场素材。

**第 2 级：烟雾测试（10–15 个 L1 样本）**
只跑主方法、单种子、小预算，验证"几何→网格→求解→优化器"全自动闭环在真实环境不掉链子（网格失败回退、发散重试、归档等）。不看优化效果。

**第 3 级：正式实验**
启动前置条件（全部满足才开跑）：① 第 0/1 级全部算法行为正常；② 烟雾测试通过；③ 下述两个先行诊断量达标。

**两个先行诊断量（正式 BO 前实测，本身就是论文图）：**

1. **L1/L2 相关系数 \(\rho\)**：从第 1 级 LHS 样本中取 15–20 点补算 L2，回归得 \(\rho\)。若 \(\rho < 0.7\)，多保真增益存疑——先换 NARGP 或调整 L1 网格/壁面处理，不要硬跑；
2. **先验残差幅度** \(\|f_{CFD} - m_{\text{phys}}\|\) 相对函数本身变化幅度的比值。若残差比信号还大，先验方案要先修（调整关联式形式、检查叠加假设），或预期退化到 πBO 衰减机制兜底。

**三个运行期保险机制：**

- **中途可诊断**：每 5 个样本检查 GP 留一交叉验证误差、采集函数是否退化为纯探索；方法失效在 10–15 个样本内即可发现并止损，不必烧完整个预算；
- **样本永不浪费**：所有 CFD 样本按设计向量哈希归档，失败 run 的样本复用为其他 run 的初始数据、回灌第 1 级伪 CFD 模型、Paper 2 素材。**注意：最终论文报告的算法对比必须用独立预算重跑，复用仅限调试阶段**，避免数据污染质疑；
- **断点续跑**：BO 循环每步落盘（GP 状态 + 历史样本），服务器重启/求解中断后可恢复，避免长 run 报废。

**平板算例的角色（降级为可选项）**：不在叶片算法验证的关键路径上。保留的三个理由：① 作为"先验最准"场景给出加速比上界，与叶栅"先验不完美"场景构成"先验质量→加速收益"梯度分析（论文卖点之一）；② 自动化链路的廉价排练场；③ 会议占位论文载体。时间紧张时可整体砍掉，不影响主线。

---

## 6. 时间表（12 个月）

| 月份 | 里程碑 | 产出 |
|---|---|---|
| M1–M2 | 自动化 pipeline 打通（几何→网格→求解→后处理全自动）；C3X 两步验证 + 网格无关性 | 验证报告；L1/L2 成本标定 |
| M2–M3 | **第 0 级**：合成气膜函数上调通全部算法；**第 1 级**：C3X 上 60–80 点 L1 LHS + 伪 CFD 闭环调试；补 15–20 点 L2 → 实测 ρ 与先验残差（两个先行诊断量） | 框架代码 + 诊断量图表（直接进论文）；（可选）平板算例会议占位 |
| M3–M4 | **第 2 级**：烟雾测试（10–15 个 L1 样本，单算法单种子）；预算表冻结 | 全自动闭环验收 |
| M4–M6 | **第 3 级**：主实验：C3X 叶栅 9 维优化，关键基线 × 5 种子 | 主结果（best-so-far 曲线、等效 L2 次数） |
| M6–M7 | 消融与鲁棒性：错误先验、固定 vs 可学习 θ、先验挂载位置 | 消融图表 |
| M7–M8 | 15–18 维第二轮（加孔径/复合角）；最优构型 + baseline 的 SBES/LES 验证 | 高维结果 + LES 背书 |
| M9–M10 | Paper 1 写作、内审、投稿 | 投稿 AST/SMO |
| M10–M12 | Paper 2 机理分析（用已归档流场）+ Turbo Expo 摘要（注意每年 9 月左右截稿） | Paper 2 草稿 |

**关键预算核算**（按 L2 = 16 h、L1 = 1 h 估）：主实验 7 个算法 × 5 种子 × 预算（约 10 次 L2 等效/run）≈ 350 次 L2 等效 ≈ 5600 核时·天量级——**这是不可行的**。对策：① 随机种子重复只对关键对比（vanilla BO / MFBO / Ours / Ours-wrong-prior）做 5 次，次要基线 3 次；② 消融实验在第 0 级合成函数 / 第 1 级伪 CFD 上做，只把最关键的 1–2 个消融上真 CFD；③ 单保真基线的预算上限设为与多保真相同的总核时而非相同迭代数。**实验矩阵的预算表在 M3–M4 烟雾测试后核算并冻结。**

---

## 7. 风险与对策

| 风险 | 概率 | 对策 |
|---|---|---|
| 网格自动化失败率高（孔与曲面相交几何破碎） | 高 | 直叶型 + 弧长参数化已大幅降低；保留"失败点分类 GP"；前缘喷淋不动 |
| L1 与 L2 相关性差，多保真不增益 | 中 | §5.4 先行诊断量 ρ：M3 实测，ρ < 0.7 则换 NARGP 或调整 L1 网格策略后再跑正式实验 |
| 关联式先验在叶栅曲面上偏差过大，先验帮倒忙 | 中 | §5.4 先行诊断量（先验残差）提前暴露；可学习 θ 兜底；πBO 衰减机制作 fallback；负结果也有信息量 |
| 正式 BO 长循环中途发现方法无效 | 中 | §5.4 验证阶梯把试错下放到第 0/1 级；运行期留一交叉验证诊断可在 10–15 样本内止损；断点续跑 + 样本归档复用 |
| RANS 预测气膜横向扩散系统性偏差 → 最优解可信度被质疑 | 中 | 两步实验验证 + 最终构型 LES 背书 + 论文限于"RANS 意义下的最优" 的诚实表述 |
| 预算超支 | 高 | §6 的预算冻结机制；主结果优先，消融降级到第 0/1 级算例 |
| πBO/ColaBO 思路被别人先发到气膜冷却上 | 中 | M3 前用第 0 级合成实验 +（可选）平板算例投会议占位（ASME Turbo Expo / ISABE / 国内工热年会） |

---

## 8. 核心文献清单（精读 ~14 篇）

**A. 基准与实验数据**
1. Hylton et al., 1983, *Analytical and experimental evaluation of the heat transfer distribution over the surfaces of turbine vanes*, NASA CR-168015（C3X 无气膜基准）
2. Hylton et al., 1988, *The effects of leading edge and downstream film cooling on turbine vane heat transfer*, NASA CR-182133（C3X 气膜版）

**B. 气膜冷却物理与关联式（先验的原材料）**
3. Sellers, 1963, *Gaseous film cooling with multiple injection stations*, AIAA J.（叠加模型原始文献）
4. Goldstein, 1971, *Film cooling*, Advances in Heat Transfer（效率衰减关联式族）
5. Baldauf et al., 2002, *Correlation of film cooling effectiveness from thermographic measurements*, ASME J. Turbomach.（现代关联式）
6. Bunker, 2005, *A review of shaped hole turbine film-cooling technology*, ASME J. Heat Transfer（综述，写 Intro 用）

**C. BO 方法**
7. Hvarfner et al., 2022, *πBO: Augmenting acquisition functions with user beliefs*, ICLR（先验加权采集函数 + regret bound）
8. Hvarfner et al., 2024, *A general framework for user-guided Bayesian optimization (ColaBO)*, ICLR（先验进代理模型的原则化框架）
9. Kennedy & O'Hagan, 2000, *Predicting the output from a complex computer code when fast approximations are available*, Biometrika（AR(1) co-Kriging）
10. Perdikaris et al., 2017, *Nonlinear information fusion algorithms for data-efficient multi-fidelity modelling (NARGP)*, Proc. R. Soc. A
11. Wu et al., 2019, *Practical multi-fidelity Bayesian optimization for hyperparameter tuning (MFKG)*, UAI
12. Balandat et al., 2020, *BoTorch: A framework for efficient Monte-Carlo Bayesian optimization*, NeurIPS（实现基础）

**D. 直接竞品（Related Work 必引）**
13. 李卓贤等, 2025, 涡轮叶片端壁气膜冷却孔高效排布优化设计, 上海交通大学学报
14. Wang et al., 2024, *Data-driven framework for prediction and optimization of gas turbine blade film cooling*, Physics of Fluids

补充泛读：arXiv 2503.17977（RANS+LES 多保真涡轮优化）、Pretsch 博士论文（TUM，高维约束叶片 BO，PCA-BO/TR-BO/CC-BO）、Souza et al. 2021 BOPrO。

---

---

# 附：Paper 2 思考（工程机理主线）

> 定位：ASME Turbo Expo 会议 → Journal of Turbomachinery / IJHMT 期刊版
> 原则：**Turbo Expo 审稿人不在乎 BO 新不新，在乎物理 insight 和工程可信度。** Paper 2 里 BO 只是工具，一段话带过，引用 Paper 1。

## P2.1 核心问题（拟回答的三个机理问题）

1. **优化器"发现"了什么排布规律？** 最优解相对 C3X baseline 把孔往哪儿移了、角度怎么变了——这些变化能否用已知机理（肾形涡对强度、横向扩散、压力梯度对贴壁性的影响）解释？有没有反直觉的发现（这是亮点）？
2. **排间耦合如何被利用？** 用"逐排关闭"数值实验（只开第 1 排 / 1+2 排 / 全开）量化叠加模型的失效程度：\(\eta_{\text{CFD}} - \eta_{\text{Sellers}}\) 沿弧长的分布。上游排如何改变下游排的来流边界层和湍流度，最优解是否刻意利用了这一点（如上游排为下游排"铺床"）？——**这同时反哺 Paper 1 的先验残差分析，一份数据两篇用**。
3. **最优解的鲁棒性如何？** 变吹风比（±30%）、变来流湍流度下，最优构型 vs baseline 的性能保持性。工程上"宽工况稳健"比"单点最优"更有价值；如果最优解是脆弱的，这本身也是对"单工况优化"范式的批评，可引出 robust BO 的后续工作（Paper 3 候选方向）。

## P2.2 素材来源（零额外优化成本）

- Paper 1 优化历史中归档的全部 L2 流场（设计空间内数十个样本，本身就是一个"准 DoE 数据库"）；
- 最优构型 + baseline 的 SBES/LES 流场（Paper 1 已算）：用于涡结构（Q 准则、肾形涡演化）、湍流热流 \(\overline{v'T'}\) 分析——RANS 看不到的内容；
- 额外只需补算：逐排关闭实验（~6 个 L2 case）+ 变工况扫掠（~8 个 L2 case），两周可完成。

## P2.3 图表骨架（先想好图再写论文）

1. 最优 vs baseline 的孔排布对比图（叶面展开图）+ 设计变量变化表；
2. η 分布云图对比（L2 RANS + LES 双列，含实验验证点）；
3. 逐排关闭实验：Sellers 预测 vs CFD 的逐排偏差瀑布图（**本文招牌图**）;
4. 孔下游涡结构对比（LES，Q 准则 + 温度等值面）；
5. 变吹风比鲁棒性曲线（η̄–M 曲线，最优 vs baseline）；
6. 总压损失与冷气量收支表。

## P2.4 风险提示

- Turbo Expo 摘要截稿一般在 9 月左右（来年 6 月会议），按 §6 时间表 M10 正好赶上——**把这个 deadline 写进日历**；
- 若 Paper 1 的优化提升幅度有限（如 η̄ 仅 +2–3%），Paper 2 的卖点就从"提升大"转为"机理 + 叠加模型失效的系统量化"，story 依然成立——机理论文不依赖优化结果的绝对幅度。

---

## 下一步行动清单（本周可做）

- [ ] 下载并通读 NASA CR-168015、CR-182133，整理 C3X 气膜构型参数表与实验工况表
- [ ] 在 Fluent 2024R1 里手动建一个 C3X 无孔算例，确认求解设置（可压、SST、边界条件）
- [ ] 装好 PyFluent + BoTorch 环境，跑通 BoTorch 的 multi-fidelity KG 官方示例
- [ ] 写 SpaceClaim 参数化脚本的第一版：拉伸叶型 + 单排孔布尔运算
- [ ] 精读 πBO 与 ColaBO 两篇，重点看它们的鲁棒性实验设计（你的消融实验直接对标它们的格式）
- [ ] 实现第 0 级"合成气膜冷却问题"（纯 Python，Sellers 叠加 + 关联式 + 系数扰动），当天就能开始调算法，不依赖任何 CFD

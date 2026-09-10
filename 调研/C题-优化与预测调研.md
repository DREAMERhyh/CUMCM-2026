# C题-优化与预测调研

**TL;DR：**建议以可解释LP/MILP、因果滚动调度为主线，以预测校正和风险预留为增益。当前口径下，免费弃电使下调至初始计划以下缺乏经济价值；Q1可用等价LP。已运行Q1、全年基础方案及四种网络功能检查，尚未证明深度学习优于官方预报。收录26篇文献，明确三天内的主线、可选扩展与停止条件。

## 1 结论、证据边界与团队决策

### 1.1 当前最值得实现的路线

三名计算机本科生适合分工为：队员A负责优化、费用与状态核验；队员B负责预测和无泄漏回放；队员C负责数据接口、实验管理和图表。GPT agent可协助实现与审查，模型口径和论文结论由队员逐项核实。实际剩余约三天，应先取得完整可行解，再选择一条增益路线；不把每次恢复任务当作重新获得72小时。

| 路线 | 回答的问题 | 分类 | 当前证据与推荐 |
|---|---|---|---|
| Q1确定性LP＋MILP交叉检查 | 给定预测下如何购电与充放电 | ✅ | 【本题验证】两者费用一致，先做这一层 |
| Q2历史基线＋计划LP＋实时反馈 | 只用过去数据制定全天承诺 | ✅ | 【本题验证】全年顺序回放已完成，仍有明显紧急购电成本 |
| Q2分位数预留＋残差场景 | 如何控制昂贵缺口风险 | ✅小规模/⚠️校准 | 【文献支持】；本题风险参数收益【未验证】 |
| Q3确定性滚动LP/MPC | 四次预报与最终结算如何衔接 | ✅ | 【本题验证】已完成修正消融；优先深化 |
| Q3多阶段随机控制 | 未知未来预报时如何提前布局 | ⚠️ | 【文献支持】；非预见性和场景树工作量大 |
| Q4历史电价预测＋少量联合场景 | 电价未知时怎样避免前视套利 | ✅基线/⚠️场景 | 基线【本题验证】，联合风险优化【未验证】 |
| LSTM/TCN＋官方预报残差校正 | 自训练模型能否改善成本 | ✅实现/⚠️胜出 | 四类网络功能【本题验证】，正式精度与收益【未验证】 |
| 大型Transformer/完整Informer/TFT | 长历史和复杂协变量是否有增益 | ⚠️ | 可做一项小对照，不作为必需环节 |
| 全年端到端可微整数调度、调度RL | 直接学习全年经济策略 | ❌ | 缺少充分训练与反事实检验时间，列为展望 |

✅表示具备当前可实施条件，不表示结果一定优于其他方法；⚠️表示需额外实现/实验；❌是本次赛程范围判断。预计工时均为工程估算，不是运行实测，也不能简单相加当作三天日程。

### 1.2 三套标签独立使用

- 来源：【核心】正式出版或官方技术文档；【参考】预印本；【线索】只用于发现，不进入参考文献。本报告研究论文26篇，其中25核心、1参考；工具文档另计。
- 结论：【文献支持】只支持原研究或明确数学命题；【本题验证】已对本题数据运行；【未验证】本题效果尚未测试。数学推导另写“本报告推导”，不冒充论文原结论。
- 本阶段是研究路线、模型与可运行骨架，不是最终竞赛论文或结果表交付。没有生成五份正式result工作簿，没有全年训练后的DL成本成绩。

### 1.3 REWRITE链条与最小可支持故事

**观察**：费用对缺口不对称，储能跨日衔接，预报存在多个发布版本。**重新表述**：核心并非“换一个更复杂预测器”，而是“在可用信息和非对称费用下，预报更新何时改变有价值的购电决策”。**问题**：Q1可否去整数化，Q2需多少风险预留，Q3何时修订，Q4如何处理价量联合不确定性。**比较位置**：Confirm标准滚动结构；Refine本题特有结算与信息边界；Extend到误差分层的成本消融。**检验**：先验证物理/结算，再比较预测，最后回放费用。**最低故事**：正确模型＋可复现全年回放＋修订收益与失败情形。没有证据时，不用“深度学习提升”作为标题。

## 2 已裁决口径与数据审计

### 2.1 当前四项口径

1. **时间为区间末端。**00:10对应00:00—00:10；00:00+1等于当日24:00，对应23:50—24:00。144个输入数值已经覆盖完整自然日；不平移数值、不跨日重分组、不补首段或删末段。结果模板的显式区间标签在后续输出副本中修正为完整自然日，原始输入保持不变。
2. **最终有效计划相对初始计划结算一次，不退款。**中间修订记录保留用于审计，不重复累计违约费；原始本金照付。100→80为110元，100→80→90为105元，100→120为130元，均取电价1元且无紧急购电。
3. **计划与实时储能分开。**购电承诺按规定时刻冻结/调整；储能根据当前已观测负载、光伏、储电量作因果纠偏。缺口紧急购电，多余电无收益弃电，不售电。
4. **首日零计划协议。**2025年1月1日购电计划为零、储能不动作、全天6000 kWh；净缺口紧急购电，过剩弃电。1月2日起仅用已发生数据，各方案独立推进1月并继承到2月1日。

此外，充、放效率主口径各90%；往返90%为敏感性。仅Q1强制日初日末电量相等。Q1—Q3制定计划时已知当天电价；Q4只在实际交易时知道实际电价。全年用于历史与状态推进，Q2—Q4提交2月1日—12月31日。

### 2.2 逐问输入权限

| 问题 | 电价输入 | 负载/PV信息 | 允许改变的购电承诺 |
|---|---|---|---|
| Q1 | 附件1的144点价格 | 附件1给定负载及预测PV | 0:00确定全天 |
| Q2 | **附件1价格每日重复** | 截至计划时已发生的附件2历史 | 0:00确定全天；缺口另购 |
| Q3 | **附件1价格每日重复** | 上述历史＋截至当前发布的附件3预报 | 0/6/12/18时修订尚未交付时段 |
| Q4-2 | 附件4过去历史；未来需预测 | 同Q2 | 同Q2 |
| Q4-3 | 附件4过去历史；未来需预测 | 同Q3 | 同Q3 |

这张表必须成为数据接口规则。特别不能把附件4的全年实际价格送入Q2/Q3，也不能在Q4零点输入当天尚未发生的实际价格。

### 2.3 本题数据盘点【本题验证】

只读检查9份工作簿，记录见[结构审计](C:/Users/30130/Desktop/数模/tmp/C_research/workbook_structure.json)和[数值审计](C:/Users/30130/Desktop/数模/tmp/C_research/data_audit.json)。

| 数据 | 数量/范围 | 建模含义 |
|---|---|---|
| 附件1 | 144时段，价格0.3713—1.3952元/kWh | Q1确定性样例；Q2/Q3固定价曲线 |
| 附件2实际负载 | 365×144；1995.7176—7978.8849 kW | 过去可用于预测，未来只用于执行/评价 |
| 附件2实际PV | 365×144；0—10216.2 kW；23540个零 | 夜间零值使普通MAPE不适合总体排名 |
| 附件4实际电价 | 365×144；0.0076—1.7936元/kWh，均正 | 主数据无负价；无需为负价设计核心策略 |
| 附件3预报 | 1460次发布×24个小时目标，共35040值 | 必须保留发布时刻和预报提前量 |
| 结果日期 | 334天×144＝48096时段 | 不能把1月删掉后直接从6000启动2月 |

核心数值区域未发现缺失、非有限值或负值，实际数据日期一致。附件3日期列的空白按表格分组向下填充，并不等于预报缺失。12月31日晚发布的部分目标落在2026年，总计36个目标无2025实际标签；评价时排除，不能补零。

数据没有给出天气、卫星图、地理位置、装机容量或2024历史。本报告中全年最大PV只用于数据描述，**不能作为已知额定容量，也不能用于过去时点的归一化**。52560个点具有强相关性，不能当成52560个独立的日预测训练样本；首次2月预测只有31天历史。

### 2.4 预报对齐与发布版本

定义发布时刻\(r\)、目标时刻\(v=r+h\)、提前量\(h=1,\ldots,24\)。保存长表键`(issue_time, target_time, lead_hour)`。真实标签按目标末端时间关联，严禁用当天最后一次预报覆盖之前版本后，再声称零点使用了该曲线。

附件3是整点功率预报，当前骨架在同一次发布的24点间线性插值，并以发布时已经观测的PV作为lead-0锚点，生成剩余自然日的10分钟点。把插值功率乘\(1/6\)转为区间电量，是本报告的数值近似；可与分段常数、分段积分作敏感性，不将插值制造的点当作新增真实观测。零点锚点取上一日末端观测；1月1日按零计划协议不调用优化。

0/6/12/18发布时刻及其未来目标不随结果模板标签修正而平移。区间末端标签只是数据归属，不表示区间开始已经知道该区间的真实平均功率；当前区间反馈是已确认的10分钟离散执行抽象，禁止进一步读取下一时段真实数据。

## 3 统一数学模型与两层控制结构

### 3.1 文献定位：滚动控制与随机规划各解决什么

微网能量管理的计划层、执行层与不确定性处理在综述C01和集中EMS研究C03中有明确先例。Parisio等将预测控制与混合整数优化结合（C02）；Elkazaz等明确研究两层滚动储能控制（C04）。因此，本题采用“日初计划＋日内滚动优化＋实时储能反馈”具有【文献支持】，是对既有结构的Confirm与本题规则的Refine，而非可直接宣称的新算法。[微网MPC原研究](https://research.manchester.ac.uk/en/publications/a-model-predictive-control-approach-to-microgrid-operation-optimi/)、[两层滚动研究](https://nottingham-repository.worktribe.com/output/1880895)。

**MPC是重算与反馈方式；两阶段随机规划是未知量与决策先后关系。**二者可以组合。每天0/6/12/18是题目给定的购电修订时刻，不是文献证明的普遍最优频率。实时10分钟储能反馈也不意味着可每10分钟免费改购电计划。

### 3.2 变量、单位及物理约束

一天\(T=144\)，\(\Delta=1/6\)小时。功率\(L_t,V_t\)单位kW；\(\ell_t=L_t\Delta,v_t=V_t\Delta\)为区间电量。定义：

| 符号 | 含义 | 单位 |
|---|---|---|
| \(g_t^0,g_t\) | 初始计划、最终交付的计划电量 | kWh |
| \(h_t\) | 当前负载缺口的紧急购电量 | kWh |
| \(C_t,D_t\) | 交流母线侧充入/放出的电量 | kWh |
| \(E_t\) | 区间开始时储能内部电量，SOC可写\(E_t/12000\) | kWh |
| \(w_t\) | 无收益弃电/未利用电量 | kWh |
| \(p_t\) | 当前交付时段实际单价 | 元/kWh |

\[
g_t+h_t+v_t+D_t=\ell_t+C_t+w_t,\qquad g_t,h_t,C_t,D_t,w_t\ge0,
\]
\[
E_{t+1}=E_t+\eta_c C_t-D_t/\eta_d,\quad1200\le E_t\le10800,
\]
\[
0\le C_t,D_t\le5000\Delta=833.333\ldots,\qquad \eta_c=\eta_d=0.9.
\]

严格单一充放状态可用\(z_t\in\{0,1\}\)：
\[
C_t\le833.333\ldots z_t,\qquad D_t\le833.333\ldots(1-z_t).
\]

这里5000限制的是**功率**，不能直接把每10分钟可充放电量写成5000 kWh。输出充放电量采用交流侧定义；内部电量变化另乘/除效率，避免重复折损。题目没有电池老化单价、售电收益、购电容量限制、柴油机或网络参数，主模型不凭空加入。

应急购电必须只补当前负载缺口：若在优化模型内显式决定\(h\)，还须限制\(h_tC_t=0\)、\(h_tw_t=0\)，防止一边紧急购电一边充电或弃电；结合供电平衡即可表达用途约束。需要MILP实现时用应急状态二元变量和经物理量推导的有效上界线性化，不能随意取巨大常数。当前可运行计划LP令\(h=0\)，实时反馈直接满足该用途规则；本文场景扩展不能省掉这一条件。

仅Q1加\(E_{144}=E_0=6000\)。Q2—Q4加\(E_{d+1,0}=E_{d,144}^{\mathrm{actual}}\)，不加每天闭环等式。一般滚动优化可以研究终端价值\(-\lambda_EE_T\)或跨日预测时域，但它是策略设计/敏感性，不是题目硬约束。经典MPC终端条件见C06，不能把该文稳定性定理不加条件移植到这里。

### 3.3 费用与最终修订的线性化

\[
u_t\ge g_t-g_t^0,\quad b_t\ge g_t^0-g_t,\quad u_t,b_t\ge0,
\]
\[
J=\sum_t p_tg_t^0+1.5p_tu_t+0.5p_tb_t+5p_th_t.
\]

所有系数为正时，最优解会使\(u_t=(g_t-g_t^0)_+\)、\(b_t=(g_t^0-g_t)_+\)。也可用等式\(g_t-g_t^0=u_t-b_t\)，正成本排除同时无意义增加二者。Q2固定\(g_t=g_t^0\)，所以只有计划本金和紧急费用。Q4用交易实际价结算，但在优化时对未知\(p_t\)使用预测/场景。

每个交付时段只取当时的最终有效\(g_t\)结算一次。6点、12点、18点的修订向量是中间承诺记录，不把每次相对初始的费用相加。骨架中原计划数组不可被修订覆盖，历史已交付的前缀也不可重写。

### 3.4 两个能简化本题的命题

**命题A：免费、不限量弃电时，下调到初始计划以下被弱支配。**【文献支持：本报告数学推导；数值例子本题验证】设某时段\(g<g^0\)。改成\(g'=g^0\)，并令\(w'=w+(g^0-g)\)，其余变量不动，供电平衡与储能轨迹仍可行。初始本金不变，违约费减少\(0.5p(g^0-g)\)。当\(p>0\)且确实下调时严格省钱。因此可选最优解满足\(g\ge g^0\)。这不禁止把先前上调过的计划从120改回110，只要最终仍与最初100比较；也不等于所有预报更新都无价值，更新仍可避免5倍紧急购电。

**命题B：在当前能量模型中，可把LP同时充放电转换为不同时充放电的等成本解。**设\(\rho=\eta_c\eta_d\)，取
\[
\delta=\min(C,D/\rho),\quad C'=C-\delta,\quad D'=D-\rho\delta,\quad w'=w+(1-\rho)\delta.
\]
储能变化满足\(\eta_cC'-D'/\eta_d=\eta_cC-D/\eta_d\)，母线等式同样保持，购电与费用不变，功率不增加，至少一个充放电量变为零。对各时段依次处理即可。因此LP最优值等于本模型的物理单状态最优值，可保留MILP作为交叉检查。**适用条件**：允许弃掉包括多余购电在内的能量；无弃电上限/费用或额外循环约束；效率积不大于1。换成受限弃电、特殊奖励或退化费用模型后，必须重新证明，不能一概去掉整数变量。

## 4 Q1：确定性购电与储能套利

### 4.1 路线Q1-A：LP主解、MILP复核 ✅

**科学问题**：给定附件1负载、价格和PV预测，如何获得最小费用计划？**定位**：Confirm能量平衡调度，Refine为本题可去整数的特例（C01—C03）。**模型**：第3.2节全部约束，\(h=0,g=g^0,E_{144}=6000\)，目标\(\min\sum_tp_tg_t\)。PV预测被当成Q1规划输入，不另造实际误差。

**套利判据**：交流侧买入1 kWh最终可提供\(\eta_c\eta_d=0.81\) kWh；只有未来替代电价满足\(0.81p_{\mathrm{high}}>p_{\mathrm{low}}\)时，这一对时段的纯电价套利才可能有利。还需考虑容量、功率、光伏占用和日末等式，不能仅按全日最高/最低价贪心充放。

```text
读取144点，功率乘1/6
建立g,C,D,w,E及能量平衡、上下界、日末等式
用HiGHS解LP，检查求解状态和原始约束残差
按命题B消除同时充放电
再加144个二元变量解MILP，比较费用与可行性
按时段汇总购电、费用及4小时充放电量
```

骨架`solve_day(..., terminal_equal=True, integer=False/True)`见第11节。基础LP有\(5T+1=721\)变量、288条主要等式；MILP再增加144二元变量和288条模式不等式。规模小，实际耗时见第9节；不能以变量数线性推断一般MILP复杂度。

**预期产出**：144时段可行计划、分时购电/储能曲线、表1/2对应汇总、LP与MILP费用差。**代价**：核心建模约2—4人时，表格接口另计。【本题验证】现有骨架已求解附件1；不能把这一结果推广为所有扰动下的最优费用。

### 4.2 路线Q1-B：储电量离散DP ⚠️

**科学问题**：不用商业求解器，能否独立核验调度逻辑？**定位**：对同一能量模型作算法对照，不宣称新的物理机制。令电量网格步长\(\delta_E\)，状态\(E\in\{1200,1200+\delta_E,\ldots,10800\}\)。每个可达\(E'\)对应唯一净充/放电：若\(E'>E\)，\(C=(E'-E)/\eta_c,D=0\)；否则\(D=(E-E')\eta_d,C=0\)。令\(g=\max(0,\ell-v+C-D)\)，多余量为弃电。

\[
F_t(E)=\min_{E'\ \mathrm{可达}}\{p_tg_t(E,E')+F_{t+1}(E')\},
\quad F_{144}(E)=\begin{cases}0&E=6000\\+\infty&\text{其他}\end{cases}.
\]

```text
终点只允许6000；倒序遍历144时段
对每个电量网格点枚举功率允许到达的下一电量
计算购电费＋下一状态价值，保存最优转移
从6000正向恢复策略，与LP比较
```

Python骨架：`for t in reversed(range(T)): for i,E in enumerate(grid): F[t,i]=min(cost(t,E,E2)+F[t+1,j] for j,E2 in reachable(E))`。\(O(TN_EK_E)\)时间，滚动值函数\(O(N_E)\)内存，恢复路径另存索引。建议先\(\delta_E=100\)再50/25比较；量化误差需报告，不能声称连续问题精确最优。已有LP/MILP双检，三天内DP优先级低，本题DP效果【未验证】。

## 5 Q2：计划冻结、预测误差与紧急购电

### 5.1 路线Q2-A：确定性预测＋因果执行 ✅

**科学问题**：日初只有历史时，如何形成可复现、无前视的全天计划？**定位**：Confirm预测后优化基线，Refine本题5倍缺口成本（C09、C12、C15）。用过去同一时段的1/7/14日均值、周同日或轻量回归得到\(\widehat L,\widehat V\)；选择只能用过去验证区间。零点解第3.2节的预测平衡，\(h=0\)，不强制日末等式。

真实执行时先计算\(a_t=g_t+(V_t-L_t)\Delta\)。基础反馈为：
\[
\begin{aligned}
a_t\ge0:&\ C_t=\min\{a_t,833.333,(10800-E_t)/0.9\},\ D_t=h_t=0,\ w_t=a_t-C_t;\\
a_t<0:&\ D_t=\min\{-a_t,833.333,0.9(E_t-1200)\},\ C_t=w_t=0,\ h_t=-a_t-D_t.
\end{aligned}
\]

储能立即更新，费用\(\sum p_tg_t+5p_th_t\)。这保证物理供电，并且紧急购电只填负载缺口，不通过5倍电价主动充电套利。该反馈是简单基线，**没有保存未来高价/高风险时段电量的能力**；因此全年费用不代表给定购电计划下的最佳实时控制。

```text
E=6000
对日期按顺序：
    首日执行零计划、储能不动协议
    其他日：只从此前已发生数据预测，解全天计划
    每10分钟仅以当前真实量执行储能反馈，缺口紧急购电
    记录实际日末E并传给下一天
    仅当日期>=2月1日，计入提交结果集合
```

调用`run_scheme(..., scheme='q2')`时价格必须是附件1重复365次；算法骨架见第11节。全年为364次日计划优化＋52560步简单反馈，实际开销通常在预测训练和审计而非此小LP上。工程估计半天可形成稳健基线；本次已运行，后续改进收益另测。

### 5.2 路线Q2-B：分位数预留与机会约束 ✅/⚠️

**科学问题**：5倍费用是否值得在计划中多买或留出储能？**定位**：Refine均值预测，借鉴概率负荷与PV评价（C11、C15），将不对称风险引入计划。

先看无储能单时段净需求\(N\)简化：\(\min_g pg+5p\mathbb E(N-g)_+\)。连续分布内点的一阶条件为\(P(N>g)=1/5\)，即\(g\)取80%分位数。这是解释风险预留的**简化推导**，不是完整144时段储能系统的最优分位数证明。

定义历史净需求误差\(e_t=(L_t-V_t)\Delta-\widehat n_t\)。在滚动校准集上估计\(q_{1-\epsilon_t}(e_t)\)，以
\[
g_t+D_t-C_t\ge\widehat n_t+q_{1-\epsilon_t}(e_t)
\]
代替均值供需下界，再加计划SOC、功率与非负约束，最小化计划费用。也可设\(E_t\ge1200+r_t\)，其中\(r_t\)由未来净缺口累计残差分位数除以放电效率给出。**这两个近似不应不加检验地叠加，否则可能重复预留。**

单时段经验分位数不是全天联合可靠性保证；若要用并集界保证全天违约概率≤\(\epsilon\)，需\(\sum_t\epsilon_t\le\epsilon\)，且单时段概率估计本身可信。31天历史无法稳健估计极端尾部，优先试\(q=.7,.8,.9\)及小幅储能预留，用过去验证段选参数，之后真实回放。

```text
以过去预测起点重建残差，不能用拟合内误差假装预测误差
按时段/提前量分组，稀少组回退到邻近组或总体
选分位数形成净需求上调曲线，解原LP
真实反馈回放，比较本金增长与紧急费用下降
```

Python骨架：`reserve=np.quantile(past_oos_residuals,q,axis=0); demand_kwh=forecast_net+reserve; plan=solve_reserved_lp(demand_kwh,known_price,E)`。`solve_reserved_lp`可直接使用第11节矩阵，把右端换成上述净需求；保留非负购电和弃电。该扩展尚未在本题运行。实现约4—8人时；经验预留✅，宣称严格机会约束保证⚠️，需要更多样本与校准证据。

### 5.3 路线Q2-C：场景随机规划与预算鲁棒 ⚠️

**科学问题**：误差时序相关且尾部费用高时，怎样同时评估多条未来路径？**定位**：Extend C05的价量场景与C07/C08的鲁棒/风险工具，保留本题信息结构。

完整因果形式：零点选择同一\(g^0\)，实时策略\(\pi_t\)只能依赖截至\(t\)的观测\(\mathcal F_t\)。
\[
\min_{g^0,\pi\ \mathrm{因果}}\sum_tp_tg_t^0+
\sum_s\omega_s\sum_t5p_th_t^s+\beta\operatorname{CVaR}_\alpha(J_s),
\]
各场景均满足第3.2节物理约束及紧急电只补负载的执行规则；共享初始SOC，同信息历史的节点必须共享相同决策。CVaR用
\[
\zeta+\frac1{1-\alpha}\sum_s\omega_s\xi_s,
\quad \xi_s\ge J_s-\zeta,\quad\xi_s\ge0
\]
线性化。\(\beta=0\)退化为期望费用，\(\alpha=.9/.95\)仅作待验证参数，不把CVaR等同于供电可靠性。

**两阶段陷阱**：把一整天实际路径揭示给场景内储能再优化，会得到完美信息再决策，不能直接称为本题可执行控制。它可用作乐观比较；要作为主策略，应采用场景树非预见性，或冻结近端动作、执行一个当前动作再重算，并用真实因果回放验证费用。连续场景几乎无完全相同历史，不能靠“相同数值前缀才绑定”假装完成了可靠的多阶段树构造。

预算集合可取\(e_t=\bar e_t+\sigma_tz_t,|z_t|\le1,\sum_t|z_t|\le\Gamma\)。线性表达\(a^Te\)的最坏值可对偶化为\(a^T\bar e+\Gamma\theta+\sum_tq_t\)，满足\(q_t\ge\sigma_t|a_t|-\theta,q_t,\theta\ge0\)。静态功率或累计风险约束可利用此式；不要把仅对目标系数的鲁棒公式直接当作含自适应SOC的完整鲁棒控制。

```text
从已到期、样本外的历史残差抽取完整日/连续块路径
保留PV与负载相关性；取10/20/50场景做规模敏感性
构建共有承诺与适当的非预见性约束，最小化期望或CVaR
只执行当前可用动作，推进真实SOC，再评价全部费用
```

骨架接口：`scenarios=sample_past_blocks(residual_history,S); model=build_tree_lp(initial_soc,scenarios,shared_plan=True); action=model.current_action(); actual_step(action)`。上面是接口级骨架，`build_tree_lp`需按场景树实现，未提供已测试的随机控制器。变量随\(ST\)增长；若加入模式/应急互斥二元变量，求解不确定性增大。预留约1天开发与诊断，不应同时开展多个复杂变体。当前效果【未验证】。

## 6 Q3：四次预报、修订费用与修订价值

### 6.1 路线Q3-A：确定性滚动LP/MPC ✅

**科学问题**：已获得新预报后，哪些剩余购电应改变？**定位**：Confirm C02/C04滚动模式，Refine“不退款、相对初始、最终一次”的费用。

零点用本次官方PV预报和历史负载预测求\(g^0\)。在\(r\in\{6,12,18\}\)时，以实际\(E_r\)为初态，仅对剩余时段\(\mathcal T_r\)优化：
\[
\min\sum_{t\in\mathcal T_r}p_tg_t^0+1.5p_tu_t+0.5p_tb_t-\lambda_EE_{144}
\]
满足新预测下的能量平衡、功率/SOC约束和第3.3节线性化；本确定性计划层\(h=0\)，实际缺口仍在执行时计5倍费用。主骨架\(\lambda_E=0\)，没有每天等电量要求。已交付前缀保持不动，原始计划\(g^0\)永不覆盖，后续修订可以覆盖尚未交付的上次修订。

```text
g0=零点预测下的全天计划；effective=g0.copy()
按10分钟顺序推进：
    若到6/12/18：取得当前发布的预报和实际SOC
        解剩余时域模型，费用基准仍为g0的剩余段
        effective[未来段]=新解；保留此次发布和修订记录
    当前区间按effective执行储能反馈
    当前交付后，根据effective与g0结算一次
```

代码`published_curve`、`solve_day(initial_plan=...)`与`run_scheme(scheme='q3')`见第11节。一次日初＋三次递减时域LP，主矩阵构造复杂度随时域线性增长。可行性难点集中在索引、已交付前缀、预测版本和实际SOC，不在求解器速度。本次主基线实际运行；预期增益必须通过下面的消融回答。

### 6.2 路线Q3-B：风险感知滚动/多阶段随机控制 ⚠️

**科学问题**：零点是否应少买，等待后续预报再上调？**定位**：Extend C05不确定性调度，同时把C04滚动执行作为部署方式。初始计划\(g^0\)对所有场景共享；各修订节点\(g^{r,s}\)只能取决于该时刻已发布预报；最终费用为
\[
\min\sum_s\omega_s\sum_t p_t\left[g_t^0+1.5(g_t^s-g_t^0)_++0.5(g_t^0-g_t^s)_++5h_t^s\right],
\]
另可加CVaR和终端价值。各场景均遵守物理、时间和应急用途规则。后续预报版本必须由历史“预报更新轨迹”建模，不能只随机生成PV实际值，却在零点偷用真实6/12/18预报。

简化单时段无储能、未来修订能准确获知需求\(N\)时，若不下调，\(\min_g pg+1.5p\mathbb E(N-g)_+\)给出\(P(N>g)=2/3\)，即初始约33%分位数；与Q2的80%分位数不同。这说明等待信息可能改变日初承诺，但**不代表本题应该统一少买到33%分位数**：未来预报也有误差，紧急费用、储能和跨日价值仍存在。

```text
由历史完整的0/6/12/18预报及其兑现误差构建少量分支
日初共享g0；6/12/18节点按可见信息共享修订
叶节点计算最终一次结算，加入物理状态与风险项
只部署当前节点决策，下一次获得新预报再更新
```

Python接口骨架：`tree=forecast_revision_tree(past_vintages); solution=optimize_commitments(tree,fee=settle); apply(solution.root); replan_on_new_issue()`。完整树、条件概率及尾部检验未实现，复杂度大于确定性MPC。推荐降险：先只在每次滚动时用10—20个残差场景，保持初始确定性计划；待可行与收益稳定再研究共同优化初始计划。实现约8—16人时，本题效果【未验证】。

### 6.3 修订价值的完整对照

| 编号 | 零点信息 | 6/12/18更新 | 目的 |
|---|---|---|---|
| A0 | 历史PV/负载均值 | 无 | Q2基础能力 |
| A1 | 官方零点PV＋同一负载预测 | 无 | 单独检验零点官方预报 |
| A2 | 同A1 | 官方PV更新，其他策略相同 | **核心：更新机制总收益** |
| A3 | 同A1 | 更新预测但禁止改变购电，只改储能控制 | 分离信息价值与购电修订价值 |
| A4 | 同A1 | 只6点/只12点/只18点/组合 | 各发布时刻的边际价值 |
| A5 | 同A2 | 风险预留或残差校正 | 检验扩展增益 |

A1与A2的负载模型、价格、效率和实时控制保持相同，但各自跨日SOC可不同，这是连续政策效果的一部分。比较单日纯修订价值时，可另外从同一日初SOC和同一\(g^0\)分叉，不能混用两类实验。主全年比较必须各自从1月1日顺序推进。

报告总费用\(J\)、初始本金、上调费、下调费、紧急费、应急kWh、弃电kWh、日末SOC、最大缺口/最差日费用。修订收益\(\Delta J=J_{A1}-J_{A2}\)，相对收益\(\Delta J/J_{A1}\)。错误越大不必然收益越大：过量预测PV造成缺口较危险；低估PV可能只产生多余购电；错误发生在低价或有富余储能时，费用影响又不同。

误差敏感性使用**仅从历史拟合的**偏差、尺度、时间块残差，以及固定种子的共同扰动；\(\kappa\in\{0,.5,1,1.5,2\}\)是实验参数。使用未来真实PV构造“精度为零误差”只能标为事后理想对照，不能进入可提交策略。按日配对比较成本，连续天自相关时采用周块重采样；这只是既有回放路径上的不确定性估计，不是重新模拟打乱日序后的政策。

## 7 Q4：未知实时电价的三条路线

### 7.1 路线Q4-A：历史日路径聚类/联合场景 ✅基线、⚠️扩展

**科学问题**：未见当天真实价格时，如何制定量的承诺？**定位**：Refine C14电价预测比较规范，Extend C05联合不确定性。首先以过去7日同一时段平均价作可执行基线，调用Q2/Q3计划模型；交易时才以实际价结算。

扩展：取过去已完成的日价格向量\(p^{(d)}\in\mathbb R^{144}\)，标准化参数只由历史拟合，K-medoids或K-means形成\(K=3,5,8\)类。优先用真实代表日/类内抽样保留尖峰，不只用平滑类中心。有限样本可直接按周块bootstrap，避免强行聚类。

\[
\min_{g^0,\pi}\sum_s\omega_s\sum_t p_t^s
\{g_t^0+1.5u_t^s+0.5b_t^s+5h_t^s\},
\]
加第3节与相应Q2/Q3的信息约束，可再加CVaR。PV、负载与电价若存在依赖，应按同一历史日/块联合抽样或对预测残差建联合模型；不能无依据地把\(\mathbb E[p h]\)替换为\(\mathbb E[p]\mathbb E[h]\)。仅价格随机、所有购电与应急量预先固定且不相关时，均价目标才是合法简化。

```text
每个预测起点只取过去日期，拟合价格基线/聚类
生成未来价量路径，保持历史相关与尖峰
解共有承诺与因果再决策模型
实际交易时记录真实价格；更新历史与SOC
```

骨架：`past=price[:day]; scenarios=sample_day_paths(past,K); plan=solve_scenario_plan(scenarios,history_only_forecasts,E)`。聚类与场景优化是待实现扩展；第11节已有历史均价可运行基线。三天内推荐“均价基线＋少量场景/CVaR”二选一增益，估计4—10人时，不以本次均价运行证明场景法胜出。

### 7.2 路线Q4-B：分时价格离散化与动态规划 ⚠️

**科学问题**：价格有少数可重复状态时，能否构建便于解释的实时储能政策？**定位**：Reframe连续价格为有限状态近似，C14支持严谨电价基线比较，但不提供本题转移概率。按历史分位数将每个时段价格分低/中/高等\(K_p\)类，历史估计\(P_t(j\mid i)\)。储能离散为\(N_E\)状态，已冻结购电和未来可修订状态必须进入模型。

当前价已可见后的储能Bellman形式可写：
\[
V_t(E,i)=\min_{a\in\mathcal A(E,\mathcal F_t)}\left\{c_t(a,p_i)+\sum_jP_t(j\mid i)\mathbb E[V_{t+1}(E',j)\mid\mathcal F_t,a]\right\}.
\]

动作\(a\)包括当期充放电/缺口补充，**不允许每个价格状态下随意重新制定整个当天的普通购电计划**。若要优化Q4-3修订，状态还需承诺向量、发布信息等，维度快速膨胀。不要只保留SOC和价格却丢掉未交付承诺。

```text
过去价格拟合分箱边界及转移，储能设置网格
固定一个合法日初计划，先做实时储能DP对照
倒推网格价值；真实时按当前价格/负载/PV选动作
逐日继承真实SOC，检验网格与转移估计敏感性
```

骨架`V[t,E,i]=min(stage_cost(a,i)+sum(P[t,i,j]*V[t+1,E_next,j] for j in states) for a in feasible_actions)`。转移和负载条件分布未实现；离散DP约\(O(TN_EK_p^2K_a)\)，承诺状态加入后远大于此。解释性强但31天样本估计稀疏，推荐仅作为固定计划控制对照；完整联合承诺DP❌，本题效果【未验证】。

### 7.3 路线Q4-C：价格预算鲁棒 ⚠️

**科学问题**：电价尖峰难预测时，怎样限制最坏成本？**定位**：将C07预算不确定性迁移到本题费用系数。对固定的非负计费等效量\(q_t=g_t^0+1.5u_t+0.5b_t+5h_t\)，令\(p_t=\bar p_t+\sigma_tz_t,0\le z_t\le1,\sum z_t\le\Gamma\)，则
\[
\max_p\sum_tp_tq_t=\sum_t\bar p_tq_t+\Gamma\theta+\sum_tv_t,
\quad v_t\ge\sigma_tq_t-\theta,\ v_t,\theta\ge0.
\]

将其加入模型仍线性。该表达严格对应**固定计费量的成本不确定性**；若\(h\)和未来修订随价格/负载自适应，须额外建可调整鲁棒策略或场景控制，不能说上式已解决全部联合不确定性。

```text
用过去电价预测残差确定sigma和预算候选Gamma
在目标中加入theta/v的线性约束，得到鲁棒承诺
在真实顺序回放中比较本金、应急费、最差日与CVaR
仅在历史验证区间选择Gamma
```

骨架：`theta=nonnegative_var(); v=nonnegative_vector(T); add(v>=sigma*q-theta); objective=mean_price@q+Gamma*theta+sum(v)`。建议\(\Gamma/T\in\{0,.05,.1,.2\}\)作为实验网格，不能从全年最大误差反向设安全边界。实现4—8人时，保守性可能吞掉平均收益，效果【未验证】。

## 8 深度学习预测与决策成本实验

### 8.1 数据清洗、滑窗和可用信息

完整pipeline：只读输入与单位检查→时间末端映射→按发布版本存储→历史基线→训练内标准化→严格滑窗→小模型早停→锁定模型→逐起点预测→优化→因果执行→费用复算。

清洗不能使用跨预测起点的双向插值补未来；当前核心数组没有缺失，无需为“清洗”修改真实值。异常峰值先保留并标记，PV为零可能是夜间，不是缺测。对后续新缺失可用过去同一时段中位数并增加缺失标志，不能把未来数值用于补过去。

令预测起点索引\(o\)，输入\(X_o=[y_{o-H},\ldots,y_{o-1}]\)，目标\(Y_o=[y_o,\ldots,y_{o+143}]\)。本骨架同时预测负载和PV，输入再加已知日历特征。训练起点满足\(o+144\le t_{\mathrm{train\_end}}\)；验证起点至少从训练边界开始，验证目标完全早于实际预测时刻。跨边界目标窗口丢弃，不随机划分滑窗。

BiLSTM可在**全为过去**的输入窗口内部双向编码；Transformer也可对这个历史窗口全注意力。不允许把预测目标与历史拼在一起后依赖掩码错误地泄漏未来。Q3可以另外加入当前官方预报这一已知未来协变量；Q2不能加入附件3。Q4不能把未来实际电价当作“已知未来协变量”。C18提供这种输入分离的架构参考。[TFT原研究](https://research.google/pubs/temporal-fusion-transformers-for-interpretable-multi-horizon-time-series-forecasting/)

### 8.2 训练协议与起点回放

第一次2月1日预测：1月1—24日用于拟合，1月25—31日用于验证/早停；标准化均值方差仅用拟合段。当前骨架\(H=144\)、预测144点、起点步长36，产生89个训练窗、25个验证窗，目标完全落在对应日期范围。窗口有重叠，因此不能将验证误差当成25个独立实验。

后续每月初从当时已发生数据重新训练/微调，或每周轻量更新；最早几天数据不足时保持历史基线。报告同时保留两类评价：**竞赛式历史顺序回放**完整覆盖2—12月；**锁定方案评价**只在早期日期选架构/超参，对较晚月份作未用于选择的比较。使用全年成本选出冠军再把同一年称为完全独立测试是不成立的，应明确是探索性事后比较。

归一化用训练均值/标准差，标准差设小下界防止全零；多输出损失可先对标准化目标取Huber/MSE，再研究按经济代价加权。预报误差训练标签必须等到目标兑现：例如1月31日18点发布的24小时预报，要到2月1日18点才完整可用，2月1日零点不能拿它全量训练。

训练建议：AdamW，学习率\(10^{-3}\)或\(3\times10^{-4}\)，weight decay \(10^{-4}\)，batch16/32，最多40—80轮，早停5—8轮，梯度裁剪1，固定随机种子2026并在候选胜出后补3个种子。这里只给候选范围，不做庞大笛卡尔积。先CPU小数据验证，再测当前GPU完整训练时长；显卡型号和CUDA包版本不等于GPU训练已验证。

### 8.3 模型逐一评估：问题→定位→方法→代价

| 模型路线 | 科学问题与文献定位 | 结构/超参起点 | 预期产出与分类 |
|---|---|---|---|
| 持续性/周同日/岭回归 | 简单季节结构能解释多少？Confirm C14、C25的强基线要求 | 昨日、过去7日同槽；岭回归用日历和历史滞后 | 必做✅；提供任何DL增益的参照 |
| LSTM | 历史动态是否补足日历？Confirm C12/C13/C19 | 1—2层、hidden32/64、H144/288，直接输出144步 | ✅结构；⚠️效果。不要声称长记忆必然优于均值 |
| BiLSTM | 历史内部的双向摘要是否有帮助？Refine C20 | 1—2层、每向32；取两方向最终隐状态 | ✅小对照；信息截止审计优先 |
| TCN | 卷积能否更快利用日内结构？Refine C21，领域Extend C17 | kernel3、channels32/64、dilation1…64；因果左填充 | ✅优先候选；受野至少覆盖所用历史 |
| 小Transformer | 注意力能否捕捉远程相关？迁移C22，接受C25负结果挑战 | d_model32/64，4头，2层，FFN64/128，位置编码 | ⚠️；少历史易过拟合，不把通用原论文当作PV证据 |
| Informer/PatchTST/TFT | 更长历史与多变量是否值得复杂结构？Extend C18/C23/C24 | 只选一种；Patch长度12/24，stride6/12；H288/1008再评估 | ⚠️单一试验；❌三天同时完整复刻三个 |
| 官方预报残差校正 | 在已有气象信息的预报上修正系统偏差是否更划算？Refine C11 | \(\hat V_{r,h}^{corr}=\max(0,\hat V_{r,h}^{off}+f(x_{past},r,h,\hat V^{off}))\) | ✅优先于从零击败官方；效果仍待验证 |

LSTM参数量约\(O(Hd(d+m))\)计算成本，TCN约\(O(Hk d^2\log H)\)，普通注意力存储含\(O(H^2)\)。这些是结构量级，不是实测GPU时长。当前网络骨架统一采用历史编码＋未来日历输出头；与正式论文的完整架构不同，不称为复现所有论文。Informer、PatchTST、TFT仅有设计建议，没有冒充实现。

伪代码统一为：

```text
对每个实际预测起点：
    如到训练日：取当时已知数据，划分更早拟合段/较近验证段
        仅用拟合段拟合归一化器，丢弃跨边界目标窗
        训练小模型，验证早停，恢复最佳权重
    用截止当前的历史＋已知日历/当前官方预报预测未来
    保存issue_time、target_time、模型版本和训练截止点
    把预测送入对应Q2/Q3/Q4模型，再按真实顺序执行
```

第12节提供LSTM/BiLSTM/TCN/Transformer四类完整PyTorch训练骨架；官方残差校正可把目标换成`actual_at_target-issued_forecast`，输入只放当时发布曲线和过去特征，训练样本必须已到期。建议先线性偏差校正或浅层网络，再决定是否需要复杂模型。实现与审计约半天，正式预测比较/调参另留半天至一天。

### 8.4 指标、表格与图设计

\[
\mathrm{RMSE}=\sqrt{N^{-1}\sum_i(\hat y_i-y_i)^2},\quad
\mathrm{MAE}=N^{-1}\sum_i|\hat y_i-y_i|.
\]
\(\mathrm{NRMSE}=\mathrm{RMSE}/s_{train}\)，明确\(s_{train}\)取训练期均值、标准差或训练最大值中的哪一个，并始终统一；没有装机容量就不能声称是额定容量归一化。若定义\(s_{train}\)为训练最大PV，要说明它是样本尺度。

普通PV MAPE在零值上无定义。仅对\(y_i>\tau\)计算带阈值MAPE，并报告\(\tau\)、保留比例；主排名用MAE/RMSE，另报全时段与日间。分位数预测增加pinball loss，区间报覆盖率与宽度，概率分布报CRPS等适当评分（C11/C15）。所有模型使用相同目标集合，不能把官方24个整点与自训144点直接混为同一个精度表。

三种落点必须分开：

1. **预测精度对比。**表：模型×发布时刻×提前量组（1—6、7—12、13—24h）×季节，列MAE/RMSE/NRMSE、日间MAPE与样本数。图：按提前量误差曲线、四季代表日真值与预报、按时刻误差热图。对官方公平比较先在整点；10分钟插值误差另表。
2. **误差分布与修订收益。**表：PV高估/低估、负载误差、储能余量、价格分层对应的\(\Delta J\)。图：预报偏差与紧急费散点、更新前后误差分位数、\(\kappa\)扰动—费用曲线。预期不是强行证明“误差大必然更需修正”，而是识别修订在哪种约束状态有价值。
3. **预测→优化成本对比。**固定求解器、风险系数、执行控制与效率，仅替换PV预测；负载模型变化另做正交对照。表：计划本金/调整/紧急费用及总费用，图：全年累计成本差、典型日SOC与缺口、最差日分析。不能由RMSE下降直接宣布经济收益。

SPO（C16）支持按决策损失评价预测，但其经典设定预测的是目标系数；本题PV/负载进入约束，需要带补救问题的重构。三天内先做预测后优化的可复现评价；端到端SPO+或对MILP反向传播本题效果【未验证】，不作为核心承诺。

## 9 已实际运行的检查与有限结果

### 9.1 Q1求解与效率敏感性【本题验证】

运行环境为Python3.12.14、NumPy2.2.4、SciPy1.16.2（HiGHS）；CPU求解。11项检查覆盖110/105/130元结算例子、LP/MILP一致、供电/储能残差、日末等式、功率上下界、充放电消除、下调支配、SOC下限应急与上限弃电。[检查记录](C:/Users/30130/Desktop/数模/tmp/C_research/optimization_checks.json)

| 效率情景 | Q1费用/元 | 全天购电/kWh | 交流侧充电/kWh | 交流侧放电/kWh |
|---|---:|---:|---:|---:|
| **主：充0.9、放0.9** | **35126.948589** | **59482.698998** | 20740.666132 | 16799.939567 |
| 敏感性：两侧均\(\sqrt{0.9}\) | 33801.495542 | 57526.243481 | 19842.710476 | 17858.439428 |
| 敏感性：充0.9、放1.0 | 33416.530707 | 57580.981296 | 20390.088630 | 18351.079767 |

后两项都为往返90%，但在内部容量与交流功率共同约束下，单程分解不同仍可改变结果。它们是显式敏感性参数组合，**不是用户已指定的往返90%唯一分解**。主口径保持两侧90%。首次LP/MILP壁钟约0.028/0.070秒，只代表当前模型和这次运行。

### 9.2 全年基础方案【本题验证】

每组都从1月1日零计划协议启动，逐日继承实际储能；下表仅计2—12月334天。Q2/Q3使用附件1固定价，Q4使用过去7日同槽价格均值预测、附件4当期价结算。负载为过去7日同槽均值；Q2的PV同样为过去均值，Q3采用当前官方预报插值。实时储能为第5.1节贪心反馈，**未做风险预留、未来价值优化或DL预测**。[全年记录](C:/Users/30130/Desktop/数模/tmp/C_research/annual_baseline.json)

| 方案 | 总费用/元 | 初始本金/元 | 上调费用/元 | 紧急费用/元 | 紧急购电/kWh |
|---|---:|---:|---:|---:|---:|
| Q2 | 28209525.38 | 11464691.82 | 0 | 16744833.56 | 2858054.08 |
| Q3 | 20152148.22 | 11660887.75 | 2550061.11 | 5941199.36 | 1143722.46 |
| Q4-2 | 29108948.75 | 11689981.54 | 0 | 17418967.21 | 2859901.54 |
| Q4-3 | 21009215.79 | 11883274.12 | 2650940.31 | 6475001.36 | 1187781.96 |

四组下调费用均为0，与命题A相符。实际SOC上下界、首日6000、跨日连续性检查通过，供电平衡最大残差约\(4.55\times10^{-13}\) kWh。2月1日初态依次约7310.211639、7310.253060、6661.678135、6661.678135 kWh；12月31日末均为1200 kWh。末态触及下限与本基线不含终端价值有关，不能据此为后续日期强加同样末态。

这四组的年度数值是**未调优策略的参考结果**，不是论文最终最优结果；Q2与Q3之间还同时改变了零点PV信息，不能直接把二者差额全归因于日内更新。

### 9.3 公平修订消融【本题验证】

补跑A1：同Q3零点官方PV、同历史负载预测、同附件1电价和实时控制，但禁止日内修订；独立推进全年。费用为27405810.06元，其中本金11661294.67元、紧急费15744515.39元；紧急购电2692372.92 kWh。A2开启修订后费用20152148.22元，因此该基线下减少约7253661.84元，约26.47%。[消融记录](C:/Users/30130/Desktop/数模/tmp/C_research/revision_ablation.json)

**支持的结论**：在这组已实现预测与控制设置下，日内更新显著降低所记录费用，主要通过减少紧急购电。**不支持的结论**：所有预测器下必然省26.47%、更新越频繁越好、DL一定带来额外收益。改进实时储能后，修订边际价值需重测。

首次消融调用误把附件4价格传给Q3，复核后已排除并用附件1固定价重跑；被排除结果单独保存于`tmp/C_research/rejected_revision_ablation.json`，未进入上表或结论。四组主基线的价格映射原本正确。

### 9.4 四种预测网络的功能检查【本题验证】

| 网络 | 参数数 | 实际训练范围 | 检查结果 |
|---|---:|---|---|
| LSTM | 14818 | 1月前24天拟合、后7天验证；1轮 | 通过 |
| BiLSTM | 37602 | 同上 | 通过 |
| TCN | 20706 | 同上 | 通过 |
| Transformer | 84098 | 同上 | 通过 |

每个模型均完成前向、反向、优化器更新、验证、最佳权重恢复和144×2预测；输出有限非负。将预测起点以后的全部真实值改为巨大数值，当前预测保持不变。CPU测试、89训练窗/25验证窗，详细记录见[预测检查](C:/Users/30130/Desktop/数模/tmp/C_research/forecast_checks.json)。

另有3项信息边界检查：改变18点未来发布预报不改变此前交付，改变Q4当天尚未揭示的真实电价不改变零点计划，改变Q2当天未揭示的真实负载/PV不改变零点计划，均通过。[信息检查记录](C:/Users/30130/Desktop/数模/tmp/C_research/information_checks.json)

这些检查不构成正式预测精度比较：没有全年滚动DL训练，没有官方预报胜负表，没有多种子统计，也没有DL带来的费用结果。GPU可用性与完整训练时长未实测。单轮验证损失不用于宣布TCN或其他模型胜出。

## 10 求解器、工程组织与三天内的取舍

### 10.1 求解器选型（2026-09-10核对官方资料）

| 工具 | 费用与规模限制 | 安装/工程成本 | 我队建议 |
|---|---|---|---|
| SciPy＋HiGHS | 开源；无商业许可证变量额度，受算力/内存限制 | 本环境已有并实际跑通LP/MILP | **当前首选**，无需先处理许可证 |
| Gurobi | 合资格学术用户可免费申请；商业授权需报价。随gurobipy的受限许可通常限2000变量/2000线性约束，含二次项限200变量 | 接口易用，学术资格及授权配置有额外工作 | 已有完整许可则适合场景MILP；不要为小LP耽误主线 |
| CPLEX | 免费版限1000变量/1000约束；合资格学术项目可无偿获取产品，具体许可按官方申请结果 | 安装/API/许可证中等成本 | 已熟悉者可用；Q3完整日LP加修订变量可能超过免费版 |
| PuLP＋CBC | 建模器和开源求解器，无上述商业额度 | 按所装版本检查CBC可执行文件；当前开发文档plain PuLP仅装建模器，支持`pulp[cbc]`额外安装 | 适合直观LP/MILP；别假设任意PuLP版本都捆绑CBC |
| CVXPY | 开源建模层；实际限额由后端求解器决定 | 默认后端不全支持整数；用`installed_solvers()`核实 | 写凸模型方便；MIP必须明确选支持整数的后端 |
| Pyomo | 开源建模层，**不自带独立求解器** | 需另装/配置HiGHS、CBC、Gurobi等 | 场景/多种模型统一时有价值，本次小LP无需再换接口 |

官方依据：[SciPy线性规划](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html)、[Gurobi价格与许可](https://www.gurobi.com/product/pricing-and-licensing)、[Gurobi学术许可](https://www.gurobi.com/academics)、[CPLEX价格与免费额度](https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing)、[PuLP安装文档](https://coin-or.github.io/pulp/main/installing_pulp_at_home.html)、[CVXPY后端能力](https://www.cvxpy.org/tutorial/solvers/index.html)、[Pyomo安装说明](https://www.pyomo.org/installation)。本次没有安装或实测Gurobi/CPLEX/CBC/CVXPY/Pyomo，不虚构商业价格或性能排名。PuLP网页为开发文档版本，不能当成当前已安装稳定版说明。

基础LP721变量；完整144时段修订模型再加288个差额变量为1009，已可能超CPLEX免费版1000变量；MILP再加模式变量。即使单日许可额度足够，多场景模型也可能很快超限。正确做法是先统计实际变量/约束，再选后端。

### 10.2 顺序推进、并行边界与结果导出

**允许并行**：不同模型、参数、随机种子、独立情景实验，各自拥有完整时间链；或同一确定预测起点内的独立训练评估。**禁止**：将365天各自从6000或某个固定SOC解完再拼接，或让子进程共同改同一个结果工作簿。

建议分层保存：不可变输入→长表预测版本→计划/修订记录→实时执行记录→结算账本→模板副本。每条执行记录至少有日期/时段、初始与有效购电、充放电、应急、弃电、E前后、当期价格、四项成本；每个模型存训练截止点和种子。

后续导出五份结果表时：复制模板到输出目录；修正显式区间标签但不移动数值；Q2—Q4只取2—12月；计划表写零点\(g^0\)，调整表写最终有效量并保留独立修订日志；充放电写实际执行汇总；相邻非零应急区间合并、合计kWh。表1指定时段10:00—10:10对应零基索引60，表2每4小时汇总24个10分钟电量，**不再乘1/6**。

导出后重新读回核对334天、144时段、日总量/费用、四个指定日期（3月20日、6月21日、9月23日、12月21日）、SOC连续和费用分解。数字仅在显示时舍入，优化与逐步状态不按单元格显示精度累计。若求解失败，应记录状态并回退到预先声明的可行因果基线，不能悄悄用真实未来数据补解。本阶段未生成正式结果工作簿，避免把研究基线误作提交成果。

### 10.3 三天剩余时间的实施优先级

优先级P0：锁定四项口径和数据接口；Q1复核；Q2—Q4完整可行因果链与结算；指定日期与模板导出。P1：A1/A2/A4修订消融、误差分层、分位数预留或官方预报残差校正。P2：从TCN/LSTM中选一主一辅，做滚动精度和成本对比；Q4加一种场景/CVaR策略。P3：Transformer大范围调参、多阶段完整场景树、端到端优化，时间不足立即停止。

若模型精度不赢，应保留负结果并检查误差方向与费用；若复杂模型运行失败，回到已通过物理/费用核验的LP基线，不为“用了深度学习”替换可用结果。此处只给任务3实施取舍；最终B/C选题与逐小时赛程留待任务5，未越阶段作最终裁决。

## 11 优化与因果回放的可运行Python骨架

依赖Python3.12、NumPy2.2.4、SciPy1.16.2。对应文件：[优化骨架](C:/Users/30130/Desktop/数模/tmp/C_research/optimization_skeleton.py)。下方是本次已运行版本，定义与正文一致；场景树、鲁棒扩展、正式模板输出另按接口实现。

```python
"""C problem research components, not final competition result export.
Python 3.12 / NumPy 2.2.4 / SciPy 1.16.2 (bundled HiGHS).
Energy variables use AC-bus kWh except E, which is stored battery energy.
"""
from dataclasses import dataclass
from time import perf_counter
import numpy as np
from scipy.optimize import linprog, milp, Bounds, LinearConstraint
from scipy.sparse import lil_matrix, vstack

@dataclass(frozen=True)
class Battery:
    eta_c: float=.9
    eta_d: float=.9
    minimum: float=1200.
    maximum: float=10800.
    power: float=5000.
    dt: float=1/6

def settle(initial, final, emergency, actual_price):
    a,b,h,p=map(lambda x:np.asarray(x,dtype=float),(initial,final,emergency,actual_price))
    if any(np.any(x<0) for x in (a,b,h)):
        raise ValueError('negative purchase quantity')
    return {'initial':float(p@a),'up':float((1.5*p)@np.maximum(b-a,0)),
            'down':float((.5*p)@np.maximum(a-b,0)),
            'emergency':float((5*p)@h)}

def solve_day(load_kw,pv_kw,price,e0=6000.,battery=Battery(),
              initial_plan=None,terminal_equal=False,terminal_value=0.,integer=False):
    """Deterministic forecast LP/MILP, no planned emergency purchases.
    initial_plan: original commitment for a FUTURE suffix, never last revision.
    terminal_value is an explicit sensitivity parameter, not a task constraint.
    Raw forecasts only; callers enforce forecast issue-time availability.
    """
    l,v,p=map(lambda x:np.asarray(x,float),(load_kw,pv_kw,price))
    n=len(l); b=battery
    if not(n==len(v)==len(p)>0) or not all(np.isfinite(x).all() for x in (l,v,p)):
        raise ValueError('shape or nonfinite inputs')
    if min(l.min(),v.min(),p.min())<0 or not b.minimum<=e0<=b.maximum:
        raise ValueError('invalid physical inputs; negative price needs another model')
    if not (0<b.eta_c<=1 and 0<b.eta_d<=1):raise ValueError('efficiency')
    idx={};cursor=0
    for name,size in [('g',n),('charge',n),('discharge',n),('spill',n),('E',n+1)]:
        idx[name]=np.arange(cursor,cursor+size);cursor+=size
    if initial_plan is not None:
        initial_plan=np.asarray(initial_plan,float)
        if initial_plan.shape!=(n,) or np.any(initial_plan<0):raise ValueError('initial plan')
        for name in ('up','down'):
            idx[name]=np.arange(cursor,cursor+n);cursor+=n
    if integer:idx['mode']=np.arange(cursor,cursor+n);cursor+=n
    objective=np.zeros(cursor);lo=np.zeros(cursor);hi=np.full(cursor,np.inf)
    hi[idx['charge']]=hi[idx['discharge']]=b.power*b.dt
    lo[idx['E']]=b.minimum;hi[idx['E']]=b.maximum
    lo[idx['E'][0]]=hi[idx['E'][0]]=e0
    if terminal_equal:lo[idx['E'][-1]]=hi[idx['E'][-1]]=e0
    objective[idx['E'][-1]]=-terminal_value
    constant=0.
    if initial_plan is None:objective[idx['g']]=p
    else:
        objective[idx['up']]=1.5*p;objective[idx['down']]=.5*p
        constant=float(p@initial_plan)
    rows=2*n+(n if initial_plan is not None else 0)
    A=lil_matrix((rows,cursor));rhs=np.zeros(rows)
    for t in range(n):
        A[t,idx['g'][t]]=1;A[t,idx['discharge'][t]]=1
        A[t,idx['charge'][t]]=-1;A[t,idx['spill'][t]]=-1
        rhs[t]=(l[t]-v[t])*b.dt
        A[n+t,idx['E'][t+1]]=1;A[n+t,idx['E'][t]]=-1
        A[n+t,idx['charge'][t]]=-b.eta_c;A[n+t,idx['discharge'][t]]=1/b.eta_d
        if initial_plan is not None:
            A[2*n+t,idx['g'][t]]=1;A[2*n+t,idx['up'][t]]=-1
            A[2*n+t,idx['down'][t]]=1;rhs[2*n+t]=initial_plan[t]
    A=A.tocsr();start=perf_counter()
    if integer:
        integrality=np.zeros(cursor);integrality[idx['mode']]=1;hi[idx['mode']]=1
        U=lil_matrix((2*n,cursor));upper=np.zeros(2*n);q=b.power*b.dt
        for t in range(n):
            U[t,idx['charge'][t]]=1;U[t,idx['mode'][t]]=-q
            U[n+t,idx['discharge'][t]]=1;U[n+t,idx['mode'][t]]=q;upper[n+t]=q
        res=milp(objective,integrality=integrality,bounds=Bounds(lo,hi),
                 constraints=[LinearConstraint(A,rhs,rhs),LinearConstraint(U.tocsr(),-np.inf,upper)],
                 options={'time_limit':30.,'mip_rel_gap':1e-8})
    else:
        res=linprog(objective,A_eq=A,b_eq=rhs,bounds=list(zip(lo,hi)),method='highs')
    if not res.success:raise RuntimeError(f'optimization failed: {res.message}')
    x=res.x;ans={key:x[ii].copy() for key,ii in idx.items()}
    # Exact removal of simultaneous cycling with free unrestricted energy spill.
    q=np.minimum(ans['charge'],ans['discharge']/(b.eta_c*b.eta_d))
    ans['charge']-=q;ans['discharge']-=b.eta_c*b.eta_d*q
    ans['spill']+=(1-b.eta_c*b.eta_d)*q
    residual=ans['g']+v*b.dt+ans['discharge']-l*b.dt-ans['charge']-ans['spill']
    balance=ans['E'][1:]-ans['E'][:-1]-b.eta_c*ans['charge']+ans['discharge']/b.eta_d
    ans.update(objective=float(res.fun+constant),wall_seconds=perf_counter()-start,
               max_supply_residual=float(abs(residual).max()),max_storage_residual=float(abs(balance).max()),
               solver_message=res.message)
    return ans

def execute_interval(e,delivery,load_kw,pv_kw,battery=Battery()):
    """Causal surplus/deficit feedback baseline at the current interval.
    It sees only current realized demand/PV, not future intervals. No emergency
    energy is purchased for charging. A controller upgrade may reserve storage.
    """
    b=battery; net=delivery+(pv_kw-load_kw)*b.dt
    if net>=0:
        charge=min(net,b.power*b.dt,max(0.,(b.maximum-e)/b.eta_c))
        discharge=emergency=0.;spill=net-charge
    else:
        discharge=min(-net,b.power*b.dt,max(0.,(e-b.minimum)*b.eta_d))
        charge=spill=0.;emergency=-net-discharge
    en=e+b.eta_c*charge-discharge/b.eta_d
    if not b.minimum-1e-7<=en<=b.maximum+1e-7:raise AssertionError('SOC bound')
    return en,charge,discharge,emergency,spill

def rolling_average(history,horizon=144,days=7):
    """Input history contains completed days only. Caller handles zero-history day."""
    h=np.asarray(history,float)
    if len(h)==0:raise ValueError('cold start needs declared protocol')
    return h[-days:].mean(axis=0)[:horizon]

def published_curve(hourly24,issue_hour,current_pv):
    """Linear interpolation of the CURRENT release, with observed lead-0 anchor.
    Returns remaining same-day interval-end values; no future release used.
    For midnight Jan 1, current_pv=0 is the declared cold-start boundary value.
    """
    h=np.asarray(hourly24,float)
    if h.shape!=(24,):raise ValueError('requires 24 lead-hour forecasts')
    future_ends=np.arange(1,(24-issue_hour)*6+1)/6
    return np.maximum(0,np.interp(future_ends,np.arange(25),np.r_[current_pv,h]))

def run_scheme(load,pv,prices,forecasts,scheme='q2',battery=Battery(),days=365,allow_revisions=True):
    """Sequential, deterministic research baseline. Not a final optimized policy.
    q2/q3 receive known tariff; q4 variants predict prices from completed days.
    Each scheme owns its entire January warmup and subsequent SOC trajectory.
    """
    e=6000.;records=[];b=battery;horizon=min(days,len(load))
    for day in range(horizon):
        initial=np.zeros(144);final=np.zeros(144);eh=np.zeros(144)
        charge=np.zeros(144);discharge=np.zeros(144);spill=np.zeros(144)
        e_start=e;revisions=[]
        if day>0:
            lh=rolling_average(load[:day]);ph=rolling_average(pv[:day])
            pf=rolling_average(prices[:day]) if scheme.startswith('q4') else prices[day]
            if scheme in ('q3','q4-3'):ph=published_curve(forecasts[day,0],0,pv[day-1,-1])
            initial=solve_day(lh,ph,pf,e,battery=b)['g'];final=initial.copy()
        for t in range(144):
            if day>0 and allow_revisions and scheme in ('q3','q4-3') and t in (36,72,108):
                hour=t//6;pvhat=published_curve(forecasts[day,hour//6],hour,pv[day,t-1])
                # Same load baseline retained to isolate PV revision effect.
                ans=solve_day(lh[t:],pvhat,pf[t:],e,battery=b,initial_plan=initial[t:])
                final[t:]=ans['g'];revisions.append({'t':t,'future_plan':final[t:].tolist()})
            if day==0:
                # Agreed cold start: zero commitment and no battery action.
                eh[t]=max(0.,(load[day,t]-pv[day,t])*b.dt)
                spill[t]=max(0.,(pv[day,t]-load[day,t])*b.dt)
            else:
                e,charge[t],discharge[t],eh[t],spill[t]=execute_interval(e,final[t],load[day,t],pv[day,t],b)
        costs=settle(initial,final,eh,prices[day])
        records.append({'day':day,'e_start':e_start,'e_end':e,'cost':sum(costs.values()),
                        'cost_parts':costs,'emergency_kwh':float(eh.sum()),
                        'initial':initial,'final':final,'charge':charge,'discharge':discharge,
                        'emergency':eh,'spill':spill,'revisions':revisions})
    return records
```

## 12 PyTorch完整训练骨架

依赖Python3.12、NumPy2.2.4、PyTorch2.10.0。对应文件：[预测骨架](C:/Users/30130/Desktop/数模/tmp/C_research/forecast_skeleton.py)。已完成第9.4节功能检查；模型输入实际历史/日历，尚未集成官方预报校正头和全年月度训练调度。

```python
"""Chronological PyTorch forecasting skeleton. No pretrained/performance claim.
Python 3.12, NumPy 2.2.4, PyTorch 2.10.0; CPU checks only.
Array rows are completed interval-end observations. Target order: load, PV.
"""
import copy, random
import numpy as np
import torch
from torch import nn
from torch.utils.data import Dataset, DataLoader

def seed_all(seed=2026):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)

def calendar_features(indices):
    # Known calendar covariates for 2025, Jan 1 was Wednesday (Monday=0).
    t=np.asarray(indices); slot=t%144; weekday=(t//144+2)%7
    return np.stack([np.sin(2*np.pi*slot/144),np.cos(2*np.pi*slot/144),
                     np.sin(2*np.pi*weekday/7),np.cos(2*np.pi*weekday/7)],axis=-1).astype('float32')

class Scaler:
    def fit(self,history):
        self.mean=np.mean(history,axis=0).astype('float32')
        self.std=np.maximum(np.std(history,axis=0),1.).astype('float32');return self
    def transform(self,a):return ((a-self.mean)/self.std).astype('float32')
    def inverse(self,a):return a*self.std+self.mean

class Windows(Dataset):
    def __init__(self,actual,origins,scaler,lookback=144,horizon=144):
        self.a=scaler.transform(np.asarray(actual,dtype='float32'))
        self.origins=np.asarray(origins);self.lookback=lookback;self.horizon=horizon
        assert self.origins.min()>=lookback and self.origins.max()+horizon<=len(self.a)
    def __len__(self):return len(self.origins)
    def __getitem__(self,k):
        o=int(self.origins[k]);past=np.arange(o-self.lookback,o);future=np.arange(o,o+self.horizon)
        x=np.concatenate([self.a[past],calendar_features(past)],axis=-1)
        return torch.from_numpy(x),torch.from_numpy(calendar_features(future)),torch.from_numpy(self.a[future])

class CausalBlock(nn.Module):
    def __init__(self,cin,cout,dilation,kernel=3):
        super().__init__();self.pad=(kernel-1)*dilation
        self.conv=nn.Conv1d(cin,cout,kernel,dilation=dilation)
        self.skip=nn.Conv1d(cin,cout,1) if cin!=cout else nn.Identity()
    def forward(self,x):
        y=self.conv(nn.functional.pad(x,(self.pad,0)))
        return torch.relu(y+self.skip(x))

class ForecastNet(nn.Module):
    def __init__(self,kind='lstm',hidden=32,layers=2,horizon=144):
        super().__init__();self.kind=kind;self.horizon=horizon
        if kind in ('lstm','bilstm'):
            self.encoder=nn.LSTM(6,hidden,layers,batch_first=True,bidirectional=kind=='bilstm',dropout=.1 if layers>1 else 0)
            width=hidden*(2 if kind=='bilstm' else 1)
        elif kind=='tcn':
            # Dilations through 64 cover 255 historical steps with one kernel-3 conv/block.
            self.encoder=nn.Sequential(*[CausalBlock(6 if i==0 else hidden,hidden,2**i) for i in range(7)])
            width=hidden
        elif kind=='transformer':
            self.project=nn.Linear(6,hidden);self.position=nn.Embedding(2048,hidden)
            layer=nn.TransformerEncoderLayer(hidden,4,hidden*2,.1,batch_first=True)
            self.encoder=nn.TransformerEncoder(layer,layers);width=hidden
        else:raise ValueError(kind)
        self.head=nn.Sequential(nn.Linear(width+4,hidden),nn.ReLU(),nn.Linear(hidden,2))
    def forward(self,x,future_calendar):
        if self.kind in ('lstm','bilstm'):
            _,(h,_)=self.encoder(x)
            z=torch.cat([h[-2],h[-1]],-1) if self.kind=='bilstm' else h[-1]
        elif self.kind=='tcn':z=self.encoder(x.transpose(1,2))[:,:,-1]
        else:
            pos=self.position(torch.arange(x.shape[1],device=x.device))[None,:,:]
            z=self.encoder(self.project(x)+pos)[:,-1,:]
        # Both bidirectional encoders and attention see strictly PAST observations.
        z=z[:,None,:].expand(-1,future_calendar.shape[1],-1)
        return self.head(torch.cat([z,future_calendar],dim=-1))

def train_at_cutoff(actual,cutoff,kind='lstm',lookback=144,horizon=144,
                    validation_days=7,epochs=40,patience=5,stride=36,batch_size=32,device='cpu'):
    """cutoff counts observations already released; never train on actual[cutoff:].
    Training targets end <= split; validation targets end <= cutoff.
    Purges origins whose target windows cross the train/validation split.
    For monthly competition replay call at Feb 1, Mar 1, ... with past-only data.
    """
    seed_all();known=np.asarray(actual[:cutoff],dtype='float32').copy()
    split=cutoff-validation_days*144
    if split<lookback+horizon:raise ValueError('insufficient history; use persistence baseline')
    scaler=Scaler().fit(known[:split])
    train_origins=np.arange(lookback,split-horizon+1,stride)
    valid_origins=np.arange(split,cutoff-horizon+1,stride)
    train=Windows(known,train_origins,scaler,lookback,horizon)
    valid=Windows(known,valid_origins,scaler,lookback,horizon)
    tr=DataLoader(train,batch_size=batch_size,shuffle=True,num_workers=0)
    va=DataLoader(valid,batch_size=batch_size,shuffle=False,num_workers=0)
    model=ForecastNet(kind,horizon=horizon).to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=1e-3,weight_decay=1e-4)
    loss_fn=nn.HuberLoss();best=float('inf');bad=0;state=None;history=[]
    for epoch in range(epochs):
        model.train();train_loss=0.;count=0
        for x,f,y in tr:
            x,f,y=x.to(device),f.to(device),y.to(device)
            optimizer.zero_grad();loss=loss_fn(model(x,f),y);loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
            train_loss+=loss.item()*len(x);count+=len(x)
        model.eval();total=0.;n=0
        with torch.no_grad():
            for x,f,y in va:
                x,f,y=x.to(device),f.to(device),y.to(device)
                total+=loss_fn(model(x,f),y).item()*len(x);n+=len(x)
        score=total/n;history.append({'epoch':epoch,'train':train_loss/count,'validation':score})
        if score<best-1e-6:best=score;state=copy.deepcopy(model.state_dict());bad=0
        else:bad+=1
        if bad>=patience:break
    model.load_state_dict(state);model.eval()
    return model,scaler,{'cutoff':cutoff,'split':split,'train_windows':len(train),'validation_windows':len(valid),'history':history}

def predict_at_origin(model,scaler,actual,origin,lookback=144,horizon=144):
    # Only historical slice copied; future actual values are inaccessible to network.
    past=np.arange(origin-lookback,origin);future=np.arange(origin,origin+horizon)
    x=np.concatenate([scaler.transform(actual[past]),calendar_features(past)],axis=-1)
    device=next(model.parameters()).device
    with torch.no_grad():z=model(torch.tensor(x[None],device=device),torch.tensor(calendar_features(future)[None],device=device)).cpu().numpy()[0]
    return np.maximum(0.,scaler.inverse(z))

def evaluate(actual,prediction,training_scale,threshold=10.):
    a,p=np.asarray(actual),np.asarray(prediction);e=p-a;mask=a>threshold
    rmse=float(np.sqrt(np.mean(e*e)))
    return {'MAE':float(np.mean(abs(e))),'RMSE':rmse,
            'NRMSE_train_scale':rmse/max(float(training_scale),1.),
            'MAPE_above_threshold':float(np.mean(abs(e[mask]/a[mask]))*100) if mask.any() else None,
            'mape_coverage':float(mask.mean())}
```

运行入口见[优化检查与全年回放](C:/Users/30130/Desktop/数模/tmp/C_research/check_optimization.py)、[预测功能检查](C:/Users/30130/Desktop/数模/tmp/C_research/check_forecast_and_ablation.py)。用于复现本报告研究结果；没有提供“执行后即生成最终比赛结果表”的承诺。

## 13 文献目录：26篇，25核心、1参考

元数据逐条核对正式出版页、作者机构存档、会议站点及DOI注册记录。英文题名/作者保留原文，正文分析为中文。文献C13按2019卷期引用，2017为在线年份；C21为预印本，不能标成正式ICLR论文。下面每条均附可借鉴点，**被引用不意味着已经复现**。

### C01 【核心】A critical and comparative review of energy management strategies for microgrids

作者：Pavitra Sharma；Hitesh Dutt Mathur；Puneet Mishra；Ramesh C. Bansal。

载体：Applied Energy，2022，327: 120028。链接：[出版记录或论文原文](https://doi.org/10.1016/j.apenergy.2022.120028)。

关联：优化综述。可借鉴点：借鉴微网能量管理分类及不确定性处理框架；本题不增加发电机或网络潮流。

### C02 【核心】A Model Predictive Control Approach to Microgrid Operation Optimization

作者：Alessandra Parisio；Evangelos Rikos；Luigi Glielmo。

载体：IEEE Transactions on Control Systems Technology，2014，22(5): 1813-1827。链接：[出版记录或论文原文](https://doi.org/10.1109/tcst.2013.2295737)。

关联：Q1/Q3 MPC。可借鉴点：借鉴MILP与预测控制结合、滚动更新状态的结构；实验系统与本题结算机制不同。

### C03 【核心】A Centralized Energy Management System for Isolated Microgrids

作者：Daniel E. Olivares；Claudio A. Canizares；Mehrdad Kazerani。

载体：IEEE Transactions on Smart Grid，2014，5(4): 1864-1875。链接：[出版记录或论文原文](https://doi.org/10.1109/tsg.2013.2294187)。

关联：分层调度。可借鉴点：借鉴集中能量管理的层次与调度接口；不移植孤岛微网的完整三相模型。

### C04 【核心】Microgrid Energy Management Using a Two Stage Rolling Horizon Technique for Controlling an Energy Storage System

作者：Mahmoud Elkazaz；Mark Sumner；Seksak Pholboon；David Thomas。

载体：2018 7th International Conference on Renewable Energy Research and Applications (ICRERA)，2018，: 324-329。链接：[出版记录或论文原文](https://doi.org/10.1109/icrera.2018.8566761)。

关联：Q3 两层滚动。可借鉴点：直接支持较长时域计划与较短时域储能控制组合；两层控制不等于两阶段随机规划。

### C05 【核心】Stochastic programming approach for optimal day-ahead market bidding curves of a microgrid

作者：Robert Herding；Emma Ross；Wayne R. Jones；Vassilis M. Charitopoulos；Lazaros G. Papageorgiou。

载体：Applied Energy，2023，336: 120847。链接：[出版记录或论文原文](https://doi.org/10.1016/j.apenergy.2023.120847)。

关联：Q2/Q4 场景。可借鉴点：借鉴电价与光伏不确定性下的两阶段MILP；其投标曲线与本题固定倍数费用应分开。

### C06 【核心】Constrained model predictive control: Stability and optimality

作者：D.Q. Mayne；J.B. Rawlings；C.V. Rao；P.O.M. Scokaert。

载体：Automatica，2000，36(6): 789-814。链接：[出版记录或论文原文](https://doi.org/10.1016/s0005-1098(99)00214-9)。

关联：MPC 终值。可借鉴点：借鉴终端约束、终端价值与滚动控制分析；不自动得到本题经济控制的稳定性证明。

### C07 【核心】The Price of Robustness

作者：Dimitris Bertsimas；Melvyn Sim。

载体：Operations Research，2004，52(1): 35-53。链接：[出版记录或论文原文](https://doi.org/10.1287/opre.1030.0065)。

关联：Q2/Q4 鲁棒。可借鉴点：借鉴不确定性预算Gamma，在过保守盒集与均值预测之间调节。

### C08 【核心】Optimization of conditional value-at-risk

作者：R. Tyrrell Rockafellar；Stanislav Uryasev。

载体：The Journal of Risk，2000，2(3): 21-41。链接：[出版记录或论文原文](https://doi.org/10.21314/jor.2000.038)。

关联：Q2/Q4 风险。可借鉴点：借鉴CVaR辅助变量线性化，单独控制高费用尾部而非只优化平均费用。

### C09 【核心】Review of photovoltaic power forecasting

作者：J. Antonanzas；N. Osorio；R. Escobar；R. Urraca；F.J. Martinez-de-Pison；F. Antonanzas-Torres。

载体：Solar Energy，2016，136: 78-111。链接：[出版记录或论文原文](https://doi.org/10.1016/j.solener.2016.06.069)。

关联：光伏综述。可借鉴点：据预测时域和可用输入选择物理、统计或学习方法，避免无气象数据时照搬NWP模型。

### C10 【核心】A review of solar forecasting, its dependence on atmospheric sciences and implications for grid integration: Towards carbon neutrality

作者：Dazhi Yang；Wenting Wang；Christian A. Gueymard；Tao Hong；Jan Kleissl；Jing Huang；Marc J. Perez；Richard Perez；Jamie M. Bright；Xiang’ao Xia；Dennis van der Meer；Ian Marius Peters。

载体：Renewable and Sustainable Energy Reviews，2022，161: 112348。链接：[出版记录或论文原文](https://doi.org/10.1016/j.rser.2022.112348)。

关联：多学科光伏。可借鉴点：连接大气科学、预测评价与电网使用价值，区分功率误差和调度收益。

### C11 【核心】Probabilistic solar forecasting: Benchmarks, post-processing, verification

作者：Tilmann Gneiting；Sebastian Lerch；Benedikt Schulz。

载体：Solar Energy，2023，252: 72-80。链接：[出版记录或论文原文](https://doi.org/10.1016/j.solener.2022.12.054)。

关联：概率光伏。可借鉴点：借鉴概率预报基准、后处理及校准评价；分位数不能当作独立路径直接拼接。

### C12 【核心】Short-Term Residential Load Forecasting Based on LSTM Recurrent Neural Network

作者：Weicong Kong；Zhao Yang Dong；Youwei Jia；David J. Hill；Yan Xu；Yuan Zhang。

载体：IEEE Transactions on Smart Grid，2019，10(1): 841-851。链接：[出版记录或论文原文](https://doi.org/10.1109/tsg.2017.2753802)。

关联：负荷 LSTM。可借鉴点：住宅负荷时序学习的领域先例；其数据量及用户聚合方式与本题不同。

### C13 【核心】Accurate photovoltaic power forecasting models using deep LSTM-RNN

作者：Mohamed Abdel-Nasser；Karar Mahmoud。

载体：Neural Computing and Applications，2019，31(7): 2727-2740。链接：[出版记录或论文原文](https://doi.org/10.1007/s00521-017-3225-z)。

关联：光伏 LSTM。可借鉴点：高引用经典光伏LSTM实例，用于结构起点；2019卷期、2017在线，不冒充近五年成果。

### C14 【核心】Forecasting day-ahead electricity prices: A review of state-of-the-art algorithms, best practices and an open-access benchmark

作者：Jesus Lago；Grzegorz Marcjasz；Bart De Schutter；Rafał Weron。

载体：Applied Energy，2021，293: 116983。链接：[出版记录或论文原文](https://doi.org/10.1016/j.apenergy.2021.116983)。

关联：Q4 电价。可借鉴点：借鉴电价预测基线与可复现比较规范；不能将某市场模型直接视作本题最优。

### C15 【核心】Probabilistic electric load forecasting: A tutorial review

作者：Tao Hong；Shu Fan。

载体：International Journal of Forecasting，2016，32(3): 914-938。链接：[出版记录或论文原文](https://doi.org/10.1016/j.ijforecast.2015.11.011)。

关联：概率负荷。可借鉴点：支持从单点预测转向区间与分布，并按决策需求选择概率评价。

### C16 【核心】Smart “Predict, then Optimize”

作者：Adam N. Elmachtoub；Paul Grigas。

载体：Management Science，2022，68(1): 9-26。链接：[出版记录或论文原文](https://doi.org/10.1287/mnsc.2020.3922)。

关联：决策导向学习。可借鉴点：借鉴以优化决策损失评价预测；原SPO针对目标系数，本题负荷/PV进入约束，不能直接套用理论。

### C17 【核心】Day-ahead regional solar power forecasting with hierarchical temporal convolutional neural networks using historical power generation and weather data

作者：Maneesha Perera；Julian De Hoog；Kasun Bandara；Damith Senanayake；Saman Halgamuge。

载体：Applied Energy，2024，361: 122971。链接：[出版记录或论文原文](https://doi.org/10.1016/j.apenergy.2024.122971)。

关联：近年光伏 TCN。可借鉴点：提供层次TCN的区域光伏应用；本题没有该文区域与气象输入，先保留单站时间结构。

### C18 【核心】Temporal Fusion Transformers for interpretable multi-horizon time series forecasting

作者：Bryan Lim；Sercan Ö. Arık；Nicolas Loeff；Tomas Pfister。

载体：International Journal of Forecasting，2021，37(4): 1748-1764。链接：[出版记录或论文原文](https://doi.org/10.1016/j.ijforecast.2021.03.012)。

关联：多时域预测。可借鉴点：借鉴历史观测、已知未来协变量与静态属性的分离；无需在三天内完整复刻TFT。

### C19 【核心】Long Short-Term Memory

作者：Sepp Hochreiter；Jürgen Schmidhuber。

载体：Neural Computation，1997，9(8): 1735-1780。链接：[出版记录或论文原文](https://doi.org/10.1162/neco.1997.9.8.1735)。

关联：LSTM 基础。可借鉴点：门控记忆结构作为小样本时序基线；不由原始任务推断本题精度。

### C20 【核心】Bidirectional recurrent neural networks

作者：M. Schuster；K.K. Paliwal。

载体：IEEE Transactions on Signal Processing，1997，45(11): 2673-2681。链接：[出版记录或论文原文](https://doi.org/10.1109/78.650093)。

关联：BiLSTM 基础。可借鉴点：只对预测起点之前的历史窗口双向编码，避免把未来真实目标喂入反向网络。

### C21 【参考】An Empirical Evaluation of Generic Convolutional and Recurrent Networks for Sequence Modeling

作者：Shaojie Bai；J. Zico Kolter；Vladlen Koltun。

载体：arXiv:1803.01271 (预印本)，2018，。链接：[出版记录或论文原文](https://arxiv.org/abs/1803.01271)。

关联：TCN 基础。可借鉴点：比较卷积与循环序列模型的结构和有效记忆；仅按预印本引用，不虚构会议归属。

### C22 【核心】Attention Is All You Need

作者：Ashish Vaswani；Noam Shazeer；Niki Parmar；Jakob Uszkoreit；Llion Jones；Aidan N. Gomez；Łukasz Kaiser；Illia Polosukhin。

载体：Advances in Neural Information Processing Systems 30，2017，。链接：[出版记录或论文原文](https://papers.nips.cc/paper_files/paper/2017/hash/3f5ee243547dee91fbd053c1c4a845aa-Abstract.html)。

关联：Transformer 基础。可借鉴点：借鉴注意力和位置编码；原论文是机器翻译，不能作为光伏胜出证据。

### C23 【核心】Informer: Beyond Efficient Transformer for Long Sequence Time-Series Forecasting

作者：Haoyi Zhou；Shanghang Zhang；Jieqi Peng；Shuai Zhang；Jianxin Li；Hui Xiong；Wancai Zhang。

载体：Proceedings of the AAAI Conference on Artificial Intelligence，2021，35(12): 11106-11115。链接：[出版记录或论文原文](https://doi.org/10.1609/aaai.v35i12.17325)。

关联：Informer。可借鉴点：借鉴长序列的稀疏注意力与生成式输出；144点场景先检验普通小模型是否已足够。

### C24 【核心】A Time Series is Worth 64 Words: Long-term Forecasting with Transformers

作者：Yuqi Nie；Nam H. Nguyen；Phanwadee Sinthong；Jayant Kalagnanam。

载体：ICLR，2023，。链接：[出版记录或论文原文](https://openreview.net/pdf?id=Jbdc0vTOcol)。

关联：PatchTST。可借鉴点：借鉴时间分块降低注意力长度及通道独立结构，用作轻量扩展实验。

### C25 【核心】Are Transformers Effective for Time Series Forecasting?

作者：Ailing Zeng；Muxi Chen；Lei Zhang；Qiang Xu。

载体：Proceedings of the AAAI Conference on Artificial Intelligence，2023，37(9): 11121-11128。链接：[出版记录或论文原文](https://doi.org/10.1609/aaai.v37i9.26317)。

关联：DLinear 对照。可借鉴点：提醒必须比较简单线性基线；其负结果不等价于所有Transformer在所有序列上无效。

### C26 【核心】A temporal distributed hybrid deep learning model for day-ahead distributed PV power forecasting

作者：Yinpeng Qu；Jian Xu；Yuanzhang Sun；Dan Liu。

载体：Applied Energy，2021，304: 117704。链接：[出版记录或论文原文](https://doi.org/10.1016/j.apenergy.2021.117704)。

关联：近年光伏 GRU。可借鉴点：以本地历史光伏进行日前细粒度预测的先例，与本题无额外气象输入的条件较接近。

## 14 检索覆盖、饱和与待检验问题

### 14.1 实际检索分支与停止理由

| 分支 | 实际使用的检索词举例 | 纳入文献 | 覆盖与停止理由 |
|---|---|---|---|
| 微网优化综述/分层调度 | `microgrid energy management MILP review`; `A critical and comparative review of energy management strategies for microgrids`; `centralized energy management isolated microgrids` | C01/C03/C05 | 经典系统、2022综述、2023不确定性应用已覆盖；本阶段主题充分 |
| MPC与滚动 | `model predictive control microgrid Parisio`; `day-ahead scheduling rolling horizon`; `Microgrid Energy Management Using a Two Stage Rolling Horizon`; `Constrained model predictive control stability optimality` | C02/C04/C06 | 经典控制、领域应用、两层执行已覆盖；仍可扩展最新经济MPC理论 |
| 鲁棒/风险/随机 | `two-stage stochastic programming microgrid`; `The Price of Robustness`; `Optimization of conditional value-at-risk` | C05/C07/C08 | 数学工具＋近年领域交叉已覆盖；可调整鲁棒、多阶段非预见性仍有空间 |
| 光伏与概率预测 | `Review of photovoltaic power forecasting`; `A review of solar forecasting`; `Probabilistic solar forecasting Benchmarks post-processing verification` | C09/C10/C11 | 2016基础、2022跨学科、2023概率评价已覆盖 |
| DL光伏/负载 | `photovoltaic power forecasting deep LSTM`; `Short-Term Residential Load Forecasting LSTM`; `hierarchical temporal convolutional neural networks solar`; `A temporal distributed hybrid deep learning model` | C12/C13/C17/C26 | 经典LSTM＋2021/2024领域论文＋TCN/GRU交叉已覆盖 |
| 电价与决策学习 | `forecasting day-ahead electricity prices review benchmark`; `Smart Predict then Optimize`; `Probabilistic electric load forecasting tutorial` | C14/C15/C16 | 强基线、概率、决策评价已覆盖；新市场迁移仍有空间 |
| 时序架构/负结果 | `Long Short-Term Memory`; `Bidirectional recurrent neural networks`; `TCN Bai Kolter Koltun`; `Attention Is All You Need`; `Informer`; `PatchTST`; `Are Transformers Effective for Time Series Forecasting`; `Temporal Fusion Transformers` | C18—C25 | 经典、2021—2023长序列、简单模型负结果已覆盖，停止横向堆模型 |
| 中文高门槛 | `光伏功率预测 LSTM 电力系统自动化`; `微电网 两阶段随机规划 中国电机工程学报`; 针对相关期刊域名的组合 | 本次未纳入 | 未取得足以逐项核对的新增合格条目；不写成中文领域没有研究 |

停止采用“经典＋近年＋交叉覆盖”规则，26篇处于20—30配额内；没有宣称达到30篇上限，也没有将未记录的搜索轮数说成已完成连续两轮饱和。这里的饱和是本次可支持研究问题的覆盖，不是穷尽全球文献。中文特定期刊、2025—2026最新研究、分布鲁棒/可调整鲁棒、完整多阶段树、天气融合仍有扩展空间；不因实施只有三天就把这些方向从研究视野删掉。

必查的高引用光伏DL经典C13，出版页显示有大量引用，但其2019卷期已不在近五年；另纳入2021年12月C26和2024年C17补充近五年路线。C26的DOI登记引用计数本次读到119，仅作为影响力线索，**不声称它取得ESI高被引认证或固定百分位排名**。引用次数随数据库和时间变化，不能用来替代场景匹配。[C26出版入口](https://doi.org/10.1016/j.apenergy.2021.117704)、[Crossref登记记录](https://api.crossref.org/works/10.1016/j.apenergy.2021.117704)

### 14.2 访问与核验局限

部分ScienceDirect全文入口403、OpenReview论坛页出现浏览器验证，改用可检索出版摘要、作者机构记录或公开论文PDF；未绕过访问限制。元数据批量查询出现3次429，低速补查成功。正式来源题名/作者/载体核实不等于所有文章都全文精读，本报告不依赖不可见实验表格编造精确效果。

原始元数据和归档书目在`tmp/C_research/metadata.json`、`literature_records.json`。本阶段未进入任务4，尚未生成统一BibTeX和跨B/C去重文献库。所有来源的领域适用性由正文说明，工具文档不混入26篇论文配额。

### 14.3 下一轮最有判别力的实验

1. 用改进实时储能控制重做A1/A2，检验26.47%的基线修订收益是否主要来自简单控制器的缺陷。
2. 以同一官方预报为起点，比较不校正、线性残差校正、小TCN校正，分别记录精度与完整成本；若费用不改善，停止复杂化。
3. 在只使用历史校准的前提下，比较分位数预留与10—20联合场景，记录本金—应急费用折中和最差日。
4. Q4比较历史均价、价量联合场景和预算鲁棒；完美未来价仅作标注清楚的事后理想参考。
5. 完成正式表格导出核验，再决定论文保留哪些扩展。当前没有需要用户重新裁决的题意问题；算法候选的效果不确定性由实验解决。

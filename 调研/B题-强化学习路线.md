# B题-强化学习路线

TL;DR：B题适合用POMDP描述未知源与主动观测，但三天内不宜押注端到端RL。推荐几何启发式主线，至多增加“候选动作排序”的混合策略对照。收录12篇文献，含有明确适用边界的负结果。DQN、PPO、树搜索和混合路线的本题效果均【未验证】；局部代码检查不等于训练或官方测试通过。

## 1 决策、范围与证据边界

### 1.1 给本队的明确选择

**总体分类：⚠️ Answerable with extra work。**这个分类针对“几何主线稳定后，完成一个有限规模的高层RL对照实验”，不针对三天内可靠替代主线。若要求独立承担正式测试的全流程端到端RL，分类为 **❌ Not answerable in scope**，原因是环境一致性、训练稳定性和未知场景泛化尚无证据。

队员A负责几何和搜索保证，队员B负责协议、记账及测试，队员C利用PyTorch能力尝试候选排序模型。GPT agent可辅助整理文献、搭骨架、检查接口与实验记录；算法正确性和竞赛结论仍须队员逐项复核。调研覆盖广泛路线，实现只选能回答关键问题的实验，不把三人同时投入RL作为默认安排。

本报告完成任务2。任务1的[几何与启发式报告](C:/Users/30130/Desktop/数模/调研/B题-几何启发式路线.md)是前置基线；任务3的C题调研、任务4统一BibTeX和任务5最终选题比较尚未执行。

### 1.2 三种标签不相互替代

| 维度 | 标签及含义 |
|---|---|
| 来源 | 【核心】正式发表或官方文档；【参考】预印本；【线索】仅供追查、不列为论文引用 |
| 证据 | 【文献支持】原文实验或满足前提的数学证明；【本题验证】本地实际运行且明确测试范围；【未验证】本题策略效果或尚未完成的实验 |
| 可回答性 | ✅ 三天内可实现的明确子任务；⚠️ 需要额外工程、训练或验证；❌ 当前范围不可控 |

**全文四条策略路线在B题的清除率、时间优势和官方兼容性均为【未验证】。**文献中的性能数值属于相应作者的实验。本报告运行的物理片段、损失函数及动作屏蔽检查，只支持相应代码行为；没有训练策略，没有登录或调用官方模拟器，没有测得百万步训练速度。

### 1.3 REWRITE在本任务中的研究问题

主问题：**当搜索覆盖、定位几何和清除判定已经有规则基线时，学习剩余的调度选择，能否减少完成全部清除的虚拟时间，并保持完成可靠性？**

| 子问题 | 文献定位 | 最小实验 | 结论如何变化 |
|---|---|---|---|
| 候选排序是否优于手工权重？ | Refine：保留几何，把固定权重改为数据驱动 | 同候选集、同兜底，规则排序对比学习排序 | 没有收益则保留规则，不声称RL优越 |
| 是否需要长时序信息？ | Extend：将主动定位扩展到未知数量、频道调度 | 历史摘要MLP对比GRU；严格隔离测试地图 | GRU无收益就保留简单模型 |
| 收益来自候选设计还是学习？ | Reframe：从“算法名称比较”改为“增益来源” | 随机合法候选、规则候选、相同候选上的RL | 候选几何贡献更大则论文重心回到几何 |
| 为什么同分布有效、边界场景失效？ | Interrogate：检查分布与观测模型偏差 | 固定误差场、最短半径、定向盲区等留出测试 | 优先排查错误或过拟合，再讨论方法局限 |

这些是预注册的研究设计，不是已经观察到的发现。

## 2 从题目规则到POMDP与半马尔可夫决策

### 2.1 必须保留的B题规则

依据[B题题目](C:/Users/30130/Desktop/数模/document/CUMCM2026Problems/B题/B题.pdf)及接口说明的已核对文本：[附件1](C:/Users/30130/Desktop/数模/tmp/B_research/附件1.txt)、[附件2](C:/Users/30130/Desktop/数模/tmp/B_research/附件2.txt)。

| 项目 | 建模口径 | 误用会导致什么 |
|---|---|---|
| 源 | 半径1800 m圆形区域内10—16个固定源；1—20频道、每频道至多一源 | 给策略真实总数会形成信息泄漏 |
| 信号 | 每源固定有效半径1000—1500 m；Q4可能有未知朝向的半平面覆盖 | 一次无信号不能判定频道为空 |
| 误差 | 示向度误差有界±1°，同位置对同源误差固定 | 原地重复测量不能按独立噪声平均消除误差 |
| 行走 | 5 m/s，直线距离计时，移动途中不自动检测；可超出目标圆形区域 | 不能把连续经过区域都记为已扫描 |
| 检测 | 移动时间＋切换频道1 s（需要时）＋检测5 s | `near`也已消耗5 s检测 |
| 清除 | 移动时间＋光学3 s＋成功时清除2 s；20 m内即可，与朝向无关 | 清除失败也耗3 s；清除频道参数不改变测向机频道 |
| 接口 | 只有`/enter /measure /clear /exit`；移动和切换隐含在请求里 | 分拆成不存在的免费动作会训练出错误策略 |
| 观测 | `no_signal / near / direction`及示向度；清除结果 | 没有连续RSSI可用于梯度爬升 |
| 结束 | 要清除全部未知源；结束位置不限 | 已发现源清完不等于全部源清完 |

总虚拟时间为

\[
T=\frac{L}{5}+N_{\rm switch}+5N_{\rm measure}
  +3N_{\rm clear\_attempt}+2N_{\rm success}.
\]

例如原地同频道检测得到`near`后原地清除成功：\(5+3+2=10\) s；不退回检测费用。正式运行还受到虚拟100 h、程序运行20 min、25 min窗口约束，实际可用时间取相关限制中先到者。**虚拟时间目标与现实执行期限必须分别维护。**

### 2.2 隐状态、可观测状态、历史

采用POMDP记号 \((\mathcal S,\mathcal A,\mathcal O,P,Z,r)\)。隐藏世界可写为

\[
W=\{z_c,q_c,R_c,m_c,u_c,e_c(\cdot),a_c\}_{c=1}^{20},
\qquad 10\le\sum_cz_c\le16.
\]

其中 \(z_c\) 表示源是否存在，\(q_c\) 为固定位置，\(R_c\) 为半径，\(m_c\) 为全向或定向类型，\(u_c\) 为定向单位向量，\(e_c(p)\) 为固定空间误差场，\(a_c\) 表示未被清除。Q3设全向；Q4不把未知朝向当成可读特征。

物理状态为 \(s_t=(W,p_t,c_t,\tau_t)\)，已知部分包括机器狗位置、当前测向频道和累计虚拟时间。现实时间余量也应在执行器中维护。完整观测历史

\[
h_t=(p_0,c_0,a_0,o_1,\Delta t_0,\ldots,a_{t-1},o_t,\Delta t_{t-1})
\]

可导出“已发现源、定位区域、已清除频道、覆盖证据”。这些集合是**信息状态**，不是源的真实物理状态。网络输入采用 \(f(h_t)\) 仅是近似；除非证明它充分，否则不能称为严格马尔可夫状态。RNN也不自动证明充分性。

### 2.3 观测方程与负观测

对未清除的频道 \(c\)，在检测点 \(p\) 有

\[
V_c(p)=z_ca_c\mathbf1\{\|p-q_c\|\le R_c\}
\begin{cases}1,&m_c=\text{全向},\\
\mathbf1\{u_c^\top(p-q_c)\ge0\},&m_c=\text{定向}.
\end{cases}
\]

若 \(V=0\) 返回无信号；若 \(V=1\) 且距离不超过5 m则返回`near`；否则返回经过接口角度约定转换、量化后的

\[
\hat\theta=\operatorname{atan2}(q_y-p_y,q_x-p_x)+e_c(p),\quad |e_c(p)|\le1^\circ.
\]

实现必须统一角度方向、取值范围和跨0°处理。接口保留两位小数时，可采用额外0.005°量化裕度的工程保守处理；这是容差策略，不是修改题目物理误差界。

`no_signal`可能来自源不存在、距离过远、定向背面、已经清除。Q3在未清除且源存在这一分支上，可排除检测点1000 m内位置；Q4不能不带朝向条件照搬该排除。连续无信号形成的区域通常不再是一个凸多边形，不能为了网络输入简单而错误删除可行解。

### 2.4 几何belief与概率belief的接口

**可行集层，✅ Answerable now：**复用任务1的半平面相交与容差处理，维护

\[
P_c\subseteq \{q:\|q\|\le1800\}\cap\bigcap_i\operatorname{Wedge}(p_i,\hat\theta_i,1.005^\circ).
\]

严格实现可保存圆约束，或用外包多边形保守近似。测到信号同时给出距离不超过1500 m的约束；几何外包若未使用全部约束，只能变松，不能删掉真源。旋转卡壳计算**全体顶点间最大距离**，不能只比较四边形对角线。多边形直径小于40 m也不充分保证可一次清除，应检查最小覆盖圆半径 \(r_c\le20-\varepsilon\)。

**概率层，⚠️ Answerable with extra work：**若自建环境明确指定先验与似然，可维护粒子或网格权重：

\[
b_{t+1}(s')\propto Z(o_{t+1}\mid s',a_t)
\int P(s'\mid s,a_t)b_t(s)\,ds.
\]

每个粒子应携带位置、是否存在、半径、朝向及有关固定误差的假设。重复相同位置的观测不是新独立证据；错误地反复乘同一个独立似然会虚假收缩后验。未知源数10—16约束还会耦合不同频道，20个独立伯努利分布只是近似。

只保留 \(P_c\) 没有概率密度，不能直接声称“熵下降了多少”或“清除成功概率为95%”。可用面积、覆盖圆半径作为明确的几何代理指标；若使用 \(\log\operatorname{area}(P_c)\) 近似熵，必须注明条件分布均匀这一额外建模假设。

**推荐接口：**几何层负责可行区域与安全证书；概率层只影响动作优先级，不推翻几何证书。不知道官方分布时，采用多种实验分布分别评估，不把任一分布宣称为官方规则。

```text
更新信息状态(历史, 动作, 回包):
    先由执行器核对请求是否被接受，再更新时间、位置、当前测向频道
    direction → 加入误差扇区；更新区域、直径、最小覆盖圆
    near      → 记录距源≤5 m的证据，生成原地清除候选
    no_signal → 记录带频道和位置的负观测；按Q3/Q4区别推理
    clear成功 → 标记该频道已清除；不改变测向机频道
    可选粒子层 → 按显式先验/似然更新，保留固定误差相关性
    将可观测摘要交给策略，隐藏真值仅留给环境和离线评价器
```

### 2.5 动作、候选集与时长

数学上可分解为移动、切换、检测、清除；实际动作定义为一个完整合法请求

\[
a=(k,c,p'),\quad k\in\{\text{measure},\text{clear}\}.
\]

不让策略选择独立“免费移动/免费切换”。`exit`由完成证书或现实截止控制器处理，不作为随意可选的获奖捷径。由于不同动作耗时不同，聚合决策构成**半马尔可夫形式**；不能把每次请求都当相同1秒。

建议生成最多32或64个候选：下一覆盖点的未知频道检测、已发现源的不同交会点、满足覆盖圆条件的清除、`near`后的原地清除，以及强制兜底动作。候选优先保留兜底和证书动作，再裁剪其它项；每个候选保留确定ID、目标坐标、频道及类型。

候选特征可包含移动时间、切换指示、操作固定费用、源区域半径、与历史测点的几何关系、覆盖进度。未知“真实新增信息”或真实距源距离不能作为输入。对未来清除是否成功，可提供保证成功标记或估计值，不能读取环境真值。

初版固定20个频道槽，每槽约10个可观测特征，加全局位置、当前频道独热、时间和覆盖统计，补齐为256维；每候选16维。未知位置用状态位与缺失值掩码区分，不用坐标0冒充已定位原点。后续可用共享频道编码器＋池化，减少对频道编号的过拟合；三天内不必引入Transformer地图编码器。

## 3 奖励、完成可靠性与稀疏性

### 3.1 目标和基础奖励

优先考虑完成全部清除，在可靠完成的策略中优化期望虚拟时间：

\[
\min_\pi\mathbb E[T_\pi],\qquad
\Pr(\text{完成全部清除且未超时})\text{满足明确验收要求}.
\]

这不是用一个任意奖励常数就能精确保证的约束。训练可采用

\[
r_t=-\Delta t_t/s_T+B\,\Delta n_{\rm clear}
-\lambda\mathbf1\{\text{本步终止且失败}\}.
\]

设计起点可取 \(s_T=100\) s、\(B=10\)、\(\lambda=1000\)，**均为未调参建议**，不能称为最优或保证足够大。对于同一地图且都完成的轨迹，累计清除奖励 \(BN\) 相同，不改变时间排序；对于失败轨迹，任何有限罚值都不能自动保证最坏情形下全部清除。

主口径取 \(\gamma=1\) 的有限回合总时间目标。若改为 \(\exp(-\kappa\Delta t)\) 的连续时间折扣，应说明研究目标已变为偏好较早收益；若机械按请求步数折扣，则会让相同物理时间的动作切分方式影响目标。

### 3.2 势函数塑形与终止处理

【文献支持】Ng等的势函数塑形给出保持策略排序的条件框架；迁移到本题需满足相应状态、折扣和终止前提。[L05原文](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf)

在本报告的 \(\gamma=1\) 有限轨迹中，令

\[
r'_t=r_t+\Phi(h_{t+1})-\Phi(h_t),\qquad
\Phi(h_{\rm terminal})=0.
\]

则求和严格望远镜消去，\(\sum r'_t=\sum r_t-\Phi(h_0)\)。同一初始信息下，完整轨迹的排序保持不变。可使用有界的覆盖进度和几何半径构造 \(\Phi\)，例如对每个区域半径归一化、截断后求和；仍需进行“不塑形/塑形”对照。

成功和失败的真正终止都置终态势为0；采样器仅因批次长度停止而截断时，不应假装任务失败，也不应把真实终态处理套上去。价值自举必须使用截断前最后观测，不能使用下一回合重置后的观测。塑形不是新增的完成保证，归一化、裁剪奖励等额外处理也可能改变原来的等价关系。

### 3.3 随机策略究竟稀疏在哪里

以下只分析一个**人为均匀分布玩具模型**，不代表官方地图分布。源在圆形区域均匀、随机选择频道、清除点也无信息时，命中特定频道且距离20 m以内的概率上界约为

\[
p_{\rm clear}\le\frac N{20}\frac{20^2}{1800^2}
=6.17\times10^{-5}\sim9.88\times10^{-5}.
\]

忽略移动且假定独立伯努利试验，对应约1.01万—1.62万次尝试才有一次成功的量级；边界截断、已清除源会进一步改变它。这个推导说明盲目清除难以启动学习，**不能用于估算自适应定位策略的实际样本量**。

相反，全向、半径1000 m的同一玩具模型，在原点随机频道测到存在信号的概率为

\[
\frac N{20}\frac{1000^2}{1800^2}=15.43\%\sim24.69\%.
\]

因此不能笼统写“随机策略几乎不可能收到信号”。难点是把发现、交会、20 m清除、全部源完成串成长期决策；定向盲区还增加隐藏原因。候选几何、模仿预热、逐级课程可降低探索难度，但效果均【未验证】。

### 3.4 防止策略绕开任务

| 可能的奖励漏洞 | 防范 |
|---|---|
| 原地反复测量以刷“信息增益” | 用固定空间误差；重复观测无独立新增信息；每次照收5 s |
| 反复发现或清除同一源刷奖励 | 奖励仅取首次状态转移；已清除集合单调增加 |
| 避开难源、主动退出 | 无学习型任意结束；使用覆盖证据和总预算控制 |
| 长距离移动按一步只罚1 | 按实际 \(\Delta t\) 记账 |
| 通过环境奖励间接读取真实总源数 | 演练和训练可离线评价，但正式策略完成判定只用历史证书 |
| 候选裁剪删除覆盖兜底 | 强制保留；检查学习阶段总步数、覆盖欠账与剩余预算 |

任务1给出Q3七点覆盖、Q4保守121点覆盖及首次有效测向后的有限清除覆盖构造。混合策略应在有限次自由选择后接管到这些基线，或维护不会被无限推迟的覆盖任务。**有限性并不直接证明在官方现实20 min内完成**；必须把请求数、网络延迟和失败恢复一并实测。剩余预算不足时提前转入基线，也需要可计算的保守剩余代价，而不是随意的“再试几次”。

## 4 路线一：离散候选上的DQN

**分类：⚠️ Answerable with extra work；本题策略效果【未验证】。**实现网络与一次更新属于✅可完成子任务，稳定学出优于基线的策略不属于该保证。

### 4.1 科学问题与文献定位

子问题：在Q3/Q4每次决策中，用历史摘要对几何候选进行长期价值排序，能否降低检测和跨源移动成本？定位为 **Refine**：借用DQN的经验回放和目标网络，将固定动作改为带特征的候选集合。DQN原论文在电子游戏环境验证了价值学习，不提供本题定位或未知数量搜索的效果证据。[L01正式论文](https://www.nature.com/articles/nature14236)

### 4.2 模型、伪代码与代码接口

令 \(x=f(h)\)，每候选特征 \(v_a\)，网络计算 \(Q_\theta(x,v_a)\)。目标为

\[
y=r+\mathbf1_{\neg\rm terminal}\max_{a'\in A(h')}Q_{\bar\theta}(x',v_{a'}),
\qquad\mathcal L=\operatorname{Huber}(Q_\theta(x,v_a)-y).
\]

这里选择标准DQN，不把双网络误称为Double DQN。后者若加入，应改为在线网络选动作、目标网络评价，并单独记录变体；本阶段没有扩展这条文献分支。

```text
初始化在线网络、目标网络与回放缓冲
在自建环境采样一张训练地图；策略只读历史摘要
循环：
    几何层生成候选与掩码，强制保留基线候选
    ε概率随机选合法候选，否则取最大Q；经过执行保护规则
    执行动作，获取观测、真实耗时，更新历史与奖励
    保存本步和下步的候选列表、掩码、终止类型及实际执行动作
    从回放抽样，以目标网络计算自举目标，反向更新在线网络
    周期同步目标网络；达到真实终止或采样预算后转入评估
```

```python
# Python 3.12 / torch 2.10.0；完整组件见第10节附录。
net = CandidateNet(state_dim=256, candidate_dim=16)
target = CandidateNet(state_dim=256, candidate_dim=16)
target.load_state_dict(net.state_dict())
optimizer = torch.optim.Adam(net.parameters(), lr=3e-4)
loss = dqn_loss(net, target, batch)  # batch来自尚待实现的轨迹收集器
optimizer.zero_grad()
loss.backward()
torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
optimizer.step()
```

### 4.3 预期产出、复杂度与代价

预期产出是学习曲线、相同测试地图上的完成率与时间分布、候选排序变化，而不是预先承诺时间下降。每次打分大致为 \(O(Kw^2)\)，几何候选生成另计；回放需保存候选内容，不能只保存随时会改变含义的数组下标。

建议起始参数：候选上限32、批量128、学习率 \(3\times10^{-4}\)、回放10万条、探索率从1降至0.05；仅是调参起点。高风险为部分可观测状态混叠、回放旧分布、Q过估计、稀疏完成信号。降险是先缩为已发现源之间的排序、使用几何课程，并规定失败即回到规则基线。预计接口已有时需队员C约8—16人时搭建与排错，训练另计；这是计划估算。

## 5 路线二：候选分类策略PPO

**分类：⚠️ Answerable with extra work；本题策略效果【未验证】。**不建议首版直接输出任意二维坐标。

### 5.1 科学问题与文献定位

子问题：用带掩码的随机策略学习“继续定位/清除/寻找新源”的切换，是否比价值学习更容易稳定？定位为 **Extend**：借用PPO的裁剪更新，以几何候选构造动作空间。PPO算法稿为2017年预印本，本报告标【参考】，不虚构其NeurIPS或ICLR发表信息。[L02原稿](https://arxiv.org/abs/1707.06347)

### 5.2 模型、伪代码与代码接口

策略在合法候选上归一化：

\[
\pi_\theta(a\mid h)=\operatorname{softmax}_{a\in A(h)}z_\theta(f(h),v_a).
\]

取 \(\rho_t=\pi_\theta(a_t|h_t)/\pi_{\rm old}(a_t|h_t)\)，使用裁剪目标

\[
L^{\rm clip}=\mathbb E\min\{\rho_t\hat A_t,
\operatorname{clip}(\rho_t,1-\epsilon,1+\epsilon)\hat A_t\}.
\]

另加价值误差和熵项。不同长度动作通过奖励中的实际时间体现，主设定仍为 \(\gamma=1\)。GAE的 \(\lambda\) 是估计器参数，不等于时间折扣；初值可取0.95。

```text
冻结旧策略，收集若干自建环境轨迹
每一步存下历史特征、完整候选及掩码、旧对数概率、实际动作
按真实终止/采样截断区分计算优势和价值回归目标
在同一批旧数据上做少量epoch的裁剪策略更新
更新时不重排候选、不重算不同的合法动作集合
独立验证地图评估，选择模型；最终测试集只在冻结方案后使用
```

```python
logits, value = net(state, candidates, mask)
dist = torch.distributions.Categorical(logits=logits)
action = dist.sample()
old_logp = dist.log_prob(action).detach()
# 由独立收集器构造batch，含old_logp、adv、returns。
loss = ppo_loss(net, batch, clip=0.2)
optimizer.zero_grad()
loss.backward()
torch.nn.utils.clip_grad_norm_(net.parameters(), 0.5)
optimizer.step()
```

### 5.3 预期产出与风险

初始可用2048步一批、4个更新epoch、128批量、 \(3\times10^{-4}\) 学习率。数字是工程起点，没有在本题调参。PPO数据重复利用程度有限，环境慢时训练成本突出；策略熵下降过快还会固化错误习惯。

采样后若保护规则替换了动作，不能仍把替换后的轨迹当作原动作的无偏PPO样本。建议**在采样前**把强制回退状态的掩码缩为仅基线动作，并将该状态的策略损失权重设0；或者明确采用独立规则阶段、不把其数据加入策略梯度更新。示例损失函数只处理真正由保存策略采样的数据，外层收集器必须完成这项过滤。

相比连续动作端到端策略，有限候选降低坐标精度负担；这只是结构优势推断，没有收敛保证。预计队员C约8—16人时接好单一PPO版本，完整RNN-PPO、长序列回放和多算法调参会明显超出该估算。

## 6 路线三：POMCP式MCTS与有限前瞻

**分类：⚠️ Answerable with extra work；本题策略效果【未验证】。**标准MCTS是规划，不必包含强化学习；不能为了凑算法把树搜索都叫RL。

### 6.1 科学问题与文献定位

子问题：不训练策略网络，能否用短期模拟比较“再测一次”与“先处理另一个源”的长期代价？定位为 **Extend**：POMCP利用生成模型与历史树处理部分可观测规划；迁移到本题需自己维护后验和合法生成模型。[L03正式论文](https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps.pdf)

连续观测会使树分支极多。Sunberg与Kochenderfer分析了简单双重渐进扩展可能退化为单粒子信念的问题，并提出带权粒子的相应算法；这是不能把普通UCT骨架称为完整POMCPOW的原因。[L04正式论文](https://ojs.aaai.org/index.php/ICAPS/article/view/13882)

### 6.2 模型、伪代码与代码接口

历史节点上使用

\[
a^*=\arg\max_a\left[\bar Q(h,a)+c\sqrt{\frac{\log(N(h)+1)}{N(h,a)}}\right].
\]

每次模拟从当前信念采样一个隐藏世界，再在模拟中按动作生成可见回包。未来动作只依赖该条模拟的可见历史，**不能用采样世界的真坐标来生成下一候选**。源真值可以用于环境生成回包、计算清除结果，不能变成规划器的全知行动依据。

```text
重复M次：
    从当前belief采样世界粒子
    从根历史出发，在合法候选上按UCT选择
    生成模型推进一个动作，得到回包与耗时
    以“历史+动作+观测”进入子节点；达到深度则用规则策略估值
    回传累计奖励，更新访问次数和Q均值
选择根节点已访问动作中估值最高者
只在真实环境执行该一个动作；收到真实回包后更新belief并重新规划
```

```python
planner = HistoryUCT(actions_from_history, generative_step,
                     observation_key, heuristic_rollout)
action = planner.choose(sample_posterior_world,
                        history=public_history, simulations=64, depth=4)
# 生成模型、belief与history编码必须由调用方接好；不是现成官方客户端。
```

代码附录实现的是**根采样历史UCT框架**，未实现POMCPOW的粒子权重、渐进扩展及完整belief更新。对示向度分箱能减小分支，但会损失信息；接口两位小数也仍有约36000种方向值。分箱大小需做敏感性分析，不能宣称仍有原算法的连续空间保证。

### 6.3 成本与降阶方案

一次决策代价近似 \(O(MH(C_{\rm sim}+C_{\rm belief}+C_{\rm candidate}))\)。64次模拟、深度4只是小规模起点，不能据此断言毫秒完成。官方接口没有反事实克隆功能，不可在真实会话里试完多条分支再“撤销”。

若完整树难以可靠实现，退化为**一步情景前瞻＋几何基线续跑**：对每个候选在相同采样世界集合上估计总时间，选均值或风险分位数更好者。它是有限前瞻规划，不是完整POMCP。此降阶的外层循环✅可实现，效果仍【未验证】，且粒子先验错误会给出错误排序。

```python
def one_step_rollout(candidates, worlds, evaluate_with_baseline):
    # evaluate函数内部允许环境读取真值；其后续决策只读取模拟回包。
    scores = {a: sum(evaluate_with_baseline(w, a) for w in worlds) / len(worlds)
              for a in candidates}
    return min(scores, key=scores.get)  # 比较完整续跑时间，失败另行处理
```

## 7 路线四：几何底层＋学习高层（优先候选）

**分类：⚠️ Answerable with extra work；本题策略效果【未验证】。**如果主线没有稳定完成，直接放弃本路线的赛期训练。

### 7.1 科学问题与文献定位

子问题：已知定位几何、时间成本和覆盖规则后，仅学习有限候选的相对收益，是否比重学全部物理关系划算？定位为 **Refine / Reframe**：把任务转成受约束的高层选择。

Active Neural SLAM提供模块化学习与规划结合的架构例子，其任务是视觉探索，不能搬来当无线电定位性能证据。[L06官方论文](https://openreview.net/pdf?id=HklXn1BKDH) 与本题更贴近的主动多目标定位工作使用TD3，但明确假定目标最初可观测、不处理搜索；可借鉴不确定性表示，不能用它支持“未知10—16源全流程已解决”。[L07作者全文](https://ksengin.github.io/papers/wafr2020active.pdf)

近期“何时定位”的风险约束研究关注机器人自身定位和昂贵测量，并不是干扰源定位；只借用付费观测时机的研究问题。[L12作者稿](https://arxiv.org/abs/2411.02788)

### 7.2 推荐的分工模型与伪代码

\[
\text{观测历史}\xrightarrow{\text{几何更新}}(P_c,\text{覆盖证据})
\xrightarrow{\text{候选生成}}A(h)
\xrightarrow{\text{学习排序}}a
\xrightarrow{\text{预算/覆盖约束}}\text{合法请求}.
\]

底层固定实现：扇区相交、旋转卡壳、覆盖圆清除条件、Q3/Q4覆盖、实际记账和请求幂等。高层只学：哪个已发现源先处理、何时继续缩小区域、什么时候插入尚未检查的频道。

先记录规则策略轨迹，对同一候选集给出教师动作，最小化

\[
\mathcal L_{\rm BC}=-\mathbb E\log\pi_\theta(a_{\rm rule}\mid h).
\]

然后仅在自建训练环境用PPO小规模微调。**行为克隆是监督学习，只有后续奖励优化阶段才是RL。**教师动作必须在候选裁剪前保留；只模仿一个教师不能保证超越教师，可能仅压缩其规则。也可训练候选续跑成本回归器，再交给规划器排序；该分支属于学习辅助规划，应准确命名。

```text
阶段A：几何规则基线独立跑通；冻结时间记账和观测接口
阶段B：收集训练地图规则轨迹，检查输入是否含真值
阶段C：模仿教师候选选择，验证集评估能否复现基本行为
阶段D：可选PPO微调，只改变高层排序，不改几何和协议
执行时：强制覆盖/剩余预算不足/学习次数达上限 → 基线接管
冻结模型后，在独立地图和边界分布上做成对比较
```

```python
loss = imitation_loss(net, state, candidates, mask, teacher_actions)
optimizer.zero_grad()
loss.backward()
optimizer.step()
chosen = shielded_choice(policy_action, baseline_action,
                         learned_used=used, learned_budget=30,
                         coverage_due=coverage_due,
                         sufficient_reserve=reserve_ok,
                         allowed=legal_actions)
```

30是演示性的整回合学习动作总上限，不是每轮重置，也不是推荐的已验证最佳值。保护规则的预算估计、覆盖进度和候选合法性需由几何执行器提供。若通过规则替换动作，训练处理须遵守第5.3节的策略梯度边界。

### 7.3 预期产出与可证伪条件

希望得到的是一个范围清楚的结论，例如“在所列自建分布及候选设计下，高层排序减少某类重复检测”，而非“RL解决B题”。若收益只出现于训练分布或只减少均值却提高失败率，则不能推荐正式使用。

同一几何骨架至少对比四个版本：规则排序、随机合法排序、模仿学习、模仿＋RL。各版本共用候选生成和兜底，才有机会区分学习与几何的贡献。若只有更丰富候选的RL版本胜出，则增益归因不成立。

完整代价包括前置仿真器，而非只算一个小网络训练。基线已稳定时，队员C可给这条路线一个明确的6—12人时探索额度，再按第9节停损；这是工作分配建议，不代表该额度内必有训练成果。

## 8 训练环境：官方接口与自建仿真

### 8.1 官方模拟器能否直接训练

结论是**不适合作为大规模在线训练后端**，不是“官方禁止任何训练”。公开接口未提供可编程重置、保存/克隆状态、指定种子或生成反事实回包的端点；演练还需要在相应会话和实际时间限制内执行。多次演练允许进行策略测试，不等于可以把一次正式会话当成百万步交互环境。

| 用途 | 判断 | 原因 |
|---|---|---|
| 少量策略的演练评估 | ✅ 可安排，具体耗时待测 | 走正常接口，获取有限轨迹与最终反馈 |
| 官方会话中边测边训练并反复重置 | ❌ 当前范围不成立 | 没有公开的自动重置/克隆训练接口，时限严苛 |
| 在官方环境进行MCTS分支模拟 | ❌ 不成立 | 每个被接受的动作都会真实推进状态，不能撤回 |
| 自建环境并行采样，官方串行验证 | ⚠️ 可行但需校准 | 独立环境可并行，单个官方会话状态必须顺序推进 |

执行器必须为新动作生成新请求ID，重试则复用相同ID和完全相同请求体；先核对HTTP与`accepted`，未被接受不能误推进本地状态。同账号不得同时在两个设备开启活动会话。演练结束后才能获得的真值或数量，不能提前放进策略输入。

### 8.2 自建环境的最小保真范围

**环境搭建本身：⚠️ Answerable with extra work。**可先写无网络物理核心，再接同一策略接口；不要把自建回包字典格式误认为官方JSON协议。

```text
离线创建隐藏世界（种子只交给环境）
    随机或构造10—16个源；分配互异频道
    固定各源位置、半径、朝向、误差场
reset → 输出机器狗初始公开状态，不输出隐藏世界
step(完整检测/清除动作)
    验证参数 → 计直线移动、切换与操作时间
    隐藏世界计算可见性、near、示向度或清除结果
    返回仅由官方可观察信息构成的反馈
    另将真值写到独立评价器，不传给策略
策略的结束器根据自己的证据结束；评价器最后判断是否真的全部清除
```

| 项目 | 应保持不变的规则 | 可随机化的实验维度／不能偷加的简化 |
|---|---|---|
| 几何 | 圆形区域1800 m、源静止、机器人可出域 | 均匀、成簇、近边界、对称布置分别测试；不是已知官方分布 |
| 源数 | 10—16；策略不可见真值 | 训练可抽取，测试按10/13/16分层 |
| 半径 | 每源固定、在1000—1500 m | 端点、混合和中间值；不只训练1500 m |
| 定向 | 半平面、朝向未知；光学清除无方向限制 | 随机朝向、背向主要扫描点、全部定向等压力场景 |
| 误差 | 同一位置固定，幅度≤1° | 平滑空间场、固定哈希场、正负接近边界的场；不可每步重采独立噪声 |
| 动作成本 | 按第2.1节逐项计费 | 不把远距离跳转或失败清除设成免费 |
| 数值 | 方位角循环、阈值闭区间、坐标有限 | 在5 m、20 m、1000/1500 m、半平面边界构造专门用例 |
| 协议 | 后续适配层需处理接受/拒绝、重试幂等 | 物理核心可暂时不实现HTTP，但不能声称已完成官方接入 |
| 完成 | 保留策略自身完成判断 | 若训练环境直接提前终止于真值全清，会隐藏错误结束器；必须另测部署版结束逻辑 |

领域随机化可借鉴模拟到现实迁移的研究思想，但随机化并不保证包含真实机制，也不能用一个方便的噪声模型代替官方固定误差规则。[L11作者稿](https://arxiv.org/abs/1703.06907)

附录`PhysicsSketch`只实现给定源列表下的检测/清除物理片段，误差取固定平滑正弦场。它**没有**地图分布生成器、完整belief、官方HTTP、现实期限、自动重置和完整训练循环；是便于接续的研究骨架，不是已完成的比赛模拟器。

### 8.3 课程与数据隔离

推荐由容易到完整：单个已发现源的交会选择 → 多个已发现源的处理顺序 → Q3未知源数与频道搜索 → Q4定向盲区。课程中的“已发现”由初始观测构造，不能直接给出真实坐标。小场景课程可以减少源数，但必须标为训练辅助任务，不能用其成绩代表满足10—16源的B题。

训练、验证、测试按**地图种子/构造家族**切分，不能从同一地图的相邻状态随机分到三份。对官方演练做过策略选择后，该演练结果属于开发证据；不能再当未经选择偏差影响的独立测试成绩。

## 9 三天内的硬评估与停损

### 9.1 算法对照表

| 路线 | 主要收益假设 | 主要成本与失败方式 | 本队优先级 | Answerability |
|---|---|---|---|---|
| DQN候选排序 | 复用旧轨迹，学习长期时间价值 | 回放和候选一致性、部分可观测、Q偏差 | 次于混合PPO；不同时实现两套训练框架 | ⚠️ |
| PPO候选策略 | 接口直接，能学随机高层切换 | 交互样本多、奖励/终止处理、种子差异 | 作为混合路线的唯一可选RL优化器 | ⚠️ |
| POMCP式MCTS | 不需要先训练策略，可比较前瞻后果 | belief/生成器质量、连续观测、在线算时 | 粒子模型已具备时再选；否则一步前瞻 | ⚠️ |
| 几何＋模仿＋可选PPO | 降低需要学习的自由度，保留基线 | 仿真分布偏差；增益可能只来自几何 | RL方向内第一选择 | ⚠️ |
| 完全端到端连续位置＋频道＋清除策略 | 极大自由度，可能发现复杂协作次序 | 样本、精度、覆盖与完成可靠性都不可控 | 三天内不进入主线 | ❌ |
| 只做物理记账/网络维度/掩码检查 | 快速暴露实现错误 | 不能说明策略有效 | 必做且已完成部分 | ✅ |

以上都是可实现范围判断。模型简单不等于训练简单，也不等于正式成绩更好。

### 9.2 时间估算必须分开工程、训练与评估

当前宿主读到Python3.12.14、PyTorch2.10.0+cu126、NumPy2.2.4；系统显卡查询为RTX 4060 Laptop GPU、8188 MiB显存。局部检查使用CPU。**没有测试CUDA训练速度，不假设全队其它机器配置相同。**该小网络实测68,226参数，参数本体很小；实际瓶颈可能在几何、采样、Python循环和多场景评估。

设交互总数 \(N_{\rm tr}\)、完整采样速度 \(v\)、优化次数 \(U\)、每次更新时间 \(t_u\)，则

\[
T_{\rm wall}\approx T_{\rm environment}+N_{\rm tr}/v+Ut_u+
T_{\rm evaluation}+T_{\rm debugging}.
\]

下表仅是算术情景，不是本题基准测试；速度单位为包含策略和几何的**完整转移/秒**。

| 假设速度 | 单种子100万转移的纯采样时间 | 三种子串行纯采样时间 |
|---|---:|---:|
| 100/s | 2.78 h | 8.33 h |
| 1000/s | 16.67 min | 50 min |
| 10000/s | 1.67 min | 5 min |

上述均未包括工程、梯度更新和评估。实际时间必须先用拟采用的完整环境测1万转移再外推；不能拿上面的物理片段速度代替全流程速度。多进程仅采样独立自建世界，不能把一个官方会话拆给多个进程乱序执行。

若回放保存状态256维、候选64×16维，两份当前/下一状态均为float32，10万转移仅这两组特征即约1.024 GB（十进制），还未包括掩码、奖励和对象开销；应主要放CPU内存，按批传入GPU，避免误以为68k参数意味着训练全部只占几MB。

### 9.3 三人分工与进入条件

按实际剩余三天规划，以下是相对工作段，**不是从此刻重新获得完整72小时**。

| 工作段 | 队员A | 队员B | 队员C与agent辅助 | 是否继续RL |
|---|---|---|---|---|
| 首个约4—6小时 | 几何主线与覆盖检查 | 协议、记账、幂等与演练准备 | 校准自建环境，复查观测特征无真值 | 主线没跑通则暂不训练 |
| 随后约6—12小时 | 修定位与清除边界失败 | 留出地图、统一指标 | 只实现一种高层模型和模仿预热 | 不能复现教师基本行为则停 |
| 次日可分配时段 | 改进启发式、论文数学推导 | 独立成对评估、压力场景 | 小规模RL微调，保留3个种子或明确样本限制 | 未见可重复增益则退出RL主实验 |
| 最后一天 | 整合已确认主线 | 正式测试前冻结与恢复预案 | 整理正负结果、图表和证据边界 | 不再引入新RL结构 |

建议给RL额外研究设置6—12人时的第一道门槛；完整自建环境如果尚未存在，环境工程可能另需8—16人时甚至更多。因此不能把两项加起来仍写成“半天可搞定”。三个人的并行工作能降低日历等待，但不能消除前置依赖。

### 9.4 评价与可证伪实验

先用少量构造用例排错，再用至少30—50张固定验证地图筛选；若进入正式比较，建议每类Q3/Q4至少100张冻结测试地图、3个训练种子，同时保留半径/朝向/误差的压力组。这是可调整的设计规模，不是已运行数量。

| 指标 | 计算与解释 |
|---|---|
| 全清完成率 | 达到所有真实源清除且未超时的回合比例；只能由评价器使用真值计算 |
| 成对虚拟时间差 | 同一地图同时成功时比较 \(T_{\rm learned}-T_{\rm baseline}\)；明确联合成功样本数 |
| 失败风险 | 单独列漏源、定位失败、虚拟超时、现实超时、协议失败；不能删掉失败回合 |
| 全样本代价 | 预先规定失败罚时/排序规则，并做罚值敏感性；与条件成功时间一起报告 |
| 代价分解 | 移动、切换、检测、光学尝试、清除；解释收益发生在哪里 |
| 稳定性 | 每个训练种子的成绩、地图分层分布、差值区间；不能只报最佳种子 |
| 运行开销 | 推理/候选生成/请求耗时分开，记录95分位与现实总时长 |

有限种子评估容易给出不稳健排名，应报告不确定性，不能把同一训练种子的1000个测试回合当成1000个独立训练重复。[L10正式论文](https://papers.nips.cc/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf) 在本题成对设计中，可先按训练种子报告，再在同一地图内配对差值，采用保留种子与地图层次的重采样；三种子的区间仍很不稳定，应如实注明。

可预设“完成率未出现新增失败、成对时间下降且跨种子方向一致”为进入进一步官方演练的筛选门槛；有限测试通过**不证明**所有地图都安全。若时间均值改善但失败率升高，继续使用几何基线。若只有训练分布改善，将结论收窄为分布内现象。若结果相反，按顺序排查协议/奖励错误、随机差异和稳定负结果，不为保留RL而无限调参。

## 10 已完成检查、骨架边界与复用方法

### 10.1 实际检查结果

【本题验证，仅限局部构件】已在本机CPU运行18项确定性检查：检测到`near`后另计清除费用、失败清除3 s且频道不变、固定位置测向一致、定向背面无信号但仍可光学清除、势函数终态消去、候选输出维度、非法动作屏蔽、DQN/PPO/模仿损失及梯度有限、空掩码拒绝、截断与真正终止自举区别、学习次数用尽回退，以及单步玩具UCT选择低代价动作等。全部通过。

记录见[构件检查结果](C:/Users/30130/Desktop/数模/tmp/B_RL_research/component_checks.json)。这些检查不覆盖完整地图生成、所有边界、长期覆盖、训练收敛或官方协议。路线标签仍为【未验证】。

### 10.2 依赖和缺失接口

骨架依赖Python3.12、NumPy2.2.4、PyTorch2.10.0。本地未安装Gymnasium和Stable-Baselines3；本次没有安装新依赖，也没有冒称用其接口跑通。当前版本来自本机实际检查，不是声称全球最新版本。

完整组件位于[研究骨架](C:/Users/30130/Desktop/数模/tmp/B_RL_research/rl_skeletons.py)，并在第14节嵌入，便于后续搬入工作流。它可导入、运行局部检查；示例训练片段中的`batch`、候选生成、belief、轨迹收集器、教师和生成模型回调需由队员实现。**没有伪造一个实际不存在的完整训练入口。**

需要补齐的最小接口为：`history.update(action, observation)`、`features(history)`、`candidates(history)`、`baseline(history)`、`termination_certificate(history)`、`collect_rollout(policy, env)`、`evaluate_frozen_policy(seeds)`。这些函数必须共享第2节的时间和可观测边界。

## 11 文献证据库：12篇及适用边界

本任务收录**12篇：11篇【核心】、1篇【参考】**。优先采用指定的NeurIPS/ICML/ICLR、IROS、TNNLS来源；另补充Nature的DQN原始论文、ICAPS的POMDP算法、WAFR的高度匹配定位论文和ACC的付费观测研究，均注明实际发表载体，不把它们改写成指定会议。作者页面用于查找其正式论文或作者全文，不把普通GitHub README当学术证据。

### 11.1 逐条元数据与借鉴点

**L01【核心】Human-level control through deep reinforcement learning**。作者：Volodymyr Mnih、Koray Kavukcuoglu、David Silver、Andrei A. Rusu、Joel Veness、Marc G. Bellemare、Alex Graves、Martin Riedmiller、Andreas K. Fidjeland、Georg Ostrovski、Stig Petersen、Charles Beattie、Amir Sadik、Ioannis Antonoglou、Helen King、Dharshan Kumaran、Daan Wierstra、Shane Legg、Demis Hassabis。Nature，518：529–533，2015。DOI：[10.1038/nature14236](https://doi.org/10.1038/nature14236)。借鉴点：经验回放和目标网络的价值学习基线；关联第4节。边界：游戏成绩不支持B题效果。

**L02【参考】Proximal Policy Optimization Algorithms**。作者：John Schulman、Filip Wolski、Prafulla Dhariwal、Alec Radford、Oleg Klimov。arXiv预印本，2017，编号1707.06347。[作者稿](https://arxiv.org/abs/1707.06347)。借鉴点：裁剪策略更新；关联第5、7节。边界：此处按预印本登记，不虚构正式venue。

**L03【核心】Monte-Carlo Planning in Large POMDPs**。作者：David Silver、Joel Veness。Advances in Neural Information Processing Systems 23（NIPS），2010，2164–2172。[会议全文](https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps.pdf)。借鉴点：用生成模型与历史树进行在线部分可观测规划；关联第6节。边界：需要可采样信念与生成模型。

**L04【核心】Online Algorithms for POMDPs with Continuous State, Action, and Observation Spaces**。作者：Zachary Sunberg、Mykel Kochenderfer。ICAPS，28(1)：259–263，2018。DOI：[10.1609/icaps.v28i1.13882](https://doi.org/10.1609/icaps.v28i1.13882)。借鉴点：连续观测下的粒子退化问题与POMCPOW/PFT-DPW方案；关联第6节。边界：普通分箱UCT骨架没有自动实现这些方法。

**L05【核心】Policy invariance under reward transformations: Theory and application to reward shaping**。作者：Andrew Y. Ng、Daishi Harada、Stuart Russell。ICML，1999，278–287。[作者全文](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf)。借鉴点：明确势函数塑形的策略不变条件；关联第3节。边界：终止、折扣和额外奖励裁剪必须核对。

**L06【核心】Learning to Explore using Active Neural SLAM**。作者：Devendra Singh Chaplot、Dhiraj Gandhi、Saurabh Gupta、Abhinav Gupta、Ruslan Salakhutdinov。ICLR，2020。[官方全文](https://openreview.net/pdf?id=HklXn1BKDH)。借鉴点：模块化学习和规划架构；关联第7节。边界：视觉地图探索，与本题无线电观测、未知频道不同。

**L07【核心】Active Localization of Multiple Targets from Noisy Relative Measurements**。作者：Selim Engin、Volkan Isler。WAFR 2020；正式论文集Algorithmic Foundations of Robotics XIV，Springer Proceedings in Advanced Robotics 17，2021，398–413。DOI：[10.1007/978-3-030-66723-8_24](https://doi.org/10.1007/978-3-030-66723-8_24)；[作者全文](https://ksengin.github.io/papers/wafr2020active.pdf)。借鉴点：测向不确定性表示和TD3主动定位；关联第2、7节。边界：作者明确不研究初始目标搜索，不能支持未知频道覆盖。

**L08【核心】Learning-Augmented Model-Based Planning for Visual Exploration**。作者：Yimeng Li、Arnab Debnath、Gregory J. Stein、Jana Košecká。IEEE/RSJ IROS，2023，5165–5171。[作者提供的正式发表信息](https://yimengli46.github.io/Projects/IROS2023Exploration/index.html)；[论文全文](https://arxiv.org/pdf/2211.07898)。借鉴点：学习预测与模型规划结合，同时提供RL改编基线不如简单启发式的条件性负结果；关联第11.2节。正式发表版与2022预印本不重复计数。

**L09【核心】DRL-Searcher: A Unified Approach to Multirobot Efficient Search for a Moving Target**。作者：Hongliang Guo、Qihang Peng、Zhiguang Cao、Yaochu Jin。IEEE Transactions on Neural Networks and Learning Systems，35(3)：3215–3228，2024；提前在线为2023。DOI：[10.1109/TNNLS.2023.3274667](https://doi.org/10.1109/TNNLS.2023.3274667)；[作者机构记录与摘要](https://ink.library.smu.edu.sg/sis_research/8217/)。借鉴点：区分期望捕获时间与期限内成功概率；关联第3、9节。边界：多机器人搜索单个移动目标，须选择只用目标belief的版本；本报告核验到元数据和摘要，未复现其算法，也未据摘要展开全部实现细节。

**L10【核心】Deep Reinforcement Learning at the Edge of the Statistical Precipice**。作者：Rishabh Agarwal、Max Schwarzer、Pablo Samuel Castro、Aaron Courville、Marc G. Bellemare。NeurIPS 34，2021。[会议全文](https://papers.nips.cc/paper/2021/file/f514cec81cb148559cf475e7426eed5e-Paper.pdf)。借鉴点：有限重复下的评估不确定性和稳健汇总；关联第9节。边界：它是评价方法证据，不是“RL必输启发式”的论文。

**L11【核心】Domain Randomization for Transferring Deep Neural Networks from Simulation to the Real World**。作者：Josh Tobin、Rachel Fong、Alex Ray、Jonas Schneider、Wojciech Zaremba、Pieter Abbeel。IEEE/RSJ IROS，2017，23–30。DOI：[10.1109/IROS.2017.8202133](https://doi.org/10.1109/IROS.2017.8202133)；[作者稿](https://arxiv.org/abs/1703.06907)。借鉴点：对模拟分布变化进行系统研究；关联第8节。边界：原研究的视觉迁移不等于本题定位策略的迁移保证，领域随机化本身也不必是RL。

**L12【核心】When to Localize? A Risk-Constrained Reinforcement Learning Approach**。作者：Chak Lam Shek、Kasra Torshizi、Troi Williams、Pratap Tokekar。American Control Conference（ACC），2025，194–199。DOI：[10.23919/ACC63710.2025.11107899](https://doi.org/10.23919/ACC63710.2025.11107899)；[2024作者预印本](https://arxiv.org/abs/2411.02788)。借鉴点：把昂贵定位调用的时机作为风险约束决策；关联第7节。边界：定位对象是机器人自身；正式发表元数据已通过出版注册记录核验，本文不把2024稿与2025发表计为两篇。

### 11.2 明确负结果：能说明什么，不能说明什么

【文献支持】L08在MP3D/Habitat的1000个测试回合中比较覆盖率，使用无噪声位姿及真值语义，结果见全文第6页Table I、II：

| 视场 | 最近前沿FBE-Near | 论文改编RL基线ANS+FBE | RL相对差值 |
|---|---:|---:|---:|
| 360° | 76.8% | 72.3% | −4.5个百分点 |
| 90° | 65.2% | 61.1% | −4.1个百分点 |

这支持“该实验下改编RL基线低于启发式”，不是原ANS在所有基准上的结论；90°小场景中ANS+FBE反而更高。LFE自身含监督学习，也不能叫纯启发式。[原文表格](https://arxiv.org/pdf/2211.07898)

本题应据此建立条件性比较，而不是预先宣称RL一定落后。作者稿第6页已本地渲染目视核对，未把摘要中的百分数混用为本表的百分点差。配对公平性仍受论文的基线适配方式与观测条件限制。

### 11.3 正结果的可迁移部分

L07支持“在其已可观测目标的主动定位实验中，学习方法有价值”这一研究动机；L09支持同时考察搜索时间与期限内成功概率。两者分别与未知源发现、机器人/目标数量及运动性存在差异。因此本题可提出高层学习假设，不能直接写“依据已有文献，该策略已在B题验证有效”。

## 12 检索范围、停止依据与尚未覆盖内容

### 12.1 实际检索分支与关键词

检索日期：2026-09-10。优先原论文、会议/期刊页面、作者全文和机构记录。以下列出实际使用过的代表性查询，记录分支而非伪造所有查询都成功：

| 分支 | 实际关键词或题名追查 | 纳入文献 | 本轮停止原因 |
|---|---|---|---|
| POMDP与在线树搜索 | `POMDP search and rescue`；`Monte-Carlo Planning in Large POMDPs Silver Veness`；`Sunberg Kochenderfer POMCPOW 2018 ICAPS` | L03、L04 | 经典规划结构和连续观测风险已找到；全任务达到12篇上限 |
| DQN/PPO/奖励 | `Human level control Nature 2015`；`Proximal Policy Optimization Algorithms Schulman`；`Policy invariance reward transformations Ng Harada Russell` | L01、L02、L05 | 原始方法依据已覆盖；数量上限停止 |
| 主动定位与付费观测 | `active target localization RL bearing`；`Active Localization Multiple Targets Noisy Relative Measurements`；`When to Localize Risk Constrained` | L07、L12 | 有直接定位与近期交叉控制研究；数量上限停止 |
| 导航探索与负结果 | `Learning to Explore Active Neural SLAM ICLR 2020`；`robot exploration RL outperform frontier benchmark`；`RL exploration outperformed by frontier`；`Learning Augmented Model Based exploration 2023` | L06、L08 | 找到原文条件性负结果和混合路线，停止扩增案例 |
| 搜索救援/目标搜索 | `reinforcement learning search and rescue ICRA`；`RL target search heuristic ICRA`；`DRL Searcher unified approach multirobot` | L09 | 找到TNNLS目标搜索代表作；救援完整任务尚有扩展空间 |
| 泛化与评价 | `Deep RL Statistical Precipice`；`Domain randomization transferring deep neural networks IROS 2017` | L10、L11 | 评价与迁移两类交叉风险有来源；数量上限停止 |

检索中也追查了`Online Planning POMDPs Continuous State Action Observation Spaces`，最后按原文核正为L04的**Online Algorithms**题名；`When to Localize ... ICRA`没有支持ICRA发表，最终核实为ACC。正式稿年份、venue以核验记录为准，不沿用查询中猜测的词。

### 12.2 饱和度的诚实表述

本轮满足用户允许的**8—12篇配额上限停止**，不是宣称全领域穷尽。总体覆盖经典算法、近五年正式研究（例如2023、2024、2025）及机器人/统计/控制交叉方向；不声称每个分支都同时达到三类覆盖，也不声称未经记录的“两轮无新增”已发生。

仍可扩展：无人机能源与动力学约束、真实搜救中的受害者发现、风险敏感/分布式RL、离线RL、部分可观测模仿、多智能体协调。它们可能有研究价值，但多机器人协作和UAV动力学不是本题的单机器狗平面规则，不作为三天实施前置依赖。

**没有检索到能直接证明“单机器人＋未知10—16源＋20频道＋固定有界测向误差＋定向半平面＋全清除时间目标”这套完整规则上RL优于本题几何基线的可靠文献。**这是组合场景缺少直接证据，不是断言不存在任何相关研究。

### 12.3 检索与核验记录

元数据在论文/出版页面核对；L11、L12另保存出版注册记录。L08网页截图工具报内部错误，随后从公开作者稿下载PDF，在本地渲染第6页并核对表格，问题已解决。未把下载或截图成功当成策略复现。

辅助材料保存在[本任务材料目录](C:/Users/30130/Desktop/数模/tmp/B_RL_research)，包括元数据记录、负结果原文与表格页、代码骨架、局部检查结果及报告审计。统一的跨任务文献库与BibTeX留待任务4，不在此阶段假称完成。

## 13 可交给论文工作流的结论边界

| 论文位置 | 本报告可提供 | 队员还须补做 |
|---|---|---|
| 模型建立 | POMDP隐状态/历史、半马尔可夫时间、观测与奖励公式 | 对正式执行器逐字段复核 |
| 算法设计 | 四种路线及几何候选接口 | 完整训练/规划主循环，完成证书与期限控制 |
| 模型检验 | 成对评价、分布外压力、消融设计 | 实际地图实验、训练种子和官方演练记录 |
| 模型评价 | 文献正负证据、代价和适用范围 | 只按实测结果填写收益数字 |
| 讨论与展望 | 端到端RL及更复杂belief的边界 | 不把未来路线写成本文已完成贡献 |

**当前可支持：**本题的信息结构需要区别隐藏世界与观测历史，成本必须按实际动作计费；已找到与主动定位、搜索和混合规划有关的文献；局部组件检查通过。

**当前合理但未验证：**几何底层＋高层学习可能降低训练自由度，并在特定分布上改善调度。是否有净收益，需要同候选、同兜底、同地图的实际对照。

**当前不宜主张：**RL优于几何、三天必能收敛、官方环境已兼容、覆盖兜底必在现实期限内完成、训练集成功率等于正式可靠性。

任务2完成后暂停；下一阶段是任务3“C题优化与预测调研”。


## 14 附录：Python组件骨架全文

以下与本地组件文件一致。回调函数和完整训练收集器的缺失范围见第10.2节；本附录没有训练结果。

```python
"""Research components only. No trained policy or official simulator adapter.
Python 3.12; numpy 2.2.4; torch 2.10.0. CPU smoke checks only.
"""
from dataclasses import dataclass
from math import atan2, degrees, hypot, sin, cos, log, sqrt
import numpy as np
import torch
from torch import nn
from torch.distributions import Categorical


@dataclass(frozen=True)
class Action:
    kind: str
    channel: int
    x: float
    y: float


@dataclass
class Source:
    x: float
    y: float
    radius: float
    orientation: float | None  # radians; None = omnidirectional
    phase: float              # fixed for the entire episode
    active: bool = True


class PhysicsSketch:
    """Known-world synthetic physics, deliberately NOT exposed to the actor.
    Does not implement HTTP, deadlines, official random fields, or reset distribution.
    Only feedback returned by step may reach a history/belief updater.
    """
    def __init__(self, sources: dict[int, Source]):
        self.sources = sources
        self.p = (0.0, 0.0)
        self.channel = 1
        self.virtual_seconds = 0.0

    def step(self, a: Action):
        if a.kind not in ('measure', 'clear') or not 1 <= a.channel <= 20:
            raise ValueError('invalid action')
        if not all(np.isfinite([a.x, a.y])) or max(abs(a.x), abs(a.y)) > 2e6:
            raise ValueError('invalid coordinates')
        dt = hypot(a.x-self.p[0], a.y-self.p[1]) / 5
        self.p = (a.x, a.y)
        s = self.sources.get(a.channel)
        exists = s is not None and s.active
        d = hypot(a.x-s.x, a.y-s.y) if exists else float('inf')
        if a.kind == 'clear':
            success = exists and d <= 20
            dt += 3 + 2 * int(success)
            if success:
                s.active = False
            obs = {'kind': 'clear', 'success': bool(success)}
        else:
            dt += int(a.channel != self.channel) + 5
            self.channel = a.channel
            visible = exists and d <= s.radius
            if visible and s.orientation is not None:
                visible = ((a.x-s.x)*cos(s.orientation) +
                           (a.y-s.y)*sin(s.orientation) >= 0)
            if not visible:
                obs = {'kind': 'measure', 'status': 'no_signal'}
            elif d <= 5:
                obs = {'kind': 'measure', 'status': 'near'}
            else:
                # A smooth, bounded, spatially fixed test field, not official noise.
                err = sin(.003*a.x + .005*a.y + s.phase)
                angle = degrees(atan2(s.y-a.y, s.x-a.x)) + err
                obs = {'kind': 'measure', 'status': 'direction',
                       'svd_deg': round(angle % 360, 2) % 360}
        self.virtual_seconds += dt
        return obs, dt


def reward(dt, newly_cleared, phi_before, phi_after, terminated,
           failed=False, time_scale=100., clear_bonus=10., failure_penalty=1000.):
    """gamma=1 shaping. Budget failure is terminal; rollout cuts are not."""
    if failed and not terminated:
        raise ValueError('failure penalty applies at a genuine terminal only')
    end_phi = 0. if terminated else phi_after
    return (-dt/time_scale + clear_bonus*newly_cleared
            - failure_penalty*failed + end_phi-phi_before)


class CandidateNet(nn.Module):
    """Inputs must contain only observations/history summaries, never hidden truth.
    Fixed 20 channel slots here; candidate padding is masked. Training stores the
    EXACT candidate list/order and mask used to sample each action.
    """
    def __init__(self, state_dim=256, candidate_dim=16, width=128):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(state_dim, width), nn.ReLU(),
                                 nn.Linear(width, width), nn.ReLU())
        self.score = nn.Sequential(nn.Linear(width+candidate_dim, width),
                                   nn.ReLU(), nn.Linear(width, 1))
        self.value = nn.Linear(width, 1)

    def forward(self, state, candidates, mask):
        if mask.dtype != torch.bool or not bool(mask.any(dim=-1).all()):
            raise ValueError('every decision needs at least one valid candidate')
        h = self.enc(state)
        z = torch.cat((h[:, None, :].expand(-1, candidates.shape[1], -1),
                       candidates), dim=-1)
        scores = self.score(z).squeeze(-1).masked_fill(~mask, -1e9)
        return scores, self.value(h).squeeze(-1)


def dqn_loss(online, target, b):
    # Standard masked DQN. Target synchronization belongs in the outer loop.
    scores, _ = online(b['s'], b['c'], b['mask'])
    if not bool(b['mask'].gather(1, b['a'][:, None]).all()):
        raise ValueError('replayed action is invalid in saved candidate list')
    q = scores.gather(1, b['a'][:, None]).squeeze(1)
    with torch.no_grad():
        future = torch.zeros_like(b['r'])
        live = ~b['terminal']  # rollout truncation alone must not set this flag
        if bool(live.any()):
            nq, _ = target(b['ns'][live], b['nc'][live], b['nmask'][live])
            future[live] = nq.max(dim=-1).values
        y = b['r'] + future  # gamma=1; terminal rows need no next actions
    return nn.functional.smooth_l1_loss(q, y)


def ppo_loss(net, b, clip=.2, entropy_weight=.01, value_weight=.5):
    logits, v = net(b['s'], b['c'], b['mask'])
    if not bool(b['mask'].gather(1, b['a'][:, None]).all()):
        raise ValueError('PPO rollout candidates/masks must stay fixed')
    dist = Categorical(logits=logits)
    ratio = (dist.log_prob(b['a']) - b['old_logp'].detach()).exp()
    adv = b['adv'].detach()
    policy = -torch.minimum(ratio*adv, ratio.clamp(1-clip, 1+clip)*adv).mean()
    critic = (v-b['returns'].detach()).square().mean()
    return policy + value_weight*critic - entropy_weight*dist.entropy().mean()


def gae(rewards, values, next_values, terminals, episode_ends, lam=.95):
    """1-D rollout. At collection cuts, bootstrap final observation's value.
    episode_ends also stops advantage recursion at truncation/reset boundaries.
    next_values must NEVER be the reset observation's value at a cutoff.
    """
    adv = torch.zeros_like(rewards)
    carry = torch.zeros((), dtype=rewards.dtype, device=rewards.device)
    for t in reversed(range(len(rewards))):
        delta = rewards[t] + (~terminals[t])*next_values[t] - values[t]
        carry = delta + lam*(~episode_ends[t])*carry
        adv[t] = carry
    return adv, adv + values


def imitation_loss(net, s, c, mask, teacher_actions):
    logits, _ = net(s, c, mask)
    if not bool(mask.gather(1, teacher_actions[:, None]).all()):
        raise ValueError('teacher action must be included before candidate pruning')
    return nn.functional.cross_entropy(logits, teacher_actions)


class HistoryUCT:
    """POMCP-style history tree with root sampling. NOT full POMCPOW.
    sample_world(): posterior particle; step(world, action): next_world, obs, r, done
    actions(history) and obs_key(obs) MUST NOT inspect a sampled world's truth.
    rollout(world, history, depth) uses only observable history for its decisions.
    History includes concrete action IDs, observations, and enough public state.
    Belief maintenance is the caller's responsibility.
    """
    def __init__(self, actions, step, obs_key, rollout, exploration=1.):
        self.actions, self.step, self.obs_key = actions, step, obs_key
        self.rollout, self.exploration = rollout, exploration
        self.tree = {}

    def simulate(self, world, history, depth):
        if depth <= 0:
            return self.rollout(world, history, 0)  # defined leaf value, not free zero
        if history not in self.tree:
            aa = self.actions(history)
            if not aa:
                raise ValueError('nonterminal node needs a fallback action')
            self.tree[history] = {a: [0, 0.] for a in aa}
            return self.rollout(world, history, depth)
        stats = self.tree[history]
        total = sum(v[0] for v in stats.values())
        def ucb(a):
            n, q = stats[a]
            return float('inf') if n == 0 else q + self.exploration*sqrt(log(total+1)/n)
        a = max(stats, key=ucb)
        nw, obs, r, done = self.step(world, a)
        nh = history + ((a, self.obs_key(obs)),)
        ret = r if done else r + self.simulate(nw, nh, depth-1)
        n, q = stats[a]
        stats[a] = [n+1, q+(ret-q)/(n+1)]
        return ret

    def choose(self, sample_world, history=(), simulations=64, depth=4):
        if simulations < 2:
            raise ValueError('need visits after tree expansion')
        for _ in range(simulations):
            self.simulate(sample_world(), history, depth)
        visited = {a:v for a,v in self.tree[history].items() if v[0] > 0}
        if not visited:
            raise RuntimeError('no visited actions')
        return max(visited, key=lambda a: visited[a][1])


def shielded_choice(policy_choice, baseline_choice, learned_used, learned_budget,
                    coverage_due, sufficient_reserve, allowed):
    """The caller computes conservative fallback reserve and prevents starvation.
    learned_budget is a TOTAL episode budget, not reset on every decision.
    """
    if learned_used >= learned_budget or coverage_due or not sufficient_reserve:
        return baseline_choice
    return policy_choice if policy_choice in allowed else baseline_choice
```

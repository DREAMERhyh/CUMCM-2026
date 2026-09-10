# B题-几何启发式路线

TL;DR：建议先实现“有界测角定位区域＋旋转卡壳＋最小包围圆判停＋覆盖扫描”，再优化测点、频道和访问顺序。本文核对25篇文献，给出四问的替代路线、推导、代码骨架与三天落地安排。局部几何及覆盖构造已做本地合成测试；整体策略尚未接入官方模拟器，不能宣称正式清除率或速度优势。

## 1 研究边界、证据与路线总图

### 1.1 本阶段回答什么

任务1只处理B题几何与启发式主线，供三名计算机专业本科生及GPT agent共同审查和实现；不代写参赛论文，不提前执行任务2—5。调研日期为2026年9月10日，按实际剩余约三天安排实现，文献范围仍覆盖计算几何、统计估计、自动控制、运筹学、信息论、机器人与无线传感网络。

规则依据：[B题原文](C:/Users/30130/Desktop/数模/document/CUMCM2026Problems/B题/B题.pdf)、[模拟器使用说明](C:/Users/30130/Desktop/数模/document/CUMCM2026Problems/B题/附件/附件1.docx)、[通信协议](C:/Users/30130/Desktop/数模/document/CUMCM2026Problems/B题/附件/附件2.docx)。原提示词中的“仅比较四边形对角线”“near免检测费”均被用户后续更正覆盖。C题不退款口径已确认：100元原计划款＋10元违约费＝110元，留待任务3建模。

证据标签与可实现性是两个维度：

- 【文献支持】：正式文献结论或本文完整数学证明；不表示算法在本题运行过。本文新推导会明确写“本报告推导”，不冒称文献已有结论。
- 【本题验证】：实际运行了注明范围的本地代码或模拟器；本阶段仅有局部合成测试，没有官方演练或正式测试。
- 【未验证】：策略迁移、参数建议、性能预测或未完成的推导。特别是B题强化学习仍为【未验证】，下一阶段另评。
- ✅ Answerable now表示可在当前团队和赛期内实现该模块；⚠️ Answerable with extra work表示额外开发或检验风险；❌ Not answerable in scope表示不纳入本届主实现。以下工时为工程估计，不是测速结论。

### 1.2 建议路线与可回答性

|路线|回答的子问题|REWRITE定位|可回答性与预计投入|证据边界|
|---|---|---|---|---|
|Q1-A 半平面裁剪＋旋转卡壳|可靠构造定位区域并求直径|Confirm经典算法；Refine数值边界|✅ 6—10人时，队员A主责|局部【本题验证】|
|Q1-B 边界交点枚举＋全点对校验＋包围圆|小规模独立复核和清除可行性|Reframe直径为包围半径问题|✅ 3—5人时，复用Q1-A|圆判据【文献支持】，反例【本题验证】|
|Q2-A 确定性区域驱动的候选测点|有限误差下兼顾定位与移动|Extend集合估计到有动作费用的主动测量|✅ 5—8人时；候选评分仍需演练|整体收益【未验证】|
|Q2-B FIM/CRLB与误差椭圆|解释测点几何、做轻量排序基准|Confirm有条件的90°最优；Refine时间目标|✅ 3—5人时|公式【文献支持】，统计模型须说明|
|Q2-C 椭球融合/连续最优实验设计|更紧估计及连续位置优化|Extend多传感器方法|⚠️ 额外8—16人时，先限定离散候选|迁移【未验证】|
|Q3-A 完整覆盖＋分层定位＋保底清除|先满足清除全部源，再计时|Reframe一般探索为可认证终止的搜索|✅ 10—16人时，复用Q1/Q2|覆盖证明成立；端到端【未验证】|
|Q3-B 信息收益/时间＋开放访问路径|减少重复检测和绕行|Extend信息采集、邻域访问与局部搜索|⚠️ 额外6—12人时，可逐项消融|时间优势【未验证】|
|Q3-C 全局自适应最优策略证明|对所有未知场景都最快|研究问题保留|❌ 当前范围不承诺；连续观测树不可控|【未验证】，仅讨论|
|Q4-A 多角度复核＋方向无关清除|最小修改Q3，应对定向漏检|Refine观测模型|✅ 4—6人时；须与Q4-B配套保证全发现|局部保证【文献支持】|
|Q4-B 对任意定向角有效的覆盖保底|严格解决未发现源遗漏|Extend几何覆盖到未知半平面|✅ 3—5人时，网络吞吐需测|证明＋覆盖局部【本题验证】|
|Q4-C 位置—朝向联合集合/粒子更新|进一步减少定向复核|Extend集合估计|⚠️ 额外8—16人时；不删保底扫描|【未验证】|

这些工时有模块复用，不能逐行相加当作总项目估时。主线与文献整理适合并行分工；同一次官方机器狗会话必须串行发送不同动作。

## 2 Q1：交会定位、直径与覆盖圆

### 2.1 从示向度构造半平面

检测点为\(s_i=(x_i,y_i)\)，读数为\(\theta_i\)，误差界\(\varepsilon=\pi/180\)。所有计算先转弧度。令

\[
u_i^-=(\cos(\theta_i-\varepsilon),\sin(\theta_i-\varepsilon)),\quad
u_i^+=(\cos(\theta_i+\varepsilon),\sin(\theta_i+\varepsilon)).
\]

本报告推导：真实源\(q\)位于**朝前的窄扇形**，约束为

\[
\operatorname{cross}(u_i^-,q-s_i)\ge0,\qquad
\operatorname{cross}(u_i^+,q-s_i)\le0.
\]

两约束的交集已经选定正向射线一侧，不可把射线无限延长成两侧双锥。转换成\(a\cdot q\le b\)：下边界\(a^-=(u^-_y,-u^-_x)\)，上边界\(a^+=(-u^+_y,u^+_x)\)，分别令\(b=a\cdot s_i\)。测了\(m\)次得到\(2m\)个半平面，

\[
P_{\rm measure}=\bigcap_{i=1}^m W_i.
\]

标准交会可得到四边形，但不保证始终四个顶点；也可能空集、点、线段、无界集合。Q1应先回答纯交会区域；Q3/Q4可以另外使用已知目标圆域与接收距离上界：

\[
P_{\rm physical}=P_{\rm measure}\cap B(0,1800)
\cap\bigcap_{i:\,\text{有信号}}B(s_i,1500).
\]

曲边圆域的精确交集未必是多边形。三天实现可先使用外接方框\([-1800,1800]^2\)，或用圆的外切正多边形保守近似；后者第\(k\)条边是\(n_k\cdot q\le R\)，而不是把圆上采样点连成内接多边形。不得仅删除圆外顶点而丢失边与圆的交点。

通信读数保留两位小数。正文误差界仍按±1°分析；工程实现可增加0.005°作为**输出舍入的保守数值裕量**，并对1°/1.005°做敏感性对照，不把1.005°说成题面新误差分布。同地重复测向误差固定，不能用重复取平均宣称方差缩小。

### 2.2 Q1-A：增量裁剪与旋转卡壳

科学问题：如何以足够简单、稳定的代码维护包含真实源的位置集合？文献定位：多边形逐边裁剪借鉴R02；凸多边形直径采用R01；浮点退化借鉴R04。是经典算法的Confirm与本题边界条件的Refine，并非新几何算法。[R01原作者说明](https://www-cgrl.cs.mcgill.ca/~godfried/research/calipers.html)、[R04原作者论文页](https://www.cs.cmu.edu/~jrs/jrspapers.html)。

裁剪一条边\(a\cdot x\le b\)时，设线段端点\(v,w\)，\(f_v=a\cdot v-b\)、\(f_w=a\cdot w-b\)。若内外状态不同，交点为

\[
t=\frac{f_v}{f_v-f_w},\qquad z=v+t(w-v).
\]

保留内点及有效交点。每次裁剪\(O(n)\)，全部\(m\)次观测的朴素增量复杂度\(O(m^2)\)，本题每源通常只需少量观测，优先考虑可审查性。大规模才用按法向排序的半平面交\(O(m\log m)\)。

旋转卡壳完整论证如下，适用顶点已按逆时针排列的凸多边形：

1. **最远点可取顶点。** 若\(x=\sum_i\lambda_i v_i\)，则\(\|x-y\|\le\sum_i\lambda_i\|v_i-y\|\le\max_i\|v_i-y\|\)。对\(y\)再做一次，因此区域直径等于顶点对距离最大值。
2. **直径端点是对踵点。** 若\(a,b\)最远，且在\(a\)沿\(a-b\)方向还有点\(x\)投影更远，则\(\|x-b\|>\|a-b\|\)，矛盾。故经过\(a,b\)、垂直\(a-b\)的两条平行线支撑多边形。
3. **旋转支撑方向会列举对踵组合。** 固定第\(i\)条边\(e_i=v_{i+1}-v_i\)，对边支撑点最大化\(A_i(j)=\operatorname{cross}(e_i,v_j-v_i)\)。边法向依次旋转时，凸多边形上最远支撑点的索引只会向前，不会回退；平行支撑边对应两个相邻并列极值点。
4. **检查两端点和并列点。** 对每条边比较\((v_i,v_j),(v_{i+1},v_j)\)；若\(A_i(j+1)=A_i(j)\)，同时比较与\(j+1\)的两对。随着法向连续旋转，在支撑点改变的事件处，所有可能的直径对都在这些组合中。
5. **复杂度。** \(i\)走一圈，\(j\)起始找极值后至多再走一圈，均\(O(n)\)。没有每条边重置\(j\)，因此不是\(O(n^2)\)。只比较平方距离，最后开方。空集不定义直径；单点为0，线段取端点距离。

```text
CALIPERS(P):                 # 已去重、去共线，严格凸、逆时针
    处理 n=0/1/2
    j ← 1; best ← 0
    对 i = 0...n-1:
        当 A_i(j+1) > A_i(j): j 前进一格
        比较 i、i+1 与 j 的距离
        若下一点面积并列：补比较 i、i+1 与 j+1
    返回 sqrt(best) 及对应顶点对
```

**不能只比较对角线。** 反例为按逆时针排列的\((0,0),(10,0),(9,0.1),(1,0.1)\)：最长边10，两条对角线均\(\sqrt{81.01}<10\)。因此四边形的稳妥常数级简化是比较**六对**，主算法仍保留旋转卡壳。

实现难点：跨0°不应靠直接大小比较角度；近平行线不能除以接近0的叉积；未排序点不可直接卡壳；外扩数值容差、消除重复点和共线点之后，仍须用独立枚举校验。普通double/long double并非R04的精确谓词实现；接近零时应触发高精度复核，不声称现有骨架完全消除舍入错误。

预期产出：观测表、逐次区域收缩图、\(D_m\)变化表、退化案例表。✅ Answerable now；附录A给实际运行过的Python与C++核心。

### 2.3 Q1-B：枚举交点、独立直径校验与最小包围圆

科学问题：小规模观测能否用容易核查的方法独立验算，及“直径足够小”是否意味着能一次清除？文献定位：交点枚举作独立对照，R03最小包围圆把判停问题Reframe为覆盖中心选择。[R03正式章节](https://link.springer.com/chapter/10.1007/BFb0038202)。

先用线性可行性检查判断\(Aq\le b\)是否为空；再分别求\(\max x,\min x,\max y,\min y\)。若任一无界，则非空区域无界，直径为无穷。不能靠加一个“足够大”的任意方框掩盖该情况。若有界，枚举所有不平行边界线交点，用全部半平面筛选，再取凸包。\(O(m^3)\)枚举可作为观测数小时的核验路线；全点对直径\(O(n^2)\)作卡壳的独立判定器。

```text
ENUMERATE_REGION(H):
    检查可行性及四个坐标方向有界性
    若空：返回 INCONSISTENT；若无界：返回 UNBOUNDED
    V ← 所有满足H的非平行边界交点
    P ← ConvexHull(V)
    D_check ← max_{a,b∈P} ||a-b||
    枚举二点直径圆和三点外接圆；保留覆盖P者，取最小半径
```

设区域直径为\(D\)，某个直径点对为\(a,b\)，\(c=(a+b)/2\)。存在直径为\(D\)的圆覆盖\(P\)的充要条件是

\[
\max_{v\in V(P)}\|v-c\|\le D/2.
\]

证明：【文献支持／本报告推导】任何半径\(D/2\)、中心\(o\)的覆盖圆都满足
\(D=\|a-b\|\le\|a-o\|+\|o-b\|\le D\)。等号迫使\(o\)为线段中点\(c\)。反之，若全部顶点都在该圆内，由圆的凸性整个多边形也在内。故不能通过“把同样大的圆挪一下”修复覆盖失败。

**严格反例：** 边长20的等边三角形，区域直径20，但最小包围圆半径\(20/\sqrt3\approx11.547>10\)。所以一般凸定位多边形没有该保证。

**直接对应两次测向的数值反例：【本题验证／合成几何】** 源取\((0,0)\)，两个检测点为\((-343.62704417,-1246.08667341)\)、\((-1212.02121821,343.74238814)\)，示向度分别为\(75.0633066461°\)、\(343.3399436481°\)，每次误差均在±1°内。两扇形交集的逆时针顶点约为：

|顶点|x（米）|y（米）|
|---|---:|---:|
|A|-41.57533651|-28.89565887|
|B|0.14867175|-42.17944515|
|C|12.33895293|0.51108517|
|D|-31.24586962|12.72944689|

区域直径约63.25032532米，直径点对为B、D，中点约\((-15.54859894,-14.72499913)\)，半径31.62516266米；最远顶点到该中点约31.77819715米，确实在圆外。枚举支撑圆算得最小包围半径约31.62553128米，仍大于\(D/2\)。这是数值构造的严格余量检查，不把有限精度结果冒称符号证明；上面的三角形与充要条件提供符号证明。接口两位小数的读数场景另有舍入裕量处理，不依赖此反例的高精度读数。

因此实际判停应为

\[
r_*(P)=\min_c\max_{q\in P}\|q-c\|\le20-\tau,
\]

\(\tau>0\)为坐标及数值裕量；到最小包围圆中心清除即可。\(D>40\)意味着无法用一个半径20的圆覆盖全区域；\(D\le40\)只是必要条件，不是充分条件。若只想一个更保守的简单充分条件，\(D\le20\)时移动到任意区域内点都可清除。

最小包围圆由2个或3个边界点支撑。R03给出固定维数随机增量的期望线性算法；本报告实际测试代码采用小规模二/三点支撑圆穷举，\(O(n^4)\)，有意保留独立性，不能把它标成Welzl线性实现。✅ Answerable now；若换随机增量版，须和支撑圆穷举版逐例对照。

### 2.4 退化与异常处置表

|情况|正确含义|处置|
|---|---|---|
|两中心示向射线近平行|误差放大，或区域无界|报告无界/大直径；侧向增加测点|
|检测点—源近共线|交会角近0或180°，信息矩阵病态|不要用矩阵求逆硬产“精确坐标”|
|区域为空|至少有误差界、单位、频道关联或数值运算不一致|保留原观测，检查度/弧度和舍入；不能删除不喜欢的观测|
|纯交会区域在目标圆外|物理先验与观测冲突或区域只是部分相交|明确分别展示交会区域与先验交集|
|区域退化为线段/点|理论上可处理；浮点误差也可能造成假退化|高精度复核，专用分支|
|新观测未收缩区域|可能几何冗余；同地重复尤其如此|换位置或进入有限保底方案|

## 3 Q2：第二检测点选择与误差传播

### 3.1 距离、交会角和误差的关系

令\(d_i=\|q-s_i\|\)，真实方位单位向量\(u_i\)，法向\(n_i=(-u_{iy},u_{ix})\)。小扰动线性化为

\[
\delta\theta_i\simeq\frac{n_i^T\delta q}{d_i},\qquad
H=\begin{bmatrix}n_1^T/d_1\\n_2^T/d_2\end{bmatrix}.
\]

本报告推导：以两测线锐/钝交会角\(\alpha\in(0,\pi)\)计，\(|\det H|=|\sin\alpha|/(d_1d_2)\)。仅依据题面有界误差，两个局部条带形成的平行四边形面积近似为

\[
A_{\rm bounded}\simeq\frac{4\varepsilon^2 d_1d_2}{|\sin\alpha|}.
\]

这是小角线性近似，接近共线、测点离估计区域很近时必须回到精确扇形交集。单次横向误差量级\(d\tan\varepsilon\)，1000米处约17.455米，1500米处约26.183米，距离缩短往往比执着90°更有价值。

若**另外建立**零均值、独立、方差\(\sigma_i^2\)的局部测角噪声模型，则

\[
F=H^T\Sigma_\theta^{-1}H,
\quad\operatorname{Cov}(\hat q)\succeq F^{-1},
\quad\det F=\frac{\sin^2\alpha}{\sigma_1^2\sigma_2^2d_1^2d_2^2},
\]

\[
\operatorname{tr}(F^{-1})=
\frac{\sigma_1^2d_1^2+\sigma_2^2d_2^2}{\sin^2\alpha},\qquad
A_{1-\beta}=\pi\chi^2_{2,1-\beta}
\frac{\sigma_1\sigma_2d_1d_2}{|\sin\alpha|}.
\]

CRLB是满足正则条件的无偏估计方差下界，不能无条件写成实际误差协方差。最后的置信椭圆还需高斯/渐近正态假设；若仅假设独立均匀\([-\varepsilon,\varepsilon]\)，虽方差可取\(\varepsilon^2/3\)，也不能直接把线性变换后的均匀误差称作高斯置信椭圆。题面没有授权误差独立均匀分布。

【文献支持】在\(d_1,d_2,\sigma_1,\sigma_2\)固定时，上述面积、迹都在90°最优；R05/R06支持把几何条件与最优准则分开讨论。移动第二测点会同时改变距离、观测成功率与路程，故“90°”不是本题总时间的普适最优答案。[R05](https://doi.org/10.1016/j.automatica.2009.12.003)、[R06](https://doi.org/10.1016/j.sigpro.2007.11.013)。

### 3.2 第二点候选区域的解析边界

以第一检测点为原点，第一示向方向为局部x轴。候选源位置写为\(q=(r\cos\phi,r\sin\phi)\)，\(|\phi|\le\varepsilon\)，与物理先验相交。普通direction反馈说明\(5<r\le R\le1500\)。**1000米是有效接收半径的下界，不是源到第一测点距离的下界。** near则直接清除。

先画名义源\(q=(r,0)\)，第二测点\(s=(u,v)\)。交会角满足

\[
\cos\alpha=\frac{r-u}{\sqrt{(r-u)^2+v^2}},\quad
|\sin\alpha|=\frac{|v|}{\sqrt{(r-u)^2+v^2}}.
\]

对\(\alpha\in[\alpha_-,\alpha_+]\)，边界是从\((r,0)\)出发的角度射线；若不跨90°，可写\(v=\pm(r-u)\tan\alpha_\pm\)，并通过原余弦条件选择正确分支。跨90°时不能把正切不等式直接翻译成一个区间，应使用点积/叉积判定。接收边界为

\[
(u-r)^2+v^2=R^2,
\]

若给移动预算\(t_m\)，还需\(u^2+v^2\le(5t_m)^2\)。坐标允许出目标圆，不应人为添加\(u^2+v^2\le1800^2\)的检测点限制。

未知源位置和未知R意味着候选域有三种不同语义：

\[
\mathcal F_{\rm possible}=\bigcup_{q\in P_1}
\{s:\|s-q\|\le1500,\ \alpha(s,q)\in[\alpha_-,\alpha_+]\},
\]
\[
\mathcal F_{\rm guaranteed}=\bigcap_{q\in P_1}
\{s:\|s-q\|\le1000,\ \alpha(s,q)\in[\alpha_-,\alpha_+]\}.
\]

名义域对一个估计\(\hat q\)构造；可能域只表明“某个场景可观测”；保证域才表示全部当前场景都能观测且满足角度要求，初次观测后它可能为空。若对\(P_1\)只取有限场景点检查，则仍是近似保证，除非另有连续集合证书。

示意图建议：图左以\(s_1\)为尖端画±1°窄扇区，标出5米近区、1500米外弧和目标圆；图右对近、中、远三个\(r\)各画以\(q\)为圆心的1000米接收圆及60°—120°候选角扇区，交集用深色、并集用浅色，再叠加从\(s_1\)出发的等时间圆。这样直接显示为什么不能凭一个示向度认定源位于1000—1500米环带。

### 3.3 Q2-A：有界误差下的候选点枚举

科学问题：在未知距离、移动收费和观测可能失败的条件下，选一个对当前区域有用的第二点。文献定位：R08的有界误差集合方法提供思想，但原文含测距和机器人位姿估计，不能照搬；迁移是Extend。[R08作者全文](https://www3.diism.unisi.it/~anto/public/papers/ACSP10.pdf)。

候选集可取当前点沿第一测向前进、左右侧移、面向区域包围圆的接近点，以及后续测点局部环。初始步长建议在50、100、200、400米上比较；这些是待调参数。对候选\(s\)和假想反馈\(z\)，精确更新\(P'=P\cap W(s,z)\)，评价最坏半径及动作耗时：

\[
J(s)=\frac{\|s-s_{\rm now}\|}{5}+1_{c\ne c_{\rm now}}+5
+\lambda\,\max_{z\in\mathcal Z(P,s)} r_*(P'),
\]

\(\lambda\)单位为秒/米；no_signal也必须进入\(\mathcal Z\)。对全向且已确认存在的源，no_signal至少排除距\(s\)不超过1000米的位置，导致非凸集合；三天版可以仅保存该信息、不在凸多边形上做危险的单块裁剪，维持保守外包区域。对不同假想真值和误差只抽样得到的\(J\)是**情景近似**，不能称为连续最坏情形优化。

更低成本的主实现：在保证接收的候选点中，用区域边界场景评分；没有保证点时，优先缩短到源区域的距离并保留原始首次观测的保底清除路径。单一沿示向向前走能缩距，但若一直共线将无法交会；必须有横向基线。

```text
CHOOSE_SET_POINT(P, 当前点, 频道):
    C ← 前进/侧移/局部环候选
    对 s∈C:
        检查坐标合法；估算当前动作时间
        对 P中的场景q及误差端点/中点:
            模拟direction/near/no_signal；求保守P'
            记录r*(P')与失败分支代价
        按最坏场景评分，不能忽略no_signal
    返回最低分候选；若持续无进展，转有限保底清除
```

复杂度为\(O(KME C_P)\)：K候选数、M位置场景数、E误差场景数、\(C_P\)一次区域和包围圆更新成本。建议先K≤40、M≤16、E=3，实际时间必须记录。✅ Answerable now；附录B给接口骨架。预期输出：第二点候选域图、移动/测量/后续清除时间分解、和固定侧移基准对照。整体优越性【未验证】。

### 3.4 Q2-B：FIM排序与误差椭圆基准

科学问题：用低成本解析分数解释“为什么换一个位置”，同时提供与区域法不同的基准。文献定位：Confirm R05/R06几何性质，Refine为带移动费用的排序。

对\(\hat q\)和候选\(s\)计算新增\(F_s=n_sn_s^T/(\sigma^2d_s^2)\)，最大化

\[
\frac{\log\det(F+F_s+\gamma I)-\log\det(F+\gamma I)}{\|s-s_{\rm now}\|/5+5+1_{c\ne c_{\rm now}}}.
\]

\(\gamma>0\)仅是排序正则，不是增加了一次真实观测。应先检查可接收性及近距离反馈，否则名义\(d\to0\)会令分数虚高。按最差的多个\(\hat q\)评分可减轻单中心偏差，但没有代替真实集合约束。

```text
CHOOSE_FIM_POINT(C, F, 源位置场景):
    对每个候选计算可观测场景中的信息增益/动作时间
    将不可观测场景作为失败而非忽略
    选分数最高者；实际反馈仍更新精确有界区域
```

2×2矩阵每候选常数成本，\(O(KM)\)。✅ Answerable now，附录B可直接实现；统计噪声条件与连续角度近似写入假设表。预期产出：\(\alpha\)与距离的等高图、区域面积与椭圆面积误差、最终清除时间对比。不能只展示椭圆更小而不展示多走的路程。

### 3.5 Q2-C：前沿与交叉路线的取舍

R09（2023）研究协同bearing估计中的椭球融合，适合学习如何防止相关信息导致过度自信；本题只有一只狗，优先保留精确扇形交集。R25传感器选择的凸松弛提供“有限候选中选测量”的框架；R07的运动协调原模型是距离测量，不能引用为本题90°测向定理。[R09全文](https://trumpf.id.au/pubs/Zamani_Trumpf_Manzie_FUSION2023.pdf)、[R25作者页](https://web.stanford.edu/~boyd/papers/sensor_selection.html)、[R07](https://doi.org/10.1016/j.automatica.2005.12.018)。

```text
候选信息矩阵离散化 → 连续权重优化 → 舍入到一个测点
→ 用精确扇形区域审核该动作 → 失败时回到Q2-A
```

⚠️ Answerable with extra work：需要核对椭球外包性、求解器与线性化误差；代价8—16人时。代码入口见附录B的`relaxed_sensor_weights`，仅作实验框架。精确求解的松弛最优值可作理论参照；普通数值解未经最优性认证时只作候选比较，不保证原始动态搜索全局最优。若要证明整个连续自适应系统最优，则转为❌ Not answerable in scope。

## 4 Q3：全向搜索、定位与清除

### 4.1 完整费用模型与优化顺序

按题面及附件，先以“全部清除”为约束，再最小化总虚拟时间：

\[
\min_\pi T=\frac{L(\pi)}5+N_{\rm switch}
+5N_{\rm measure}+3N_{\rm clearAttempt}+2N_{\rm success},
\quad N_{\rm success}=N_{\rm source}.
\]

|行为/指令|耗时（秒）|状态与常见错误|
|---|---:|---|
|移动|两指令位置间直线距离/5|measure与clear均可能包含移动；没有独立move指令|
|切换测向频道|不同频道1，同频道0|只由measure触发；clear的频道参数不改变测向频道|
|measure返回direction|5|另加移动和可能切换|
|measure返回no_signal|5|不是免费试探|
|measure返回near|5|随后在原地clear仍为3＋2，共10秒，另计先前移动/切换|
|clear失败|3|光学定位已发生；没有2秒激光费用|
|clear成功|3＋2|与信号定向覆盖无关；可直接发clear，无须先measure|
|enter、exit|0虚拟秒|enter启动真实运行计时；exit无需返回原点|

无论信号强弱，接口不返回连续RSSI；不能实现依赖场强梯度或功率反演距离的算法。本报告不采用“RSS越强就越近”的不可用观测。对公式的一个附件校验是移动500米＋400米、3次检测、1次切换、1次失败清除：\(900/5+15+1+3=199\)秒，与附件示例一致。

一般搜索论可帮助分析检测顺序，但本题检测有硬范围、频道以及同点固定误差，与独立随机发现模型不同，不能直接套用重复扫视独立概率公式。[R12 Koopman原论文](https://doi.org/10.1287/opre.4.5.503)。

### 4.2 三类完整覆盖扫描：点数、发现率与时间

R10/R19/R22用于区分覆盖与探索，R11用于弓字形遍历思想；本题不需要避障地图或三维轨迹优化，下述具体覆盖坐标及证书是**本报告推导**。[R10综述](https://doi.org/10.1016/j.robot.2013.09.004)、[R19综述](https://doi.org/10.1016/j.phycom.2023.102073)、[R22中文综述](https://kzyjc.alljournals.cn/html/2022/3/20220301.htm)。

设检测点序列\(S=(s_1,\ldots,s_k)\)，最保守接收半径1000米。对任意给定位置先验密度\(p(q)\)，完成前k点后的期望发现率为

\[
p_k=\int_{\|q\|\le1800}1\{\min_{j\le k}\|q-s_j\|\le1000\}\,p(q)\,dq.
\]

题面没有给源位置分布，因此不能给一个“官方期望值”。本文另定义均匀圆域合成基准，只用于公平比较布局：\(p(q)=1/(\pi1800^2)\)、每源R=1000；它不是对官方随机生成机制的假设。完成有证书的覆盖后，全发现率为100%，无需任何分布假设；这仍不等于全部清除。

|布局|具体检测点与顺序|不同点数|20频道全扫次数|无定位绕行的路长|纯扫描虚拟时间|
|---|---|---:|---:|---:|---:|
|环形7点|原点；半径1500米的正六边形顶点，按周向访问|7|140|9000米|2633秒（43.88分）|
|扇区13点|原点；6个60°方向，每方向依次半径900、1500米|13|260|11038.35米|3754.67秒（62.58分）|
|弓字形25点|先原点；\(\{-2000,-1000,0,1000,2000\}^2\)从左下蛇形遍历，跳过已测原点|25|500|26828.43米|8340.69秒（139.01分）|

各点扫描先测当前频道，然后测其余频道，每点19次切换，故表中\(T=L/5+119k\)。未加入定位、清除、跳过已完成频道等优化，不能称总体策略耗时。弓字形25点是易审查的对照，不是为本题优化后的最少网格；环形7点也没有宣称所有布局中的最小点数。

**7点覆盖证明：【文献支持／本报告推导】** 半径\(r\le1000\)由原点覆盖。对\(r\in[1000,1800]\)，总有一个环点与源的极角差\(|\delta|\le30°\)。距离平方

\[
d^2\le r^2+1500^2-3000r\cos30°.
\]

右边是r的凸函数，区间最大值在端点；r=1000时约651923.79，r=1800时约813462.82，均小于\(1000^2\)。因此全部圆域被覆盖。扇区13点包含这7点，直接继承证书。25点方格覆盖整个\([-2000,2000]^2\)内的目标域，最远离最近格点\(1000/\sqrt2\approx707.11\)米，也有证书。

**均匀圆域合成比较：【本题验证／仅检测覆盖】** 固定随机种子20260910，共20000个位置样本，同一批样本用于三布局；R统一1000米，未模拟误差和清除。结果为：

|布局|前1点发现率|前3点发现率|前5点发现率|全扫发现率|首次发现平均点序号|
|---|---:|---:|---:|---:|---:|
|环形7点|30.655%|56.675%|80.300%|100%|3.26495|
|扇区13点|30.655%|47.410%|58.985%|100%|4.65170|
|弓字形25点|30.655%|36.975%|46.280%|100%|7.96410|

原点覆盖率的解析值为\(1000^2/1800^2=30.8642\%\)，抽样值合理接近。最大二项标准误约0.354个百分点，表中小数位用于复现，不代表那么高的统计精度。“首次发现平均点序号”不是发现时间，后者还取决于路程与频道在点内的检测顺序。正式比较须计算逐源首次发现虚拟时刻。

### 4.3 Q3-A：有保证的分层框架

科学问题：在源总数未知但每源频道唯一时，如何同时完成“搜索充分性”和“清除充分性”？文献定位：R10/R11的覆盖思想加R03/R08的几何判据，Reframe为两类可审核证书。✅ Answerable now，整体【未验证】。

**基准版先完整扫描，再逐源清除。** 每个频道保存首次有效观测，以及后续direction构成的区域。完成7点全频道覆盖后，仍从未收到信号的频道可判定无源；已清除频道无需再扫。未清除但已确认存在的频道进入定位队列。这样不依赖“已经找到10个就够了”的错误终止条件。

|层级|动作|进入下一层/判停条件|失败处理|
|---|---|---|---|
|发现|覆盖点停下逐频道measure|direction或near|单个no_signal只能表示该点无信号；继续覆盖|
|粗定位|Q2选择不同方位第二点|区域有界、非空并可算直径与包围圆|近平行换侧向点；no_signal保留首次观测|
|收缩|选择第三点，之后有限次改进|\(r_*(P)\le20-\tau\)|直径/面积停滞，或超过预设改进预算，转保底|
|接近|移动到包围圆中心或可清除访问区|clear成功|有证书仍失败则记录模型/数值异常，不能假定源不存在|
|保底清除|有限网格覆盖首次测向扇区|该频道clear成功|遍历完仍失败意味着规则/观测/实现不一致，报告失败|
|全局结束|逐频道核对存在性与清除状态|全部20频道均已清除或有完整无源证书|剩余未知频道继续覆盖；不能因长时间无信号退出|

第三点无需死守固定90°：对多个候选模拟扇形更新，优先让最小包围半径跨过20米，而不是只优化面积。细长区域面积很小也可能仍无法清除；单看面积会误判。

**有限清除保底构造：【文献支持／本报告推导】** 一次direction反馈后，以测点为局部原点、读数为x轴，真实源位于\(0\le x\le1500\)、\(|y|\le1500\sin1.005°<26.32\)的矩形内。在局部坐标设置

\[
(x,y)=(20i,20j),\qquad i=0,1,\ldots,75,\quad j=-1,0,1.
\]

共228个clear候选点，按三行蛇形遍历。任一矩形点到某候选的x、y差均不超过10米，因此距离\(\le\sqrt{200}<20\)米。**每个点直接clear该频道，不先measure**；必有一次成功，与误差的统计分布、定向覆盖角均无关。实际可只覆盖当前更小区域，但删点必须保留覆盖证书。

这个构造是保证有限结束的兜底，不是高效定位主算法。若从首次测点出发，完整蛇形路程4560米（包含到第一行起点的20米），移动912秒；228次clear最多\(3\times228+2=686\)秒，共1598秒，另加返回首次测点的路程。正常交会应显著减少候选清除次数，但这点尚需本题演练证实。

```text
BASELINE_Q3:
    enter；p=(0,0)；current_channel=1
    对7个覆盖点：
        先当前频道、再其余未清除频道，逐条measure
        near → 原地clear；direction → 保存首次观测并更新区域
    对仍无任何信号且未清除的频道：标记已认证无源
    对每个已发现未清除频道：
        若near：clear
        否则进行有次数上限的第二/第三点定位
        若包围半径≤20-τ：到中心clear
        若尚未成功：蛇形遍历首次测向矩形的clear点，成功即停止
    仅在全部频道已清除/已认证无源时exit
```

代码骨架见附录C；局部几何复用附录A。预期输出：源发现顺序、定位区域迭代图、频道最终状态表和五项时间分解。代码成本集中在接口状态一致性及失败分支，而非求解器。

### 4.4 Q3-B：搜索—清除交错调度与访问路径优化

科学问题：基准保证正确以后，怎样减少“全部扫完再远距离折返”的代价？文献定位：R13集合覆盖、R14局部路径交换、R15邻域访问、R16信息采集；借鉴R21/R24的全局覆盖与局部视点分层，属于Extend，不能引用无人机论文的倍数加速作为本题效果。[R15](https://doi.org/10.1016/S0196-6774(03)00047-6)、[R16](https://doi.org/10.1177/0278364914533443)、[R21作者存档](https://repository.hkust.edu.hk/ir/bitstream/1783.1-108720/1/033635_1.pdf)、[R24团队发表记录](https://uav.hkust.edu.hk/publications/)。

同一状态生成三类动作：新覆盖点扫描、已知源新测向、可以直接成功的清除。给动作a记录预计新增覆盖\(\Delta C\)、定位改善\(\Delta U\)、清除收益\(\Delta N\)及耗时：

\[
\operatorname{score}(a)=
\frac{w_C\Delta C(a)+w_U\Delta U(a)+w_N\Delta N(a)}{t(a)}.
\]

\(\Delta C\)可用最保守接收圆覆盖的未覆盖面积；\(\Delta U\)可用包围半径下降；\(\Delta N\)有确定清除证书时取1。其他概率收益必须说明估计来源。不同指标的权重须归一化并消融，不能任意调到单个案例好看。

**频道优先级建议：** near立即清除；当前附近有单次清除保证的源优先处理；已知源若只需少量移动使包围圆小于20米，优先于远处开新点；其余按覆盖收益/时间。保留覆盖欠账队列，每经过有限数量的局部动作至少完成一个欠账，防止算法一直优化已知源而永远不找最后一个源。

**减少切换：** 每点先检测当前频道，再检测其他需要的频道；可交替升/降序，跨点承接上一个频道。任意两频道切换均为1秒，与频道编号差无关。clear之后测向频道保持不变。对已清除频道不再测；对已知源若本站测向没有信息价值可跳过；对未知频道不得因单次无信号永久删除。

**路径与清除访问区域：** 已知区域\(P_i\)对应保证成功的访问区

\[
K_i=\bigcap_{q\in P_i}B(q,20).
\]

对多边形只需相交各顶点的20米圆。\(K_i\ne\varnothing\)等价于\(r_*(P_i)\le20\)。在\(K_i\)内选离当前位置近的点，可比总是去中心省路；尚未实现精确投影时取包围圆中心即可。若只用\(B(\hat q_i,20)\)，那是名义访问区，没有覆盖未知真值的保证。

将已可清除的目标写成**固定起点、自由终点的开放邻域访问路径**。最近邻初始化\(O(n^2)\)，n≤16；对固定代表点做2-opt，每轮\(O(n^2)\)检查，采用边长差值评价可常数时间判断交换，再更新路径。允许翻转后缀，因为不需返回起点。下式用于内部片段：

\[
\Delta L=\|a-c\|+\|b-d\|-\|a-b\|-\|c-d\|.
\]

如果交换末尾片段，则没有\(b-d\)、\(c-d\)两项。不能套闭合TSP强制返回原点。尚未定位的源有观测先后依赖，不能与已可清除源一起任意交换；先规划可清除集，状态变化后滚动重排。

```text
ADAPTIVE_Q3:
    维护未覆盖频道/空间欠账、已知源区域、可清除访问区
    生成新扫描/复测/清除候选，估算收益和完整时间
    在有限动作预算内贪心选优；周期性偿还覆盖欠账
    可清除集：最近邻初始化 → 有限轮开放2-opt
    每收到反馈更新状态，重新规划
    每个源定位达到预算仍不成功 → Q3-A有限保底
    结束条件完全沿用Q3-A
```

⚠️ Answerable with extra work，附录C给收益排序与开放2-opt骨架。预期产出是与Q3-A相比的总时间差、额外检测、绕行和清除成功率，优势【未验证】。

R13的集合覆盖近似界适用于固定集合成本；这里移动成本依赖历史路径，不能照搬其近似比例。R17/R18/R23的信息/自适应次模理论可用于审查贪心条件；本题信息相关、成本随位置变化，尚未证明次模性，因此没有\(1-1/e\)的本题性能保证。[R13](https://doi.org/10.1287/moor.4.3.233)、[R17](https://www.jmlr.org/papers/v9/krause08a.html)、[R18作者说明](https://www.cs.cmu.edu/~dgolovin/pubs.htm)、[R23正式会议论文](https://proceedings.mlr.press/v134/esfandiari21a.html)。

### 4.5 Q3-C：全局最优研究为何只留讨论

完整策略\(\pi\)的动作依赖历史反馈，源位置、有效半径、误差场、频道占用均未知。目标可写\(\min_\pi\sup_{\omega\in\Omega}T(\pi,\omega)\)，但这不是把16个点做一次TSP就能解决的模型。连续场景与观测分支会产生巨大策略树。❌ Not answerable in scope：三天内不承诺求全局最优或证明启发式最优。

```text
研究用：离散场景集 → 枚举动作 → 对每种反馈分支递归
       → 记忆化与下界剪枝 → 在极小场景中得到参照值
```

附录C仅给小规模递归接口，其终止条件必须有深度预算；本阶段未运行。能帮助理解启发式损失，不能据极小实例推广到官方完整场景。

## 5 Q4：定向盲区与保证搜索

### 5.1 观测模型与漏检含义

定向源q具有未知单位方向\(u\)，接收点s可检测条件为

\[
\|s-q\|\le R,\quad u^T(s-q)\ge0,\qquad R\in[1000,1500].
\]

边界±90°包含在内。no_signal可能来自频道本来无源、源已清除、距离大于R、或位于发射半平面外。同一个位置重复检测不会改变几何可见性；近于5米但处于背面，仍可能no_signal。clear只检查距离，不受u影响。

R20研究有向传感器的目标覆盖，给本题提供扇区覆盖的跨领域参照，但它能够设计传感器布置和方向，且有通信连通性目标。本题源方向未知且不可控制，不能移植它的近似比作为本题保证。[R20官方会议摘要](https://infocom.info/infocom23/day/3/track/Track%20B)。

### 5.2 Q4-A：Q3最小改动＋局部多角度复核

科学问题：已经发现或有疑似区域的源，怎样降低后续测向失联风险？文献定位：Refine Q3的接收模型，保留几何定位及光学清除主体。✅ Answerable now；局部规则有下面的证明，效率【未验证】。

改动清单：

1. no_signal不再排除整个1000米圆，因为圆内也可能是发射背面。
2. 保存首次成功观测点，明确至少该点可见；其原始扇区始终可作为清除保底区域。
3. 普通复测失败后换空间方位，不能原地重测；复测只更新确定成立的约束。
4. near仍支付5秒检测后清除，且仅在可见半平面内可能返回。
5. 小定位区域优先直接clear；无需为获取无线信号绕到发射正面。
6. Q3的7点覆盖证书失效；全局未发现频道必须采用Q4-B证书，或者其他经过证明的定向覆盖。
7. 频道清除状态、费用、开放路径、API串行规则全部保持一致。

**四方向局部证书：** 若\(P\subseteq B(c,r)\)，在\(c\pm\rho e_x,c\pm\rho e_y\)四点复核。对任意u，至少一个点满足

\[
u^T(s-q)\ge\rho/\sqrt2-r.
\]

若\(\rho/\sqrt2>r\)且\(\rho+r\le1000\)，则该点同时处于可见半平面和必收范围。例\(r\le100,\rho=200\)成立。该保证是至少发现信号，不是保证新的bearing一定产生足够好的交会角。两个关于估计中心的对称点没有一般保证：u与两点连线垂直，真实源又向u偏离中心时，两点可能同在背面。

```text
REFINE_DIRECTIONAL(P):
    若包围半径≤20-τ：直接clear
    否则：挑选Q2候选，失败后检查四方向证书是否适用
    适用 → 四方向逐点measure，遇near清除，direction更新区域
    不适用或达到预算 → 首次测向扇区有限clear保底
```

附录D给四方向候选及过滤骨架。预期输出：全向/定向分组耗时、每源复核次数、no_signal原因在本地真值中的分解；官方反馈看不到原因时不能自行分类成“背面”。

### 5.3 Q4-B：任意方向的全局覆盖保底

科学问题：源位置和方向都未知时，如何证明最后一个隐藏源不会被遗漏？以下是本报告的几何构造，不归功于某篇文献的现成结论。

使用网格

\[
G=\{(500i,500j):i,j=-5,-4,\ldots,5\},\quad |G|=121.
\]

**覆盖证明：【文献支持／本报告推导】** 对任意\(\|q\|\le1800\)和任意单位u，考虑\(z=q+500u\)。各坐标绝对值≤2300，所以G中存在最近网格点s，使\(\|s-z\|\le250\sqrt2\approx353.553\)。于是

\[
\|s-q\|\le500+250\sqrt2<1000,
\]
\[
u^T(s-q)=500+u^T(s-z)\ge500-250\sqrt2>0.
\]

因此s必位于发射正面且距离小于所有可能的有效半径。所有G点对未知频道扫描完成后，没有信号的频道确实无源；无需估计u，也适用于全向源。

这不是最省点的方案，而是容易实现、证明和复核的有限保底。先原点全扫，再按11行蛇形走遍网格、跳过原点重复测量，121个不同测点，最多2420次measure。纯扫描路程约\(60000+2500\sqrt2=63535.53\)米，虚拟时间约

\[
63535.53/5+121\times119=27106.11\text{秒}\approx7.53\text{小时}.
\]

若再对最多16个源使用228点clear保底，最多3648次clear；计入远距离转移，仍可给出保守的虚拟100小时以内上界：有效首次测点距原点≤3300米，清除网格上的位置距原点<4810米，返回另一个有效首次测点最多8110米，故每源按\(8110/5+1598=3220\)秒上界计，总计\(27106.11+16\times3220<22\)小时。此上界针对“先全扫、再有限保底”，不包含无限重复优化；启发式必须设动作预算。

**真实20分钟另算：** 最坏约\(2420+3648+2=6070\)个RPC，仅平均每次0.2秒就超过1200秒，尚未留规划与异常重试时间。因此虚拟时间可保证不意味着真实窗口可保证。必须测接口响应延迟，启用跳过已完成频道、局部精定位、提前成功停止和批内状态复用，保持不同动作串行。⚠️端到端实时完成仍需额外演练；✅网格与证书本身可立即实现。

```text
GLOBAL_DIRECTIONAL_FALLBACK:
    对G中未完成的点：扫描仍需证明不存在的频道
    若发现信号：记录；near可即时clear
    已发现源采用Q4-A/Q3有限clear保底
    全部频道有清除或无源证书后exit
```

附录D直接生成121点。预期产出：任意朝向的覆盖证明、随机朝向验证、边界/背向极端案例以及真实RPC吞吐测量。本阶段对20000个合成位置及随机方向检查了上述构造，全部找到满足条件的网格点；没有运行完整2420次官方扫描。

### 5.4 Q4-C：位置—方向联合状态，作为增量实验

令\(\mathcal B\subseteq\{q,R,u\}\)表示仍可能的场景。有信号加入距离与正面约束，no_signal加入析取条件

\[
\|s-q\|>R\quad\text{或}\quad u^T(s-q)<0.
\]

它是非凸、非单一半平面约束，不能直接放入Q1凸裁剪。可用离散朝向区间＋多个位置多边形，或带权粒子做候选评分。没有明确先验时，粒子权重只作为人工场景权重，不称作官方概率后验；有限粒子不承担“绝不漏源”的保证。文献定位：Extend R08/R09的集合估计思想，场景差异显著。

```text
生成位置/半径/方向场景 → 按反馈相容性过滤
→ 对候选计算剩余场景量或最坏分裂 → 选下一点
→ 所有场景为空时回查误差与离散化；始终保留Q4-B
```

⚠️ Answerable with extra work，附录D给相容性过滤骨架。预期输出：相同清除率下能否少用复核点；整个策略【未验证】。将有限粒子当作严格真值集合属于不可接受的过强结论。

## 6 演练、消融与三天实现安排

### 6.1 本阶段实际完成的核验

复现记录：[本地检查结果](C:/Users/30130/Desktop/数模/tmp/B_research/local_checks.json)、[几何检查代码](C:/Users/30130/Desktop/数模/tmp/B_research/verify_geometry.py)、[C++卡壳代码](C:/Users/30130/Desktop/数模/tmp/B_research/calipers.cpp)。本地代码为本次调研的证据附件，正式五份调研Markdown的数量不变。

|检查|实际运行范围|结论标签与限制|
|---|---|---|
|Python卡壳对全点对枚举|2013组，含点、线段、四边形、细长矩形和随机凸包|【本题验证】最大直径差0；不替代任意浮点输入的严密数值证明|
|C++卡壳对全点对枚举|GCC13.2.0，C++17，2000组随机凸包|【本题验证】全部通过|
|测向半平面交包含真值|1000组合成位置、每组4次有界扰动观测|【本题验证】全部包含；未检验官方误差场|
|覆盖圆反例|等边三角形及真实两扇形四边形|【本题验证】直径圆不能普遍覆盖|
|三种全向扫描布局|20000个均匀圆域位置，R=1000|【本题验证】覆盖构造及前缀比较；没有清除状态机|
|定向网格证书|同批20000位置、随机朝向|【本题验证】均找到可见且在1000米内的点|
|首次测向清除网格|1501个距离×3个角度，共4503点|【本题验证】最大最近点距离约14.079米；连续保证来自正文证明|
|计时公式|附件199秒示例、合成219秒示例、near后成功10秒|代数核验；没有执行官方客户端状态转换|
|半平面区域分类|5组空集、无界、方形、单点、线段|【本题验证】辅助LP分类通过；不是全部病态输入验证|
|开放2-opt辅助函数|100组各16点的随机路径|【本题验证】保持点集且路长不增加；没有验证整体搜索收益|

文档检查：[审计结果](C:/Users/30130/Desktop/数模/tmp/B_research/report_audit.json)。25个文献编号唯一、TL;DR为136字符、6个Python代码块通过语法解析、所有本报告本地链接指向现存文件。

**尚未完成：** 官方模拟器连接、完整Q3/Q4清除、HTTP重试/超时实测、候选测点评分对照、开放2-opt整体收益、算法真实20分钟内完成率。本阶段任何“全部源最终可清除”的表述均限定为规则成立且动作完成的数学构造，不能写入正式测试结果表。

### 6.2 独立验证问题与实验矩阵

把研究问题固定为以下五项，避免先看结果再选故事：

|问题|对照/改动|主指标|反驳该路线的观察|
|---|---|---|---|
|定位区域是否可靠|精确扇形 vs 线性椭圆|真值包含率、包围半径、退化率|出现违反误差界之外无法解释的真值丢失|
|高信息测点是否真的省时间|固定侧移 vs Q2-A vs Q2-B|全部成功前提下总时间、分项费用|少测几次却多走更长路线|
|覆盖布局是否改善发现|7点/13点/25点，同一合成场景|逐源首次发现时刻与全发现时刻|点数少但空间顺序导致后期定位绕行更大|
|调度与路径是否值得复杂化|基准→跳已清频道→交错调度→2-opt，逐项加入|清除率、总时间、规划CPU、RPC数|出现遗漏、状态错误或真实窗口超时|
|定向改动是否有效|局部多角度/全局保底/联合粒子|定向源清除率、无信号次数、最坏时长|只在有利朝向成功，边界方向遗漏|

合成压力场景覆盖：源数10/13/16；R=1000/1250/1500；源在圆心、边界、同侧聚集、两远簇；测角误差端点、平滑相关、同点固定；定向比例0/0.5/1以及背向原点、边界朝外、近切向。它们是主动构造的实验情景，不是声称官方生成服从这些分布。每次策略调用只看到协议规定的观测，不能把合成真值泄露给规划器。

合成对照可按同场景配对比较，至少报告中位数、90%分位数、最坏值与失败数量。官方演练如果无法重复同一案例，不得冒充配对实验；记录每次案例编码，采用事先固定策略和多次独立演练。单个失败案例也必须保留。正式测试每问只有三次，不把它们当参数搜索数据。

“平均定位清除时间”按题面为总虚拟时间/成功清除数。若成功数为0，标记未定义，不强行除以1。较低清除率可能人为拉低该指标，必须先比较清除比例，再比较时间，不能只报告成功的容易目标。

### 6.3 模拟器迭代计划与止损条件

|阶段|实施内容|必须得到的证据|停止扩展的条件|
|---|---|---|---|
|第1天首个4—6小时|几何内核、费用记账、串行客户端、Q3-A|读数与角度单位正确；199秒例场景一致；动作重试不重复计时|核心几何不稳就不做高级调度|
|第1天后半段|完整Q3合成状态机、官方演练；并加Q4-B|逐频道终止证书；真实RPC延迟分布；失败日志|官方吞吐不够则优先减少调用，暂停前沿方法|
|第2天前半段|Q2候选/第三点；Q4-A多角度；独立合成实验可并行|基准与改进的清除率、总时间、RPC数|改进不稳定立即回退基准|
|第2天下半段|频道跳过、清除顺序、少量2-opt；汇总消融|固定参数的多次演练；论文所需图表与统计|没有清晰增益就删复杂模块|
|第3天尽早|冻结版本，逐次执行Q3三次、Q4三次正式测试|导出原名日志、核对案例编码与上传状态|正式窗口不再调参或临时换依赖|
|9月13日15:30前为目标|完成全部正式测试及支撑材料核验|各3份正式记录齐全|17:30后不得启动新测试，不依赖最后窗口|

这是一套可选B题后的实现安排；当前只交付任务1调研，不自动开始正式测试。总体精确到小时的B/C两套安排按约定留到任务5。

分工建议：队员A负责几何证明与C++/Python内核；队员B负责Python状态机、客户端、实验自动记录；队员C负责实验设计、文献核对、图表与论文组织，并实现轻量预测/信息评分对照。GPT agent可生成骨架、查错、补反例和整理实验，但三名队员须逐项审核规则、公式与正式结果。算法型队员不应同时承担全部几何和协议排错。

协议硬要求：不同新动作不得并发；每个新动作新request_id；网络超时重试时保持同一路径及全部原请求内容和request_id。必须同时检查HTTP状态与accepted；accepted=false里的virtual_time_s=0不是当前时刻。enter后最长20分钟，同时受窗口25分钟限制，按返回实际剩余时长设截止；保持联网和登录状态，提交日志保留模拟器文件原名。测试真实时限是工程关键风险，虚拟100小时不是可用计算时间。

## 7 文献清单与可信度边界（25篇）

### 7.1 如何使用这份清单

以下25条均对应正式期刊、会议或正式书籍章节，标为【核心】；原文预印本只作为已发表版本的可读存档，不重复计数。博客和GitHub README不进入参考文献。本阶段没有把未正式发表预印本凑入配额。所有条目给出可借鉴点和适用限制；最终BibTeX汇总按执行顺序留给任务4。

核验深度不完全相同：R08、R09、R21阅读作者/机构全文的相关段落；R01/R04核对原作者原始发表记录及方法说明；其余主要通过出版方摘要、正式目录、作者书目或开放论文核对。**25条书目信息可追溯，不等于25篇全文都已精读。** 使用某条精细定理之前，队员仍须核对原文假设和定理位置。

### 7.2 几何、估计与主动测量

|编号/级别|标题、作者|发表信息|原始来源/DOI|本题可借鉴点与关联|
|---|---|---|---|---|
|R01【核心】|*Solving geometric problems with the rotating calipers*；Godfried T. Toussaint|IEEE MELECON’83，1983|[作者原始记录](https://www-cgrl.cs.mcgill.ca/~godfried/research/calipers.html)|Q1-A：卡壳框架与对踵点；作者说明直径思想先见Shamos1978学位论文，Toussaint命名并推广，勿误写所有思想首创年份|
|R02【核心】|*Reentrant polygon clipping*；Ivan E. Sutherland、Gary W. Hodgman|Communications of the ACM，17(1):32–42，1974|[DOI 10.1145/360767.360802](https://doi.org/10.1145/360767.360802)；[ACM SIGMOD目录](https://www.sigmod.org/publications/dblp/db/journals/cacm/cacm17.html)|Q1-A：逐裁剪边处理凸窗口；适用于有界初始多边形，不自动解决无界半平面交|
|R03【核心】|*Smallest enclosing disks (balls and ellipsoids)*；Emo Welzl|New Results and New Trends in Computer Science，LNCS555:359–370，1991|[DOI 10.1007/BFb0038202](https://link.springer.com/chapter/10.1007/BFb0038202)|Q1-B/Q3判停：最小包围圆与随机增量；现有核验代码是穷举支撑圆版本|
|R04【核心】|*Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates*；Jonathan Richard Shewchuk|Discrete & Computational Geometry，18(3):305–363，1997|[作者页](https://www.cs.cmu.edu/~jrs/jrspapers.html)；[DOI 10.1007/PL00009321](https://doi.org/10.1007/PL00009321)|Q1数值边界：方向及内圆谓词；普通epsilon与long double不等于精确谓词|
|R05【核心】|*Optimality analysis of sensor-target localization geometries*；Adrian N. Bishop、Barış Fidan、Brian D. O. Anderson、Kutluyıl Doğançay、Pubudu N. Pathirana|Automatica，46(3):479–492，2010|[DOI 10.1016/j.automatica.2009.12.003](https://doi.org/10.1016/j.automatica.2009.12.003)|Q2-B：Fisher信息与最优几何，必须保留测量类型及约束条件|
|R06【核心】|*Optimal angular sensor separation for AOA localization*；Kutluyıl Doğançay、Hatem Hmam|Signal Processing，88(5):1248–1260，2008|[DOI 10.1016/j.sigpro.2007.11.013](https://doi.org/10.1016/j.sigpro.2007.11.013)|Q2-B：固定距离下的测角传感器角度配置；本题移动费用另建模|
|R07【核心】|*Optimal sensor placement and motion coordination for target tracking*；Sonia Martínez、Francesco Bullo|Automatica，42(4):661–668，2006|[DOI 10.1016/j.automatica.2005.12.018](https://doi.org/10.1016/j.automatica.2005.12.018)|Q2-C：把信息与运动协调结合；原模型为距离观测，不当作bearing-only结论|
|R08【核心】|*Path planning with uncertainty: A set membership approach*；Nicola Ceccarelli、Mauro Di Marco、Andrea Garulli、Antonio Giannitrapani、Antonio Vicino|International Journal of Adaptive Control and Signal Processing，25(3):273–287，2011（在线2010）|[DOI 10.1002/acs.1217](https://doi.org/10.1002/acs.1217)；[作者全文](https://www3.diism.unisi.it/~anto/public/papers/ACSP10.pdf)|Q2-A/Q4-C：用有界集合维护可行真值；原文含测距、位姿与地标，不能照搬状态模型|
|R09【核心】|*Collaborative Bearing Estimation Using Set Membership Methods*；Mohammad Zamani、Jochen Trumpf、Chris Manzie|26th International Conference on Information Fusion（FUSION），2023，论文号8570|[作者正式书目](https://trumpf.id.au/pubs.html)；[作者全文](https://trumpf.id.au/pubs/Zamani_Trumpf_Manzie_FUSION2023.pdf)|Q2-C：相关信息融合及椭球外包；协作机器人设定不同，仅用于可控扩展|
|R25【核心】|*Sensor Selection via Convex Optimization*；Siddharth Joshi、Stephen Boyd|IEEE Transactions on Signal Processing，57(2):451–462，2009|[作者页](https://web.stanford.edu/~boyd/papers/sensor_selection.html)；[DOI 10.1109/TSP.2008.2007095](https://doi.org/10.1109/TSP.2008.2007095)|Q2-C：候选测量选择的凸松弛与舍入；不能视为连续自适应路径的精确解|

### 7.3 覆盖、搜索论与路径

|编号/级别|标题、作者|发表信息|原始来源/DOI|本题可借鉴点与关联|
|---|---|---|---|---|
|R10【核心】|*A survey on coverage path planning for robotics*；Enric Galceran、Marc Carreras|Robotics and Autonomous Systems，61(12):1258–1276，2013|[DOI 10.1016/j.robot.2013.09.004](https://doi.org/10.1016/j.robot.2013.09.004)|Q3-A：覆盖分解和路径分类；用于方法定位，不提供本题最优点数|
|R11【核心】|*Coverage Path Planning: The Boustrophedon Cellular Decomposition*；Howie Choset、Philippe Pignon|Field and Service Robotics，203–209，1998|[DOI 10.1007/978-1-4471-1273-0_32](https://doi.org/10.1007/978-1-4471-1273-0_32)|Q3-A：弓字形区域遍历；书章1998与会议1997版本不能混用页码|
|R12【核心】|*The Theory of Search. II. Target Detection*；B. O. Koopman|Operations Research，4(5):503–531，1956|[DOI 10.1287/opre.4.5.503](https://doi.org/10.1287/opre.4.5.503)|Q3发现率：明确探测模型与搜索努力；题中硬阈值不等于独立随机重复发现|
|R13【核心】|*A Greedy Heuristic for the Set-Covering Problem*；V. Chvátal|Mathematics of Operations Research，4(3):233–235，1979|[DOI 10.1287/moor.4.3.233](https://doi.org/10.1287/moor.4.3.233)|Q3-B：单位代价覆盖收益；依赖路径的费用使原近似保证不能直接引用|
|R14【核心】|*A Method for Solving Traveling-Salesman Problems*；G. A. Croes|Operations Research，6(6):791–812，1958|[DOI 10.1287/opre.6.6.791](https://doi.org/10.1287/opre.6.6.791)|Q3-B：经典路径局部改进脉络；本题需开放路径并保持观测依赖|
|R15【核心】|*Approximation algorithms for TSP with neighborhoods in the plane*；Adrian Dumitrescu、Joseph S. B. Mitchell|Journal of Algorithms，48(1):135–159，2003|[DOI 10.1016/S0196-6774(03)00047-6](https://doi.org/10.1016/S0196-6774(03)00047-6)|Q3-B：从访问精确点改为访问区域；本题保证清除区是交集而非名义20米圆|
|R16【核心】|*Sampling-based robotic information gathering algorithms*；Geoffrey A. Hollinger、Gaurav S. Sukhatme|The International Journal of Robotics Research，33(9):1271–1287，2014|[DOI 10.1177/0278364914533443](https://doi.org/10.1177/0278364914533443)|Q3-B：受预算约束的信息采集与路径联合；渐近性质不等于有限20分钟最优|
|R19【核心】|*Region coverage-aware path planning for unmanned aerial vehicles: A systematic review*；Krishan Kumar、Neeraj Kumar|Physical Communication，59:102073，2023|[DOI 10.1016/j.phycom.2023.102073](https://doi.org/10.1016/j.phycom.2023.102073)|Q3路线地图：区域、资源、在线覆盖等维度；本题不需复现三维飞行动力学|
|R21【核心】|*FUEL: Fast UAV Exploration Using Incremental Frontier Structure and Hierarchical Planning*；Boyu Zhou、Yichen Zhang、Xinyi Chen、Shaojie Shen|IEEE Robotics and Automation Letters，6(2):779–786，2021|[DOI 10.1109/LRA.2021.3051563](https://doi.org/10.1109/LRA.2021.3051563)；[机构全文](https://repository.hkust.edu.hk/ir/bitstream/1783.1-108720/1/033635_1.pdf)|Q3-B：增量维护探索状态与分层规划；仅借架构，不借原文倍数效果|
|R22【核心】|《旋翼无人机环境覆盖与探索规划方法综述》；张世勇、张雪波、苑晶、方勇纯|控制与决策，37(3):513–529，2022|[期刊全文；DOI 10.13195/j.kzyjc.2021.1751](https://kzyjc.alljournals.cn/html/2022/3/20220301.htm)|Q3：中文覆盖/探索术语与相关路线分类|
|R24【核心】|*FALCON: Fast Autonomous Aerial Exploration Using Coverage Path Guidance*；Yichen Zhang、Xinyi Chen、Chen Feng、Boyu Zhou、Shaojie Shen|IEEE Transactions on Robotics，41:1365–1385，2025（团队页列在线2024）|[DOI 10.1109/TRO.2024.3522148](https://doi.org/10.1109/TRO.2024.3522148)；[作者团队页](https://uav.hkust.edu.hk/publications/)|Q3-B：全局覆盖指导局部探索，减少回访的架构；年份用出版方登记的正式卷年2025|

### 7.4 信息论、自适应优化与定向覆盖

|编号/级别|标题、作者|发表信息|原始来源/DOI|本题可借鉴点与关联|
|---|---|---|---|---|
|R17【核心】|*Near-Optimal Sensor Placements in Gaussian Processes: Theory, Efficient Algorithms and Empirical Studies*；Andreas Krause、Ajit Singh、Carlos Guestrin|Journal of Machine Learning Research，9(8):235–284，2008|[JMLR正式页面](https://www.jmlr.org/papers/v9/krause08a.html)|Q3-B：信息收益的次模分析；本题未建立GP或证明该性质|
|R18【核心】|*Adaptive Submodularity: Theory and Applications in Active Learning and Stochastic Optimization*；Daniel Golovin、Andreas Krause|Journal of Artificial Intelligence Research，42:427–486，2011|[作者页](https://www.cs.cmu.edu/~dgolovin/pubs.htm)；[作者BibTeX所列DOI 10.1613/jair.3278](https://www.cs.cmu.edu/~dgolovin/bibtex.htm)|Q3-B/C：审查自适应贪心的成立条件；本题没有原定理保证|
|R20【核心】|*Target Coverage and Connectivity in Directional Wireless Sensor Networks*；Tan D. Lam、Dung T. Huynh|IEEE INFOCOM，1–10，2023|[DOI 10.1109/INFOCOM53939.2023.10229093](https://doi.org/10.1109/INFOCOM53939.2023.10229093)；[官方会议摘要](https://infocom.info/infocom23/day/3/track/Track%20B)|Q4：扇区覆盖的计算几何视角；原问题方向可设计且含连通性，本题不同|
|R23【核心】|*Adaptivity in Adaptive Submodularity*；Hossein Esfandiari、Amin Karbasi、Vahab Mirrokni|Proceedings of the 34th Conference on Learning Theory，PMLR134:1823–1846，2021|[PMLR正式论文](https://proceedings.mlr.press/v134/esfandiari21a.html)|Q3-B/C：理解自适应轮次成本；仅在满足自适应次模假设时使用理论结论|

## 8 检索停止规则、未闭合分支与结果审计

### 8.1 检索记录与饱和度

本阶段收录25篇，达到任务1配额上限，按用户Stop Rule结束本阶段扩展检索。**这是配额停止，不是宣称整个领域穷尽。** 近五年严格以2021年9月10日后计，R09/R19/R20/R22/R24覆盖2022—2025；2021年的R21/R23仅作为邻近时段成果，不用来虚构严格五年覆盖。

|分支|实际使用的代表检索词（保留原搜索语言）|已收录支撑|停止状态/仍有空间|
|---|---|---|---|
|旋转卡壳与数值几何|`Toussaint Solving geometric problems with the rotating calipers 1983 PDF`；`Robust Adaptive Floating-Point Geometric Predicates Shewchuk 1997`|R01/R04|经典与数值实现已覆盖；近年鲁棒半平面实现仍有空间，配额停止|
|多边形裁剪与包围圆|`Reentrant polygon clipping`；`Smallest enclosing disks balls ellipsoids Welzl`|R02/R03|问题已可回答；不宣称近期算法穷尽|
|测角几何与CRLB|`Bishop Fidan Anderson Dogancay Pathirana optimality sensor target geometries bearing only localization 2007`；`Optimal angular sensor separation for AOA localization`；`bearing-only 2024 optimal sensor placement`|R05/R06/R07|经典结论清楚；近年场景更复杂，尚有空间|
|有界集合定位|`bearing only localization set membership bounded error 2021 2022 2023 2024`；`set-membership bearing localization uncertainty`；`Path planning with uncertainty a set membership approach journal`；`Collaborative Bearing Estimation Using Set Membership Methods publication`|R08/R09|经典、2023方法和协作估计交叉方向已覆盖；按三类覆盖停止，单机器人带费用路线仍可扩展|
|覆盖与探索|`Galceran Carreras survey coverage path planning robotics 2013`；`coverage path planning survey 2021 2023 2024 robotics autonomous systems`；`Coverage Path Planning Boustrophedon Cellular Decomposition`；`FUEL Fast UAV Exploration`；`FALCON Fast Autonomous Aerial Exploration Using Coverage Path Guidance`|R10/R11/R19/R21/R22/R24|经典＋2022—2025＋机器人交叉已覆盖，按三类覆盖停止|
|搜索论与集合覆盖|`Koopman Search and Screening General Principles Historical Applications 1980`；`The Theory of Search II Target Detection Koopman 1956`；`A Greedy Heuristic for the Set-Covering Problem Chvatal`|R12/R13|经典已定位；现代未知分布搜索仍有空间|
|访问顺序与邻域TSP|`A Method for Solving Traveling-Salesman Problems Croes`；`Approximation algorithms for TSP with neighborhoods in the plane`|R14/R15|开放、在线、带信息的近年算法仍有空间，配额停止|
|主动信息采集与凸选择|`Sampling-based robotic information gathering algorithms Hollinger Sukhatme`；`Near-Optimal Sensor Placements Gaussian Processes`；`Sensor Selection via Convex Optimization Joshi Boyd`|R16/R17/R25|理论与跨领域基础覆盖，精确适配本题未闭合|
|自适应次模|`Adaptive Submodularity Theory Applications Active Learning Stochastic Optimization`；`Adaptivity in Adaptive Submodularity`|R18/R23|已找到成立条件；未证明本题满足，不宣称已饱和|
|定向盲区|`directional sensor coverage unknown orientation target detection 2022 2024`；`directional coverage sensor 2023 IEEE`；`Target Coverage and Connectivity in Directional Wireless Sensor Networks Lam Huynh 2023`|R20，结合R13及几何证书|找到交叉正式文献；未知发射方向且单狗收费检测的完全匹配文献未找到，仍有空间|
|中文定位/覆盖|`交会定位 最优 site:sys-ele.com`；`纯方位 测站 site:ejournal.org.cn`；`覆盖 探索 张世勇 2023`；`旋翼无人机环境覆盖与探索规划方法综述`|R22|中文综述已找到；本阶段未检索到足够可靠且完全匹配本题的中文测向原始论文，不以泛相关条目补数|

上述表记录实际检索词，不把原计划中的所有关键词冒充已经执行。没有完整记录某分支连续两轮零新增，就不使用“连续两轮无新增”宣布饱和。

### 8.2 可追溯性与失败记录

部分ACM、IEEE、Elsevier/JAIR页面通过浏览工具直接打开时失败；改为公开的作者/机构原稿、官方目录、出版方可检索摘要及出版方提交的Crossref书目信息核对，没有绕过付费限制。一次Crossref核验中R02/R25返回429，R18返回404；这不是文章不存在的证据。R18的DOI从作者BibTeX核对，链接保留能访问的作者页。R24正式卷年2025与团队页在线2024已区分；R04页码按作者及出版记录305—363，不采用不一致的聚合站页码。

Koopman书名检索出现过书评，未把书评作者/DOI当作原书；最终采用作者的1956正式搜索论论文。GitHub项目页仅帮助定位原论文，不列为核心文献，不据README宣称复现。原始材料在当前工作区实际位于`document/CUMCM2026Problems/`，报告链接按实际路径修正。

下一步决策只需确认是否进入任务2。若继续，保持B强化学习【未验证】，评估其相对当前几何主线的增益、训练与接口风险；不改变本阶段可证明与已运行证据的边界。


## 9 附录A：Q1可运行几何内核与独立复核

### 9.1 依赖、接口与验证范围

已核对的本地环境：Python 3.12.14、NumPy 2.2.4、SciPy 1.16.2、GCC 13.2.0（C++17）。基础几何只需Python标准库；线性规划、FIM与松弛骨架才需要NumPy/SciPy。本阶段没有安装新依赖。公开函数的输入约定是以米为单位的二维坐标，角度仅在接口处用度，内部用弧度。

以下核心摘自本地核验文件。`intersect_bounded`明确使用目标区域的已知外框，只用于有物理先验的Q3/Q4；纯Q1无界性先用9.3检查。`mec_oracle`是小规模穷举支撑圆，不是期望线性算法。浮点容差未形成任意输入的严格区间证书；正式代码应对近退化结果再次核验。

### 9.2 Python与C++直径骨架

```python
import math, itertools

def sub(a,b): return (a[0]-b[0],a[1]-b[1])
def cross(a,b): return a[0]*b[1]-a[1]*b[0]
def dot(a,b): return a[0]*b[0]+a[1]*b[1]
def d2(a,b): return dot(sub(a,b),sub(a,b))
def hull(points):
    p=sorted(set(map(tuple,points)))
    if len(p)<=1: return p
    def part(seq):
        out=[]
        for q in seq:
            while len(out)>1 and cross(sub(out[-1],out[-2]),sub(q,out[-1]))<=0: out.pop()
            out.append(q)
        return out
    return part(p)[:-1]+part(p[::-1])[:-1]

def diameter(p):
    """Strict convex CCW vertices; hull() removes duplicates and collinear points."""
    n=len(p)
    if n==0: raise ValueError('empty polygon')
    if n==1: return 0.0,(p[0],p[0])
    if n==2: return math.sqrt(d2(*p)),(p[0],p[1])
    best=-1.0; pair=None; j=1
    def area(i,j): return cross(sub(p[(i+1)%n],p[i]),sub(p[j%n],p[i]))
    for i in range(n):
        ni=(i+1)%n
        while area(i,(j+1)%n)>area(i,j): j=(j+1)%n
        candidates=[j]
        if math.isclose(area(i,(j+1)%n),area(i,j),rel_tol=1e-12,abs_tol=1e-9): candidates.append((j+1)%n)
        for a in (i,ni):
            for b in candidates:
                val=d2(p[a],p[b])
                if val>best: best,pair=val,(p[a],p[b])
    return math.sqrt(best),pair

def clip(p,a,b,tol=1e-8):
    # Clip to outward-relaxed a.x <= b+tol. Norm(a)=1 for bearing planes.
    if not p: return []
    b+=tol; out=[]
    for x,y in zip(p,p[1:]+p[:1]):
        fx,fy=dot(a,x)-b,dot(a,y)-b
        if fx<=0: out.append(x)
        if (fx<=0)!=(fy<=0):
            t=fx/(fx-fy)
            out.append((x[0]+t*(y[0]-x[0]),x[1]+t*(y[1]-x[1])))
    return out

def wedge(s,theta,eps=math.pi/180):
    lo,hi=theta-eps,theta+eps
    a=(math.sin(lo),-math.cos(lo)); c=(-math.sin(hi),math.cos(hi))
    return [(a,dot(a,s)),(c,dot(c,s))]

def intersect_bounded(planes,box=1800):
    p=[(-box,-box),(box,-box),(box,box),(-box,box)]
    for a,b in planes: p=clip(p,a,b)
    return hull(p)

def mec_oracle(p):
    """Enumerate support circles. O(n^4), deliberate small-n independent oracle."""
    if not p: raise ValueError('empty')
    candidates=[(p[0],0.0)]
    for a,b in itertools.combinations(p,2):
        c=((a[0]+b[0])/2,(a[1]+b[1])/2); candidates.append((c,d2(c,a)))
    for a,b,c in itertools.combinations(p,3):
        u,v=sub(b,a),sub(c,a); det=2*cross(u,v)
        if abs(det)<1e-12: continue
        x=(dot(u,u)*v[1]-dot(v,v)*u[1])/det
        y=(u[0]*dot(v,v)-v[0]*dot(u,u))/det
        center=(a[0]+x,a[1]+y); candidates.append((center,d2(center,a)))
    valid=[(c,r2) for c,r2 in candidates if all(d2(c,v)<=r2+1e-7*max(1,r2) for v in p)]
    c,r2=min(valid,key=lambda t:t[1]); return c,math.sqrt(r2)


```

C++17核心（与Python使用独立的随机样本对照全点对枚举）：

```cpp
#include <algorithm>
#include <cmath>
#include <iostream>
#include <random>
#include <vector>
struct P { long double x,y; };
P operator-(P a,P b){return {a.x-b.x,a.y-b.y};}
long double cross(P a,P b){return a.x*b.y-a.y*b.x;}
long double dist2(P a,P b){a=a-b;return a.x*a.x+a.y*a.y;}
std::vector<P> hull(std::vector<P> p){
  std::sort(p.begin(),p.end(),[](P a,P b){return a.x<b.x || (a.x==b.x && a.y<b.y);});
  p.erase(std::unique(p.begin(),p.end(),[](P a,P b){return a.x==b.x && a.y==b.y;}),p.end());
  if(p.size()<3)return p;
  std::vector<P> h(2*p.size());size_t k=0;
  for(P q:p){while(k>=2 && cross(h[k-1]-h[k-2],q-h[k-1])<=0)--k;h[k++]=q;}
  for(int i=(int)p.size()-2,t=(int)k+1;i>=0;--i){while(k>=(size_t)t && cross(h[k-1]-h[k-2],p[i]-h[k-1])<=0)--k;h[k++]=p[i];}
  h.resize(k-1);return h;
}
long double diameter2(const std::vector<P>& p){
  int n=(int)p.size(); if(n==0)throw std::runtime_error("empty polygon");
  if(n==1)return 0; if(n==2)return dist2(p[0],p[1]);
  int j=1;long double best=0;
  auto area=[&](int i,int k){return cross(p[(i+1)%n]-p[i],p[k]-p[i]);};
  for(int i=0;i<n;++i){
    int ni=(i+1)%n;
    while(area(i,(j+1)%n)>area(i,j))j=(j+1)%n;
    best=std::max({best,dist2(p[i],p[j]),dist2(p[ni],p[j])});
    long double a=area(i,j),b=area(i,(j+1)%n);
    if(std::abs(a-b)<=1e-12L*std::max(1.0L,std::abs(a))){
      best=std::max({best,dist2(p[i],p[(j+1)%n]),dist2(p[ni],p[(j+1)%n])});
    }
  }return best;
}

```

### 9.3 Q1-B：无界检查与交点枚举

以下使用SciPy线性规划检查有界性；默认变量范围已显式改成允许负坐标，避免把目标误限制在第一象限。LP与浮点顶点枚举仍需对近退化输入做数值复核。

```python
import numpy as np
from scipy.optimize import linprog
import itertools
# 复用9.2的cross、dot、hull。
def enumerate_region(planes):
    A=np.asarray([a for a,b in planes],float); b=np.asarray([b for a,b in planes],float)
    opts=dict(A_ub=A,b_ub=b,bounds=[(None,None),(None,None)],method='highs')
    feasible=linprog([0.,0.],**opts)
    if feasible.status==2: return 'EMPTY',[]
    if not feasible.success: raise RuntimeError(feasible.message)
    for obj in ([1,0],[-1,0],[0,1],[0,-1]):
        res=linprog(obj,**opts)
        if res.status==3: return 'UNBOUNDED',[]
        if not res.success: raise RuntimeError(res.message)
    vertices=[]
    for (a,b1),(c,b2) in itertools.combinations(planes,2):
        det=cross(a,c)
        if abs(det)<1e-12: continue
        q=((b1*c[1]-a[1]*b2)/det,(a[0]*b2-b1*c[0])/det)
        if all(dot(n,q)<=v+1e-7 for n,v in planes): vertices.append(q)
    if not vertices: raise RuntimeError('有界但未恢复顶点，需要高精度复核')
    return 'BOUNDED',hull(vertices)
```


## 10 附录B：Q2候选评分与松弛骨架

### 10.1 模块入口

Q2-A复用`choose_set`和9.2的扇形更新。`branches`必须同时枚举位置、接收半径及误差，包含no_signal；`radius_after`由具体场景更新函数提供。它是带明确回调接口的研究骨架，未给出连续最坏情形求解器。Q2-B使用`choose_fim`，只能评价给定的源场景；保证与名义候选不得混淆。Q2-C使用`relaxed_sensor_weights`，数值松弛返回后必须舍入、验可观测性并用精确区域复核。

```python
import math
import numpy as np
from scipy.optimize import minimize
def fim_increment(sensor,target,sigma_rad):
    d=np.asarray(target,float)-np.asarray(sensor,float); r=float(np.linalg.norm(d))
    if r<=5: return None  # near不能伪造为无限精度的bearing
    normal=np.array([-d[1],d[0]])/r
    return np.outer(normal,normal)/(sigma_rad*r)**2

def choose_fim(candidates,now,F,target_scenarios,sigma_rad,switch_cost=0):
    base=np.linalg.slogdet(F+1e-12*np.eye(2))[1]; scored=[]
    for s in candidates:
        cost=math.dist(now,s)/5+5+switch_cost; gains=[]
        for q in target_scenarios:
            inc=fim_increment(s,q,sigma_rad)
            # 保守半径1000；不可见/near由专用动作处理。
            if math.dist(s,q)>1000 or inc is None: gains.append(float('-inf'))
            else: gains.append((np.linalg.slogdet(F+inc+1e-12*np.eye(2))[1]-base)/cost)
        scored.append((min(gains),s))
    best=max(scored,key=lambda z:z[0])
    return None if not math.isfinite(best[0]) else best[1]

def choose_set(candidates,now,branches,radius_after,switch_cost=0,seconds_per_m=1.):
    # branches(s)须包含误差、位置、半径及no_signal的情景分支。
    # radius_after返回保守后验半径；有限情景评分并非连续最坏保证。
    def score(s):
        outcomes=list(branches(s))
        if not outcomes: return float('inf')
        return math.dist(now,s)/5+5+switch_cost+seconds_per_m*max(radius_after(z) for z in outcomes)
    return min(candidates,key=score)

def relaxed_sensor_weights(information_matrices,F0):
    # Q2-C：sum(w)=1，0<=w<=1的连续松弛；仅为数值候选基准。
    mats=np.asarray(information_matrices); k=len(mats)
    def objective(w):
        sign,logdet=np.linalg.slogdet(F0+np.einsum('i,ijk->jk',w,mats)+1e-10*np.eye(2))
        return -logdet if sign>0 else 1e100
    res=minimize(objective,np.ones(k)/k,method='SLSQP',bounds=[(0,1)]*k,
                 constraints=[{'type':'eq','fun':lambda w:np.sum(w)-1}],
                 options={'maxiter':100,'ftol':1e-8})
    if not res.success: raise RuntimeError(res.message)
    # 数值结果不等于经过认证的松弛上界；舍入后重新检查区域/接收约束。
    return res.x,int(np.argmax(res.x))
```


## 11 附录C：Q3状态机、频道与路径骨架

### 11.1 基准策略与客户端约定

下面`baseline`落实“先覆盖、再清除”的有限保底流程；高效第二/第三测点策略有明确插入位置，尚待团队实现与官方演练。`client.action`是必须补齐的协议适配层，不是现成可用于正式测试的客户端：必须维护当前位置和测向频道，检查accepted、保存最后有效virtual_time_s、实现同ID同内容重试、管理真实截止，并把反馈持久化。`clear`不得更新`client.channel`。骨架没有自动登录或启动正式测试功能。

实际研究文件为[路线骨架](C:/Users/30130/Desktop/数模/tmp/B_research/route_skeletons.py)，导入9.2对应的本地几何函数。本文代码块为方便逐路线审查的摘录，不需要在不同文件重复维护多套实现。

```python
import math
# 复用clip、wedge、hull、mec_oracle。
def ring7():
    return [(0.,0.)]+[(1500*math.cos(k*math.pi/3),1500*math.sin(k*math.pi/3)) for k in range(6)]

def grid121():
    seq=[(500*x,500*y) for y in range(-5,6)
         for x in (range(-5,6) if (y+5)%2==0 else range(5,-6,-1))]
    return [(0.,0.)]+[p for p in seq if p!=(0,0)]

def strip_clear_points(sensor,bearing_deg):
    theta=math.radians(bearing_deg); u=(math.cos(theta),math.sin(theta)); n=(-u[1],u[0])
    for row,y in enumerate((-20,0,20)):
        indices=range(76) if row%2==0 else range(75,-1,-1)
        for i in indices:
            yield (sensor[0]+20*i*u[0]+y*n[0],sensor[1]+20*i*u[1]+y*n[1])

def baseline(client,directional=False):
    # client.action须实现串行、截止、accepted检查、幂等重试和当前测向频道状态。
    # 调用前由用户在模拟器中准备演练；这里不会自动启动或登录。
    client.action('/enter')
    sources={}; cleared=set()
    for p in (grid121() if directional else ring7()):
        order=[client.channel]+[c for c in range(1,21) if c!=client.channel]
        for c in order:
            if c in cleared: continue
            feedback=client.action('/measure',position={'x':p[0],'y':p[1]},channel=c)
            result=feedback['measure_result']
            if result=='near':
                done=client.action('/clear',position={'x':p[0],'y':p[1]},channel=c)
                if done['clear_result']!='success':raise RuntimeError('near后清除失败，检查协议/状态')
                cleared.add(c)
            elif result=='direction':
                if c not in sources:
                    sources[c]={'first':(p,feedback['svd_deg']),
                                'poly':[(-1800,-1800),(1800,-1800),(1800,1800),(-1800,1800)]}
                for a,b in wedge(p,math.radians(feedback['svd_deg']),math.radians(1.005)):
                    sources[c]['poly']=clip(sources[c]['poly'],a,b)
                if not sources[c]['poly']:raise RuntimeError('观测区域为空')
            elif result!='no_signal':raise RuntimeError('未知检测结果')
    absent=set(range(1,21))-set(sources)-cleared  # 完整扫描后才有无源证书
    for c,state in sources.items():
        if c in cleared:continue
        poly=hull(state['poly']); center,radius=mec_oracle(poly)
        if radius<=19.9:
            ans=client.action('/clear',position={'x':center[0],'y':center[1]},channel=c)
            if ans['clear_result']=='success':cleared.add(c);continue
            raise RuntimeError('有保证的清除失败，需要回查数值/协议')
        # 可在此插入“有动作预算”的Q2第二/第三点策略；骨架先采用有限保底。
        for p in strip_clear_points(*state['first']):
            ans=client.action('/clear',position={'x':p[0],'y':p[1]},channel=c)
            if ans['clear_result']=='success':cleared.add(c);break
        if c not in cleared:raise RuntimeError('有限保底遍历后仍未清除')
    assert cleared|absent==set(range(1,21))
    return client.action('/exit')
```


### 11.2 Q3-B/C：开放路径与小规模策略树接口

`nearest_neighbor`与`open_two_opt`适用于已可清除的代表点集。`choose_action`仅实现评分选择，必须在调用前加入覆盖欠账的有限优先规则。`tiny_minimax`只用于极小离散模型，深度耗尽返回无穷避免把未完成当免费成功；没有以此求解官方问题。

```python
def nearest_neighbor(start,points):
    left=list(points); out=[]; now=start
    while left:
        q=min(left,key=lambda x:math.dist(now,x)); left.remove(q);out.append(q);now=q
    return out

def open_two_opt(start,route,max_passes=20):
    p=[start]+list(route)
    for _ in range(max_passes):
        delta=0.; move=None
        for i in range(1,len(p)-1):
            for j in range(i+1,len(p)):
                change=math.dist(p[i-1],p[j])-math.dist(p[i-1],p[i])
                if j+1<len(p): change+=math.dist(p[i],p[j+1])-math.dist(p[j],p[j+1])
                if change<delta-1e-9:delta,move=change,(i,j)
        if move is None:break
        i,j=move;p[i:j+1]=p[i:j+1][::-1]
    return p[1:]

def choose_action(actions):
    # 每个候选预先计算合法性、完整耗时与归一化收益；覆盖欠账强制策略另实现。
    legal=[a for a in actions if a['legal'] and a['seconds']>0]
    return max(legal,key=lambda a:a['gain']/a['seconds'])

def tiny_minimax(state,depth,actions,outcomes,terminal,transition,cost):
    if terminal(state):return 0.
    if depth==0:return float('inf')  # 未完成分支不能当作免费终止
    options=list(actions(state))
    if not options:return float('inf')
    return min(cost(state,a)+max(tiny_minimax(transition(state,a,z),depth-1,
                    actions,outcomes,terminal,transition,cost) for z in outcomes(state,a)) for a in options)
```


## 12 附录D：Q4增量骨架

### 12.1 多方位、全局网格及相容性

Q4-A使用`four_sided_points`，不满足证书条件时返回空列表，转全局/首次观测保底；Q4-B直接复用11.1的`grid121()`及`baseline(client, directional=True)`；Q4-C用`compatible`过滤场景。有限场景过滤器只作候选评价，不能承担连续空间不漏检的证明。

```python
# 复用math、sub、dot。
def four_sided_points(center,radius,rho=200.):
    if rho/math.sqrt(2)<=radius or rho+radius>1000:return []
    x,y=center
    return [(x+rho,y),(x,y+rho),(x-rho,y),(x,y-rho)]

def compatible(particle,sensor,feedback,eps_deg=1.005):
    # 粒子=(q,R,u)，u=None表示全向；假设该频道已确认存在且未清除。
    q,R,u=particle; delta=sub(sensor,q); distance=math.hypot(*delta)
    visible=distance<=R and (u is None or dot(u,delta)>=0)
    kind=feedback['measure_result']
    if kind=='no_signal':return not visible
    if kind=='near':return visible and distance<=5
    if not visible or distance<=5:return False
    true=math.degrees(math.atan2(q[1]-sensor[1],q[0]-sensor[0]))
    error=(true-feedback['svd_deg']+180)%360-180
    return abs(error)<=eps_deg
```

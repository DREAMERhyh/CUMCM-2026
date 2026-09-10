# B题当前核验状态

核验日期：2026-09-10 至 2026-09-11。Q1、Q2已完成本地验收；Q3、Q4完成offline验收但尚未接入官方模拟器。分题证据见 [`test_res_q1.md`](test_res_q1.md)、[`test_res_q2.md`](test_res_q2.md)、[`test_res_q3_offline.md`](test_res_q3_offline.md) 和 [`test_res_q4_offline.md`](test_res_q4_offline.md)。

## 已通过

- Python `unittest`：33项全部通过，包含原有22项回归、7项算法 testbench 和4项 CLI/产物 testbench。
- 旋转卡壳与全点对 oracle：固定种子20260910，共2000个随机凸包，直径在8位小数比较下一致。
- 解析与退化案例：3×4矩形、等边三角形反例、最长点对为边、空集、单点、线段、无界扇区与无界条带。
- 测向规则：正向 ±1° 扇区、跨0°、误差端点、同地重复观测不缩小区域。
- 不变量：显示范围不影响真实直径；整体平移不改变直径；新增相容观测后有界区域直径不增；求解器不读取源真值。
- 端到端：实测坐标及示向度输入、文本结果、JSON、PNG、SVG、非法输入拒绝均通过。
- 1°/1.005°敏感性：放宽误差界后可行区域没有缩小，示例直径由43.542596530 m增至43.760465680 m。
- `node --check code/visualization/app.js`：通过。
- `output/q1_demo.png`：完成目视核验；全局几何、局部定位区域、直径、直径圆和图例清晰，无裁切或重叠。

## Q1 结论核验

- 内置三测点示例得到6顶点有界区域，直径43.542596530 m；本例直径圆能够覆盖。
- 边长20的等边三角形直径为20 m，最小包围圆半径为11.547005384 m，大于直径圆半径10 m，因此不能覆盖。
- 两次测向四边形反例直径为63.250325289 m，直径圆最大超出0.153034491 m，最小包围圆半径31.625531267 m，因此不能覆盖。
- 由正例和反例确认：直径圆是否覆盖必须逐个区域检查；对一般凸定位区域不能恒称“能”。

## Q2至Q4核验摘要

- Q2：保守物理区域、有限候选、最坏后验半径评分、FIM基准、CLI、JSON和PNG均有专用testbench。
- Q3 offline：7点全向覆盖、228点有限清除保底、199秒计时例、幂等请求、协议负载和状态机有限终止已检查。
- Q4 offline：121点任意方向覆盖、四方向局部证书和定向状态机有限终止已检查。
- Q3/Q4尚无官方演练日志、真实RPC吞吐或正式测试成绩。

## 复核命令

在 `problem_b/` 下执行：

```powershell
python -B -m unittest discover -s code/tests -v
node --check code/visualization/app.js
python -B code/plot_cli.py --demo --no-show `
  --output output/q1_demo.png `
  --result-json output/q1_demo.json
python -B code/plot_cli.py --demo --no-show --output output/q1_demo.svg
```

## 已知限制

- 普通双精度加显式容差不是任意病态输入的形式化精确算术证书；极端近平行或尺度差异巨大时需要高精度复核。
- 半平面交采用小规模 `O(m³)` 枚举；最小包围圆采用 `O(n⁴)` 支撑圆 oracle，均以可审查性优先。
- 旧浏览器界面本次仅做 JavaScript 语法回归；完整浏览器交互不是当前 Q1 命令行入口的验收条件。

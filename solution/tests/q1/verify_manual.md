# Q1 人工验证步骤清单

本清单是改变 Q1 状态的唯一依据。AI 运行脚本只说明脚本可运行，不能代替人工验收。

## 1. 准备

在 `solution/` 目录安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 2. 分块单元测试

```powershell
python tests/q1/test_unit.py
python tests/q1/test_algorithms.py
python tests/q1/test_cli.py
```

期望：三个命令均以 `OK` 结束；CLI 测试生成的 JSON、PNG、SVG 均非空。任何异常、失败断言或非零退出码都算失败。

## 3. 三类数据与对拍

```powershell
python tests/q1/gen_data.py --mode random --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/random
python tests/q1/gen_data.py --mode boundary --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/boundary
python tests/q1/gen_data.py --mode adversarial --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/adversarial
```

期望：每次生成器打印用例数量；每次对拍最后打印“失败：0”和“全部检查通过”。若失败，保留对应 JSON 和完整终端输出。

## 4. 手算交叉核对

1. 半平面：检测点 `(0,0)`，示向 `0°`，误差 `1°`。允许方向应夹在 `-1°` 与 `+1°` 之间；人工抽查 `(100,0)` 满足两条约束，而 `(-100,0)` 不满足。
2. 矩形直径：顶点 `(0,0),(3,0),(3,4),(0,4)`，两条对角线长度都是 `sqrt(3²+4²)=5`。在 `test_unit.py` 对应断言中确认程序返回 5。
3. 等边三角形：边长 20，区域直径 20，直径圆半径 10；最小包围圆半径 `20/sqrt(3)≈11.547`，所以任取一条直径形成的圆不能覆盖第三个顶点。确认测试返回 `covers == false`。
4. 运行 `python src/q1/cli.py --demo --no-show --output output/q1_manual.png --result-json output/q1_manual.json`，人工查看图中检测点、射线、误差边界和定位区域与 JSON 顶点对应。

## 5. 记录与状态

- 将日期、执行人、运行命令、通过数量、失败详情和手算结果填入 `test_res.md`。
- 全部通过后，由人工将 Q1 状态改为【已验证】，并同步更新全局指南；AI 不得代为修改。
- 任一项失败则保持【待验证】，在 `test_res.md` 记录输入、实际输出、期望输出和复现命令。

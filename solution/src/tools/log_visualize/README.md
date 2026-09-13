# Q3/Q4 模拟器日志可视化

本组件只读取 `output/sim/q3_*.jsonl` 和 `output/sim/q4_*.jsonl`，根据文件名的 `q3_`/`q4_` 前缀切换界面模式，不会连接模拟器，也不会修改策略或日志。每一帧表示一个动作完成后的状态；第 0 帧表示尚未执行动作，右上角虚拟时间从 00s 开始。

在 solution/ 下运行指定日志：

~~~powershell
python src/tools/log_visualize/app.py output/sim/q3_20260912-023543-994488.jsonl
python src/tools/log_visualize/app.py output/sim/q4_20260912-225859-514262.jsonl
~~~

省略路径时自动选择 `output/sim/` 中最后修改的 Q3 或 Q4 日志：

~~~powershell
python src/tools/log_visualize/app.py
~~~

按钮支持上一步、下一步、重置和自动播放；Q3/Q4 自动播放均支持 1x、2x、4x、16x，其中 1x 每秒前进一个动作。键盘右/左方向键也可逐步播放，空格键切换自动播放。

无界面检查或导出某一帧：

~~~powershell
python src/tools/log_visualize/app.py output/sim/q3_20260912-023543-994488.jsonl --frame 124 --save-frame output/log_visualize/q3_last.png --no-show
~~~

## 图形语义

- 淡绿色圆：半径 1800 m 的源分布圆域。
- 黑色三角形：日志推导出的机器狗当前位置；三角形不表示朝向。
- 坐标视野：一次性按整份日志的机器狗轨迹扩展并保留边距；Q4 轨迹超出 1800 m 圆域时仍会完整显示，播放期间视野保持稳定。
- 橙色区域：截至当前动作，同一频道所有 direction 观测、最大接收距离和场地圆域形成的保守相交区域，几何参数与当前 Q3/Q4 定位逻辑一致。
- 蓝色星号：尚未清除源的估计点。
- 红色叉号：已经成功清除源的估计点。
- 细深蓝箭头：按成功清除发生顺序，连接上一个成功清除动作的实际目标坐标和当前成功清除坐标；第一次成功清除只有起点，从第二次开始出现箭头。

官方 JSONL 不含真实源坐标，所以蓝色星号与红色叉号都不能解释为真值。优先使用定位区域的最小包围圆中心；只有没有可用定位区域时，才使用 near 测点或成功清除位置。侧栏会持续显示这项限制。

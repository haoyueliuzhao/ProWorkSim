# CAL2轻量最终报告方法

新增`scripts/software_calibration_v051_cal2_final_report.py`只在r3宿主进入`complete`或`paused`且worker区间全部闭合后工作。当前准备不读取运行中结果，也不生成正式final。旧45MB r2阶段JSON、原两阶段报告、运行器结果和评分不修改、不重生成。

最终报告将已合并r1+r2阶段作为唯一前阶段费用来源，仅增加r3原七槽。原18逻辑槽中，只有parse-2/U与xmltodict两题的R/P/U可被新行替换；其余原未知、raw结果、环境无效性和固定交付口径原样保留。七槽如果再次暂停，未开始仍为not_started，不填失败。完整六题P−R、U−P仍因历史未知保持null，不能用raw固定交付0或失效环境下的raw代码0补齐。

报告只保存逐槽身份、raw/严格指标、状态、实际费用计数、测试观察计数、停止类别及原件path/SHA；历史完整行以阶段报告引用加JSON位置追溯。新worker报告引用绑定原生回包、测试和测量原件。不会再次嵌入整份旧阶段、监督器、native请求/回答、测试输出或大段测量正文。原四技术历史和R双历史层保留精确来源指针，不复制内容。

费用使用前阶段已独立闭合的2,904,643 token/275回包/3,842.5873663425446秒加r3唯一新工作；不能再加原首阶段227,876token。评分环境未知与实际费用是否闭合分开。CAL1不加入CAL2费用，worker内嵌时长不再叠加。

新增两个纯CPU控制一次通过：大段正文剔除后指标和精确来源仍保留，错误前阶段引用被拒绝；七槽唯一合并保持原未知、允许未开始状态、费用只加一次。2项通过（0.06秒），新文件范围Ruff通过，未重跑旧控制或任何真实模型/测试/分词。机器凭据：`artifacts/software-calibration-v051/cal2-final-report-controls/result.json`。

root确认r3终态后使用新输出前缀执行一次：

```bash
PYTHONPATH=src:. .venv/bin/python -m scripts.software_calibration_v051_cal2_final_report \
  --predecessor-report docs/experiments/software-calibration-v051-cal2-r2-stage.json \
  --r3-root runs/software-calibration-v051-cal2-r3 \
  --output-prefix docs/experiments/software-calibration-v051-cal2-final
```

目标已存在即拒绝覆盖。报告本身不执行HOLD资格、读取HOLD业务材料、prepare、launch、评分或模型调用，不释放任何后继。

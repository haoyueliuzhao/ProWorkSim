# 报告附件与复现说明

主报告为上级目录的 `software-organization-strategies-comparison-20261015.md`，同名HTML和PDF为可阅读导出。PNG供正文使用，SVG用于清晰缩放和再排版；四图只使用已保存实验结果。

## 数据

- `comparison-data.json`：v045、v047、v048的逐槽和配置数据、派生均值/配对差、原JSON字段指针与SHA。
- `historical-context.json`：v038、v044结果与制度信息，以及不纳入主排名的v039/v040背景。
- `strategy-catalog.json`：主要策略的制度、实际观察及解释范围，含协议/源码定位。
- `comparison-configurations.csv`：各版本独立的配置表，包含三个未设置的500k条件标记。
- `comparison-slots.csv`：v038/v045/v047/v048共100条唯一槽记录。它们不等于100个独立业务任务，不合并计算总排名。
- `assembly-checks.json`：唯一性、费用合计、缺设置与缺指标语义等必要文档检查，以及来源文件哈希。
- `quality-review.json`：数值、策略、历史范围和导出版式的复核记录。
- `manifest.json`：交付文件的相对路径、大小和SHA256，清单本身不纳入自身哈希。

CSV空值表示未设置、未报告或无对应事件，按status与字段定义区别，不是零。v045的Q未在原汇总中提供；`comparison-data.json`的Q覆盖统计unknown仅表示缺数值Q记录，不表示正式R技术未知。核心三份数据的正式R均完整已知。非Γ标记中的`vXXX_original`只表示该版本自身协议，不能当作v048的Γ0。

首次提交费用只对实际提交事件有定义；完整token包含所有失败、成员、阶段及提交后活动。所有图展示固定分母内的完整费用与结果，未设置配置不会画成0成功。显示舍入不改变JSON/CSV中的数值精度。

## 生成顺序

1. `extract-comparison-data.py --source-root <仓库> --output <新的分析目录>`只读三份已有最终JSON；本次已执行一次，成功产物直接归档。
2. `assemble-report.py`使用附件中的既有数据和`report-template.md`生成主Markdown、CSV及必要算术检查，不运行实验。
3. `render-report.py charts`生成四组PNG/SVG；`render-report.py render --markdown <主Markdown>`生成独立HTML和中文PDF。版本与本次渲染环境见`quality-review.json`。

实际文档渲染使用隔离的Python3.14依赖，包含Matplotlib、NumPy、Pillow、Markdown和ReportLab。中文使用系统Droid Sans Fallback，Latin/数字使用DejaVu；PDF嵌入字体，HTML图片内嵌，HTML来源链接指向报告分支中的对应文件。

本次汇总没有新增模型调用、训练、GPU worker、分词或业务验收。活动实验的两个源码工作区保持冻结；报告在独立`organization-strategy-report`分支保存。首次渲染存在依赖ABI及字体问题，修正后重导出，未据此修改实验数据或结果；过程日志保留在既有本地分析目录。

# v0.45原14槽接续启动记录

原14槽接续监督已于北京时间 **2026-10-11T09:08:57.366260+08:00** 启动，PID 4004655，冻结源码 `e62841df9a4672af3e98630f705f55c979b95bd1`，src树仍为 `944e4ae925423b62af54db5c5bd1bef8c5c7f7684ed23a89a533ae4c73035163`。这是启动快照，不能当成14槽已经执行或全部完成。

实际运行根为 `runs/software-organization-v045-complete-r1`，隔离源码目录 `runs/v045-complete-frozen-source`。监督和worker均使用原 `runs/v016-sdk/resident-venv/bin/python`（Python3.12），每槽仍恢复原完整common3/3、原初态和完整seed。原14清单、case配置和源码与准备计划精确相同；没有模型重采、旧成员恢复、旧预算转移、C/A或训练。

## 启动前失误与保留

首次生成plan时，工作目录未切到隔离源码目录，plan的source_root因此指向主工作区；代码是同一已提交字节，但目录绑定不符合隔离执行目的。当时根目录只有plan.json，无worker/episode。该plan及回执完整保存在 `runs/v045-complete-controls/source-root-preparation-01/`，随后从隔离目录重新生成计划。

首次09:05启动时，根代理命令误用项目 `.venv/bin/python`。宿主入口通过sys.executable派生worker，worker在from_candidate首个import torch即报缺依赖，尚未加载模型、创建episode或作实际调用。该运行 `runs/software-organization-v045-complete` 已终态，原14全未开始；其监督器、日志、停止和自动报告提交 `0ff4d18` 均保留。物理GPU4被分配的宿主进程生命期 **5.067300081秒** 单独计费，不伪称已加载common或模型驻留，也不抹去此成本。

更正仅是从独立新根使用原SDK解释器启动；冻结源码、资格、模型、病例、seed、顺序、预算和停止作用范围未更改。新启动回执绑定两个计划的assignments/cases/source一致及原失败根无episode，旧失败停止不覆盖。这不是重跑模型槽。

## 调度与归档

最多3个resident，仅物理GPU3/4/5/7，原容量稳定性及单任务保护保持；等待资源不等于实验终态。可信局部context/预算终止继续独立槽，真正完整性或测量未决暂停未开库存；原10槽仅作封存引用。

新增14上限7000000token、1792决定/attempt、448测试；旧10实际191调用/2563352token/19测试各计一次。最终成本将拆分原首槽、首次接续9、失败宿主5.0673秒与新接续实际工作，不能遗漏失败进程或把其算作一个模型样本。

费用/资源、输入来源/拒绝、反馈/工作三条只读审阅随新槽闭合增量执行，同一新槽只审阅一次并缓存。旧10不重新扫描191个模型输入；新审计和业务覆盖诊断不会进入模型提示。详细结果在终态后单独报告。

[启动机器快照](software-organization-v045-complete-launch.json) · [冻结协议](software-organization-v045-complete-protocol.md) · [CPU及只读准备](software-organization-v045-complete-preparation.md) · [审计补充](software-organization-v045-audit-original14-transition.md)

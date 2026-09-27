# v0.17 固定后继：H1结束后继续实际工作与在线学习

`scripts/continue_harness_v017.py`只实现本轮固定实验图，不接受任意job图、不提供重试或自动恢复。参数为 `--project` 项目目录、`--source` 已冻结且clean的H2源码树、`--output` 新目录。**必须从声明的冻结源码执行这个脚本**。启动时将源码commit、解释器原路径、复用launcher字节SHA、两份H1 launch位置、离线环境、素材路径、固定GPU分配和等待上限写入 `config.json`；每次子任务启动前重新核对同一clean commit和launcher SHA。

例如冻结源准备好后，可由一个独立会话运行：

```bash
/data1/zhuxinrui/projects/ProWorkSim/.venv/bin/python \
  /data1/zhuxinrui/projects/ProWorkSim/runs/frozen-v017-h2/scripts/continue_harness_v017.py \
  --project /data1/zhuxinrui/projects/ProWorkSim \
  --source /data1/zhuxinrui/projects/ProWorkSim/runs/frozen-v017-h2 \
  --output /data1/zhuxinrui/projects/ProWorkSim/runs/harness-v017-continuation
```

## 固定阶段

1. 只观察两模型的H1 launcher文件，等待真实end及整数exit_code；此时不读取部分成绩，也不根据部分分数调度。
2. 两进程均结束后，调用只读H1报告器，保存完整report和selection。没有selected时准确停止，不强行选模型。
3. 从真实selected的protocol_ref和原owner的base_identity取得模型、权重manifest和harness。调用冻结builder生成migration与pilot-planned。后继不恢复H1或迁移检查点。
4. 单次fresh migration（4训练+4新策略评价）与四项目评价（静态2例、明确变更2例）各用独立session并行；复用原 `runs/v015-launch/launcher.py` 保存真实子进程PID、退出、资源竞争与日志。
5. 只有migration进程确实结束、原report complete，才构造内存中的pilot准入候选并调用真实 `validate_h2_launch`。通过后才写新 `pilot-admitted.json`，保留原pilot-planned不变。校验失败则pilot不启动，失败原因独立保存；项目线继续。
6. fresh pilot执行原冻结64训练+48评价，不恢复migration权重，不选最佳检查点。迁移/主试验实际report及launch-protocol都存在时，调用H2只读报告器；缺少实际文件时明确记录skip原因。

进程exit0本身不等于阶段成功；`state.json`分别保留actual report status、exit code、文件SHA及是否实际启动。部署的8/112/4预定量不能当成已发生episode数量。

## 固定资源与过程独立性

| 选定模型 | migration与pilot | 四项目 | 每指定卡最小free |
|---|---|---|---:|
| Qwen3.5-9B | GPU0,1 | GPU2,3 | 65,536MiB |
| Qwen3.8-27B | GPU0,1,2,3 | GPU4,5,6,7 | 78,000MiB |

阈值依据既有长请求的9B约46GiB/卡、27B最大71.84GiB推理峰值及预声明余量。它不是反向训练容量证明；实际容量仍由这一次migration检查。模型/采样/容差不因结果临时改变。

每次资源判断保存原始 `nvidia-smi` GPU和计算进程输出，允许满足阈值时的小量竞争，不停止或抢占其他项目。查询不完整、卡不存在、free不足或未知时保持等待。每个等待资源的job最多48小时，轮询30秒。达到上限只结束observer，已启动的下游session不接收终止信号。一次资源检查不能保证其他项目之后不再使用显存；如实际运行失败，保留失败，不重试。

每job在启动前先持久化唯一launch intent，随后 `Popen(start_new_session=True)`。其生命周期不绑定交互会话或observer；observer被中断不取消下游。既有output、launcher日志或已记录attempt禁止再次启动。同样不自动恢复发生中断的observer，避免在不确定的launch边界重复采样；它的原state与独立launcher仍可供只读跟踪。

## 无GPU控制

`tests/test_continue_harness_v017.py`的5项控制覆盖：两H1真实退出守卫、两模型固定容量阈值及互斥lane、真实迁移validator通过前不落盘pilot、exit0不冒充实际stage成功、持久化单次intent和独立session/禁止重启。5项通过（0.05秒），Ruff通过。首次有1个夹具错误把目录枚举顺序当成稳定顺序，已改为比较文件集合；初始失败日志保留。这些控制没有读取实际GPU、加载模型或启动任何真实后继。

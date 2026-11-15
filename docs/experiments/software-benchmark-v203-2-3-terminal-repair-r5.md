# 公开测试故障修复及已锁定候选补评

2026年11月15日，用户明确选择保持累计130元上限，只补评已有候选，暂不重跑模型。最后未启动的Flask K1保持未运行；剩余额度31.25543296元不用于新模型调用。

## 根因与影响

11个已运行回合的首个公开测试RPC均报相同错误：找不到`/opt/pws-runtime/project/tools/public_test_execution_v175.py`。该路径在actor隔离封存时被正常移除。原留存适配器预加载调用为`load_base()`，真正测试调用为`load_base(None)`；`lru_cache`将两者视为不同键，测试时发生缓存未命中，重新打开已删除文件。

因此，末尾`sync_terminal`的“failed or closed internal transfer”是后续症状。公开测试反馈从第一次测试起就不可用，模型仍继续耗尽接近500万Token；原工程门只识别SDK故障，没有把这一传输故障阻止在后续模型调用之前。不能将本次低分解释为上下文策略或模型能力差异。

## 修订

新r5模块在进入缓存前统一规范化根路径，使省略参数、显式None和相同实际路径共用同一预加载对象；执行源和observer字节只在封存前读取。旧冻结源码保持原状。

新增控制器修订在每次工作机会后检查actor传输是否永久失败；失败立即结束该回合，阻止下一次模型调用。普通断言失败不使传输通道进入该状态，仍允许模型继续修复。

三项CPU控制通过：旧实现删除私有源后准确复现FileNotFoundError；新实现相同生命周期下真实pytest通过且原journal留存；故障／已关闭通道在下一次模型机会前被拒绝。新模块属于后续部署材料，本轮不恢复模型生成，也不宣称已完成新的真实模型环境准入。

## 补评边界

11份终态候选已在最终同步前由原控制器唯一锁定。逐份核对原锁、完整候选、树、绑定、补丁回读验证及原资源清理证据；不重新选择候选、不修补代码、不将其他成员的工作树代替member_001终态。

补评使用原先未消费的11个code-score资源，最多单路、每个4CPU／16GiB，沿用已通过的官方评分环境及Requests r4严格HTTP／TLS规则。评分请求单列`supplemental_locked_code_after_public_test_interface_failure`，另附新的候选准入说明；实际官方测试与resolved判定规则不变。补评不向模型反馈。

原生成状态继续保留technical_unknown。补评可以说明这些锁定代码是否通过官方验收，但不能把受损的求解过程改写成正常上下文对照；不据此宣称K0、K1或K2的优势。最后一题仍保留在原12回合计划中。

## 证据与状态

目录`artifacts/software-benchmark-v203-2-3/terminal-repair-r5/`保存11份来源清单、独立补评准入、锁定引用、评分请求清单及动态`progress.json`。旧1069次恢复批次API请求、旧费用和之前48次失败尝试均保留。评分产生CPU与网络测试成本，新增被测模型API费用为0。

修复模块为`software_public_test_retention_v203_2_3_r5.py`、`software_benchmark_public_test_evidence_v203_2_3_r5.py`及`software_benchmark_managed_actor_v203_2_3_r5.py`；后续控制器入口为`tools/run_role_context_controller_v203_2_3_r5.py`。补评单独使用`software_benchmark_supplemental_v203_2_3_r5.py`与`tools/run_role_context_supplemental_v203_2_3_r5.py`，没有绕过或覆盖旧正常生成状态。

## 补评完成结果

11份全部取得明确官方结果，8通过、3未通过、评分技术未知0；所有评分容器清理完成。

| 任务 | K0 | K1 | K2 |
|---|---|---|---|
| Astropy-13033 | 未通过 | 未通过 | 未通过 |
| SymPy-17655 | 通过 | 通过 | 通过 |
| Requests-1766 | 通过 | 通过 | 通过 |
| Flask-5014 | 通过 | 未运行 | 通过 |

三组共同已评分的三题上结果一致。Flask K1未运行，不能把K1的较少通过数解释为方法较差。所有分数仅是原锁定代码的补充验收，受损的测试反馈仍使正常上下文效果比较无效。

补评期间child账本请求数保持1069不变，新增模型调用0；含旧失败尝试累计费用上界98.74456704元，剩31.25543296元。最终来源、逐题评分和清理回执见同目录final-summary.json；可运行tools/summarize_role_context_repair_v203_2_3_r5.py查看区分后的状态。

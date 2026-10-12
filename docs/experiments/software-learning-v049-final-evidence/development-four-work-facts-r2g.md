# v049 原四槽 B 开发：r1＋r2g 只读合并

逐槽读取原件，原r1两DA只计一次，r2g只加入原两DB首次执行；旧r2为零worker等待及主动资源扩展停止，不占模型样本或GPU worker成本。DA2的正式结果、完整实际费用和完整四槽F_B均保持null。没有重新模型生成、分词、测试、验收、训练导出或读取.pt。

| 槽 | 阶段 | 状态 | R / Q | 完整回包 | 已知token | 账本扣账 | 测试 |
|---|---|---|---:|---:|---:|---:|---:|
| org49-dev-DA-s1-B | original_r1_retained_once | closed | 1 / 1.0 | 33 | 491926 | 491926 | 7 |
| org49-dev-DA-s2-B | original_r1_retained_once | technical_unknown_interrupted | None / None | 4 | 39347 | 52396 | 0 |
| org49-dev-DB-s1-B | r2g_original_unstarted_DB_first_execution | closed | 1 / 1.0 | 14 | 178399 | 178399 | 2 |
| org49-dev-DB-s2-B | r2g_original_unstarted_DB_first_execution | closed | 1 / 1.0 | 14 | 179838 | 179838 | 2 |

已保存完整回包费用合889510 token，账本扣账已知合902559，成员测试11。完整实际费用及F_B/Q_B仍null；DA2的不确定预约不能当作实际生成token。

GPU worker：原开发1338.457052230835秒只计一次；新r2g 516.901211977005秒；唯一开发合1855.35826420784秒。训练计算与采集费用不在这里重复相加。

反馈统计只覆盖已有正式测量的槽['org49-dev-DA-s1-B', 'org49-dev-DB-s1-B', 'org49-dev-DB-s2-B']：{'all_saved_feedback_units': 61, 'protocol_feedback_saved_exactly': 61, 'with_later_actual_generation': 55, 'presented_in_later_actual_generation': 55, 'presented_in_first_actual_followup': 55, 'without_later_actual_generation': 6}；无后继原因{'team_budget': 2, 'current_work_ended_no_reachable_event': 4}。缺少DA2完整反馈测量，四槽反馈分母保持null。

## 实际 GPU 调度与原资源守卫

实际候选物理卡：[0, 1, 2, 3, 4, 5, 6, 7]；继承原库存中的3457字面保持历史身份，实际调度以r2g资源协议、plan和worker-launch为准。
旧r2主动停止保留：interrupted，worker/调用/GPU worker秒均0；原signal15/KeyboardInterrupt与另存资源扩展回执并列，不回写旧异常分类。

- dev-B-DB-s1：物理GPU 0，UUID GPU-f813ce38-39d7-ab21-f72b-55f87284eaa5；实际launch与supervisor命令一致=True；保存资源样本38条，原资源stop原因[]，绑定问题[]。
- dev-B-DB-s2：物理GPU 1，UUID GPU-0a62363e-fb3c-74fd-c5fe-1a2720c7e66a；实际launch与supervisor命令一致=True；保存资源样本40条，原资源stop原因[]，绑定问题[]。

worker-launch中的requested r2命令是继承预启动意图；actual_command与supervisor进程身份记录真实r2g执行。资源汇总读取既有采样，不新调用GPU，也不将离散采样升级为连续无风险保证。

## org49-dev-DA-s1-B

起始步骤：{'actor_steps': 4, 'critic_steps': 4, 'policy_revision': 4}。
B绑定：{'branch': 'B', 'loaded_checkpoint_state_digest': 'ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39', 'declaration_sha256': 'bfce0ba9086b2d47b98a431964c3c22c8a84ca617da90d74488c082107867bbe', 'design_sha256': 'b3cbafdc71e4f13c0f1bef742e9f2c8f5a616ec4a351371a0d00f3626bcb28dd'}。
单槽guard：{'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}。
新DB保存的恢复/关闭回执摘要：None。
反馈：{'all_saved_feedback_units': 33, 'protocol_feedback_saved_exactly': 33, 'with_later_actual_generation': 31, 'presented_in_later_actual_generation': 31, 'presented_in_first_actual_followup': 31, 'without_later_actual_generation': 2, 'no_followup_reasons': {'team_budget': 2}, 'by_tool': {'claim_task': {'feedback_units': 1, 'presented_in_actual_generation': 1, 'no_followup_reasons': {}}, 'create_task': {'feedback_units': 1, 'presented_in_actual_generation': 1, 'no_followup_reasons': {}}, 'fix_patch': {'feedback_units': 2, 'presented_in_actual_generation': 1, 'no_followup_reasons': {'team_budget': 1}}, 'format_feedback': {'feedback_units': 3, 'presented_in_actual_generation': 2, 'no_followup_reasons': {'team_budget': 1}}, 'list_files': {'feedback_units': 1, 'presented_in_actual_generation': 1, 'no_followup_reasons': {}}, 'read_file': {'feedback_units': 7, 'presented_in_actual_generation': 7, 'no_followup_reasons': {}}, 'run_tests': {'feedback_units': 7, 'presented_in_actual_generation': 7, 'no_followup_reasons': {}}, 'submit_integration': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'write_file': {'feedback_units': 9, 'presented_in_actual_generation': 9, 'no_followup_reasons': {}}}}；分页：{'reports_saved': 7, 'reports_storage_verified': 7, 'reports_with_directory_presented': 7, 'reports_with_any_page_presented': 7, 'reports_historically_fully_presented': 0, 'verified_page_feedback_returns': 7, 'actual_page_read_requests': 0, 'page_read_outcomes': {}, 'continuation_reasons': {'not_requested': 7}}。
局部资源拒绝：{'team_budget': 2}；机械判断：continue。

最后固定交付：{'delivery_id': 'delivery-1', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v3'}, 'source_sha256': '8f3dc12644b4dd53ba7e90a42aebb7739f5a7547628489c24aae81e95d0085f9', 'files_sha256': 'e26cf48ba832a52f1ca01003aac52cb4536d4bff60d29f69046523049545379b', 'included_patch_ids': [], 'test_sequence': 10, 'message': 'Implemented exact signed credit apportionment with largest remainders. All public tests pass.'}。
原绑定测试事件：{'sequence': 10, 'kind': 'test', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v3'}, 'files_sha256': 'e26cf48ba832a52f1ca01003aac52cb4536d4bff60d29f69046523049545379b', 'source_sha256': '8f3dc12644b4dd53ba7e90a42aebb7739f5a7547628489c24aae81e95d0085f9', 'passed': True, 'executed': True, 'operation_id': 'command:9a07e95b77a3da48f5a4fbb82912ff29bc484e59c3038fc7c3cd8723bab6a33b', 'action_id': 'action-10'}。
原件没有完整候选采用事件；不据此推断所有语义伙伴信息均未使用。
采用、本人同树测试、原固定交付是文件动作事实，不自动等于交付收益或Contribution。

## org49-dev-DA-s2-B

起始步骤：{'actor_steps': 4, 'critic_steps': 4, 'policy_revision': 4}。
B绑定：{'branch': 'B', 'loaded_checkpoint_state_digest': 'ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39', 'declaration_sha256': 'bfce0ba9086b2d47b98a431964c3c22c8a84ca617da90d74488c082107867bbe', 'design_sha256': 'b3cbafdc71e4f13c0f1bef742e9f2c8f5a616ec4a351371a0d00f3626bcb28dd'}。
单槽guard：{'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}。
新DB保存的恢复/关闭回执摘要：None。
反馈：None；分页：None。
局部资源拒绝：None；机械判断：None。

保留原中断与第5attempt未知：39347完整回包token＋13049不确定预约，账本52396；单槽cleanup guard不证明可精确恢复第5生成，原正式结果和完整费用仍null。

## org49-dev-DB-s1-B

起始步骤：{'actor_steps': 4, 'critic_steps': 4, 'policy_revision': 4}。
B绑定：{'branch': 'B', 'loaded_checkpoint_state_digest': 'ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39', 'declaration_sha256': 'bfce0ba9086b2d47b98a431964c3c22c8a84ca617da90d74488c082107867bbe', 'design_sha256': 'b3cbafdc71e4f13c0f1bef742e9f2c8f5a616ec4a351371a0d00f3626bcb28dd'}。
单槽guard：{'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}。
新DB保存的恢复/关闭回执摘要：{'loaded_branch': 'B', 'loaded_steps_as_saved': {'actor': 4, 'critic': 4}, 'loaded_checkpoint_matches_plan_reference': True, 'loaded_state_sha_matches_original_B': True, 'serialized_reload_exact_as_saved': True, 'evaluation_flags_as_saved': {'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}, 'frozen_collection_close_status': 'evaluation_only_no_learning_computation', 'frozen_collection_training_happened': False, 'frozen_collection_actor_steps': 0, 'frozen_collection_critic_steps': 0, 'scope': 'Read saved JSON restoration and guard receipts; no checkpoint tensor reload/comparison. Missing fields remain null, and cleanup guards do not make DA2 a closed episode.'}。
反馈：{'all_saved_feedback_units': 14, 'protocol_feedback_saved_exactly': 14, 'with_later_actual_generation': 12, 'presented_in_later_actual_generation': 12, 'presented_in_first_actual_followup': 12, 'without_later_actual_generation': 2, 'no_followup_reasons': {'current_work_ended_no_reachable_event': 2}, 'by_tool': {'fix_patch': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'read_file': {'feedback_units': 4, 'presented_in_actual_generation': 4, 'no_followup_reasons': {}}, 'replace_file': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'run_tests': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'staff_done': {'feedback_units': 2, 'presented_in_actual_generation': 0, 'no_followup_reasons': {'current_work_ended_no_reachable_event': 2}}, 'submit_integration': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}}}；分页：{'reports_saved': 2, 'reports_storage_verified': 2, 'reports_with_directory_presented': 2, 'reports_with_any_page_presented': 2, 'reports_historically_fully_presented': 0, 'verified_page_feedback_returns': 2, 'actual_page_read_requests': 0, 'page_read_outcomes': {}, 'continuation_reasons': {'not_requested': 2}}。
局部资源拒绝：{}；机械判断：continue。

最后固定交付：{'delivery_id': 'delivery-2', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v2'}, 'source_sha256': 'c90d23bfb0418d0d2b57a1de6ae4ab0cddbc373738ba73dff32ffeb45a2d947c', 'files_sha256': '70730199719c1ac19e0a6fa7471cf5af57ad01a13db6d89dceb7becec011153b', 'included_patch_ids': [], 'test_sequence': 9, 'message': 'Fixed plan_jobs to properly batch jobs up to max_parallel instead of processing one at a time'}。
原绑定测试事件：{'sequence': 9, 'kind': 'test', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v2'}, 'files_sha256': '70730199719c1ac19e0a6fa7471cf5af57ad01a13db6d89dceb7becec011153b', 'source_sha256': 'c90d23bfb0418d0d2b57a1de6ae4ab0cddbc373738ba73dff32ffeb45a2d947c', 'passed': True, 'executed': True, 'operation_id': 'command:ab76b166542d9395b3fa8f1496b53d9b6d9956a55bed6b2b70cfbd34870924ce', 'action_id': 'action-9'}。
原件没有完整候选采用事件；不据此推断所有语义伙伴信息均未使用。
采用、本人同树测试、原固定交付是文件动作事实，不自动等于交付收益或Contribution。

## org49-dev-DB-s2-B

起始步骤：{'actor_steps': 4, 'critic_steps': 4, 'policy_revision': 4}。
B绑定：{'branch': 'B', 'loaded_checkpoint_state_digest': 'ff8c828bcc475132d6d6bbddad3a114da62ace9da9c905e560d7d7c5a3cefc39', 'declaration_sha256': 'bfce0ba9086b2d47b98a431964c3c22c8a84ca617da90d74488c082107867bbe', 'design_sha256': 'b3cbafdc71e4f13c0f1bef742e9f2c8f5a616ec4a351371a0d00f3626bcb28dd'}。
单槽guard：{'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}。
新DB保存的恢复/关闭回执摘要：{'loaded_branch': 'B', 'loaded_steps_as_saved': {'actor': 4, 'critic': 4}, 'loaded_checkpoint_matches_plan_reference': True, 'loaded_state_sha_matches_original_B': True, 'serialized_reload_exact_as_saved': True, 'evaluation_flags_as_saved': {'learning_unchanged': True, 'rng_restored_exactly': True, 'software_binding_unchanged': True, 'actor_identity_unchanged': True}, 'frozen_collection_close_status': 'evaluation_only_no_learning_computation', 'frozen_collection_training_happened': False, 'frozen_collection_actor_steps': 0, 'frozen_collection_critic_steps': 0, 'scope': 'Read saved JSON restoration and guard receipts; no checkpoint tensor reload/comparison. Missing fields remain null, and cleanup guards do not make DA2 a closed episode.'}。
反馈：{'all_saved_feedback_units': 14, 'protocol_feedback_saved_exactly': 14, 'with_later_actual_generation': 12, 'presented_in_later_actual_generation': 12, 'presented_in_first_actual_followup': 12, 'without_later_actual_generation': 2, 'no_followup_reasons': {'current_work_ended_no_reachable_event': 2}, 'by_tool': {'fix_patch': {'feedback_units': 1, 'presented_in_actual_generation': 1, 'no_followup_reasons': {}}, 'list_files': {'feedback_units': 1, 'presented_in_actual_generation': 1, 'no_followup_reasons': {}}, 'read_file': {'feedback_units': 3, 'presented_in_actual_generation': 3, 'no_followup_reasons': {}}, 'replace_file': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'run_tests': {'feedback_units': 2, 'presented_in_actual_generation': 2, 'no_followup_reasons': {}}, 'staff_done': {'feedback_units': 2, 'presented_in_actual_generation': 0, 'no_followup_reasons': {'current_work_ended_no_reachable_event': 2}}, 'submit_integration': {'feedback_units': 3, 'presented_in_actual_generation': 3, 'no_followup_reasons': {}}}}；分页：{'reports_saved': 2, 'reports_storage_verified': 2, 'reports_with_directory_presented': 2, 'reports_with_any_page_presented': 2, 'reports_historically_fully_presented': 0, 'verified_page_feedback_returns': 2, 'actual_page_read_requests': 0, 'page_read_outcomes': {}, 'continuation_reasons': {'not_requested': 2}}。
局部资源拒绝：{}；机械判断：continue。

最后固定交付：{'delivery_id': 'delivery-1', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v2'}, 'source_sha256': 'c90d23bfb0418d0d2b57a1de6ae4ab0cddbc373738ba73dff32ffeb45a2d947c', 'files_sha256': '70730199719c1ac19e0a6fa7471cf5af57ad01a13db6d89dceb7becec011153b', 'included_patch_ids': [], 'test_sequence': 5, 'message': 'Fixed plan_jobs to respect max_parallel limit. Changed batch = ready[:1] to batch = ready[:max_parallel]. All public tests now pass.'}。
原绑定测试事件：{'sequence': 5, 'kind': 'test', 'actor_id': 'member_001', 'source_reference': {'object_id': 'obj-c567f5b9c7d905481548e89b', 'version_id': 'v2'}, 'files_sha256': '70730199719c1ac19e0a6fa7471cf5af57ad01a13db6d89dceb7becec011153b', 'source_sha256': 'c90d23bfb0418d0d2b57a1de6ae4ab0cddbc373738ba73dff32ffeb45a2d947c', 'passed': True, 'executed': True, 'operation_id': 'command:19bf3b1693c3b82a181c931f5bff8e8d33ed14ea56a6e6b4d3f4ceb48396bf12', 'action_id': 'action-7'}。
原件没有完整候选采用事件；不据此推断所有语义伙伴信息均未使用。
采用、本人同树测试、原固定交付是文件动作事实，不自动等于交付收益或Contribution。

完整四槽结果缺证，不能以已知成功子集宣称F_B=1或学习改善。源文件SHA、每次采用前后/来源整文件树凭据、原同树测试与实际反馈呈现细节保留在JSON。

# 模块与边界验证

所属领域 AI/ML，子方向 传统ML。

## 功能模块

| 序号 | 模块 | 职责 | 实现 | 测试 |
| --- | --- | --- | --- | --- |
| M1 | pallet_custody | 单据接入与时点裁决 | `src/redocket/pallet_custody/service.py` | `tests/test_pallet_custody.py` |
| M2 | route_age | 业务特征与时点档案 | `src/redocket/route_age/service.py` | `tests/test_route_age.py` |
| M3 | return_survival | 训练、估计与时距概率 | `src/redocket/return_survival/service.py` | `tests/test_return_survival.py` |
| M4 | censored_replay | 时间回放与核验 | `src/redocket/censored_replay/service.py` | `tests/test_censored_replay.py` |
| M5 | lane_population | 群组偏移与可信分派 | `src/redocket/lane_population/service.py` | `tests/test_lane_population.py` |
| M6 | retrieval_slots | 业务锁与资源分派 | `src/redocket/retrieval_slots/service.py` | `tests/test_retrieval_slots.py` |
| M7 | deposit_manifest | 逐单证据与资源守恒 | `src/redocket/deposit_manifest/service.py` | `tests/test_deposit_manifest.py` |
| M8 | custody_release | 版本登记与追溯 | `src/redocket/custody_release/service.py` | `tests/test_custody_release.py` |

## 易错边界

| 用例 | 业务后果 | 处理位置 | 验证位置 |
| --- | --- | --- | --- |
| TRAP-14 | 同版本异值隔离，较旧修订不能复活 | `src/redocket/pallet_custody/service.py` | `tests/test_pallet_custody.py::test_conflicting_revision_is_quarantined` |
| TRAP-19 | 业务锁优先，未获准的单据不消耗资源 | `src/redocket/retrieval_slots/service.py` | `tests/test_retrieval_slots.py::test_prohibited_entries_never_spend` |
| TRAP-26 | 使用过期版本登记被拒，保留前次结果 | `src/redocket/custody_release/service.py` | `tests/test_custody_release.py::test_stale_generation_keeps_prior` |
| TRAP-32 | 零方差业务特征仍有有界尺度 | `src/redocket/route_age/service.py` | `tests/test_route_age.py::test_zero_variance_uses_unit_scale` |
| TRAP-42 | 训练冻结后到达的单据或回执不会回填 | `src/redocket/route_age/service.py` | `tests/test_route_age.py::test_future_and_late_measurements_do_not_fit` |
| TRAP-43 | 训练与独立回放的单据按时段隔离 | `src/redocket/censored_replay/service.py` | `tests/test_censored_replay.py::test_holdout_separates_ordered_periods` |
| TRAP-44 | 稀疏或常量参考出现越界值时拦住自动分派 | `src/redocket/lane_population/service.py` | `tests/test_lane_population.py::test_constant_distribution_detects_outside` |
| TRAP-53 | 同批重排仍得到相同证据和决策 | `src/redocket/deposit_manifest/service.py` | `tests/test_deposit_manifest.py::test_report_is_permutation_invariant` |
| TRAP-54 | 单笔推理与合并调用的结果一致 | `src/redocket/return_survival/service.py` | `tests/test_return_survival.py::test_score_is_batch_invariant` |
| TRAP-55 | 只看在途回执不能判「两天内没回」，删失需满窗口 | `src/redocket/return_survival/horizon.py` | `tests/test_horizon_rules.py::test_censor_only_proves_absence_when_window_is_covered` |
| TRAP-56 | 线路样本不足借全场，全场不足转人工且不占车位 | `src/redocket/return_survival/horizon.py` | `tests/test_horizon_rules.py::test_thin_lane_borrows_overall_then_falls_back_to_manual` |
| TRAP-57 | 概率严格过半才派单，舍入不改派单资格 | `src/redocket/return_survival/horizon.py` | `tests/test_horizon_rules.py::test_probability_over_half_uses_exact_arithmetic` |
| TRAP-58 | 快照日已确认归还不占位，晚到归还不改当班 | `src/redocket/pallet_custody/service.py` | `tests/test_horizon_rules.py::test_snapshot_return_withdraws_but_late_return_does_not` |

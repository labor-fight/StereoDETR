# 零 GPU 实施会话收据(2026-08-31,session f223df)

前情:同日的根因判决报告(oracle 分解定位排序/深度/样本三层瓶颈,EpiTube4D-R 四机制
方案)。本会话执行其中全部零 GPU 项。运行时证据 NDJSON 在
`StereoDETR/.cursor/debug-f223df.log`(session f223df)。

## 1. oracle-after-OERD 探针(新测量,DIAGNOSTIC ONLY)

工具 `.epitube4d/tools/ep4d_evidence/oracle_after_oerd.py`,收据
`.epitube4d/reports/ep4d_evidence/rescore/ORACLE_AFTER_OERD.json`。定义:
**视图受限 oracle** = 冻结官方视图 pickle 的同一批框,分数替换为同类最大有向 3D IoU
(c2 `_oracle_rescored` 语义),冻结评测器打分。预注册假设先于任何 AP 读数写入日志。

| 框集 | Veh oracle | Ped oracle |
|---|---:|---:|
| A3 control | 9.0772 | 4.2193 |
| A3 + OERD 深度修正 | 9.0772(逐位同) | **6.6329(+2.414)** |
| R1 control | 10.8749 | 2.1218 |
| R1 + OERD | 10.8749(逐位同) | **4.1474(+2.026)** |

裁决(预注册门):

- **H_A CONFIRMED**:OERD 不只是修排序,它把行人天花板抬升 +2.41(gate ≥+0.40)。
  行人达标(3.6448)所需排序效率从"擦线"变为 3.6448/6.633 = **0.55**——恰为车辆侧
  已实现的效率(0.549)。此前"行人 margin 仅 0.008"的担忧解除。
- **H_D CONFIRMED ×2**:车辆 oracle 在两组 control/OERD 间逐位相等(OERD 只动行人),
  装置健康。`oriented_iou_3d` 恒等/旋转恒等/不相交自检先行通过。
- **H_B 人工降级为 INCONCLUSIVE(定义混杂)**:收据 JSON 内的机械判定"CONFIRMED"
  不可引用。原因:视图受限 oracle(A3 Ped 4.219)**高于** c2 全候选 oracle 旧收据
  (3.653),而前者在同一评测口径下应为后者的下界——两把尺子至少有一处口径差
  (最可能:c2 `_official_ap` 的下游对 IoU 值分数复加 0.1 阈值,或评测包装不同)。
  **两收据间的 oracle 数字不可跨引;本探针内的配对读数(同定义/同工具/同评测器)
  不受影响。** 后续引用 oracle 一律注明"视图受限(f223df 口径)"或"c2 口径"。

## 2. 台账取证对方案的三处修正(载荷性)

1. **C68/C70(D1)**:稠密一对多辅助头已跑过并 FAIL(行人升、Veh oracle 10.04<11.39,
   稠密 cls 头挤占共享主干一半梯度),无复活条款 → ARM-SCORE v1 中该组件撤回。
2. **P1 梯度审计**:"正样本饥饿"被证伪(每 GT 恰 11 匹配 query,两类供给一致,
   分配线关闭)→ RECIPE_DIFFERENTIAL 差分表第 1 项的机制解释不可再引用为动机。
3. **C41 + 既有基建**:自由融合 quality 头有死刑前科;而**对齐式 3D IoU 质量目标已
   实现在库**(`hybrid_matcher.py::IoUAwareLabelLoss`,`quality_metric: "iou_3d"`,
   按类门控 + `bind_geometry`)→ ARM-SCORE 变成纯配置臂,零新代码。

## 3. 实现落账

- **QC-EER 模块(ARM-EVIDENCE, M1)**:`.ep4d_q1/lib/models/event4d/qc_eer.py` 新建;
  `stereodetr_voxel_event.py`(wrapper 层接线,+qc_eer 参数)与
  `build_voxel_event.py`(`model.qc_eer` 门控构造)最小改动。缺省关闭 = 冻结路径
  逐字节不变。梯度只进 gate/offset 头;测量量全 detach;零初始化位移 <0.05 m。
- **测试**:新增 `tests/event4d/test_qc_eer_contract.py` 6 项(含视差列序功效臂:
  u_right = u_left − d,翻转方向必须打不出峰)。回归:`tests/event4d/` 453 passed /
  19 skipped / 2 xfailed;唯一 error 为 `test_flags_off_parameter_count_is_the_a0plus_one`
  在 CUDA 屏蔽下的环境性失败,GPU0 复跑该文件 **18/18 全过**(冻结参数量未动)。
  Lint 零问题。
- **预注册**:`ARM_SCORE_PREREG_DRAFT.md` 重写为 v2(对齐式 3D 质量目标纯配置臂,
  含 C.4 的 train 侧饱和对照义务与 C41 同款自动删除条款);
  `ARM_EVIDENCE_PREREG_DRAFT.md` 更新实现落账(v1 不含融合/quality 监督,P7 另行
  预注册);`ARM_TIME_PREREG_DRAFT.md` 维持"入场条件 = 前两臂至少一 PASS,本轮不实现"。
- **H4 尾部补测**:命令文档 `reports/ep4d_debug/H4_TAIL_BACKFILL_COMMANDS.md`
  (两条短 GPU 命令,待窗口)。

## 4. 运维注记

- 本日早间按用户指令清场:Q12 训练止于 ~e013(e012 checkpoint 与评测在盘),
  `q13_when_free.sh` 自动接力与 anneal 链已杀——**Q13 需手动发车**;Q12/Q13 的
  matched-epoch 配对在 e012 之后断裂。
- GPU 主臂序(恢复训练后):Q13(手动发车,唯一变量=深度修复包)→ ARM-SCORE
  (配置臂,发车前先跑 §2 的 train 侧饱和对照)→ ARM-EVIDENCE(qc_eer.enabled)
  → 视裁决进 ARM-TIME / P7 / 终局合成(胜者 + OERD 推理组件,多 seed)。

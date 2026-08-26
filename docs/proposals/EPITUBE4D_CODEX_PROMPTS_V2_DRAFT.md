# EpiTube4D：Codex 逐阶段执行提示词 v2（debug 审计修订版，待负责人确认）

> **v2.1 指针（2026-08-26）**：主控文档已升级为同目录
> `EPITUBE4D_EXECUTION_PLAN_V2_DRAFT.md`（Runbook v2.1 重组版）。该文新增
> Phase 0.5、七处避坑补丁（P2 装置修复前置、P6 实现 checklist、P7 C65 前置、
> C70 审计、运维三条、oracle×效率口径）、C01–C82 避坑矩阵与战略判定；
> 与本文冲突处以 v2.1 为准。本文各 Prompt 的门数值不变。

**修订依据**：debug session `5fd9ba` 对 v1 计划的逐条运行时审计（证据
`.cursor/debug-5fd9ba.log`，7 条 NDJSON；审计脚本 `/tmp/epitube4d_plan_audit.py`
可复跑）、`reports/repo_contract.md`（R0）、`docs/proposals/` 六份草稿。
本文件是草稿，不直接修改 `docs/EXPERIMENTS_AND_PITFALLS.md`。

## v1 → v2 修订清单

| # | v1 的问题 | 证据 | v2 处置 |
|---|---|---|---|
| 1 | Prompt 0 重做 R0 已完成的审计，且"R1 重评 ≤0.05 AP"按字面永不可满足（`epoch_012.pth` 永久丢失、远端恢复已关闭） | repo_contract §7.2/§8：`PASS_WITH_ONE_MISSING_ARTIFACT`，R1 只作数字基线；`p0_reeval_r1.py evaluator` 84/84 字段 1e-9 复现 | Prompt 0 改写为"核验并继承"，三条冻结入口写死实际路径 |
| 2 | v1 不知道 A1–A3 臂与 C76–C82 草稿（2026-08-24~26） | 日志 GAP1：A3 判 KILL；C76–C82 全部未合入账本 | 阅读清单与约束继承表补全；Phase 1 改为复核；Phase 2 前提改写；Phase 6/7 吸收 C82 打分结论 |
| 3 | 缺执行层环境纪律 | repo_contract §3、C80/C81 草稿 | 全局规则 2–7 |
| 4 | 分支落点未写死 | 日志 H1_H2/H5：研究代码在 `9446413`，`lib/models/epitube4d/` 命名空间零冲突 | 全局规则 1 |
| 5 | 对应性探针真值定义缺失（会复发 C76 缺陷） | C76 草稿：中心视差真值制造了 D2 全部反直觉模式 | 全局规则 10；Phase 1/2 探针强制 8 角点表面带真值 |

v1 的十条全局纪律（/tmp 脚本、不新增 gate JSON、未过门即停删未授权文件、
不覆盖旧 baseline、不改 frozen evaluator、不做无关重构、每次结果追加
SHA/dirty/manifest hash/config hash/完整命令/TSV/PASS-FAIL）**全部保留**，以下为新增。

## 全局执行规则（v2 新增，每个 Prompt 默认继承）

1. **开发树落点**：`git worktree add -b epitube4d-dev /data1/lyq/code/.epitube4d 9446413`。
   研究基础设施（dsec3dod 数据合同、冻结评测器、monodetr 主干、`train_event4d.py`）
   都在 `9446413`（`epst4d-archive` 分支保护）。不动 `main`、不动 `.epst4d_*` 三棵树；
   不从 A3 配方（已 KILL，见 C82 草稿）出发。文档写的 `src/models` 一律读作 `lib/models`。
2. **解释器**：`/data1/lyq/miniconda3/envs/stereodetr/bin/python`（Python 3.8，
   torch 2.1.2+cu118）。裸 `python` 无 torch。
3. **numba CUDA 陷阱**（repo_contract §3.1）：非交互 shell 里 numba CUDA 段错误。
   评测一律走子进程 worker（`official_eval_worker.py`）；不要用 torch 探针替代 numba 探针。
4. **单进程 GPU 工具调用约定**（C80 草稿，已在生产路径验证）：
   `CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<nvidia-smi编号> … --device cuda:0`。
   禁止把非 0 的 `cuda:N` 传进任何冻结工具。
5. **工作区外的树**（`.epitube4d` 等）：命令一律非沙箱 + 内嵌 `cd <绝对路径>`；
   watcher/轮询只用绝对路径（C81.2 草稿）。
6. **训练成败判据**（C81.3 草稿）：`training_log.jsonl` 的 `epoch_summary`
   （epoch == max_epochs）**且** checkpoint 落盘；`train.log` 尾部与 shell 退出码
   不作判据。同一 config 不排双份 `wait_and_train`。长任务按"可被随机杀"设计
   （收据幂等、流式进度日志）；重投前 `nvidia-smi` 确认无 `ERR!` 卡（C81.1）。
7. **被 `source_sha256` 锁定的 config 连注释都不可改**（C75）。
8. **数据入口**：manifest `records.jsonl`（SHA256 `b2afa842…`，53,578 query，
   135,886,083 字节）是唯一数据入口；其实体在主树 untracked 的
   `lib/datasets/dsec3dod/manifest/`（事件树 symlink 目标）。清理主树或换机前先从
   `/data1/lyq/stereodetr_docs_backup_20260824/` 恢复（repo_contract §4）。
9. **R1 身份裁决**（repo_contract §8，永久生效）：`epoch_012.pth` 丢失且远端恢复
   路线已关闭，**不要再查**。R1 只作数字基线（strict 6.2552/0.1896、loose
   25.2045/1.5205、2D 16.1715/5.7552，由预测 pickle + 冻结评测器精确复现）。
   不得声称任何权重与 R1 原 artifact 同一；需要权重起点时用 `epoch_011.pth`
   （674/674 键 strict 加载已验，18,405,547 参数）并显式标注是第 11 个 epoch。
10. **对应性探针真值纪律**（C76 草稿）：任何立体对应/匹配探针的真值一律取
    8 角点投影视差带 `[fB/z_far_corner, fB/z_near_corner]±容差`，**禁止 box 中心
    视差**（中心真值在 10m 处偏差 8px+，正是 D2 0.3590 反直觉模式的来源）。
    同时继承 C71–C74：计数单位与阈值同冻结；正负对照同报且都在留出集评分；
    禁止概率巧合断言；fixture 对齐合同语义而非 shape。
11. **草稿约束的地位**：C76–C82 尚未合入账本（`docs/proposals/` 六份草稿），
    本计划按已生效约束执行；负责人合入时若有改动，以合入版为准。

---

## Prompt 0 v2：核验并继承已裁决的仓库合同（不重做审计）

```text
你在 StereoDETR 项目工作。先不要改任何模型代码。

前置事实（已由 reports/repo_contract.md 与 debug 审计 5fd9ba 固化，禁止重新发现、
禁止重查）：
- 主树 /data1/lyq/code/StereoDETR@main 只有 RGB/KITTI legacy + 文档/收据/审计探针；
- 全部事件研究代码在提交 9446413（epst4d-archive 分支保护；另有 .epst4d_r1 /
  .epst4d_r1a_frozen / .epst4d_v3 三个 worktree，一律不动）；
- R1 的 epoch_012.pth 永久丢失、远端恢复路线已排查关闭（repo_contract §7.2）；
- A3 臂已判 KILL（C82 草稿），其配方不得作为起点；
- tests/episet4d/test_p0_receipt_contract.py 的 13 项 error 是已知已归因状态
  （唯一原因 = epoch_012 缺失），不得读作回归。

严格执行：

1. 只读核验（不训练、不写 tracked 文件）：
   a. git worktree list、git status --short、git rev-parse HEAD；
      确认 9446413 仍被 epst4d-archive 引用；
   b. 重算并比对 repo_contract §2 的身份 hash：评测器 4 文件 +
      g0_official_protocol.yaml（5/5 fingerprint）、manifest records.jsonl
      （b2afa842…，135,886,083 字节）、dsec_infos_val.pkl（1df3ba49…）；
   c. 通读 docs/EXPERIMENTS_AND_PITFALLS.md（6777 行冻结账本）、
      reports/repo_contract.md，以及 docs/proposals/ 全部六份草稿：
      A1_A2_RESULTS、A3_RESULTS、C76_C77、C78_C82、SEIT_PREREG、P2B_PREREG。
      提取并打印：三基线冻结数字、C13/C14/C19/C22/C47/C52/C55/C59/C68/C69/
      C71–C75 约束、草稿 C76–C82 约束、防复活规则清单。

2. 三条冻结重评入口（全部无需训练、无需 GPU identity 验证）：
   a. R1：python tools/episet4d/p0_reeval_r1.py evaluator --output-dir <tmp>；
      要求 84/84 字段 1e-9 内一致（含 6.2552/0.1896 等六门字段）；
   b. D1：核对 9446413 上 tracked 的 reports/episet4d/d1_dense/ 收据链与
      /data1/lyq/rep4d_archive/episet4d_d1_20260823/prune_manifest.tsv 的 hash；
      对照冻结数字 5.4986/0.7787；
   c. EvStereo3D：核对 tracked 收据 reports/g0_official_protocol/
      20260811_g0_official_v1/evstereo3d_pinned_result.json 的 8.0215/3.6448；
      确认竞品库 /data1/lyq/code/Ev-Stereo3D 在位。

3. 创建开发树：git worktree add -b epitube4d-dev /data1/lyq/code/.epitube4d 9446413。
   原目录与三棵既有 worktree 一律不动。

4. 在开发树新建 docs/EPITUBE4D_EXECUTION_LOG.md，登记：代码/数据/评测三方身份、
   三条入口的复现读数、继承约束清单、允许复用资产（manifest、标定、冻结评测器、
   monodetr 主干 utility、train_event4d.py/eval_event4d.py 入口、tools/r1_audit
   两个留档探针）、主树两个 untracked 目录（lib/datasets/dsec3dod/ 是 manifest
   实体，tools/epst4d_v3/ 属 A 系列）的性质与保护要求。

5. 临时脚本只写 /tmp/epitube4d_phase0_audit.py；不向仓库添加测试/工具文件。

PASS：hash 全一致 + R1 精确复现 + D1/EvStereo3D 数字可追溯 + tests/dsec3dod
84 项合同测试通过 + 约束清单落档。
FAIL：任何 hash 漂移或复现失败 → 停止，先修身份，不创建 EpiTube4D 文件。

最后只输出：核验结论、PASS/FAIL、下一阶段唯一允许命令。不要开始 Phase 1。
```

---

## Prompt 1 v2：标定复核（非重做）+ intensity 正控制

```text
只执行 EpiTube4D Phase 1。不要训练 detector，不写 event state，不写 epipolar tube。

前置事实（v1 假定标定未验，已过时）：
- 标定/同步审计已 CLOSED_CLEAN（C76_C77 草稿：4 份标定 ty/tz≈1e-15、cx/cy 差=0、
  方向 96.8%、左右窗口时间一致、rectify 丢弃率 8-13% 属正常畸变出界）；
- C79 草稿已给事件侧亚像素可达性普查（装置留档 tools/r1_audit/
  probe_subpixel_disparity.py，正负控制全过）。

因此本阶段是"复核 + 补测"，分三件事：

1. 重放两个留档装置（audit_stereo_geometry.py、probe_subpixel_disparity.py），
   读数与 C76/C79 草稿表格在预注册容差内一致即记 VERIFIED；不一致即停（说明
   数据或环境漂移）。
2. intensity truth-vs-wrong probe（v1 设计保留）：对每个对象支持点计算正确视差
   与对称错误视差的匹配分数。硬性要求：
   - 真值用 8 角点表面视差带（C76），禁止 box 中心视差；
   - 五臂齐全：合成正控制、噪声负控制、wrong-disparity、timestamp-shuffle、
     wrong-calibration；正负对照都在留出集评分（C72）；
   - 阈值与 disparity offsets 在 train diagnostic split 冻结，held-out 一次读取；
   - 支持点从 GT box 按 center/edge/corner/visible-region 规则固定采样；
   - 逐 box 容差用附录 D §2.3 公式 tol_d = f·B·l·(1−t)/(1+t)/Z²。
3. 覆盖率与 AUC 分开报告，禁止静默删除无覆盖样本。

临时脚本只放 /tmp/epitube4d_phase1_calib_probe.py；输出 TSV 与可选 PNG 到临时目录；
不读 val/test 调参。

PASS：
- 装置重放 VERIFIED；
- synthetic AUC >= 0.95；held-out intensity aggregate AUC >= 0.95；
- Vehicle/Pedestrian 与主要距离桶均 >= 0.90；
- wrong-calibration/timestamp-shuffle 接近 chance 且显著低于正确臂；
- 支持覆盖率 >= 80%。

FAIL 路由（v1 的 FIX_CALIBRATION_OR_DATA 已过时——标定子项 CLOSED_CLEAN）：
- 装置重放不一致：环境/数据漂移，停止并定位漂移源；
- synthetic 失败：仪器错误，停止；
- held-out intensity < 0.95：按 texture/遮挡/标签质量分桶定位后停止，
  不笼统归因标定；
- 负控制异常高：泄漏或记忆，停止。

不要降低 0.95。最后只给出 PASS/FAIL、决定性数字和下一阶段唯一命令。
```

---

## Prompt 2 v2：event-only stereo/motion descriptor 预训练与 0.95 授权门

```text
只执行 Phase 2：训练 event-only matching descriptor。未过 0.95 之前，
禁止创建完整 EpiTube4D detector。

前提陈述（v1 版已过时，按下述修订）：
- D2 的 0.3590 已被 C76 草稿定位为疑似装置伪影（中心视差真值缺陷；修正为
  8 角点表面带后 train 0.414→0.631、0-10m 桶 0.000→0.778）；直接事件特征
  路线已解禁（零训练计数图+ZNCC 带命中 0.63-0.78）；
- 但 C52/C69 的判别性复活线**不变**：聚合 AUC ≥ 0.95（C79 草稿自我声明
  "本条不得替代 0.95 门"）。本阶段就是执行该复活申请：用修正装置 + 专门
  预训练 + 运动补偿 + 多时刻 epipolar tube 推翻旧读数。

永久代码最多新增两个文件：
- lib/models/epitube4d/event_descriptor.py
- lib/models/epitube4d/pretrain_loss.py
训练入口复用 train_event4d.py；所有 probe 与可视化写 /tmp/epitube4d_phase2_*.py。

模型输入：原始事件或稀疏 voxel，不允许 10→32→3 pseudo-RGB。事件特征至少含
x, y, 归一化相对时间, 极性。

训练目标：L_pre = L_epiNCE + lambda_t L_timeNCE + lambda_lr L_cycle
+ lambda_dist L_teacher。
- 正样本：正确 disparity（表面带定义，C76）、正确时间、正确局部 motion warp；
- hard negatives：错误 disparity、错误 d_dot、timestamp shuffle、左右交换；
- teacher 只在训练期使用同步 intensity/LiDAR；推理与 held-out probe 只输入 events。

装置纪律：真值 = 8 角点表面带（C76）；正负对照同报、留出集评分（C72）；
K 与 tube 的计数单位在预注册冻结（C71）；fixture 语义对齐（C74）。

必须分开报告：
- K=1 与 K={3,5,9,12}；静态点 vs motion-compensated tube；
- pseudo-RGB vs direct-event pretrained；
- Vehicle/Pedestrian、distance、size、manual/interpolated 标签；
- aggregate AUC、bootstrap CI、coverage、truth margin。

授权 PASS：
- held-out aggregate AUC >= 0.95，bootstrap 95% CI 下界 >= 0.95；
- Vehicle/Pedestrian 及主要距离桶各 >= 0.90（行人距离桶只对 <=20-25m 设门，
  C79 物理边界）；
- timestamp shuffle / wrong d_dot / wrong calibration 显著下降；
- K=1 不是唯一来源，tube 聚合带来稳定增益；
- 不使用 val/test 选择超参。

0.85 只能记为里程碑，不能授权 detector（账本 v2.1 修订裁决原文：
"0.85 只能作分层诊断里程碑，不授权任何实现"）。

FAIL：
- 最佳真实 AUC < 0.95：停止 EpiTube 主线，删除未授权 detector 文件；
  保留 descriptor 与负结果作为组件科学出口；
- 只有 teacher 输入时过门、event-only 失败：不算 PASS；
- 只有 aggregate 过门但 Ped/距离桶（<=20-25m 段）明显失败：不算 PASS。

成功后提交一个干净 commit。最后不要进入 Phase 3，只给出唯一下一命令。
```

---

## Prompt 3 v2：Causal Event State Pyramid

```text
只执行 Phase 3：实现因果双目事件状态，不接 detector，不接 temporal object memory。

永久文件最多：
- lib/models/epitube4d/event_state.py
- 必要时 lib/models/epitube4d/__init__.py
临时测试 /tmp/epitube4d_phase3_state_contract.py，执行后删除。

合同：S_l,k = exp(-softplus(lambda_l)*Delta_t) * S_l,k-1 + U_l(Phi_l(E_k))。
- 左右相机权重共享，recurrent state 分离；
- state 由 caller 持有，不能 module-global；API 显式 init/reset/detach/update/read；
- 只接受 timestamp <= query_tau；发现未来事件必须 raise；
- 输出 stride 4/8/16 多尺度状态；不出现 pseudo-RGB；
- 初版使用 max-duration + max-event-count 混合微包，不实现复杂 ASTW。

临时合同测试（九项，v1 不变）：future leakage；reset residue；batch/sequence
ownership；左右 state 不串；同一事件集不同合法 packetization 的输出误差；
query rate 10/20/50/100 Hz；state_dict 与 DDP；空微包/长间隔/极端事件率；
p50/p95 update latency 和显存。

PASS：
- 未来事件 100% 拒绝；reset 后历史残留为 0；
- packetization relative error <= 1e-4 或预注册容差；
- query-rate 改变不重新编码完整 50ms；
- 无 NaN/Inf；性能预算满足预注册值（预算数字先写进 EXECUTION_LOG 再测）。

定位纪律（C55）：分包不变性是线性时不变递归的定理，只作 correctness 测试，
不写成论文贡献；本模块整体定位为编码器组件（CEPE 类），不作头号贡献。

FAIL 时删除 event_state.py，不进入 tokenizer。
```

---

## Prompt 4 v2：梯度解耦的高分辨率对象 tokenizer

```text
只执行 Phase 4：实现 Decoupled Object Tokenizer。不要写 epipolar posterior。

新增永久文件：
- lib/models/epitube4d/tokenizer.py
- 必要时小改 event_state.py 暴露只读 feature API
禁止修改 legacy monodetr/stereodetr 冻结主干。

设计（v1 不变）：
- 原始 event embedding 后分成 proposal state 与 geometry state；
- proposal branch 为轻量 stride-4 class-agnostic objectness/center/scale/motion seed；
- proposal loss 不得反向覆盖 geometry state；优先独立 shallow branch，
  必要时明确 stop-gradient；
- top local maxima 产生 Q_birth，与 Q_learned fallback 并集；
- 每 query 生成 K 个 support：center、四边、可见角、沿 motion curve 点；
- 不建 dense BEV、3D anchor、ROIAlign；不引入 learned quality score。

临时脚本 /tmp/epitube4d_phase4_tokenizer_probe.py 评估：proposal recall@0.25/0.5、
distance/size/class 桶、matched IoU 与 oracle ceiling、well-covered score median、
proposal loss 对 geometry blocks 的梯度范数、token/support 覆盖率与越界率。

PASS（锚点显式化）：
- Ped recall@0.25 >= 0.75（账本锚 = R1 的 0.7095，本门为收紧值）；
- Vehicle recall 不比 frozen baseline 低超过 0.01；
- Vehicle oracle ceiling >= 11.3907（= R1 打分 oracle 重排值，C77）；
- Ped oracle 不下降；
- well-covered score median >= R1 基线的 80%：Ped >= 0.0101、Veh >= 0.4377
  （基线 0.0126 / 0.5471，账本冻结值）；
- proposal→geometry gradient 为 0 或低于预注册阈值；
- 推理新增延迟在预算内。

FAIL（C59/C82 模式）："召回或 matched IoU 提升但 oracle/score 下降"即打分塌缩
前兆，立即停止；不要继续调 top-k 掩盖。删除未通过的 tokenizer 变体。
```

---

## Prompt 5 v2：GT-ray Motion-Conditioned Epipolar-Tube Posterior

```text
只执行 Phase 5：在 GT center/GT box/support 上实现 EpiTube posterior oracle。
禁止接完整 detector，禁止 temporal memory。

新增永久文件：
- lib/models/epitube4d/epipolar_tube.py
- 必要时 lib/models/epitube4d/posterior_utils.py

核心公式（v1 不变）：
uL(q,k,s) = [x_qk + xdot_qk*dt_s, y_qk + ydot_qk*dt_s]
uR(q,k,m,n,s) = [x_qk + xdot_qk*dt_s - (d_m + r_n*dt_s), y_qk + ydot_qk*dt_s]
logit_q(m,n) = sum_{k,s} a_qks * psi(F_L(uL), F_R(uR), dt_s, d_m, r_n)
p_q(m,n) = softmax(logit_q)，r = d_dot。

物理定界（新增，全部预注册）：
- 粗层假设覆盖物理可行范围，细化网格宽度按 C47 从 f·B 与逐框容差公式
  tol_d = f·B·l·(1−t)/(1+t)/Z² 推导，不取经验值；
- 15m 等效分辨率 <=0.5px，目标 <=0.25px；
- d_dot 网格用 C77 跨窗运动先验定界（50ms 窗间运动中值车 2.95px/行人 3.42px、
  P90≈10px，3,359 相邻帧对实测）；
- 不允许 [B,D,H,W] 或 [B,C,D,H,W] 全图 volume；运行时加临时 tensor shape guard。

按顺序做四个 oracle，不允许跳级：
A. synthetic positive control；B. GT center + fixed supports；
C. GT box + visibility supports；D. predicted tokenizer supports。

训练/监督：d*=fx*b/z；d_dot* 从相邻 3D boxes 的 class-aware set matching 或
官方 velocity 推导，主线不使用 track ID；离散标签用相邻 bins 双线性软标签；
NLL + CRPS；manual/interpolated 分层。

临时 probe 输出：AUC、depth median/p75、strict-depth hit、CRPS、ECE、entropy、
coverage、峰数、distance/class 桶、latency/memory。

PASS：
- truth-tube AUC >= 0.95；
- Ped 10–20m median depth error <= 0.49m；Ped strict-depth hit >= 35%
  （两者是账本撤销表中 SCEP 的关闭线原数字，C52 条目）；
- posterior CRPS/ECE 优于单点回归；
- D arm 不显著低于 C arm；无 dense volume；
- wrong-time/wrong-d_dot/wrong-calib destruction 显著。

主张边界（C79，预注册写死）：行人指标与主张只覆盖 <=20-25m
（20-30m 需 0.13px、实测 0.55px，物理接近不可达）；>25m 行人不设门也不设主张。

若 B（GT center）失败，立即停止，不接 detector，不解释为 query 问题。
若只有 C 过、D 失败，返回 tokenizer 阶段；不要在 detector 里补救。
```

---

## Prompt 6 v2：Posterior-Sufficient 静态 3D Set Detector

```text
只执行 Phase 6：把已过门的 event_state、tokenizer、epipolar_tube 接成静态
query-time 3D detector。此阶段仍不加入历史对象 memory。

新增永久文件：
- lib/models/epitube4d/model.py
- lib/models/epitube4d/criterion.py
- lib/models/epitube4d/build.py
如超过三个文件，先解释必要性；禁止把旧 stereodetr.py 复制后改名。

硬性修复（v1 不变，均有账本条目）：
1. class-aware Hungarian（C19）：每个 GT 列读取其真实类别概率，不得 max 后广播；
2. matcher 初期不使用未校准 posterior cost；
3. depth/dims/yaw/3D box 在全部 Hungarian matched pairs 上监督，
   禁止 predicted-2D-IoU filter；
4. query depth 不再依赖一个 detached sample point（C14）；
5. 输出含 class、2D、3D center、dims、yaw、velocity、covariance；
6. 不使用 learned quality head；不使用 dense BEV/3D anchors/ROIAlign（C13）。

打分优先纪律（新增，C82/C77）：A3 已证明当前配方族第一瓶颈是打分——同一批框
用 3D-IoU 重排即达竞品线（Ped 3.653/Veh 7.82 vs 竞品 3.6448/8.02），紧覆盖框
中位分数 0.547→0.129 是 KILL 直接原因。因此：
- 每次诊断必须落盘 well-covered score median 与 score-IoU Spearman；
- "score median 不塌"是与 AP 同级的硬门，塌缩即 FAIL 不看 AP。

先运行临时 correctness（v1 九项不变）：2–8 样本 overfit；matcher toy examples；
wrong class cost；empty frame；Ped/Vehicle 混合；gradient reaches event
state/tube；no NaN；inference 独立于 training-only teacher。

损失：L = L_det + lambda_p L_post + lambda_v L_vel + lambda_c L_cal。
不同时扫权重；先单 batch 测各项单位与梯度范数，冻结权重并写日志。

训练采用 tiny→scout→12ep gate；训练成败按全局规则 6 判定（C81.3）。
第一授权门：
- Vehicle strict >= 6.5；Ped strict >= 1.5；
- 两类 oracle ceiling 不下降；Ped proposal recall >= 0.75；
- well-covered score median 不塌（硬门）；
- manual/interpolated 分层无异常反转。

未过第一门不得长训。通过后 3 seed 静态目标：mean Vehicle >= 8.2、Ped >= 3.8，
或与 public checkpoint（8.0215/3.6448）统计不可分且 oracle 明显更高。

FAIL 时输出最窄根因：proposal、posterior、box lifting、classification 或
transfer；不要一次改多个模块。
```

---

## Prompt 7 v2：物理 strict-risk 分数，带自动删除条件

```text
只执行 Phase 7：验证 posterior-derived strict-risk score。
不要添加自由 learned quality MLP。

动机（新增，运行时证据）：打分/排序是已证实的第一瓶颈——C77：R1 的 oracle
重排 Veh 6.26→11.39（超竞品 8.02）、Ped 0.19→1.87；C82：A3 的行人 oracle
3.653 ≈ 竞品 3.6448，全部缺口在分数不在框。本阶段是对该瓶颈的第一个
posterior 原生修复。

定义：s = p_cls^alpha * q_strict^(1-alpha)；q_strict 是 posterior 在由类别
box length 与官方 IoU threshold 推导的深度/box 容差区间内的概率质量。

只允许三个预注册 arm：
A. alpha=1，纯分类分数；
B. 固定 alpha=0.5；
C. calibration split 一次性选 alpha，held-out 固定读取。
禁止连续 sweep、禁止按最终 AP 反复调 alpha。

输出：两类 strict/loose AP、score-IoU Spearman、ECE、well-covered score
median、oracle ceiling、distance 桶。

PASS：风险分数使两类 strict AP 均不下降，且 calibration/ranking 至少一项
明确改善。

KILL：alpha=1 在两类所有主指标全面更好，立即删除风险项，最终模型只用
分类分数。不保留 default-off quality code。
```

---

## Prompt 8 v2：无 ID Anonymous Posterior Transport

```text
只执行 Phase 8，前置条件：静态 detector 已达 Vehicle >= 6.5、Ped >= 1.5，
且 oracle 不下降。否则拒绝执行。

新增唯一永久文件：lib/models/epitube4d/set_memory.py；小改 model.py 接入
caller-owned memory。

任务：把上一查询时刻的无序 posterior set 传播到当前 tau，作为当前
tube/detector 的先验。不输出 track_id、不使用 ReID、不保存身份 embedding。
时序次序纪律（C22）：本阶段在单帧观测已过门之后才执行，正是账本要求的顺序。

状态元素只含：posterior token、3D mean/covariance、d/d_dot/image motion、
class distribution、timestamp。先按 d_dot 与 image motion 传播（传播先验
物理量级见 C77：50ms 窗间中值车 2.95px/行人 3.42px、P90≈10px），再用
permutation-invariant cross-attention；UOT 只作软质量融合，不产生轨迹 ID。

API：init/reset/detach/predict/update/read。state caller-owned，
DDP sequence 分片明确。

临时 destruction tests（v1 八项不变）：memory slot 随机置换；reset every
query；history shuffle；timestamp sign flip；constant/wrong dt；future-state
injection；remove d_dot；remove covariance。

PASS：
- slot permutation output diff < 1e-5；future access 为 0；
- 100Hz blind-time strict AP 相对提升 >= 10%；3D center jitter 下降 >= 20%；
- 10Hz AP 下降 < 0.1；
- reset/shuffle/wrong-dt 至少消除 70% temporal gain；
- memory bounded，不随序列无限增长。

如果只有平滑指标改善、AP 不变且 destruction 不敏感，不算 4D 贡献，
删除 set_memory.py。
```

---

## Prompt 9 v2：最终三种子、SOTA、消融、代码清理

```text
只执行 Phase 9：冻结 EpiTube4D 配方，完成 3 seed、统计、系统与 claim 审计。
禁止再改方法。

1. 冻结：commit、config、manifest、calibration、pretrain data、checkpoint
   selection、decode、hardware UUID。
2. 三个独立 seed；禁止根据第一个 seed 修改配方。
3. 同 evaluator 输出：Vehicle/Ped strict/loose R40、2D/BEV/3D、100Hz
   blind-time、不同 query rate。
4. paired sequence-block bootstrap 95% CI；三列分报（repo_contract §10
   交接要点 6 口径，loose 一并列全）：本方法、EvStereo3D public checkpoint
   （strict 8.0215/3.6448、loose 42.0074/12.9412、epoch 22、缺 35 个
   dense_head_2d.* 张量）、EvStereo3D paper row（19.62/12.93，不可复现）。
5. DSEC-only 与 external-pretrain 分报。
6. manual-keyframe 与 interpolated-label 分层。
7. 系统：同 GPU p50/p95 latency、吞吐、显存、参数量、几何张量峰值；
   验证无 dense BEV/3D volume/ROIAlign。
8. 最小消融（v1 七项不变）：pseudo-RGB vs causal event state；static point vs
   motion epipolar tube；single depth vs posterior；coupled vs decoupled
   tokenizer；no memory vs anonymous transport；DSEC-only vs external
   pretrain；timestamp/calibration destruction。
9. 删除所有失败/default-off 实验分支、临时脚本、死配置；主模型不得是
   布尔开关集合。
10. 更新 execution log 与 README，只写证据支持的 claim。claim 审计必须引用：
    A 系列 KILL 语境（C82：行人轴有效但打分塌缩触发 KILL，本方法与其正交）、
    C79 物理边界（>20-25m 行人不设主张）、R1 身份裁决（不声称权重同一）。

G-public PASS（账本冻结门，不变）：
- 3 seed mean 的 Vehicle strict > 8.0215 且 Ped strict > 3.6448；
- paired bootstrap 差值 95% CI 下界均 > 0；协议完全一致。

若未过：不得写无条件 SOTA。按真实结果选择"event-native object-level geometry
improves X""better temporal stability""component science"中的最窄表述
（账本预注册接受 COMPONENT_SCIENCE_VALID_BUT_NOT_SOTA 为合法出口）。

最终输出：一页结果摘要、完整命令、表格、清理后的文件树和可投稿/不可投稿判决。
```

---

## 备注

- 本 v2 未改动 v1 的任何冻结门数值（0.95 复活线、8.0215/3.6448 G-public、
  11.3907 oracle、0.49m/35% SCEP 线、well-covered 基线），只做了：入口路径写死、
  过时前提改写、草稿约束继承、环境纪律补全、探针真值纪律强制。
- 若负责人合入 C76–C82 时对 D2 修订案（`SUSPECT_RIG_ARTIFACT`）另有裁决，
  Prompt 2 的前提陈述随之更新，但 0.95 授权门不受影响。

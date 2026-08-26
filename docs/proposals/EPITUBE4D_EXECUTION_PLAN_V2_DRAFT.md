# EpiTube4D 完整执行计划（Runbook v2.1 重组版，待负责人确认）

**文档分工**：本文是唯一主控文档（战略判定、状态、命令、路径、门、避坑矩阵）；
逐阶段提示词原文见同目录 `EPITUBE4D_CODEX_PROMPTS_V2_DRAFT.md`（本文 v2.1 的
补丁条款优先于该文）；逐阶段结果落
`/data1/lyq/code/.epitube4d/docs/EPITUBE4D_EXECUTION_LOG.md`。
证据来源：debug session `5fd9ba`（Phase 0 已实跑通过；C01–C82 全量对照审计
2026-08-26 完成，命令均经运行时验证）。

**v2 → v2.1 变更清单**（不改任何冻结门数值）：

| # | 变更 | 依据 |
|---|---|---|
| 1 | 新增 §1 战略判定（SOTA 算术 + 已关闭路线清单） | A1/A2/A3 oracle×效率分解实测 |
| 2 | 新增 Phase 0.5 零训练证据补全（裁决 H4） | A1_A2 结果文档 §4：H4 OPEN，缺 R1/A1 基线 |
| 3 | P2 前置补丁：移植 `_tiny_overfit` 装置修复 | 开发树 `train_event4d.py:409` 继承 A 系列缺陷 1（已核验） |
| 4 | P6 实现级 checklist（C04–C08/C29/C36/C45/C64）；P2/P6 C70 审计；P7 C65 前置 | C01–C82 全量对照发现的残余缺口 |
| 5 | 训练运维三条显式化：GPU UUID（C39）、冻结 b64 配方（C38）、setsid 验活（C48） | 账本 §5.9/§6/§3.5.5 |
| 6 | 诊断口径统一加 oracle 天花板与排序效率两列（C62） | A1/A2 证明同一 AP 损失可以是两种病 |
| 7 | 新增 §14 C01–C82 避坑矩阵、§15 残余风险 | 本次全量对照落档 |

## 0. 总状态板

| 阶段 | 内容 | 状态 | 依赖 |
|---|---|---|---|
| P0 | 核验并继承仓库合同 | **DONE / PASS**（2026-08-26） | — |
| P0.5 | 零训练证据补全：H4 尾部裁决 + oracle×效率基线 | **NEW / READY** | P0；含 1 处装置修复移植 |
| P1 | 标定复核 + intensity 正控制 | READY（可与 P0.5 并行） | P0 |
| P2 | event descriptor 预训练，0.95 授权门 | 待 P1 | P1 PASS + 装置修复完成 |
| P3 | Causal Event State Pyramid | 待 P2 | P2 PASS（0.95） |
| P4 | Decoupled Object Tokenizer | 待 P3 | P3 PASS |
| P5 | EpiTube Posterior oracle A→D | 待 P4 | P4 PASS + P0.5 赌注确认 |
| P6 | 静态 3D Set Detector（首门 + 3 seed 静态目标） | 待 P5 | P5 PASS |
| P7 | strict-risk 分数（三臂，带自动删除） | 待 P6 | P6 首门 PASS + C65 前置 |
| P8 | Anonymous Posterior Transport | 待 P6 达标 | Veh≥6.5 且 Ped≥1.5 |
| P9 | 3 seed / SOTA / 消融 / 清理 | 最后 | P6–P8 定型 |

### 0.1 快速验证调度（2026-08-26 增补，GPU 4–7 共 4 卡）

目标：最快拿到"是否 SOTA"的三 seed 判定。**门槛一个不减**，加速只来自四个杠杆：

1. **P8 后移**：G-public 是静态逐窗口协议，时序传输不影响 SOTA 数字；P8 与消融
   （P9b）移到判定之后。若 P8 之后改变主上报配方，论文主数字按新配方另跑 3 seed。
2. **seed-1 复用**：P6 首门的 12 epoch run 即冻结配方的 seed 1；P7 是评测期
   重打分（不重训），α 选定后配方冻结，判定阶段（P9a）只补跑 seed 2/3
   （串行 2×13h ≈ 26h）。
3. **并行**：P0.5（CPU）与 P1（单卡）同日并行；4 卡训练窗口内只做 /tmp 探针
   准备、P5 网格推导预注册与文书，不写未授权生产代码（0.95 授权纪律不破）。
4. **时间盒**：每阶段设上限，超时即汇报换路。

排卡：单卡工作默认 smi 4（C80 约定）；4 卡窗口（P2 预训练、P6 12ep、P9a seeds）
用 `CUDA_VISIBLE_DEVICES=4,5,6,7` + torchrun 4×16 b64 AMP off，启动前
`nvidia-smi -L` 映射 UUID 并与 §2.2 四卡清单核对；窗口内独占，不排其他 GPU 任务。

时间线（工作日上限，kill 点可提前终局）：D0 P0.5∥P1 → D1–D4 P2
（**最早否决点 D3–D4：0.95 不过即组件科学出口**）→ D4–D9 P3/P4/P5 →
D9–D13 P6 首门（**首个 SOTA 量级读数**）→ D13–D14 P7 → D14–D16 P9a
（**G-public 三 seed 判定 ≈ D15–D16**）→ 判定后 P8 + P9b。
上限约 16 个工作日；每个门 FAIL 都会更早终局并给出最窄根因。

## 1. 战略判定：为什么这是当前最有希望 SOTA 的路线

### 1.1 分解框架与实测记分板

A1/A2 臂建立的裁决口径：**strict AP = oracle 天花板 × 排序效率**
（oracle = 用真实 3D IoU 替换置信度重排同一批框；效率 = 模型 AP ÷ oracle AP）。
同一 AP 损失可以是两种病：A1 砍天花板（−32.7%）而效率分毫未动，
A2 守住天花板（−2.6%）而效率 −17.9%。只看 AP 必然误诊。

| 臂 | Veh 模型 | Veh oracle | Veh 效率 | Ped 模型 | Ped oracle | Ped 效率 |
|---|---|---|---|---|---|---|
| R1（基线） | 6.2552 | 11.3907 | 0.549 | 0.1896 | 1.8659 | 0.102 |
| A1（hybrid matching） | 4.2104 | 7.6704 | 0.549 | 0.7218 | 2.5632 | 0.282 |
| A2（SEIT） | 5.0090 | 11.0994 | 0.451 | 0.6686 | 3.3273 | 0.201 |
| A3（联合，KILL） | 3.954 | 7.818 | ≈0.506 | 0.943 | 3.653 | ≈0.258 |
| 竞品 public ckpt | **8.0215** | 未测 | 未测 | **3.6448** | 未测 | 未测 |

### 1.2 SOTA 缺口的算术

- **Vehicle > 8.0215**：R1 = 11.3907 × 0.549。守住天花板时需效率 0.549 → **0.705**
  （+28%）；或效率不变时天花板到 14.6。效率修复有已证预算（C77：oracle 重排
  11.39 > 8.02），是纯排序/打分问题。
- **Pedestrian > 3.6448**：R1 = 1.8659 × 0.102。历史最好效率 0.282（A1）、最好
  天花板 3.653（A3），两者相乘 ≈0.94 = A3 实测值。**配方级组合的数学上限就在
  1 附近，永远够不到 3.64**。按效率 0.5 计需天花板 ≈7.3——只能来自新的深度精度
  机制；按历史最好效率 0.282 计需天花板 12.9，更不可能靠配方。

### 1.3 已被关闭数字否决的替代路线

每条都有关闭数字，禁止复活（防复活规则见账本）：

| 路线 | 关闭数字 | 出处 |
|---|---|---|
| 调解码阈值/top-k | 阈值降 0 双向更差（A1 +0.03 噪声级；A2 Veh −0.29/Ped −0.07） | H1/H8 |
| 加 3D NMS | Veh +0.03 / Ped +0.007，噪声内 | H5 |
| 输出预算重分配 | 限制在分数阈值不在 top-k | H7 |
| learned quality head | gamma=0 全面更好 | C41 |
| 全局 IoU-aware 分类 | Veh 天花板 −32.7% | A1 |
| 加行人粘贴剂量 | A3 联合 KILL（Veh 3.954） | C82 |
| 正则化/event dropout | Ped loose 1.501→0.514 | C26 |
| dense 归纳偏置 | D1 联合门 FAIL | C68 |
| sample-point 修补 / dense map | perfect point 无收益 / MAP_LIMITED | C14/C13 |
| 逐点光度匹配 | 0.3590（真值缺陷已由 C76 修正，但 0.95 复活线不变） | C52/C69/C76 |

### 1.4 剩余可用杠杆与本计划的对应

物理预算仍然存在的杠杆只剩三个，全部在本计划主链上：

1. **预训练匹配描述子**（P2）：D2 路由授权方向；C76 修正装置后零训练带命中已
   0.63–0.78（train 0.414→0.631、0–10m 0.000→0.778），加专门预训练 + 运动补偿 +
   tube 聚合冲 0.95。
2. **对象级深度后验**（P5）：C79 证明 10–20 m 行人亚像素物理可达
   （0.203 px vs 容差 0.489 px，70% 带命中）——行人天花板翻倍的唯一已知机制。
3. **posterior 原生 strict-risk 分数**（P7）：攻效率缺口 0.549→0.705；替代被
   C41 杀死的自由 quality head，且带同款自动删除条款。

与账本 v2.1 活跃路线（§3.5）的判定同构："Vehicle 缺口可达性较高；Pedestrian
是主风险，需要数据臂与深度后验同时起效"。数据臂教训已吸收：A2 的 SEIT-v2 供体池
（841 行人供体 / 43 sequence）保留为**预备役**——仅当 P6 后行人天花板仍不足时，
按 C54 最小类门与 C82 约束（下一刀是车辆打分/深度，不是加剂量）单独预注册重开，
不进主链关键路径。

### 1.5 风险与合法出口

第一 kill 点在 P2 的聚合 AUC ≥0.95（C52/C69 冻结复活线）。不过门则停主线、删除
未授权 detector 文件，descriptor + 负结果走组件科学出口
（`COMPONENT_SCIENCE_VALID_BUT_NOT_SOTA`，账本预注册接受）。Pedestrian 需要
天花板（P5）与效率（P7）同时起效，是主风险；P0.5 用零训练证据先行检验
"深度精度是行人 strict 的绑定约束"这一赌注。

## 2. 全局不变量（每条均已验证或有账本出处）

### 2.1 树与身份

- 主树 `/data1/lyq/code/StereoDETR`@`main`（501c462+）：计划文档、审计探针
  `tools/r1_audit/`、manifest 实体；三份基线冻结数字的最高出处是
  `docs/EXPERIMENTS_AND_PITFALLS.md` 与 `reports/repo_contract.md`。
- 开发树 `/data1/lyq/code/.epitube4d`@`epitube4d-dev` = `9446413`：所有 EpiTube4D
  生产代码与训练都在这里；新永久文件只进 `lib/models/epitube4d/`。
- `.epst4d_r1 / .epst4d_r1a_frozen / .epst4d_v3` 三棵旧树**只读不动**；P0.5 需要
  读取 `.epst4d_v3` 的 A 系列收据与装置实现——只拷贝到 /tmp 处理并登记 SHA256，
  不在该树内执行任何写操作。
- 新建任何 worktree 后必须重建 manifest symlink（见 §2.4，P0 实测教训）。

### 2.2 调用模板与训练运维

```bash
# 解释器（裸 python 无 torch）
PY=/data1/lyq/miniconda3/envs/stereodetr/bin/python

# 单进程 GPU 工具（C80）：先 nvidia-smi 挑空闲卡并确认无 ERR! 卡（C81.1）
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<smi编号> \
  $PY <tool.py> ... --device cuda:0        # 禁传非 0 cuda:N

# 开发树在工作区外：非沙箱 + 内嵌 cd（C81.2），watcher 只用绝对路径
cd /data1/lyq/code/.epitube4d && $PY ...
```

- 评测一律走子进程 worker（numba CUDA 非交互 shell 段错误，repo_contract §3.1）。
- 训练成败判据（C81.3）：`training_log.jsonl` 的 `epoch_summary`
  （epoch == max_epochs）且 checkpoint 落盘；不看 train.log 尾部/退出码；
  同一 config 不排双份 launcher；长任务按"可被随机杀"设计（收据幂等）。
- 被 `source_sha256` 锁定的 config 连注释不可改（C75）；每阶段至多新增
  1 份 `configs/dsec3dod/epitube4d_p<N>_*.yaml`，不触碰任何锁定 config。

**多卡训练运维（v2.1 显式化，适用 P2/P6/P9 的正式训练）**：

- **GPU 身份用 UUID 不用序号**（C39：序号寻址已两次选错物理卡）。启动前
  `nvidia-smi -L` 现场映射，并与账本 §6 登记的四卡 UUID 清单核对，不一致即停：
  `GPU-2855c9b4-…`、`GPU-92570675-…`、`GPU-103d5a46-…`、`GPU-d68247d7-…`。
  README 里的旧 UUID 清单不得沿用（账本 §3.5.5）。
- **冻结 b64 配方**：`torchrun --nproc_per_node=4`、每卡 16、全局 batch 64、
  **AMP off**（C38：MSDeformAttn 仅 FP32，端到端 AMP 不可用）。
- **长训练投递**：`setsid ... nohup ... </dev/null` 并二次验活（C48：裸 nohup
  挡不住 agent shell 的 SIGHUP）；重投前 `nvidia-smi` 确认无 `ERR!` 卡。

### 2.3 科学纪律（探针/门通用）

- 对应性真值 = 8 角点表面视差带 `[fB/z_far, fB/z_near]±容差`，禁 box 中心视差
  （C76）；逐框容差 `tol_d = f·B·l·(1−t)/(1+t)/Z²`。
- 正负对照同报、全部留出集评分（C72）；计数单位与阈值同冻结（C71）；
  断言不得依赖随机巧合（C73）；fixture 对齐合同语义（C74）。
- **oracle×效率两列纪律（v2.1 新增，C62）**：P4/P6/P7 每次诊断，凡报 strict AP
  必须并列 oracle 天花板与排序效率两列（复用 `tools/c2_bottleneck_diagnostic.py`
  装置），禁止只报乘积。
- 行人主张边界 ≤20–25 m（C79：20–30 m 需 0.13 px、实测 0.55 px）。
- 匹配机制授权门 = 聚合 AUC ≥0.95（C52/C69 冻结线；0.85 只作里程碑）。
- R1 身份裁决：`epoch_012.pth` 永久丢失、恢复路线关闭；R1 只作数字基线
  （6.2552/0.1896）；权重起点用 `epoch_011.pth` 并显式标注。
- 已知非回归：`tests/episet4d/test_p0_receipt_contract.py` 13 项 error。

### 2.4 载荷性依赖（换机/清树前必读）

- 主树 `lib/datasets/dsec3dod/manifest/records.jsonl`（untracked，
  `b2afa842…`，135,886,083 B）是所有树 symlink 的目标；
  备份 `/data1/lyq/stereodetr_docs_backup_20260824/dsec3dod_manifest/`。
- `9446413` 只 tracked `summary.json`/`provenance.json`；新 worktree 必须执行：
  `ln -s /data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl \
     <新树>/lib/datasets/dsec3dod/manifest/records.jsonl`
- R1 预测恢复位：`reports/episet4d/p0/restored/predictions_model.pkl`
  ← 归档 `/data1/lyq/rep4d_archive/episet4d_p0_20260822/reports/r/r1_stereo_flip/diagnostic/`。

### 2.5 耗时基准（实测锚点）

| 操作 | 实测 | 来源 |
|---|---|---|
| R1 冻结重评（CPU） | 27.9 s | P0 本次实跑 |
| tests/dsec3dod 84 项 | 38.8 s | P0 本次实跑 |
| 12 epoch 训练（4×L20） | ~10 h（51 min/ep） | A3/C82 |
| 完整诊断（val 11400q + train 2000q） | ~2 h 37 m | A3/C82 |
| P0.5 全部（CPU 为主） | 预计 ≤1 h | 量级 = 冻结重评同级 |

## 3. Phase 0 — 已完成（PASS，2026-08-26，session 5fd9ba）

实跑命令与结果（全文见 EXECUTION_LOG §Phase 0；证据
主树 `.cursor/debug-5fd9ba.log` runId `phase0-1`）：

```bash
# 1. 建树（唯一 git 写操作）
git worktree add -b epitube4d-dev /data1/lyq/code/.epitube4d 9446413
# 2. 恢复 R1 预测（工具用前自验 SHA256）
mkdir -p /data1/lyq/code/.epitube4d/reports/episet4d/p0/restored
cp /data1/lyq/rep4d_archive/episet4d_p0_20260822/reports/r/r1_stereo_flip/diagnostic/predictions_model.pkl \
   /data1/lyq/code/.epitube4d/reports/episet4d/p0/restored/
# 3. manifest symlink（首跑 3 failed/16 skipped 的唯一根因，修复后全绿）
ln -s /data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl \
   /data1/lyq/code/.epitube4d/lib/datasets/dsec3dod/manifest/records.jsonl
# 4. 冻结重评：PASS，84/84 字段 0 差异，六门字段最大 |Δ| 4.62e-05
cd /data1/lyq/code/.epitube4d && $PY tools/episet4d/p0_reeval_r1.py evaluator \
   --output-dir /tmp/epitube4d_p0_reeval
# 5. 合同测试：84 passed（38.81 s）
cd /data1/lyq/code/.epitube4d && $PY -m pytest tests/dsec3dod -q
```

核验读数：评测器/config/manifest/infos/预测 9 项 hash 全 OK；R1 6.255211 /
0.189565、D1 5.498630 / 0.778744、EvStereo3D 8.021549 / 3.644764 全部可追溯。

## 4. Phase 0.5 — 零训练证据补全（v2.1 新增，READY）

**性质**：零训练、零生产代码，CPU 为主，预计 ≤1 h + 半天分析。
**目的**：(a) 裁决 A 系列遗留的 H4（"均值 3D IoU 上升掩盖尾部变薄，而 strict AP
活在尾部"）；(b) 建立 R1/A1/A2/A3/D1 的 oracle×效率基线总表，作为 P4/P6/P7 的
标准诊断口径；(c) 用数据先行检验 P5 赌注——行人 strict 上限是否由深度精度绑定。

**步骤 0（装置修复移植，本计划唯一的 P2 前代码改动，也可归并到 P2 执行）**：
开发树 `train_event4d.py:409` 读 `config["experiment"]["output_dir"]`，而全部
config 把 `output_dir` 定义在 `training` 下——A 系列缺陷 1（所有臂 tiny-overfit
预检静默抛 KeyError，C40 修复因此从未生效）。修复只存在于 `.epst4d_v3` 的未提交
改动。移植规则：只读对照 v3 树实现后在开发树做同义单点修改，跑一次 tiny-overfit
冒烟验证装置活了，记入 EXECUTION_LOG（性质 = 测量装置修复，C50 的活例）。

**步骤 1–4（证据计算，全部 /tmp 脚本 + NDJSON）**：

1. `/tmp/epitube4d_p05_tail_and_efficiency.py`；证据写主树
   `.cursor/debug-5fd9ba.log`，runId `p05-1`。
2. 数据源（全部只读；v3 树文件先拷 /tmp 并登记 SHA256）：
   - R1 预测：开发树 `reports/episet4d/p0/restored/predictions_model.pkl`
     （`9f6b8be9…` 已验）；GT：`dsec_infos_val.pkl`（`1df3ba49…`）；
   - R1/D1 oracle×效率：开发树 tracked 的
     `reports/r/r1_stereo_flip/diagnostic/C2_BOTTLENECK.json` 与
     `reports/episet4d/d1_dense/diagnostic/C2_BOTTLENECK.json/`，直接读字段；
   - A1/A2/A3：`.epst4d_v3` 的 `reports/epst4d_v3/<arm>/diagnostic/` 收据
     （A2 的 `recall_by_iou_3d_threshold` 已落盘，直接引用；A3 路径以 C82
     草稿登记为准）。
3. 尾部指标计算：对 R1（必做）与 A1（若 v3 树预测 pickle 在位）计算
   `recall_by_iou_3d_threshold`（≥0.25/≥0.50/≥0.70 档被覆盖真值占比）。IoU
   装置**复用** `tools/c2_bottleneck_diagnostic.py` 的既有实现（子进程调用，
   numba 陷阱 §2.2；禁止新写第二把 IoU 尺子，C63）。
4. 产出并追加 EXECUTION_LOG：oracle×效率总表、R1/A1 尾部表（对照 A2 已知值：
   Veh ≥0.70 = 11.1%（2607/23412）、Ped ≥0.70 = 0.26%（15/5701））、H4 裁决、
   P5 赌注确认段。

**预注册裁决规则（先冻结再算数）**：

- H4 成立判据：A1 的 Veh 覆盖率@IoU≥0.70 相对 R1 下降 ≥30%（与 A1 oracle
  −32.7% 同向，即"均值升尾部薄"得证）；
- P5 绑定约束确认判据：R1 的 Ped 覆盖率@IoU≥0.70 < 1%（独立于已知的 A2 值）；
- 路由：确认 → P5 赌注不变，进 P1/P2；若 R1 行人尾部反而丰富（≥0.70 覆盖 >5%）
  且 A1 尾部不薄 → 排序优先重估（把 P7 类打分诊断前移），决策写 EXECUTION_LOG。

本阶段不是科学门（无 PASS/FAIL 淘汰），是证据补全；但裁决规则先于计算冻结。

## 5. Phase 1 — 标定复核 + intensity 正控制（READY，可与 P0.5 并行）

**性质**：零训练、零生产代码；1 张 GPU（或 CPU）够用；预计 0.5–1 天。

前置决策点（跑 held-out 前写进 EXECUTION_LOG，负责人可改默认值）：
- D1（offset 网格）：预注册的小型 left-right timestamp offset 网格范围与步长；
- D2（支持点规则）：center / 四边中点 / 可见角 / visible-region 采样数量表；
- D3（分桶）：距离桶边界（建议沿用 C79 的 10-20/20-30/30-45）与 bootstrap 次数。

步骤：
1. 装置重放 A：按 `reports/r1_audit/R1_AUDIT_RECEIPT.md` 登记的原始命令复跑
   主树 `tools/r1_audit/audit_stereo_geometry.py`，读数与 C76_C77 草稿一致
   （ty/tz≈1e-15、方向 96.8%、rectify 丢弃 8-13%）即记 VERIFIED。
2. 装置重放 B：同法复跑 `tools/r1_audit/probe_subpixel_disparity.py`，
   对照 C78_C82 草稿 C79 表格（行人 10-20m 0.203/0.489/70% 等）。
3. 新探针 `/tmp/epitube4d_phase1_calib_probe.py`（intensity truth-vs-wrong）：
   - 五臂：合成正控制 / 噪声负控制 / wrong-disparity / timestamp-shuffle /
     wrong-calibration；真值按 §2.3 表面带；
   - 阈值与 offsets 在 train diagnostic split 冻结 → held-out 一次读取；
   - 输出 TSV + 可选 PNG 到 /tmp；覆盖率与 AUC 分报。
4. 追加 EXECUTION_LOG：frozen offset、calibration hash、全部读数、PASS/FAIL。

门（完整文本见 PROMPTS_V2 Prompt 1）：synthetic ≥0.95；held-out aggregate
≥0.95；两类与主要距离桶 ≥0.90；破坏臂接近 chance；覆盖率 ≥80%。
FAIL 路由：装置重放不一致 → 定位漂移；synthetic 失败 → 仪器错误；
held-out <0.95 → 按 texture/遮挡/标签分桶归因后停止（标定子项已 CLOSED_CLEAN，
不再笼统归因标定）。

## 6. Phase 2 — descriptor 预训练与 0.95 授权门

**性质**：本线第一批生产代码 + 第一次训练；预计数天（含 scout）。

- **前置（v2.1）**：P0.5 步骤 0 的 `_tiny_overfit` 装置修复已完成并冒烟通过；
  否则 tiny-overfit 预检必崩（KeyError），流程走不到 scout。
- 永久文件：`lib/models/epitube4d/event_descriptor.py`、
  `lib/models/epitube4d/pretrain_loss.py`、1 份新 config
  `configs/dsec3dod/epitube4d_p2_pretrain.yaml`；入口复用 `train_event4d.py`
  （沿用其 argparse 与 config 先例，不新写 trainer）。
- 决策点：teacher 信号源（同步 intensity / LiDAR-视差 GT 的组合与权重
  lambda_t/lambda_lr/lambda_dist，单 batch 量纲测定后冻结）；是否引入
  external pretrain 数据（默认 DSEC-only，若引入则 P9 分报）。
- **C70 审计（v2.1）**：teacher 蒸馏项与各对比项在冻结权重前，先单 batch 量
  逐块梯度 cosine 与 norm 占比，写明各项是"分享"还是"置换"梯度预算，登记
  EXECUTION_LOG 后才允许长训。
- 流程：tiny overfit（合同自检）→ scout（短 epoch 确认损失下降与显存）→
  正式预训练（按 §2.2 运维三条投递）→ held-out 探针
  （/tmp/epitube4d_phase2_probe.py，表面带真值，分报 K∈{1,3,5,9,12}、
  static vs tube、pseudo-RGB vs direct、类别/距离/标签分层，bootstrap CI）。
- 门：held-out aggregate AUC ≥0.95 且 CI 下界 ≥0.95；两类与 ≤20-25m 距离桶
  ≥0.90；破坏臂显著下降；tube 聚合有稳定增益；event-only 输入达标。
- FAIL：<0.95 → 停主线，删除未授权 detector 文件，descriptor+负结果走
  组件科学出口。PASS → 干净 commit（epitube4d-dev 分支）。

## 7. Phase 3 — Causal Event State Pyramid

- 永久文件：`event_state.py`（+`__init__.py`）；临时
  `/tmp/epitube4d_phase3_state_contract.py`（九项合同测试，跑完删除）。
- 合同：`S_l,k = exp(-softplus(λ_l)·Δt)·S_l,k-1 + U_l(Φ_l(E_k))`；
  caller-owned state；future event 必 raise；stride 4/8/16；混合微包。
- **实现纪律（v2.1，C45）**：query 周期/微包参数一律从 config 传入，提交前
  搜索全部 split/repeat 字面量，不得写死。
- 门：future 100% 拒绝；reset 残留 0；packetization 相对误差 ≤1e-4；
  变 query-rate 不重编码 50ms；无 NaN/Inf；性能预算先写 EXECUTION_LOG 再测。
- 定位（C55）：分包不变性只作 correctness；模块定位编码器组件。
- FAIL：删 `event_state.py`，不进 P4。预计 ~1 天。

## 8. Phase 4 — Decoupled Object Tokenizer

- 永久文件：`tokenizer.py`（+`event_state.py` 只读 API 小改）；
  探针 `/tmp/epitube4d_phase4_tokenizer_probe.py`。
- 门（锚点）：Ped recall@0.25 ≥0.75（账本锚 0.7095，收紧值）；Veh recall
  降幅 ≤0.01；Veh oracle ≥11.3907；Ped oracle 不降；well-covered score
  median Ped ≥0.0101 / Veh ≥0.4377（= R1 基线 0.0126/0.5471 的 80%）；
  proposal→geometry 梯度为 0 或低于预注册阈值；延迟在预算内。
- **落盘口径（v2.1，C62）**：探针输出含 oracle 天花板与排序效率两列
  （对照 §1.1 基线表）。
- FAIL 模式（C59/C82）："召回或 matched IoU 升而 oracle/score 降" = 打分
  塌缩前兆，立即停止，不调 top-k 掩盖。预计 1–2 天。

## 9. Phase 5 — EpiTube Posterior oracle（A→D 不许跳级）

- **前置（v2.1）**：P0.5 的 P5 赌注确认段已落 EXECUTION_LOG（行人尾部
  ≥0.70 覆盖 <1% 即深度精度绑定得证）。
- 永久文件：`epipolar_tube.py`（+必要时 `posterior_utils.py`）。
- 物理定界全部预注册：细化网格按 C47 从 `f·B` 与逐框容差公式推导；
  15 m 等效分辨率 ≤0.5px（目标 ≤0.25px）；d_dot 网格用 C77 运动先验定界
  （50ms 窗间中值车 2.95px / 行人 3.42px，P90≈10px）；禁全图 volume，
  运行时挂临时 shape guard。
- 四个 oracle 顺序：A 合成正控制 → B GT center → C GT box+visibility →
  D predicted supports。
- 门：truth-tube AUC ≥0.95；Ped 10–20m 深度误差中位 ≤0.49 m 且
  strict-depth hit ≥35%（SCEP 关闭线原数字）；CRPS/ECE 优于单点回归；
  D 不显著低于 C；破坏臂显著。
- 路由：B 失败 → 全线停（不解释为 query 问题）；C 过 D 败 → 回 P4。
  预计 2–3 天。

## 10. Phase 6 — 静态 3D Set Detector

- 永久文件：`model.py`、`criterion.py`、`build.py` + 1 份 config。
- 硬性修复：class-aware Hungarian（C19）；不用未校准 posterior cost；
  全 matched pairs 监督 3D（禁 predicted-2D-IoU filter）；不依赖 detached
  sample point（C14）；无 learned quality head；无 dense volume（C13）。
- **实现级 checklist（v2.1 新增，提交 correctness 前逐项自查并登记）**：
  - C04：3D 维度内部固定 `[h,w,l]`，任何 adapter 显式转换 + corner round-trip；
  - C05：yaw 用 rectified camera 系；边界减 `pi/2`；`sin/cos` 连续性测试；
  - C06：2D 固定 `(l,r,t,b)`，`box2d_ref` 与 `ray_ref` 分离不混用；
  - C07：class mean size 必须有效非零；`mean*exp(residual)`；分母不用近零 residual；
  - C08：sigmoid 多标签下前景判断不得用 `label>0`；
  - C29：dimension loss 分母用 class mean size，保留 NaN/倍率合同测试；
  - C36：任何 wrapper 委托 `state_dict`/`named_parameters`，键名集合与逐位输出合同；
  - C45：query 周期/组数从 config 传入，搜索 split/repeat 字面量；
  - C64：group assignment 令每 GT 正样本数为常数，避免逐实例正梯度饥饿。
- **C70 审计（v2.1）**：`L_post/L_vel/L_cal` 各辅助项冻结权重前，单 batch 量
  逐块 cosine 与 norm 占比，说明分享还是置换（与既有"单 batch 测单位与梯度
  范数"合并执行）。
- 打分优先纪律（C82/C77）：每次诊断落盘 well-covered score median 与
  score-IoU Spearman；score median 塌缩 = 与 AP 同级硬 FAIL。
- **落盘口径（v2.1，C62）**：诊断输出 oracle 天花板与排序效率两列。
- 流程：临时 correctness 九项 → tiny → scout → 12 ep 首门 →（过门后）
  3 seed。训练 ~10 h/12ep（4×L20，按 §2.2 运维三条），诊断 ~2.6 h/次（§2.5）。
- 首门：Veh strict ≥6.5；Ped strict ≥1.5；两类 oracle 不降；Ped recall
  ≥0.75；score median 不塌；分层无反转。
- 3 seed 静态目标：mean Veh ≥8.2、Ped ≥3.8，或与公开 ckpt（8.0215/3.6448）
  统计不可分且 oracle 显著更高。
- FAIL：输出最窄根因（proposal/posterior/lifting/classification/transfer），
  一次只改一个模块。

## 11. Phase 7 — strict-risk 分数（三臂，自动删除条件）

- **C65 前置（v2.1 新增）**：先落盘 train split 的 score-IoU Spearman 与
  well-covered score median，证明 train 侧排序目标未饱和；若 train 侧已
  饱和而 val 缺口仍在，则排序臂预期无效，本阶段改走校准/数据路由并记录，
  不白跑三臂。
- 零新文件倾向（实现进 `model.py`/`criterion.py` 现有面）；
  三臂：A α=1 / B α=0.5 / C calibration split 一次性选 α。
- PASS：两类 strict AP 均不降且 calibration/ranking 至少一项改善。
- KILL：α=1 全面更好 → 删除风险项，不留 default-off 代码。诊断级耗时。
- 落盘口径含 oracle×效率两列（效率提升与否是本阶段的直接判据）。

## 12. Phase 8 — Anonymous Posterior Transport

- 前置硬条件：P6 达 Veh ≥6.5 且 Ped ≥1.5 且 oracle 不降，否则拒绝执行。
- 永久文件：`set_memory.py` + `model.py` 小改；传播先验常数取 C77。
- 八项 destruction 全跑；门：slot permutation diff <1e-5；future access 0；
  100Hz blind-time strict AP 相对 +≥10%；jitter −≥20%；10Hz AP 降 <0.1；
  破坏消除 ≥70% temporal gain；memory 有界。
- 仅平滑改善 + destruction 不敏感 → 删 `set_memory.py`。

## 13. Phase 9 — 3 seed / SOTA / 消融 / 清理

- 冻结配方后 3 独立 seed（seed 值预注册；禁按第一个 seed 改配方）：
  训练 ~3×10 h + 诊断 ~3×2.6 h，另加消融臂；总预计 1–2 周。
- 三列分报（strict+loose 全列）：本方法 / EvStereo3D 公开 ckpt
  （8.0215/3.6448、42.0074/12.9412，epoch 22、缺 35 个 dense_head_2d 张量）/
  论文行（19.62/12.93，不可复现）。paired sequence-block bootstrap 95% CI。
- 七项最小消融（见 PROMPTS_V2 Prompt 9）；系统指标同 GPU p50/p95。
- G-public：3 seed mean Veh strict >8.0215 且 Ped strict >3.6448，
  差值 CI 下界 >0。未过 → 按最窄真实表述，接受
  COMPONENT_SCIENCE_VALID_BUT_NOT_SOTA 出口。
- 清理：删除失败分支/临时脚本/死配置；claim 审计引用 A 系列 KILL 语境、
  C79 物理边界、R1 身份裁决。

## 14. C01–C82 避坑矩阵（2026-08-26 全量对照落档）

状态含义：**内建** = 计划条款直接覆盖；**补丁** = 本 v2.1 新增覆盖；
**N/A** = 坑属已废弃机制且本计划不含该机制（防复活规则仍继承）。

### 14.1 协议、数据、几何与旧机制（C01–C25）

| ID | 坑（一句话） | 计划对应 | 状态 |
|---|---|---|---|
| C01 | AP11 地板 | 全文内部决策只用 R40；P9 三列分报 | 内建 |
| C02 | decode 与协议不一致 | 冻结评测器+worker 不触碰；P0 hash 核验 | 内建 |
| C03 | strict/loose 混报 | 每门写明口径，机器字段落盘 | 内建 |
| C04 | 3D 维度约定 | P6 checklist | 补丁 |
| C05 | yaw 与 rectification | P6 checklist | 补丁 |
| C06 | 2D 参考系混用 | P6 checklist | 补丁 |
| C07 | class prior 为零/分母 | P6 checklist | 补丁 |
| C08 | 前景判断 label>0 | P6 checklist | 补丁 |
| C09 | 固定多窗≠跨 query 状态 | P3 真因果状态 + query-rate 合同 | 内建 |
| C10 | TSSE 禁复活 | 不含该机制；P3 破坏臂配正对照 | N/A |
| C11 | RBEP 取消 | 不含；P5 posterior 走 C52 复活门 | N/A |
| C12 | streaming 破坏合同 | P3 九项合同（split/rate/timestamp） | 内建 |
| C13 | dense map 主瓶颈 | P5/P6 禁 dense volume + shape guard | 内建 |
| C14 | sample-point repair | P6 硬性修复 4 | 内建 |
| C15 | center-only disparity | P4 K support（center/edge/corner/motion） | 内建 |
| C16 | 过早 soft-argmin | P5 多峰 posterior，禁单点压缩 | 内建 |
| C17 | 只调 score/threshold | P7 三固定臂；H1/H8 已证阈值路线死 | 内建 |
| C18 | budget 吞噬小行人 | P4 分桶 recall + 预算算术 | 内建 |
| C19 | class-unaware Hungarian | P6 硬性修复 1 | 内建 |
| C20 | posterior 过早进 matcher | P6 硬性修复 2 | 内建 |
| C21 | confidence≠3D quality | P7 校准证明后才参与排序 | 内建 |
| C22 | 观测不可靠先加 memory | P8 前置硬条件（先单帧后时序） | 内建 |
| C23 | 照抄 track-query | P8 无 ID/permutation-equivariant 设计 | 内建 |
| C24 | Scene Flow 主线 | 不含 | N/A |
| C25 | VO/SLAM 主线 | 不含（无外部 pose） | N/A |

### 14.2 训练、运行、测量（C26–C52）

| ID | 坑（一句话） | 计划对应 | 状态 |
|---|---|---|---|
| C26 | dropout/WD 修不了结构 | 主线不依赖正则化补救；数据臂重开按 C54 | 内建 |
| C27 | 直接长训看 AP | P2/P6 tiny→scout→gate 流程 | 内建 |
| C28 | module-global state | P3 caller-owned + 显式生命周期 | 内建 |
| C29 | dimension loss 分母 | P6 checklist | 补丁 |
| C30 | adapter 存在≠被调用 | 冻结生产路径 + tests/dsec3dod 84 项 | 内建 |
| C31 | train/val 不并列 | 诊断纪律 + P7 C65 前置 | 内建+补丁 |
| C32 | 测量单元先失败 | 各阶段先合成正对照再真数据 | 内建 |
| C33 | 陈旧 GT 证明时序 | P2 teacher 同步；P5 d_dot 从相邻框推导 | 内建 |
| C34 | 吞吐外推 | P9 系统指标实测 | 内建 |
| C35 | fixture 并发竞态 | 复用现有 trainer 机制；多卡启动检查 | 内建 |
| C36 | wrapper 静默改名 | P6 checklist | 补丁 |
| C37 | numba 段错误 | §2.2 子进程 worker 全局规则 | 内建 |
| C38 | AMP 不可用 | §2.2 冻结 b64 配方（AMP off） | 补丁（显式化） |
| C39 | cuda:N 序号错位 | §2.2 UUID 现场映射 + 核对 | 补丁（显式化） |
| C40 | tiny-overfit 覆写收据 | /tmp 输出 + P0.5 步骤 0 装置修复 | 内建+补丁 |
| C41 | learned quality head | P6 禁用；P7 同款 KILL 条款 | 内建 |
| C42 | recall 与 AP 不同 IoU | P4 matched-IoU 分布并列 | 内建 |
| C43 | gap 门放走天花板 | 所有门带 oracle 不降约束 | 内建 |
| C44 | 预算搬运召回 | P4 预算算术先行 | 内建 |
| C45 | 周期写死 50 | P3/P6 checklist（config 传入+搜字面量） | 补丁 |
| C46 | 空帧静默测 0 | P6 correctness 空帧项；诊断跨采样 | 内建 |
| C47 | 经验值违反像素物理 | P5 网格从 f·B 与容差公式推导 | 内建 |
| C48 | nohup 挡不住 SIGHUP | §2.2 setsid + 二次验活 | 补丁（显式化） |
| C49 | 诊断重复跑 backbone | 复用 c2_bottleneck 共享接口 | 内建 |
| C50 | 门写仪器不测的字段 | 每门列落盘字段；P0.5 修装置即本条执行 | 内建 |
| C51 | 事后解释未验证 | FAIL 路由"最窄根因、一次一模块" | 内建 |
| C52 | 稀疏光度信噪不足 | P2 授权门 = 0.95 复活线原样 | 内建 |

### 14.3 数据解释、预注册与 A 系列（C53–C82）

| ID | 坑（一句话） | 计划对应 | 状态 |
|---|---|---|---|
| C53 | 记录数≠样本量 | 身份/插值分层报告（P2/P5/P9） | 内建 |
| C54 | 增广杀最小类 | 主线无增广；SEIT 预备役重开时适用 | N/A（预备役条款） |
| C55 | 定理当创新 | P3 定位纪律（只作 correctness） | 内建 |
| C56 | 行人≠证据不足 | 主张措辞边界继承 | 内建 |
| C57 | 期望销毁多峰 | P5 保多峰 + CRPS/ECE | 内建 |
| C58 | 数值带指错方向 | oracle 守卫（同 C43） | 内建 |
| C59 | 打分塌缩≠几何塌缩 | P4/P6 well-covered median 硬门 | 内建 |
| C60 | recipe differential | P9 三列 + C78 语境 | 内建 |
| C61 | 单臂过度外推 | P9 claim 审计边界 | 内建 |
| C62 | 比值门瞒分子分母 | oracle×效率两列纪律（§2.3） | 补丁 |
| C63 | 三把 decode 尺子 | 不触碰 decode；P0.5 禁新 IoU 尺子 | 内建 |
| C64 | 正梯度饥饿 | P6 checklist（每 GT 正数常数） | 补丁 |
| C65 | train 侧已饱和 | P7 前置饱和检查 | 补丁 |
| C66 | 框数掩盖身份稀缺 | 同 C53 分层 | 内建 |
| C67 | loss_depth 79% 梯度 | P6 单 batch 梯度范数测定 | 内建 |
| C68 | 联合门 FAIL 即停 | 全部阶段 FAIL 即停路由 | 内建 |
| C69 | 0.3590 复活线 | P2 前提陈述 + 0.95 不变 | 内建 |
| C70 | 辅助头置换梯度 | P2/P6 逐块 cosine/norm 审计 | 补丁 |
| C71 | 计数单位未冻结 | §2.3 全局纪律 | 内建 |
| C72 | 对照臂假通过 | §2.3（正负对照同报、留出集） | 内建 |
| C73 | 概率巧合断言 | §2.3 | 内建 |
| C74 | fixture 只对齐 shape | §2.3 | 内建 |
| C75 | 锁定 config 不可改 | §2.2 | 内建 |
| C76 | 中心视差真值缺陷 | §2.3 表面带真值全局强制 | 内建 |
| C77 | 三修复目标确认 | P4/P7/P8 锚点数字来源 | 内建 |
| C78 | 竞品配方差分 | P9 三列 + 语境引用 | 内建 |
| C79 | 行人物理边界 | P5/P9 主张边界 ≤20–25 m | 内建 |
| C80 | GPU 调用约定 | §2.2 | 内建 |
| C81 | 环境三陷阱 | §2.2 | 内建 |
| C82 | A3 KILL 约束 | 不从 A3 出发；P6 打分优先纪律 | 内建 |

## 15. 残余风险与诚实声明

1. **第一 kill 点 = P2 的 0.95**。现有最好证据是修正装置后的零训练带命中
   0.63–0.78，距 0.95 仍有大缺口；预训练 + 运动补偿 + tube 聚合能否补上没有
   先例担保。不过门即走组件科学出口，这是纪律不是悲观。
2. **行人需要双杠杆同时起效**（天花板 P5 + 效率 P7）；P0.5 的绑定约束检验
   只能确认方向，不能担保幅度。
3. **C76–C82 已于 2026-08-27 合入账本**（`docs/EXPERIMENTS_AND_PITFALLS.md`
   附录 B，索引在其 §4.4，A 系列实验记录在 §3.6–3.9）：D2 修订案
   `SUSPECT_RIG_ARTIFACT` 与"标定/数据子项 `CLOSED_CLEAN`"已是账本正文，P2 前提
   陈述按账本引用；**0.95 授权门不变**。本计划与账本冲突时以账本为准。
4. **`.epst4d_v3` 只读依赖**：P0.5 读 A 系列收据、装置修复移植对照 v3 实现；
   该树是未提交工作树状态，清理该树前须先把 A1/A2/A3 收据归档（与账本归档
   惯例一致），否则 H4 证据不可复核。
5. **门槛不对称**：P6 三 seed 静态目标（8.2/3.8）高于 G-public（8.0215/3.6448），
   是刻意留的余量；若 P6 落在两者之间，按 G-public 原文裁决，不得移门。

## 16. 立即下一步

顺序：**P0.5 步骤 0（装置修复移植）→ P0.5 证据计算 → 汇报 H4 裁决 → P1**。
第一条命令（只读对照 v3 树的修复实现）：

```bash
cd /data1/lyq/code/.epst4d_v3 && git diff -- train_event4d.py | head -80
```

每阶段收尾三件事：EXECUTION_LOG 追加（身份+命令+TSV+PASS/FAIL+理由）、
临时脚本按惯例处置（删除或登记 hash 留档）、给出下一阶段唯一允许命令。

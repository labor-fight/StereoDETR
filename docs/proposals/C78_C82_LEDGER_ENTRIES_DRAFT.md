# 账本条目：C78–C82（debug session 522f14，**已于 2026-08-27 合入账本**）

依据：session 522f14 的 NDJSON 证据日志（395 行，已随会话清理——数值读数
以本文表格为准，装置为 `tools/r1_audit/probe_subpixel_disparity.py` 可复跑）与
诊断收据 `/data1/lyq/code/.epst4d_v3/reports/epst4d_v3/a3_joint/diagnostic/`（留存）。

**合入状态：** C78–C82 五条全文进 `docs/EXPERIMENTS_AND_PITFALLS.md` 附录 B，
概览进其 §3.9、索引进 §4.4；C78 另在附录 A 与附录 C §2.1 就地加了批注。
本文件保留为逐字原件，未被删除；按账本第 7 节的事实优先级，本文件高于账本汇总。

**runId 索引**（会话内各轮运行的内容映射）：

| runId | 内容 | 对应条目 |
|---|---|---|
| runA-train / runA-val | 零训练亚像素视差普查（386 行逐 box 数据 + 汇总） | C79 |
| runB-smoke | diagnose_arm 崩溃裁决实验 + epoch-1 流水线冒烟（6940s 过） | C80 |
| runC-official | 正式诊断两次被杀的取证（沙箱陷阱 + 宿主机复位） | C81 |
| runD-official | 重启后第三次正式诊断：健康检查、完成、KILL 判定 | C81/C82 |

---

## C78 | RECIPE_DIFFERENTIAL_CORRECTION | 附录 C 漏检：EvStereo3D 训练配方含重剂量事件 copy-paste

**现象**：附录 C（配方差分）§2.1 写"Their sole geometric augmentation is exactly
our R1 arm ... no copy-paste"，并把"R1 镜像恰是竞品唯一增广"当作独立支持。

**事实**（本次直接读竞品源码核实）：
`/data1/lyq/code/Ev-Stereo3D/configs/stereo/dataset_configs/dsec_dataset_fused_event_4_train_val200.yaml`
第 42-49 行：

```yaml
- NAME: stereo_event_gt_sampling
    filter_by_min_points: ['Vehicle:5', 'Pedestrian:1']
  SAMPLE_GROUPS: ['Vehicle:4', 'Pedestrian:8']
```

实现在 `liga/datasets/augmentor/stereo_event_database_sampler.py`。即：**竞品
每个训练样本粘贴至多 8 个行人 + 4 辆车的事件实例**（行人最低点数门槛仅 1）。
附录 C 当时只检查了 `stereo_data_augmentor.py` 的 crop/flip 段，漏掉了
DB-sampler 增广阶段——这是"审计必须核到调用点"（F27 教训）在竞品代码上的复发。

**影响**：

1. 配方差分表新增一行数据侧差异（与 #1 标签分配同级）：竞品行人 3.6448 是在
   **稠密分配 + 放宽判据 + 8 行人/样本 copy-paste + 60 epoch** 的联合配方下取得。
2. SEIT 的定位从"我们独有的新增广"修正为"补齐配方缺口的更强形态"（立体一致、
   深度重缩放、密度补偿、遮挡语义、覆盖率守卫是相对竞品 sampler 的增量）。
3. A3 的 `max_pedestrians_per_sample: 6` 处于竞品 8 的同一量级，剂量不属激进。
4. "R1 镜像 = 竞品唯一增广"的独立支持句需按本条修订（镜像仍是竞品唯一的
   **几何变换**增广，但不是唯一增广）。

**规则**：对竞品做配方差分时，数据管线的每个 stage 列表（augmentor chain、
sampler、resample）都必须逐项列举后再下"没有 X"的结论；"没有 X"类结论必须
附 stage 清单证据。

## C79 | MECHANISM_CONFIRMED | 零训练：物体级事件视差的亚像素精度普查

**装置**：`tools/r1_audit/probe_subpixel_disparity.py`（session 522f14）。
继承 C76 的 8 角点表面带判据与 C71-C74 装置纪律。方法：全窗（50ms）计数图
ZNCC 峰 + 三点抛物线亚像素细化；以两个不相交 25ms 半窗的独立估计之差
|d_A−d_B| 为精度上界（含真实物体运动与半量事件噪声，双重保守）；逐 box 容差
tol_d = f·B·l·(1−t)/(1+t)/Z²（附录 D §2.3 公式，l 用逐框实际长度）。

**控制臂**（全过）：
- 合成分数位移正控制（0.30/0.70px 线性插值注入）：恢复中位误差
  train 0.129px / val 0.141px ≤ 0.25px 门 → 装置具备亚像素功效；
- 错行负控制（dy=+40）：带命中率 9.2%/9.4%，对照主臂 57-80% → 测的是极线对应；
- H2b 装置健康：带命中@±2px 与 C76 收据同量级（train 0.65-0.80 主桶）。

**读数**（中位 |d_A−d_B| px / 中位 tol_d px / ≤tol 比例）：

| 类 | 深度 | train | val |
|---|---|---|---|
| Pedestrian | 10-20m | **0.203 / 0.489 / 70%** (n=10) | 0.076 / 0.610 / 100% (n=2) |
| Pedestrian | 20-30m | 0.549 / 0.130 / 14% (n=7) | 2.913 / 0.141 / 0% (n=2) |
| Vehicle | 10-20m | 0.312 / 1.487 / 81% (n=31) | 0.337 / 1.318 / 89% (n=28) |
| Vehicle | 20-30m | 0.267 / 0.408 / 64% (n=28) | 0.208 / 0.472 / 77% (n=30) |
| Vehicle | 30-45m | 0.238 / 0.219 / 53% (n=34) | 0.118 / 0.231 / 66% (n=29) |

**推论**：

1. **行人 strict 所需的亚 0.5px 物体级视差在 10-20m 物理可达**（朴素 ZNCC 即达
   0.2px），车辆到 45m 大体可达 → P4A 判 MAP_LIMITED 的稠密图确实把物理可达
   精度留在了桌上，"对象条件稀疏对应"方向有精度预算。
2. 行人 20-30m+ 需 0.13px、实测 0.55px：**物理接近不可达**，主张与剂量应集中在
   ≲20-25m 行人（该段承载行人 strict AP 的主要质量）与全距离车辆。
3. 本条只证明**精度可行域**，不是 C52/C69 冻结的 ~0.95 truth-beats-wrong
   判别性复活线：M3 类机制的授权门仍是 R1' 预训练描述子探针，本条不得替代。

**限制**：n 小（train 120 / val 106 box）；重复性含运动（保守上界）；
表面→中心偏移需学习头/多峰后验解决，本装置未测该项。

---

## C80 | ENV_TRAP | 单卡工具禁传非 0 设备索引 + 本机 CUDA 枚举顺序与 nvidia-smi 不一致

**现象**（A3 期间 epoch-1 诊断冒烟，session 522f14 runB-smoke）：
`diagnose_arm.py --device cuda:1` 在 c2 val 前向 161 秒处崩溃：
`CUBLAS_STATUS_EXECUTION_FAILED`，栈顶是 `ms_deform_attn.py:164 output_proj`
（自定义 MSDeformAttn kernel 之后第一个 cublas 调用——异步错误的冒泡点）。

**裁决实验**（单变量，同一块物理卡）：
- 尝试 1：8 卡可见 + `--device cuda:1` → 崩（PID 1415644，物理总线 56:00.0）；
- 尝试 2：`CUDA_VISIBLE_DEVICES=1` + `--device cuda:0` → **同一物理总线 56:00.0、
  同一邻居负载**，干净跑过崩溃点（13.9GB 已分配，>12min 无错）。
硬件/共卡争抢假设被排除；确认根因 = 自定义算子在**进程内非 0 设备索引**上的
当前设备上下文错配（工具未调 `torch.cuda.set_device`）。

**陷阱 2（同时暴露）**：`/proc/<pid>/environ` 证实 `CUDA_VISIBLE_DEVICES=1` 生效，
但落到的物理卡是总线 56:00.0 = **nvidia-smi GPU 2**（当时与他人 7.2GB 任务共卡），
而非预期的 nvidia-smi GPU 1（总线 52:00.0，空闲）。即本机 **CUDA 默认枚举顺序 ≠
PCI/nvidia-smi 顺序**（索引 1/2 互换）。

**规则**：
1. 本仓所有单进程 GPU 工具（diagnose_arm、c2、eval、探针）一律以
   `CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<smi编号> ... --device cuda:0`
   方式调起；禁止把非 0 的 `cuda:N` 传进冻结工具（工具哈希被 repo_contract pin，
   不改代码，靠调用约定守住）。
2. 按 nvidia-smi 挑空闲卡时必须带 `CUDA_DEVICE_ORDER=PCI_BUS_ID`，否则挑错卡。
3. 与 repo_contract "numba CUDA 陷阱"同族（环境陷阱）；`wait_and_train.sh`
   的 CVD-only 约定是既有先例，本条把它明文化到诊断/评测侧。

**后续确认**（runD-official）：正式诊断以该约定在 nvidia-smi GPU 7 上
（`CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=7 --device cuda:0`）
端到端跑完 ~2h37m 无错，约定在生产路径上成立。

---

## C81 | ENV_TRAP | 2026-08-26 上午的三个环境/运维坑：宿主机 GPU 复位链、代理沙箱 cwd、重复排队 launcher 的"假失败"

三个坑同一上午连环出现，浪费约 2 次 × ~20min 诊断 GPU 时 + 数小时人误判风险。
逐条记录现象、根因与规则。

### 坑 1：宿主机级 GPU 驱动退化 → 全机 CUDA 进程团灭（外因，非本仓代码）

**现象与时间链**（证据：train.log、终端 nvidia-smi 快照、runC/runD 日志）：
1. 07:29:46 — 一个新起的 torchrun 在 CUDA lazy init 即崩：
   `device >= 0 && device < num_gpus INTERNAL ASSERT FAILED ... device=3, num_gpus=`
   （报错文本里 num_gpus 数值被截断；CVD=4,5,6,7 却枚举不足 4 卡 → 驱动已开始丢卡）；
2. 09:53 — nvidia-smi 显示 GPU 0 整卡 `ERR!`（温度/功率/利用率全 ERR）；
3. 10:23:22 — **全机所有 CUDA 进程同时消失**（我们的诊断 + 其他用户的
   EventHandsTrain、water-gs 一起死），进程无任何 Python traceback；RAM 余 481G，
   排除 OOM；
4. ~10:30 — 宿主机重启（Xorg PID 2331955→280260，Persistence-M Off→On），
   GPU 0 恢复正常，各用户任务陆续重投。

**根因**：宿主机/驱动级复位事件（外部），不是本仓栈。正式诊断 attempt1
（GPU4，val 6800/11400 @6.7q/s）与 attempt2（val 1200）都是被它杀掉的。

**识别特征**（与代码 bug 区分，下次先查这四条再怀疑自己）：
- 死亡无 traceback、无 exit 日志；
- **跨用户**全机 CUDA 进程同时消失（`nvidia-smi` 进程表对比）；
- nvidia-smi 出现 `ERR!` 卡（复位前的化石证据）；
- 重启后 Xorg/persistenced PID 变化、Persistence-M 状态翻转。

**规则**：长任务（>1h）按"可被随机杀"设计。`diagnose_arm.py` 的
receipt 幂等（`if not receipt.is_file()` 跳过已完成阶段）+ 流式
`c2_progress.log` 是正确纪律，保留；重投前先 `nvidia-smi` 确认无 `ERR!` 卡、
再确认目标卡空闲。

### 坑 2：代理沙箱把 cwd 强制到工作区根 + 禁写工作区外（H8-sandbox）

**现象**：通过沙箱化 bash 启的 3 个 watcher 循环轮询**相对路径**永不触发
（全部空转到超时）；diagnose 启动时
`PermissionError: Errno13 reports/epst4d_v3/a3_joint/diagnostic`。

**根因**：沙箱强制 cwd = 工作区根（`/data1/lyq/code/StereoDETR`），而训练树
`/data1/lyq/code/.epst4d_v3` 在工作区**外**：相对路径解析错位 + mkdir 越界被拒。

**规则**：凡是要在工作区外的树（`.epst4d_v3`、`.epst4d_r1a_frozen`）里跑的
命令，一律非沙箱启动 + 命令内嵌 `cd <绝对路径>`；watcher/轮询只用绝对路径。

### 坑 3：同一 arm 重复排队 wait_and_train + 共享 train.log → 完成的训练看起来"失败"

**现象**：用户 shell 报 `[2] 退出 1`，`train.log` 尾部是 torchrun
ChildFailedError（4 个 rank 全 exitcode 1）——表面上"A3 训练失败了"。

**事实**（差点误判重训 12 小时）：
- `training_log.jsonl` 末行 `{"epoch": 12, "epoch_summary": true}`，
  `epoch_012.pth` 07:29 落盘，`max_epochs: 12` → **job[1] 训练完整完成**；
- 崩的是 job[2]：同配置**重复排队**的第二个 `wait_and_train.sh`，07:29:40 在
  job[1] 释放显卡的瞬间抢到卡启动，撞上已退化的驱动（见坑 1 时间链第 1 条），
  CUDA init 即崩，traceback **append 到同一个 train.log**，把成功信号盖住了。

**根因**：(a) 同一 config 排两份 wait_and_train 无互斥；(b) 用 train.log 尾部
/退出码判断训练成败。

**规则**：
1. 训练成败判据 = `training_log.jsonl` 的 `epoch_summary`（epoch == max_epochs）
   **且** 对应 checkpoint 落盘；train.log 尾部只是"最后一个写入者的遗言"。
2. 同一 arm/config 不排双份 wait_and_train；重投前 `pgrep -f wait_and_train`
   查存量队列。

---

## C82 | GATE_VERDICT_KILL | A3 joint 12-epoch 正式门读数：行人 strict 5× 提升，但车辆 strict −36.8% 触发 KILL；oracle 证明瓶颈在打分不在框

**实验**：
- 训练：`configs/dsec3dod/a3_joint.yaml`，12/12 epoch（GPU 4-7 四卡，
  batch 657/epoch，world_size 4），loss 11.09 → 3.04 单调下降、
  0 次 5× 中位数 spike——机械上完整、无发散（epoch_001 22:10 →
  epoch_012 8月26 07:29 落盘）。
- 诊断：`diagnose_arm.py`，checkpoint `epoch_012.pth`
  （sha256 `570012434b30…ff79237`），GPU 7 按 C80 约定，10:47 起跑、
  13:24 完成（~2h37m：val 11400q 升速至 4.7q/s ≈40min +
  train-split 2000q @0.31q/s ≈1.8h 占大头 + evals 数分钟）。
- 收据：`reports/epst4d_v3/a3_joint/diagnostic/`
  `{DASHBOARD, C2_BOTTLENECK, official_model, official_oracle}.json`。
  epoch-1 冒烟收据在 `../diagnostic_smoke_ep001/`（KILL 空读数，见其内
  `SMOKE_ONLY_NOT_A_GATE.md`）。

**门判定：KILL**（双条同触）：
- pass 未达：veh_strict 3.954 < 8.0215 且 ped_strict 0.943 < 3.6448
  （门要求双班同过竞品公开 ckpt 线）；
- kill 触发：veh_strict 相对 R1 **−36.8%**（6.2552 → 3.9536，限额 20%）。

**读数**（官方 moderate R40）：

| 指标 | A3 | R1 基线 | 竞品公开 ckpt | A3 oracle（同框、3D-IoU 当分数） |
|---|---:|---:|---:|---:|
| 行人 3D strict | **0.943** | 0.190 | 3.645 | **3.653** |
| 车辆 3D strict | **3.954** | 6.255 | 8.022 | **7.818** |
| 行人 3D loose | 4.548 | 1.521 | — | 7.873 |
| 车辆 3D loose | 25.664 | 25.205 | — | 22.739 |
| 行人 2D | 11.103 | 5.755 | — | 10.143 |
| 车辆 2D | 19.513 | 16.172 | — | 13.093 |

**机制解读**（按缺陷面）：

1. **行人轴真实移动**：strict 0.190→0.943（5×）、loose 1.52→4.55、
   2D 5.76→11.10；框质量（面 3）0.234→0.364；近距证据覆盖（面 4）
   0-10m 0.715→0.927。与 C79（10-20m 行人亚像素物理可达）一致：
   SEIT/实例多样性这条轴有效。
2. **车辆 strict 崩塌 = 打分崩塌（面 1），是 KILL 的直接原因**：
   2D/loose 不掉反升（19.5 / 25.7），strict 却 6.26→3.95 —— 定位还在，
   IoU 0.7 级的深度/尺寸精度分数没了。紧覆盖框中位分数 **0.547→0.129**
   （−76%）；Spearman 反而 0.332→0.452（排序略好、绝对分数塌，
   好框被阈值/NMS 滤掉）。
3. **oracle 把责任钉在打分而不是框**：行人 oracle strict **3.653 ≈ 竞品
   3.6448**——当前框集合里已经有竞品量级的行人 strict，被模型分数压到
   0.943（oracle gap 2.71，比 R1 时代的 1.68 更大）；车辆 oracle 7.82 ≈
   竞品 8.02。车辆 oracle 的 2D/loose 反而低于模型分数（负 gap）：分数在
   宽判据上过拟合、在 strict 3D 上欠校准。
4. **行人证据边界向近距集中**（面 4）：0-10m +0.21，但 10-20m −0.05、
   20-30m −0.08、30m+ −0.05 全段回退——copy-paste 剂量把覆盖挪到了近处。
5. **远距行人可证伪线未过**（面 2）：val/train 远行人比 0.0052→0.0280，
   仍 < 0.05 门（train_mean 0.680 vs val_mean 0.019）。与 C79 推论 2 一致
   （20-30m 需 0.13px、实测 0.55px，物理接近不可达）。
6. 面 5/6（梯度冲突、合成伪影）：A3 训练日志未记录该两项观测（samples=0），
   本轮无读数。

**对后续臂的约束**：
1. A3 不能作为联合胜出配方复投；车辆 −37% 是硬 KILL。
2. 下一刀应打**车辆 strict 的分数校准/深度精度**，不是加行人剂量
   （C78：竞品 8 行人/样本，A3 的 6 不激进；行人剂量也不解释车辆掉点）。
3. 行人 strict 的主瓶颈已被 oracle 定位为**打分**（框集合够到竞品线）：
   score head / 质量估计 / NMS 排序是下一臂的第一优先级。
4. 远距（>20-25m）行人不设主张（物理边界，C79）。

**限制**：单臂单 seed；faces 5/6 缺观测；oracle 用官方 3D-IoU 重排序，
是"框存在性"上界，不含 NMS 交互的反事实。

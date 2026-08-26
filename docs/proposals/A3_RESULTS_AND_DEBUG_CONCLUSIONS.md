# A3 臂结果与 debug 结论（session 522f14，**已于 2026-08-27 合入账本**）

**配套文档：** `docs/proposals/C78_C82_LEDGER_ENTRIES_DRAFT.md`（本会话五条账本
条目全文）、`docs/proposals/A1_A2_RESULTS_AND_DEBUG_CONCLUSIONS.md`（前序臂，
其 §6 预注册了 A3 的证据链，本文档闭环）、`docs/proposals/SEIT_PREREG_DRAFT.md`。

**合入状态：** KILL 判定与 oracle 归因进 `docs/EXPERIMENTS_AND_PITFALLS.md`
§3.7 与附录 B 的 C82 条目，读数进其第 2 节记分板。本文件保留为逐字原件，
未被删除；按账本第 7 节的事实优先级，本文件高于账本汇总。

---

## 0. 身份

- 臂：`a3_joint`（hybrid matching + SEIT 联合配方），
  `configs/dsec3dod/a3_joint.yaml`，`max_pedestrians_per_sample: 6`。
- 训练：12/12 epoch，GPU 4-7 四卡，8月25 晚起跑 → 8月26 07:29 完成
  （epoch_001 22:10 → epoch_012 07:29，~51min/epoch）；
  loss 11.09 → 3.04 单调、0 次 5× spike——机械上完整、无发散。
- 正式判定 checkpoint：`epoch_012.pth`（sha256 `570012434b30…ff79237`）。
- 诊断：`diagnose_arm.py` 在 nvidia-smi GPU 7（C80 约定调起），
  10:47 → 13:24（~2h37m）。收据：
  `/data1/lyq/code/.epst4d_v3/reports/epst4d_v3/a3_joint/diagnostic/`。
- 会话内零训练审计：竞品配方复核（C78）、亚像素视差普查（C79，
  装置 `tools/r1_audit/probe_subpixel_disparity.py` 留档可复跑）。

## 1. 记分板（moderate R40）

| 指标 | A3 | R1 基线 | EvStereo3D 公开 ckpt | A3 oracle（同框、3D-IoU 当分数） |
|---|---:|---:|---:|---:|
| 行人 3D strict | **0.943** | 0.190 | 3.645 | **3.653** |
| 车辆 3D strict | **3.954** | 6.255 | 8.022 | **7.818** |
| 行人 3D loose | 4.548 | 1.521 | — | 7.873 |
| 车辆 3D loose | 25.664 | 25.205 | — | 22.739 |
| 行人 2D | 11.103 | 5.755 | — | 10.143 |
| 车辆 2D | 19.513 | 16.172 | — | 13.093 |

**门判定：KILL**（双条同触）：pass 未达（veh 3.954 < 8.0215 且
ped 0.943 < 3.6448，门要求双班同过）；kill 触发（veh_strict 相对 R1
**−36.8%**，6.2552 → 3.9536，限额 20%）。

## 2. 主结论

### 2.1 行人轴真实移动，SEIT/实例多样性方向有效

strict 0.190→0.943（**5×**）、loose 1.52→4.55、2D 5.76→11.10；
框质量 0.234→0.364；0-10m 证据覆盖 0.715→0.927。与 C79 零训练普查一致
（10-20m 行人亚像素视差 0.2px 物理可达、容差 0.49px）。

### 2.2 车辆 strict 崩塌 = 打分崩塌，是 KILL 的直接原因

三条运行时证据钉死"分数塌了而不是框没了"：
1. 2D/loose 不掉反升（19.5 / 25.7）而 strict 6.26→3.95——定位还在，
   IoU 0.7 级精度的**分数**没了；
2. 紧覆盖框中位分数 **0.547 → 0.129（−76%）**（行人本就贴地：0.013→0.016）；
3. Spearman 反升 0.332→0.452——排序变好、绝对分数塌，好框被阈值/NMS 滤掉。

### 2.3 oracle 把行人瓶颈也钉在打分，不在框

同一批预测框、用官方 3D-IoU 当分数重排：行人 strict **3.653 ≈ 竞品 3.6448**。
即**框集合里已经有竞品量级的行人 strict**，被模型分数压到 0.943
（oracle gap 2.71，比 R1 时代 1.68 更大）；车辆 oracle 7.82 ≈ 竞品 8.02。
下一臂第一优先级 = score head / 质量估计 / 排序校准。

### 2.4 远距行人可证伪线仍未过，且剂量把覆盖挤向近距

far-ped val/train 比 0.0052 → 0.0280，仍 < 0.05 门。行人证据边界
0-10m +0.21 但 10m 以上全段回退（10-20m −0.05、20-30m −0.08、30m+ −0.05）
——copy-paste 剂量把覆盖挪到了近处。与 C79 推论一致：20-30m 行人需
0.13px、实测 0.55px，物理接近不可达，**>20-25m 不设主张**。

## 3. 本会话裁决的假设（全部有运行时证据）

| 假设 | 裁决 | 关键证据 |
|---|---|---|
| H2a 物体级事件视差可达 strict 容差（10-20m 行人） | **确认** | 普查 0.203px vs 容差 0.489px，70% ≤tol；正控制 0.129/0.141px 过 0.25px 门 |
| H2b 装置健康（复现 C76 带命中） | **确认** | 带命中@±2px 0.65-0.80 主桶；错行负控制 9.2%/9.4% |
| H6 diagnose_arm 崩溃 = 非 0 设备索引上下文错配 | **确认** | 单变量：同一物理卡（总线 56），`cuda:1` 崩 / `CVD=1 + cuda:0` 干净跑过 |
| H7 本机 CUDA 枚举序 = nvidia-smi 序 | **否决** | CVD=1 落到 smi GPU2（总线 56），非 GPU1（总线 52）；修正 = `CUDA_DEVICE_ORDER=PCI_BUS_ID` |
| H8 watcher/诊断静默失效 = 沙箱 cwd/权限 | **确认** | 3 个 watcher 相对路径空转；mkdir 工作区外 Errno13；非沙箱 + 内嵌 cd 后消失 |
| H9 诊断两次死亡 = 本仓代码 bug | **否决（外因）** | 无 traceback、跨用户全机 CUDA 进程同时消失、GPU0 `ERR!`、随后宿主机重启 |
| "A3 训练失败"（shell 报退出 1） | **否决** | `training_log.jsonl` epoch_summary 12/12 + epoch_012.pth 落盘；崩的是重复排队的 job[2]（CUDA init 撞退化驱动） |

## 4. 实验时间线（runId 与耗时）

| 轮次 | 内容 | 结果 |
|---|---|---|
| runA-train/val | 零训练亚像素普查（226 box） | C79 读数，正负控制全过 |
| runB-smoke | 崩溃裁决 + epoch-1 流水线冒烟 | C80 确立调用约定；流水线 1h56m 机械验证过 |
| runC-official | 正式诊断两次被杀取证 | H8/H9 裁决（沙箱 + 宿主机复位链） |
| runD-official | 重启后第三次正式诊断（GPU7） | 2h37m 完成，KILL 判定落账 |

诊断耗时结构（供以后估 ETA）：val 11400q 升速至 ~4.7q/s ≈ 40min；
**train-split 2000q @ ~0.31q/s ≈ 1.8h 是大头**；官方 eval/oracle/dashboard 数分钟。

## 5. 踩坑与规则（详见 C80/C81 条目全文）

1. **单卡工具禁传非 0 `cuda:N`**；一律
   `CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<smi编号> … --device cuda:0`
   （C80，已在 runD 生产路径验证）。
2. **宿主机复位事件的识别四特征**：无 traceback / 跨用户团灭 /
   nvidia-smi `ERR!` 卡 / 重启后 Xorg PID 变化——先查这四条再怀疑自己代码（C81.1）。
3. **工作区外的树一律非沙箱 + 内嵌 `cd`**，watcher 只用绝对路径（C81.2）。
4. **训练成败判据 = `training_log.jsonl` epoch_summary + checkpoint 落盘**，
   train.log 尾部只是"最后一个写入者的遗言"；同一 config 不排双份
   wait_and_train（C81.3）。

## 6. 对下一臂的约束

1. A3 不得作为联合胜出配方复投（车辆 −37% 硬 KILL）。
2. 下一刀 = **车辆 strict 分数校准/深度精度**；不是加行人剂量
   （C78：竞品 8 行人/样本，A3 的 6 不激进，且剂量不解释车辆掉点）。
3. 行人 strict 主瓶颈已被 oracle 定位为**打分**（框集合够到竞品线 3.65）。
4. faces 5/6（梯度冲突、合成伪影）本轮 samples=0，下一臂训练日志应补记。

## 7. 清理状态

- 会话 NDJSON 证据日志已删（读数以本文与 C78_C82 草稿表格为准）；
- 探针 `tools/r1_audit/probe_subpixel_disparity.py` 按惯例留档（同
  `audit_stereo_geometry.py` 先例），可复跑复核 C79；
- 诊断收据全部留存于 `reports/epst4d_v3/a3_joint/diagnostic/`
  （冒烟收据在 `../diagnostic_smoke_ep001/`，带 `SMOKE_ONLY_NOT_A_GATE.md` 防误读）;
- 冻结训练树零改动（tools/lib/configs 无本会话插桩）；无遗留进程。

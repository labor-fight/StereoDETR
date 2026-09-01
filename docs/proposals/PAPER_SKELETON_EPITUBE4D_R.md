# 论文骨架:EpiTube4D-R(工作名),目标 CVPR/NeurIPS

**状态:** 骨架 v1(2026-08-31,session f223df)。数字占位符 `[]` 只能由冻结收据填充;
每张表注明收据路径。写作纪律:内部裁决一律 R40 strict;AP11 只出现在与公开权重
对照的列(F26);对比只对 **public checkpoint 口径**(8.0215/3.6448)宣称,论文
headline(19.62/12.93)按 comparator identity 未闭合如实分列(三列制)。

## 0. 标题候选

1. *Ranking the Evidence: Sparse Query-Conditioned Epipolar Readout for
   Stereo-Event 4D Object Detection*
2. *EpiTube4D: Measurement-Driven 4D Detection from Stereo Event Streams*
3. (中文备忘)"证据排序视角下的双目事件 4D 检测"

## 1. 叙事主线(测量驱动,三段式)

1. **诊断**:在唯一的纯事件双目 3D 检测基准(DSEC-3DOD)上,oracle 分解显示
   稀疏 query 检测器的框集合天花板已达/超过 SOTA(Veh 11.39 vs 8.02;
   OERD 修正后 Ped 6.63 vs 3.64,f223df 口径),缺口几乎全在
   **打分/排序与深度监督质量**,而不在提案能力。
   收据:C2_BOTTLENECK 系列、`ORACLE_AFTER_OERD.json`。
2. **机制**:三个各自答复一条测量的组件:
   (a) 深度监督修复捆绑(时刻对齐/栅格统一/软目标——Q13,攻 k≤0.43 收缩面);
   (b) 查询条件对极证据读出 QC-EER(可学习 OERD,含类条件表面→中心偏移,
       攻"证据通道缺失",零参数版先胜出再证明可学习增量);
   (c) strict-质量对齐打分(iou_3d 对齐目标,ARM-SCORE,攻排序效率)。
3. **4D 定位**:输出契约 = 流式时间上任意查询时刻的无序 3D 框集(无 ID,
   与 DetAny4D 惯例对齐);时间机制(TubeState)只有通过时间戳破坏 falsifier
   才进正文,否则 4D 由任务契约与任意时刻查询能力承载。

审稿人拿不到"模块堆砌"的把柄:每个组件先有失败/瓶颈测量,后有机制,再有
破坏对照。C41/A1/D1/E1 的负结果作为设计依据写进正文(诚实性即卖点)。

## 2. 章节结构

- §1 Intro:诊断故事(oracle 分解图作 Fig.1)
- §2 Related:双目 RGB 3D(DSGN/LIGA/RTS3D/SIDE/DSC3D/StereoDETR/DDStereo)、
  事件双目深度(TES/EMatch/IED2S/DERD)、事件检测(RVT/SAST/SSM)、
  流式 3D(StreamPETR/Sparse4D/StreamDSGN)、EvStereo3D/Ev-3DOD/DetAny4D
- §3 Method:任务契约 → 基座 → 三机制(按叙事顺序) → 训练配方
- §4 Experiments:主表 + 消融 + 破坏对照 + 分层诊断
- §5 Limitations:>20m 行人物理边界(C79)、comparator identity 边界

## 3. 反相似表(正文 Table,防"像 EvStereo3D")

| 维度 | EvStereo3D(ICCV25) | 本文 |
|---|---|---|
| 候选 | 0.2m BEV 网格稠密 anchor | 稀疏时空 query(50×11 组) |
| 立体几何 | 全图 plane-sweep 代价体(maxdisp 288) | 候选条件化对极带稀疏读出,无全图体 |
| 时间 | 逐时间片独立推理 | 跨子帧状态/任意时刻查询(通过 falsifier 才宣称) |
| 深度语义 | 代价体 CE | 证据残差 + 类条件表面→中心偏移 |
| 打分 | focal + 3D NMS | strict-3D-IoU 对齐目标 + 证据通道 |
| 阶段 | 两阶段(ROI 精化) | 单阶段,读出即精化 |

破坏性检验承诺(正文写明):去掉跨视图对应/打乱时间戳后指标增益若不消失,
对应差异化主张撤回。

## 4. 实验表设计(每格标注收据来源)

**T1 主表(val 11,400 query,官方冻结评测器):**
三列制——EvStereo3D paper(转引,注明 artifact 未闭合)/ EvStereo3D public
checkpoint(逐位 parity 评测器,C72)/ 本文(3 seeds mean±std,F29)。
指标:Veh/Ped 3D R40 strict(主)+ AP11(对照列)+ loose(附录)。

**T2 组件消融(matched-epoch 配对,每行单变量):**
基座(Q12 配方)→ +ARM-DEPTH(Q13)→ +ARM-SCORE → +QC-EER → +OERD 推理组件
→(条件)+TubeState。收据:各臂链评测 + 预注册判门文件。

**T3 破坏对照(挑战案例 E3 纪律):**
时间戳块打乱 / 右目匹配供体置换 / 极性打乱 / OERD 配对抖动 null(Z1 先例)
/ 左目 parity。每行给出"移除增益百分比"。

**T4 诊断(解释性,不作主张):**
oracle 天花板与排序效率演化(f223df 口径,标注定义);行人分深度段
(0-10/10-20/>20m,>20m 只报告不主张,C79);紧覆盖分数中位。

**图:**Fig.1 oracle 分解;Fig.2 架构;Fig.3 QC-EER 剖面可视化(真带 vs 负控,
Z1 rig 数据);Fig.4 分深度段增益;Fig.5 时间机制消融(若 TubeState 过门)。

## 5. Claim 边界(硬约束,来自 countersearch + 台账)

**永久禁语:**"first stereo-event continuous-time 3D detector"(EvStereo3D 占)、
"first continuous-time 3D detection"(Ev-3DOD)、"first 4D detection"(DetAny4D)、
"首个 posterior fusion"(ARES)、超过 19.62/12.93 的任何暗示(除非 comparator
identity 闭合)。

**安全定位:**"首个具有跨时刻状态传播与 strict-质量证据排序的稀疏 query 双目
事件 4D 检测器"(投稿前复查 2026 下半年 arXiv;C124:每个卖点先在 R40 上、
补齐对手行后重读)。

**SEIT 增广、盲时段对比**:前者作 recipe 披露;后者按 C124 修正后的表述
(行人侧方向差异,过 bootstrap CI 才写)。

## 6. 红队预案(rebuttal 弹药库)

| 攻击 | 防线 |
|---|---|
| "OERD 是推理期 hack" | QC-EER 端到端化 + 零参数版作消融基线;null 对照(Z1) |
| "与 EvStereo3D 相似" | 反相似表 + 破坏性检验;无全图代价体在代码可验(NoDenseVolume 守卫) |
| "4D 只是逐帧 3D" | TubeState falsifier;任意时刻查询协议;若未过门则不宣称时间机制 |
| "行人物理封顶" | C79 物理表 + 分层报告;主张限定 ≤20m,基准指标含封顶仍越线 |
| "60ep vs 36ep 不公平" | 三列制 + artifact 差异清单(35 缺失 tensor、epoch22 等) |
| "cherry-pick seed" | 3 seeds 全报 + 配对差(F 台账纪律) |

## 7. 待填依赖(按时间序)

1. Q13 链读数(e012 判门 → e036 终态)——训练中;
2. ARM-SCORE / ARM-EVIDENCE 臂裁决(各 12ep 侦察);
3. 终局合成 + 3 seeds;
4. TubeState(条件项);
5. 主表数字冻结后才允许写 abstract 的数字句。

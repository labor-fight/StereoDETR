# ARM-TIME 预注册(TubeState:跨子帧查询状态传播,4D 机制)

**执行状态:** 草稿,未执行,**本轮不实现代码**(dataloader 需改为序列批,工程成本
"大",见代码审计)。冻结时点 2026-08-31(session f223df)。
入场条件(硬):ARM-SCORE 或 ARM-EVIDENCE 至少一个 PASS 落账(F00/F17 纪律:
时间机制不得在深度/打分未修复前进场,否则增益不可归因)。

**机制主张(单变量):** query 状态沿 interval 内 10 个子帧递归传播(GRU 起步,
SSM 备选),参考点随状态前进,损失落在全部子帧的**时间对齐目标**上(依赖 Q13 的
`depth_gt_temporal_align`,否则子帧监督本身是错的);跨 interval 流式推理时状态
延续,任意查询时刻由传播态 + 当前事件出框。

## 0. 动机(收据 + 已核实的空位)

- 竞品**无时序递归**,逐时间片独立推理(MASTER_ARM_QUEUE §0,agent1 三更正之一);
- DSEC-3DOD 数据契约本身是 interval×10 子帧结构,现有管线把 10 个子帧当独立样本,
  时间结构未被任何机制使用;
- 文献空位(2026-08 检索):StreamPETR/Sparse4D 式 query 传播 × 双目事件未被占据;
  StreamDSGN 占 RGB 双目流式,DetAny4D 占 RGB 4D 命名(文献代理调研,检索有限);
- C124 警告:旧"盲时段增益"卖点在 R40 口径下不成立(对手 +45.1% vs 我方 +4.5%),
  时间主张必须重新用 R40 + 补齐对手行测量。

## 1. 装置

`model.tube_state.enabled`(默认 false):decoder query embedding 经 GRUCell 跨子帧
传播;每子帧用当前事件表示 forward;匹配与损失逐子帧独立(仍无 ID、无跨帧分配损失,
输出契约 = 每查询时刻无序 3D 框集)。dataloader 改为按 interval 采样连续子帧序列
(序列长度 = 预算允许的 4–10,梯度截断跨度冻结后不扫)。

## 2. 门(冻结)

- 基座 = 前序胜者配方,唯一 diff = `tube_state.enabled: true`;12ep 侦察,
  e009/e012 均值(F29)。
- **G1**:双类 strict ≥ 对照 ×0.97,且至少一类绝对增量 ≥ +0.50。
- **G2(时间必要性,4D 主张的生死线)**:时间戳块打乱(子帧顺序破坏)或状态冻结
  (h_t ≡ h_0)消融移除 ≥50% 增益;否则**撤下 4D 时间主张**,机制删除,任务命名
  仍按输出契约成立(挑战案例:"4D 命名不能替代操作性时间机制")。
- **G3(诊断,非门)**:流式一致性/抖动指标(相邻子帧同物体框中心漂移),只作
  论文机制解释,不替代主裁决量(机会图谱纪律:diagnostic 不替代 confirmatory)。
- **Kill**:G1 失败即删;不得用"加长序列/加大状态维度"抢救(F08 加重教训)。

## 3. 不做什么

- 不引入 track ID、ReID、跨帧分配损失、轨迹头(任务契约明确排除);
- 不做显式 ego-motion warp 进主方法(F17:陈旧深度对齐已判 PROXY_INVALID;
  ego 补偿只允许以"可选 nuisance 消融"出现,且必须来自 event-only 输入);
- 不在 ARM-SCORE/ARM-EVIDENCE 未裁决前占用 GPU 臂位。

## 4. 实现落点(留档,本轮不动代码)

`.ep4d_q1`:dataloader 增加 interval-sequence 采样模式(不改 manifest 与评测);
`lib/models/event4d/tube_state.py`;训练循环子帧内共享 encoder 前向、逐子帧 decode。
预估工程量:dataloader 序列化(中)、显存×序列长(需按 F21/F23 先例重探 batch 形状)。

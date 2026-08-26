# SEIT 预注册（ARM-AUG 强化形态，**已执行 = A2/A3 臂，Gate FAIL / KILL**）

**执行状态：** 本预注册于 2026-08-25 冻结并作为 A2 臂执行（FAIL：Veh
6.2552→5.0090、Ped 0.1896→0.6686，天花板 +78% 而排序效率 −17.9%），随后以
`max_pedestrians_per_sample: 6` 的加大剂量进入 A3 联合臂（KILL：Veh −36.8%）。
结果见 `A1_A2_RESULTS_AND_DEBUG_CONCLUSIONS.md` 与
`A3_RESULTS_AND_DEBUG_CONCLUSIONS.md`，已合入 `docs/EXPERIMENTS_AND_PITFALLS.md`
§3.7 与附录 B 的 C82。SEIT 现为**预备役**：仅当 P6 后行人天花板仍不足时，按 C54
最小类门与 C82 约束单独预注册重开。本文件按预注册惯例只读，不因结果改写。

Stereo-consistent Event Instance Transplant：立体一致的事件实例移植
数据引擎。打击目标 = L1 实例稀缺（134 行人身份 → 泛化崩塌，T1/C66）。

## 0. 动机（全部有收据）

- 行人 15-20m 分类概率 train 0.690 → val 0.0036（192 倍崩塌，C2 收据）；
- 行人 3D IoU≥0.5 召回仅 0.234（框回归质量差，C2 收据）；
- oracle 打分上限 1.87 << EvStereo3D 3.64 → 打分修复之外必须造几何多样性；
- C62：mirror 对 134 身份只翻面不产生新几何 → 深度/位置重采样才是把重复
  转化为多样性的方式；
- 物理可行性已验证（C77.2：移植命中 0.75-1.00 ≥ 真实基准，控制 4/4）。

## 1. 装置（在线增广，dataset 层合成，不改 manifest、不写磁盘样本）

1. **供体池**（离线一次性构建，产物只有索引 json）：
   train split、manual 帧、Pedestrian 与 Vehicle 分池；条件：z∈[6,30]m、
   投影宽 ≥12px、完整在画（边缘 margin 10px）、原位表面带审计命中
   （复用 `audit_stereo_geometry.py` 的判据函数）。记录：record_id、
   box 索引、双视图事件管索引区间、几何元数据。
2. **提取**：左视图 box 投影区 ±2px；右视图 [x0−d_near−3, x1−d_far+3]。
   生产版新增（原型未做，必须补）：
   a. **前景分离**：区内背景事件按"事件-视差一致性"剔除——对区内事件做
      局部 ZNCC 微匹配，视差落在表面带外的判为背景（保守阈值，宁少勿错）；
   b. **供体自遮挡检查**：num_points_in_gt 或 GT disparity 覆盖率低的
      供体丢弃。
3. **变换**：Δu ∈ [−140, +140]px（保持完整在画且右图区不越界）；
   α = z'/z ∈ [0.7, 1.6]；y 按地平面约束调整（用目标场景标定的地平线
   近似，v' = horizon + (v−horizon)/α）；**密度补偿**（修 T2_nearer
   0.75）：α<1 时按 1/α² 对事件做双线性权重复制或时间抖动上采样。
4. **粘贴（遮挡语义）**：
   a. 目标区与目标场景既有 GT box 的 2D IoU > 0.1 时重采位置（≤5 次，
      失败放弃本次移植）;
   b. 移植体默认前景：清除目标区内场景事件（左右视图按各自区域）；
   c. 若目标场景该区 GT disparity 中值 > 移植体视差（即场景内容更近），
      放弃（不做部分遮挡合成，保守）。
5. **标注合成**：boxes_3d 按 (Δu, α) 反投影更新 (X,Y,Z)，尺寸/朝向不变；
   labels 同供体。合成 box 走与真实 box 相同的 target 校验
   （validate_target）。
6. **预算**：每训练样本移植 ≤2 个行人 + ≤1 个车；类别配比使行人有效
   出现次数提升 ≥5×；对空场景（无行人帧）优先注入。
7. **确定性**：per-sample 种子 = hash(record_id, epoch, 全局种子)；
   default-off，config 开关 `seit.enabled`（沿 D1 default-off 先例）。

## 2. 单变量对照与门

- 基线：R1 冻结配方（r1_stereo_flip.yaml + seed 20260812），唯一变量
  = seit.enabled。评测：冻结评测器，moderate R40 strict。
- **通过门**：Pedestrian_3d strict > 1.0 且 Vehicle_3d strict ≥ 5.95
  （允差 −0.3）。
- **强门（后续联合臂目标，不在本臂）**：Ped ≥ 3.6448。
- **kill 条件**：(a) 训练 20% 处合成样本的行人匹配率 < 真实样本的一半
  （在线监控）；(b) val Pedestrian_image 2D AP 相对基线下降 >10%
  （提示合成伪影可辨识）；(c) 任何 NaN/确定性破坏。
- **移植质量抽检**：每 epoch 抽 50 个合成样本跑表面带审计，命中率
  < 0.55 即 kill（低于真实基准 0.667 一个容差）。

## 3. 不做什么

- 不做 EventDrop/稀疏化类删除增广（C26）；不改 manifest 与评测器；
- 不引入外部数据/模型（与 ARM-SSL 互斥性由负责人裁决——本臂替换原
  ARM-AUG 的"epipolar-preserving crop/shift"设计，理由：C62 已证
  几何翻面类增广对行人无效，而位置/深度重采样有 C77.2 物理证据）；
- 不声称身份多样性增加（134 个身份不变，增加的是每身份的几何配置）。

## 4. 实现落点

新分支 from `epst4d-archive`(9446413)；新文件
`lib/datasets/dsec3dod/seit_transplant.py` + 配置
`configs/dsec3dod/seit_arm.yaml`；不修改任何冻结文件本体。

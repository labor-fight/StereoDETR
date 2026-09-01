# ARM-SCORE 预注册 v2(对齐式 3D 质量目标,纯配置臂)

**执行状态:** 草稿 v2,未执行。v1(同日早版)在台账取证后**大幅收缩**:v1 承诺的三个组件
里有两个已被历史臂封死,详见 §0.1。冻结时点 2026-08-31(session f223df),门在任何
本臂 AP 出现前固定。发车条件:Q12/Q13 胜者裁决落账。

**机制主张(单变量):** 把匹配 query 的分类目标从硬 1.0 改为其与 GT 的
**有向 3D IoU**(下限 floor),仅对行人类开启——即已实现的
`losses.hybrid_matching.{iou_aware_classification: true, quality_metric: "iou_3d",
iou_aware_classes: [1]}` 配置路径(`lib/models/epst4d_v3/hybrid_matcher.py::IoUAwareLabelLoss`,
含 `bind_geometry` 与 `camera_boxes_from_encoded` 重建,**零新代码**)。

## 0. 台账约束(本臂设计的边界条件)

### 0.1 v1 撤回的组件及其死刑判决

| v1 组件 | 判决 | 出处 |
|---|---|---|
| Co-DETR 式稠密一对多辅助头 | **已跑过并 FAIL,无复活条款**:D1 臂行人升但 Veh 3D 5.4986<5.9424、Veh oracle 10.04<11.39;C70 测得稠密 cls 头挤占共享主干一半梯度范数 | C68/C70,`GATE_D1.json` |
| "正样本饥饿"动机 | **假设被 P1 梯度审计证伪**:每 GT 恰好 11 个匹配 query,两类紧覆盖未奖励分 Ped 9.47 vs Veh 9.21(比 1.03),分配线关闭(不做 P2/P3) | `P1_GRADIENT_AUDIT.md`,台账 §2 |
| 自由融合式 quality 头(γ 指数融合) | **C41 kill**:γ=0 关闭融合后两类每项指标都变好(Veh 1.838→2.092 等);只许"对齐形式"重开且带同款 kill | 台账 C41、§3 撤销表 |
| 匹配 cost 深度项 | 机制存在(`StableHungarianMatcher.cost_depth`)但权重为 0 是冻结配方;改它是第二变量,本臂不动 | 代码审计 |

### 0.2 C.4 路由义务(打分臂的两项前置)

1. **说明哪个机制移动 val-only 分量**:对齐目标改写的是"分数的含义"(校准),不是特征
   记忆。实测先例:A3 的 iou_2d 行人限定版把 **val** 排序效率 0.102→0.258(A1 全局版
   0.282)——对齐目标的增益已被证明可迁移到 val;3D 轴携带其余排序信息(同框 3D IoU
   重排 0.943→3.653,`IoUAwareLabelLoss` 文档串已记)。
2. **train 侧饱和对照(发车前必测,短 GPU)**:基座 checkpoint 上分别测 train/val 的
   按类 score–3D-IoU Spearman 并落盘。若行人 train 侧 3D-rho 已 ≥0.85(2D 轴先例
   0.91,台账 §2.x),则本臂动机降级,发车需另行修正案。

## 1. 装置

- 配置 diff(唯一变量,против Q12/Q13 胜者配方):

```yaml
losses:
  hybrid_matching:
    enabled: true
    iou_aware_classification: true
    quality_metric: "iou_3d"      # A1/A3 用的是 iou_2d;3D 轴是本臂的新变量
    iou_aware_classes: [1]        # 行人限定(A1 教训:全局开砍车辆天花板 −32.7%)
    quality_floor: 0.25           # 冻结,不扫(C41:kill 即删机制,不调参)
```

- `localisation_cost_scale_by_class` 不开(A3 已含,归因干净起见本臂不带)。
- 历史对照锚:A3 的 iou_2d 行人限定版 = 本臂的直接前驱,其行人 strict 0.943 /
  排序效率 0.258 是"2D 轴天花板"读数;本臂检验的就是 3D 轴增量。

## 2. 门(R40 strict,冻结评测器;12ep 侦察;主门读数 = e009 与 e012 两点均值,报标准差,F29)

- **G1(行人主门)**:Ped strict ≥ 对照 ×1.30。
- **G2(车辆守卫)**:Veh strict ≥ 对照 ×0.95。
- **G3(天花板守卫,A1 教训)**:视图受限 oracle(`oracle_after_oerd.py` 同定义,
  零 GPU 复评)Veh ≥ 对照 ×0.95 且 Ped ≥ 对照 ×0.95。**必须并报解码视图框数**:
  H4 复检(2026-08-31)证明 oracle 只在相近框数下可比——A1 的车辆 oracle 塌陷
  实为视图冗余伪影(26,705 框 vs A3 22,307;覆盖尾部 10.4%≈A2 11.1%),
  不是几何损失。若本臂框数相对对照漂移 >15%,G3 改用覆盖视图
  (`recall_by_iou_3d_threshold` ≥0.70 档)裁决。
- **G4(分数守卫,A3 教训)**:紧覆盖框中位分 ≥ 对照 ×0.8。
- **C41 同款 kill(自动删除条款)**:任一类 strict 两点均值 < 对照 ×0.90 → 删机制;
  不扫 floor/metric/类集合(扫参数 = 拿旋钮拟合门,台账 §16)。
- **联动**:与 ARM-EVIDENCE 不同臂合跑(A3 联合臂教训);若两臂各自 PASS,合并臂
  另行预注册。

## 3. 不做什么

不动解码阈值(H1/H8);不加 NMS(H5);不做逐类分数缩放与车辆证据重打分(Z1 死刑);
不复活稠密辅助头(C68)与自由融合头(C41);不在看到读数后改门。

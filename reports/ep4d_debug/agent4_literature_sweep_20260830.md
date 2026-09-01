# Agent-4 文献侦察 — DSEC-3DOD 双目事件流 3D 检测：可移植机制扫荡（2023–2026）

生成时间 2026-08-30。方法：网络检索 + 论文原文表格逐条抽取。本地只读 `reports/repo_contract.md` 作背景。**未跑任何 GPU 任务。**

目标线：冻结评测器 strict 3D AP moderate R40 **Vehicle > 8.0215 / Pedestrian > 3.6448**（Ev-Stereo3D 公开 ckpt）。我方对照 **5.0077 / 0.6688**。缺口 **+3.01 / +2.98**。

本文所有数字分两类，逐条标注：

- **【收据】** = 论文原表里的数字，可点开原文核对。
- **【估计】** = 我把论文相对增益映射到我方误差预算上的推算，附推算过程。**估计不是收据，不得当门用。**

---

## 0. 三条改变优先级的发现（先看这个）

### 0.1 竞品的"框紧度"模块叫 OCRA，它值 +2.54 mAP —— 这既是路标也是雷区

Ev-Stereo3D（ICCV 2025）Table 3 消融，easy mAP3D（motion×1，time-slice 10）：

| 配置 | mAP 3D | mAP BEV |
|---|---:|---:|
| baseline（仅几何 plane-sweep 体素 G） | 12.92 | 20.78 |
| G+S（加语义体素） | 14.60 | 24.85 |
| G + OCRA | 14.56 | 21.73 |
| DSGF 全套（SDR+GSV，G+S） | 19.12 | 29.64 |
| **DSGF 全套 + OCRA** | **21.66** | **31.52** |

**OCRA（Object-Centric ROI Alignment）单独值 +2.54 mAP3D**【收据】。它的机制是：把 BEV 语义特征按预测框切成 k×k 网格池化，MLP 回归 `ΔP_L = (δx',δy',δz',δh',δw',δl',δθ')` 局部对齐偏移。

**这就是竞品自己的框紧度解法。** 任何"第二阶段 ROI 池化 + 框残差回归"的提案，审稿人第一反应就是"这是 OCRA 换皮"。我方的框紧度路线必须走**非 ROI-refine** 的机制（几何重参数化、尺寸先验、去噪监督），否则相似度分直接拉满。

### 0.2 竞品已经试过 RGB 融合并公开否决了它 —— 这给"训练期蒸馏"留了一扇干净的门

Ev-Stereo3D Table 4【收据】：

| 设置 | 方法 | VEH AP3D | PED AP3D | VEH AP_BEV | PED AP_BEV |
|---|---|---:|---:|---:|---:|
| Motion ×1 | Ours (E) | 23.47 | 19.86 | 40.13 | 22.91 |
| Motion ×1 | Ours (E+I) | 25.23 | 21.50 | 46.21 | 29.14 |
| Motion ×2 | Ours (E) | 22.72 | 19.04 | 39.81 | 22.71 |
| Motion ×2 | **Ours (E+I)** | **20.14** | **10.50** | 37.93 | 12.76 |

他们的结论原话："under large motion, the performance significantly degrades due to misalignment between the synchronous RGB data and the actual object location."

关键区分：**他们否决的是推理期融合，不是训练期蒸馏。** 训练期 RGB 教师 + 推理期纯事件学生，完全绕开了"blind-time 没有 RGB"这个物理事实，因为学生根本不需要 RGB。这条路在论文叙事上是干净的差异化。**但它有一个我方独有的硬限制，见 §3.3 和 battle log #3。**

### 0.3 行人深度的两条物理路各有各的死法 —— 这决定了行人打法必须是"近中程修深度 + 远程降分数"

台账收据说"30–40m 处等效视差 0.05–0.07px，立体匹配物理极限之下，行人深度实际主要来自身高先验"。我把两条路都算到底（f·B = 349.5 px·m，DSEC 基线 0.6m → f ≈ 582.5px）：

| 路线 | 30m 处的量 | 达到 0.19m 深度误差所需精度 | 判定 |
|---|---|---|---|
| 立体视差 | d = 349.5/30 = **11.65 px** | Δd = 0.0738 px | 跨视图对应精度 0.074px —— **物理封死** |
| 单目身高投影 | h_2D = 582.5×1.7/30 = **33.0 px** | Δh = 0.209 px（= 0.63% 相对） | 单视图边缘定位 0.21px —— **难但可改进**，像素预算宽 2.8× |
| 身高先验本身 | H_3D 类内 σ ≈ 0.10m / 1.7m = **5.9%** | — | 30m 处深度误差地板 **1.77m**，40m 处 **2.36m** |

**结论（这是本报告最重要的一条）：** 30–40m 的行人，视差路物理封死，身高路被 H_3D 类内方差封死在 1.8–2.4m —— **两条路都到不了 0.19m。** 134 个训练身份意味着不可能学到 per-person 身高。

所以行人的正确打法不是"把所有行人的深度修好"，而是：

1. **近中程（<25m）用几何误差深度头把 median 从 0.2388m 压进 0.19m 门内** —— 这里 H_3D 方差贡献只有 0.7–1.5m 绝对误差在 12–25m，且相对门限更宽；
2. **远程（30–40m）不修深度，改用不确定度把它们的分数压下去** —— 台账的"完美排序 +79% R40"就是这条的收据上限。

第 2 条有一个硬上限必须先说清楚：**0.6688 × 1.79 = 1.197**。也就是说**纯排序改进最多只值 +0.53 行人 AP**，离 +2.98 的缺口差得远。这和台账"纯重排序臂只能作为组件"的否决完全一致，且给出了那条否决的定量理由。**校准必须排在框质量改进之后做**，因为框变好之后完美排序的 oracle 也会跟着抬高。

---

## 方向 1 — 框紧度机制（车辆主线）

### 1.1 MonoDGP 几何误差先验（CVPR 2025）★ 本报告 Top-1 的一半

- **论文**：Pu et al., *MonoDGP: Monocular 3D Object Detection with Decoupled-Query and Geometry-Error Priors*, **CVPR 2025**。
- **机制一句话**：不直接回归深度，而是回归"透视投影公式的残差" `Z = f·H_3D/h_bbox + Z_err`，因为 `Z_err` 只依赖物体自身属性（尺寸、朝向），是透视不变的，分布集中且中位数近零。
- **论文定量收益**【收据】，KITTI val Car AP3D|R40：

| 深度预测模式 | Easy | **Mod.** | Hard |
|---|---:|---:|---:|
| Depth Map | 24.33 | 18.87 | 15.31 |
| Direct Depth | 26.60 | 19.23 | 16.47 |
| Geometric Depth (h_bbox) | 9.15 | 7.99 | 5.52 |
| Geometric Depth (h_c) | 27.63 | 20.73 | 18.04 |
| Weighted Fusion（多深度融合） | 30.57 | 21.64 | 18.74 |
| GD + Bbox Height Error | 28.45 | 21.18 | 17.91 |
| GD + Dim Height Error | 30.46 | 22.09 | 18.85 |
| **GD + Depth Error** | **30.76** | **22.34** | **19.01** |

  行人侧更关键（附录 Table 6，KITTI val Pedestrian AP3D|R40 @IoU=0.5）【收据】：

| 配置 | Ped Easy | **Ped Mod.** | Ped Hard |
|---|---:|---:|---:|
| MonoDGP 完整 | 13.77 | **10.06** | 7.96 |
| w/o Segment Embeddings | 13.02 | 9.67 | 7.66 |
| w/o RSH | 12.50 | 9.42 | 7.34 |
| **w/o Depth Error** | 9.90 | **7.55** | 6.09 |

  **深度误差机制单独在行人上值 +2.51 moderate AP（7.55 → 10.06，+33.2% 相对）**，是三个组件里对行人最大的一个。作者的解释原话："error prediction significantly improves 3D pedestrian prediction compared to cars and cyclists... pedestrians have consistent depth errors across orientations."

  主消融（Table 5，Car）【收据】：baseline 26.56/20.22/17.21 → 完整 30.76/22.34/19.01，即 **+4.20 / +2.12 / +1.80**。四个组件：mixup3D 增广、2D query 解耦初始化、区域分割增强、几何深度误差。

- **映射瓶颈**：**行人深度精度**（主）+ 车辆框紧度（次）。
- **与台账收据的关系**：**强相容，且是台账那句话的正规化。** 台账说"行人深度实际主要来自身高先验"—— MonoDGP 就是把这个隐式行为写成显式的 `f·H_3D/h_2D + Z_err`。一旦显式化，H_3D 与 h_2D 各自的误差就可以被单独监督和诊断，而不是埋在一个黑箱深度头里。
  **一处必须先验证的冲突**：MonoDGP 附录 Table 8 说"网络对 H_3D 误差比对 h_bbox 更敏感"。我方尺寸头已经塌缩到类别众数（斜率 0.24）—— 如果 H_3D 被钉死在众数，`Z_geo` 就退化成 2D 框高的确定性函数。这不必然是坏事（见 §0.3 的像素预算表：身高路的像素预算宽 2.8×），但**它把行人深度问题转化成了行人 2D 框高定位问题，必须先测我方 2D 框高的相对误差是否 < 现有深度相对误差**。这是一次零 GPU 的离线诊断（现有预测 pickle 里就有 2D 框），应当作为 Gate 前置。
- **移植难度**：**低–中。改深度头 + 损失**。我方是 monodetr 系，MonoDGP 就是 MonoDETR 的直系后继，代码结构对齐。不动 query 参数化，不动 backbone。
- **与 Ev-Stereo3D 相似度（审稿人视角）：1/5。** 竞品是 anchor-based BEV 体素两阶段，全篇没有透视投影公式，没有 per-object 几何解码。完全正交。

### 1.2 Dimension Embeddings + 可学习形状模板（CVPR 2022）★ 直击尺寸头塌缩

- **论文**：Zhang et al., *Dimension Embeddings for Monocular 3D Object Detection*, **CVPR 2022**。
- **机制一句话**：把尺寸回归换成"先在 dimension-aware embedding 空间里用方差归一化的 log-ratio 损失约束物体两两距离，再用注意力和一组可学习形状模板交互得到粗尺寸，最后残差精修"。
- **论文定量收益**【收据】，KITTI val Car AP3D@0.7 R40：

| 基线 | Easy | Mod. | Hard |
|---|---:|---:|---:|
| Monodle | 17.13 | 13.96 | 12.00 |
| Monodle + DimEmbed | 20.82 | **15.64** | 13.82 |
| GUPNet | 20.53 | 14.70 | 12.77 |
| GUPNet + DimEmbed | 23.47 | **16.19** | 14.15 |
| AutoShape | 20.02 | 14.30 | 11.70 |
| AutoShape + DimEmbed | 20.95 | 14.99 | 12.33 |

  逐组件（Table 3/4，Car val mod. BEV/3D）【收据】：baseline 13.96 → +embed 14.26 → **+embed+方差归一化 14.78** → +模板 14.37（**单加模板会掉**）→ +模板+辅助解码器 14.82 → +残差精修 15.32 → +注意力锐度正则 **15.64**。额外延迟约 **3ms**。

- **映射瓶颈**：**车辆框紧度 —— 尺寸头向类别众数塌缩（斜率 0.24）**。这是我方车辆瓶颈的字面对应物。
- **与台账收据的关系**：**强相容。** 台账"误差方差的 85% 是真值可解释的系统项"意味着尺寸误差不是噪声，而是一个没被学到的系统映射（外观 → 子类别 → 尺寸）。DimEmbed 的形状模板正是学这个映射。反过来说，"纯降噪干预天花板只有 8%"这条收据恰好解释了为什么单纯加 L1 权重没用 —— 要学的是结构不是降噪。
  **一处已知风险（论文自陈的 Limitations）**：作者写"unclear whether the proposed method can work for anchor-based methods. The concern is raised because the log-ratio loss tends to collapse when multiple anchors have the same target dimensions."我方是 query-based 不是 anchor-based，落在安全侧；但如果我方 query 的正样本分配也导致多个 query 指向同一 GT 尺寸，同样的塌缩风险成立。**移植时必须只在匹配上的 query（每 GT 恰一个）上算 log-ratio 损失。**
- **移植难度**：**低–中。替换尺寸回归头 + 加两个辅助损失**。
- **与 Ev-Stereo3D 相似度：2/5。** 竞品用"fixed-size class anchors, determined based on the training set statistics"—— 那是一个全局类别常数，本质上就是我方正在塌缩到的那个众数。DimEmbed 是 per-instance 的注意力模板。审稿人可能问"你们不就是把他们的类别 anchor 变软了吗"，需要在文里用"斜率 0.24 → 目标斜率"这个指标正面回应。

### 1.3 StereoDistill 的 X-component Guided Distillation（AAAI 2023）

- **论文**：Liu et al., *StereoDistill: Pick the Cream from LiDAR for Distilling Stereo-based 3D Object Detection*, **AAAI 2023**。
- **机制一句话**：不用阈值筛选教师框，而是把 3D 框拆成 center/size/rotation 三个分量，**逐分量**判断"教师−学生"向量与"GT−学生"向量是否成锐角，成锐角才留作软目标。
- **论文定量收益**：KITTI test 上 stereo 3D 检测 SOTA（具体逐分量消融见原文 Table）。核心主张是显著提升正样本软目标数量、降低学生模仿难度。
- **映射瓶颈**：车辆框紧度（尺寸/横向分量）。
- **与台账的关系**：**部分相容。** 可移植内核是"**逐分量锐角门控**"这个筛选规则本身，它不要求教师必须是 LiDAR —— 可以换成 EMA 自教师（见 §8.2 OD-DETR）。用 LiDAR 教师则有公平性争议（竞品是纯事件训练），会被审稿人质疑监督量不对等。
- **移植难度**：**中。加蒸馏损失 + 教师分支**（自 EMA 教师则只加一个 EMA 副本）。
- **与 Ev-Stereo3D 相似度：3/5。** LIGA-Stereo 的 LiDAR 蒸馏是竞品的直系祖先谱系（竞品 baseline 明确 "inspired by [DSGN/LIGA]"）。用 LiDAR 教师 = 走进他们的家谱。用自 EMA 教师则降到 1/5。

### 1.4 其余候选（列而不推）

| 论文 | 机制 | 为什么不推 |
|---|---|---|
| StreamDSGN (NeurIPS 2024) | DSGN++ 的流式版，Feature Flow Fusion + Motion Consistency Loss，KITTI 上比强 baseline 高至 4.3% | 解的是"推理延迟导致的错位"，不是框紧度；且我方无 BEV 大核骨干 |
| SIDE (WACV 2022) | 几何约束后处理精修框 | 与 OCRA 同类，相似度 5/5 |
| Disp R-CNN (CVPR 2020) / OC-Stereo | 实例级视差 + 形状先验 | 需要实例视差网络；且台账已两次否决"稀疏逐点光度匹配" |
| DIRM (2024) | 解耦属性回归 + 交互式质量预测；发现低质框（IoU≤0.5）的 IoU 预测 MSE 是高质框的 **22 倍** | 那条 22× 的观察值得记，但主体是 anchor-based 一阶段 LiDAR 检测器 |

---

## 方向 2 — 分数校准与 IoU-aware（行人主线的组件）

**统一前置约束（本方向所有机制共享）**：台账"完美排序 +79% R40" ⇒ **纯排序改进的绝对上限是 0.6688 × 0.79 = +0.53 行人 AP**。本方向所有机制的期望增益都被这个数封顶。它们只能是组件，不能是主臂 —— 与台账否决"纯重排序臂"一致。

### 2.1 GUPNet++ 的 IoU-guided Uncertainty-Confidence（TPAMI 2024）★ 本方向首选

- **论文**：Lu et al., *GUPNet++: Geometry Uncertainty Propagation Network for Monocular 3D Object Detection*, **TPAMI**（ICCV 2021 GUPNet 的期刊版）。
- **机制一句话**：把深度建模成分布（由 h_2D 与 h_3D 两个高度分布按几何约束传播而来），再把"真值框落在与预测框 IoU≥0.7 的深度区间内的概率"作为 3D 置信度，与 2D 分类分相乘。
- **论文定量收益**【收据】，KITTI val Car 3D@IoU=0.7：

| 配置（Table IV 摘录） | Easy | **Mod.** | Hard |
|---|---:|---:|---:|
| (j) RoI-FR + GeP + GeU++ | 23.56 | 16.53 | 14.24 |
| (k) **+ IoUnC** | 24.76 | **17.43** | 14.78 |
| (l) + β-NLL | 26.08 | 17.85 | 15.10 |
| (n) + NMS3D + DCN | 29.03 | 20.45 | 17.89 |

  **IoUnC 单独 +0.90 moderate AP3D（16.53 → 17.43，+5.4% 相对）**。另外 GUPNet（会议版）报告过对**行人类别 +4.7% AP40**。
- **映射瓶颈**：**行人分数校准**（+79% 头room 的组件），兼带 §0.3 的"远程行人降权"功能 —— 深度不确定度在 30–40m 自然会大，IoUnC 会自动把它们的分数压低，这正是我们想要的行为。
- **与台账的关系**：**相容，且明确规避了否决项。** 台账否决的是"IoU3D 损失（天花板反降 40%）"—— IoUnC **不是**一个 IoU3D 回归损失，它是把已有的深度不确定度经过一个概率积分映射成置信度，不向框回归反传 IoU 梯度。这个区别必须在预注册里写清楚，否则会被误判为已否决路线的重复。
- **移植难度**：**低。加不确定度输出 + 改推理期打分函数**。与 §1.1 的几何误差头天然共生（都要 h_2D/h_3D 分布）。
- **与 Ev-Stereo3D 相似度：2/5。** 竞品是 anchor 分类分，无不确定度建模。

### 2.2 Stable-DINO 位置监督损失（ICCV 2023）/ Align-DETR Align Loss（BMVC 2024）★ 有条件推荐

- **论文**：Liu et al., *Detection Transformer with Stable Matching*, **ICCV 2023**；Cai et al., *Align-DETR: Enhancing End-to-end Object Detection with Aligned Loss*, **BMVC 2024**。
- **机制一句话**：Stable-DINO —— "只用位置度量（IoU）监督正样本的分类分"，消解 DETR 的多优化路径问题；Align-DETR —— 软目标 `t_c = e^{−r/τ}·q`（q 是分类置信×回归精度的联合质量，r 是层内排名），实现正→负样本的平滑过渡。
- **论文定量收益**【收据】，COCO val，DINO/H-DETR ResNet-50 基线（Align-DETR Table 3）：

| 损失 | AP | AP50 | AP75 |
|---|---:|---:|---:|
| Focal Loss | 49.0 | 66.0 | 53.5 |
| IoU branch | 49.2 | 66.3 | 53.5 |
| QFL (GFL) | 47.6 | 64.3 | 51.8 |
| VFL (VarifocalNet) | 48.7 | 67.0 | 52.3 |
| PSL (Stable-DINO) | 49.8 | 66.7 | 54.5 |
| PSL + PMC | 50.2 | 66.7 | 55.0 |
| **Align Loss** | **50.5** | 67.8 | 55.3 |

  注意 **QFL 在 DETR 上是负收益（47.6 < 49.0）**，VFL 也低于 focal（48.7 < 49.0）。这是一条重要的反面收据：dense detector 上有效的质量损失搬到 DETR 上会掉点。Stable-DINO 单独 +0.8，Align Loss +1.5。GFLv2 的 DGQP 在 dense detector 上 ResNet-101 从 ATSS 43.6 → **46.2 AP（+2.6）**；VFNet 相对强 baseline **约 +2.0 AP**【收据】—— 但这两条是 dense detector 的数字，按上表在 DETR 上不成立。

- **映射瓶颈**：行人分数校准。
- **与台账的冲突 —— 红队标红**：Stable-DINO 的核心原则是"use **and only use** positional metrics to supervise classification scores of positive examples"。在我方行人上，**3D IoU 就是那个位置度量，而它正处于物理噪声地板**（§0.3：30–40m 视差需要 0.074px）。把 3D IoU 当分类软目标 ⇒ 远程行人的分类目标 ≈ 0 ⇒ **模型会学会不预测远程行人**。这不是理论担忧：行人只有 134 个训练身份，本来就在过拟合边缘，再把最难的那批的正目标砍掉，很可能直接负收益。
  **可移植的安全变体**：软目标里的质量度量**对行人换成 2D / 投影框 IoU**（这个量可测、不在物理地板上），对车辆才用 3D IoU。这就是任务书里"类别特定校准 —— 注意我们只需要行人侧"那句话的落地方式，且论文本身不覆盖这个变体，是我方的增量。
- **移植难度**：**很低。只改分类损失**（focal 的软目标替换）。
- **与 Ev-Stereo3D 相似度：1/5。** 竞品无 DETR 结构。

### 2.3 长尾/稀有类校准（列作背景，不进 Top-10）

| 论文 | 机制 | 定量【收据】 | 对我方 |
|---|---|---|---|
| Rank & Sort Loss (ICCV 2021) | 直接优化排序，无需辅助头 | LVIS mask AP 21.7 → 25.2，**稀有类 APr +7** | 无超参、抗类别不平衡；但需要更长训练 + 更多增广 |
| NorCal (NeurIPS 2021) | 按类频率归一化分数，纯推理期 | LVIS 上一致提升，且**不牺牲频繁类** | 纯后处理 = 台账已否决的"纯重排序臂"；只能作组件 |
| FRACAL (CVPR 2025) | 分形维度捕捉类−位置依赖，后校准 | LVIS **稀有类 mask AP +8.6%**，零训练零推理开销 | 同上；我方只有 2 类，分形维度的收益基础不成立 |
| C2AM Loss (CVPR 2022) | 类别感知角边距推移决策边界 | LVIS 稀有类 **+11.9% APm** | 2 类场景下边距重排的收益不确定 |

**统一判断**：这一族的巨大数字全部来自 1203 类 LVIS 的极端长尾。我方只有 Vehicle/Pedestrian 两类（94,916 / 26,287 实例，3.6:1），不是长尾问题，是**少身份问题**（134 个行人身份）。长尾损失不解决身份稀缺。**不推荐。**

---

## 方向 3 — 事件相机 3D / 立体与跨模态蒸馏

### 3.1 Ev-Stereo3D 主表（竞品定位，必须记录）

DSEC-3DOD blind-time 100 FPS，Table 1【收据】：

| 模态 | 方法 | VEH 3D Easy | VEH 3D **Mod.** | PED 3D Easy | PED 3D **Mod.** |
|---|---|---:|---:|---:|---:|
| LiDAR | VoxelNeXt | 12.66 | 11.06 | 10.59 | 6.61 |
| LiDAR | HEDNet | 14.31 | 12.96 | 10.16 | 8.29 |
| LiDAR+RGB | LoGoNet | 17.65 | 15.39 | 11.66 | 8.20 |
| LiDAR+RGB+Event | Ev-3DOD (CVPR 2025) | 29.53 | 25.07 | 18.42 | 12.49 |
| RGB-Stereo | DSGN | 16.29 | 13.45 | 4.06 | 2.42 |
| RGB-Stereo | LIGA | 14.26 | 10.98 | 6.02 | 3.58 |
| **Event-Stereo** | **Ev-Stereo3D (ICCV 2025)** | 23.47 | **19.62** | 19.86 | **12.93** |

两条值得注意的事实：(a) **Ev-Stereo3D 的行人 AP3D 超过了用了 LiDAR 的 Ev-3DOD**（12.93 vs 12.49），作者归因于"specialized modules that effectively leverage semantic features from event data"—— 说明行人在事件域是可做的，不是数据的锅；(b) 帧式立体 DSGN/LIGA 的行人几乎全灭（2.42 / 3.58），我方 0.6688 比它们还低一档 —— **我方行人不是"接近 SOTA 差一点"，是"还没进入可比区间"**。这印证行人侧需要机制性改动而不是调参。

（提醒：论文数字 19.62/12.93 与公开 ckpt 在冻结评测器下的 8.0215/3.6448 是两套数，按 `repo_contract.md` §10.6 的三列分报规则引用。）

### 3.2 事件立体深度：概念可借，模块难移

| 论文 | 机制 | 定量【收据】 | 对我方 |
|---|---|---|---|
| **TESNet** — Cho, Kang, Yoon, *Temporal Event Stereo via Joint Learning with Stereoscopic Flow*, **ECCV 2024** | 定义"立体流"（左右各一个水平位移 + 共享一个垂直位移），用它把上一时刻的**特征和整个 cost volume** warp 到当前时刻；用 temporal disparity consistency loss 免除光流 GT | DSEC benchmark：1PE **8.662** / 2PE **2.259** / MAE **0.493** / RMSE **1.172**，全指标超 DTC-SPADE (9.277/2.416/0.527/1.291) 与 Se-CFF。MVSEC 消融：single 15.2cm → +特征 warp 14.7 → **+cost volume warp 13.6** → full 13.0 | **这是竞品同组同一作者的前作。** 相似度 5/5。且我方 DETR query 结构里根本没有 cost volume，无处可 warp。**不推荐移植**，但见 battle log #5 —— 它是"时序对深度无效"这条台账收据的一个反例，值得记录边界 |
| Se-CFF, *Concentrate and Focus on the Future*, CVPR 2022 | 注意力式 event concentration network，把多密度 event stack 压成清晰边缘张量；训练期蒸馏未来事件 | DSEC 上 SOTA（当年） | concentration 的思想（学习式事件聚合替代手工累积）可以进我方 event voxelizer，但这属于表征层改动，风险高收益不明 |
| URNet, *Visual Intelligence* 2025 | 局部−全局精修 + 逐像素方差，用 KL 散度调制损失 | DSEC 上 MAE/RMSE/像素错误率全面超 SOTA | 不确定度调制损失的做法与 §2.1 的 GUPNet++ β-NLL 同源，取后者即可 |
| EV-MGDispNet (2024) | 边缘感知聚合 + 运动引导注意力 + census 左右一致性损失 | DSEC MAE/RMSE SOTA | 左右一致性损失是低成本的自监督正则，但台账已两次否决"稀疏逐点光度匹配（信噪 <95% 门）"—— census 变换版本是否能过门需要重新验，**默认视作已否决** |

### 3.3 跨模态蒸馏（事件学生 / 图像教师）

- **论文 A**：Rossi et al., *Event-Aware Distilled DETR for Object Detection in an Automotive Context*, **IEEE IV 2025**（EA-DETR，代码公开）。
- **机制一句话**：RGB 教师（YOLOv7-E6E）+ 事件学生（DETR），用 **Binary Events Mask (BEM)** 做掩码 MSE 的骨干蒸馏 + logits 蒸馏，推理期只用事件。
- **定量**【收据】：DSEC-DET 上事件 baseline DETR mAP50 27.2 / mAP50:95 14.7；Hard-DSEC-DET 上 EA-DETR mAP50:95 **15.3**（baseline 14.6），**APM 49.5**（baseline 46.0）、**APL 47.2**（baseline 23.5），但 **APS 6.3 < baseline 7.5**。消融：骨干蒸馏单独约 +1 mAP50:95，logits 蒸馏更少，两者结合最好。
- **论文 B**：Zhang et al., *Enhanced Event-based Dense Stereo via Cross-Sensor Knowledge Distillation*, **ICCV 2025**。多级 intensity→event 蒸馏 + intensity-event 联合左右一致性；MVSEC/DSEC 上超 baseline；推理期只保留事件。
- **论文 C**：*EventVGGT: Exploring Cross-Modal Distillation for Consistent Event-based Depth Estimation*（2026）。从 VGGT 蒸馏时空+多视图几何先验，三级蒸馏（CMFM/STFD/TCD）；**EventScape 30m 处绝对平均深度误差从 2.30 降到 1.06（−53%）**。
- **映射瓶颈**：行人深度 + 车辆框紧度（语义特征质量）。
- **与台账的冲突 —— 红队标红**：EA-DETR 自己的结果里 **APS 反而下降**，作者归因于"BEM-based distillation concentrates on regions with high event activity (mostly medium or large objects)"。**行人在 DSEC-3DOD 就是小目标。** 直接照搬 BEM 掩码蒸馏很可能对我方的关键类别是负收益。若要移植，掩码必须改成"GT 框内 + 按类别面积归一化"，而不是按事件活跃度。
- **我方独有的硬限制**：manifest 里 `manual 5,518 / blind 48,060`。RGB 只在 active time 存在 ⇒ 教师信号只覆盖 **10.3%** 的 query，且是非随机的、系统偏易的那 10%。见 battle log #3。
- **移植难度**：**中–高。加教师分支 + 数据管线要对齐 RGB**。
- **与 Ev-Stereo3D 相似度：2/5**（叙事上还是加分项，见 §0.2）。

### 3.4 2026 年事件检测的一条侧面证据

*No Dense Tensors Needed: Fully Sparse Object Detection on Event-Camera Voxel Grids*（SparseVoxelDet，2026）报告了一个和我方车辆瓶颈同构的现象【收据】：FRED benchmark 上 mAP@50 = 83.38%，**把 IoU 阈值从 0.50 放宽到 0.40，mAP 回升到 89.26%**；11.9 万测试帧的误差取证显示 **71% 的失败是定位近失（localization near-miss）而非漏检**。作者结论："the remaining accuracy gap is dominated by **box regression precision** rather than detection capability."

**这与我方台账逐字同构**："22.6% 的车停在 IoU 0.65" + "召回天花板是目标的 4.9 倍"。一个独立数据集、独立架构上的同构发现，说明**框回归精度是事件域 3D 检测的系统性瓶颈**，不是我方实现的偶然。这条可以直接写进论文的 motivation。

---

## 方向 4 — 少样本类别增广（行人 134 身份）

### 4.1 MixUp3D（MonoLSS, 3DV 2024）★ 事件域有额外物理正当性

- **论文**：Li et al., *MonoLSS: Learnable Sample Selection For Monocular 3D Detection*, **3DV 2024**。
- **机制一句话**：在 2D MixUp 上加物理约束（**必须同焦距、同主点、同分辨率、同相机视角 pitch/roll**），使混合结果等价于"一台相机在同一时刻拍到的空间重叠场景"，从而不引入深度歧义。
- **定量**【收据】，KITTI val Car AP3D@0.7 R40（150 epoch，5 seed 中位数）：LSS 单独 **+3.06** Easy，MixUp3D 单独 **+3.8** Easy，**两者合用 +11.74**（远超相加的 +6.68）—— 论文明确称之为 synergistic effect。另有实现细节：**不用 MixUp3D 时训 150 epoch 就过拟合；用了可以训 600 epoch 不过拟合**。
- **映射瓶颈**：**行人 134 身份稀缺**（主）+ 训练配方（长训练的前提）。
- **与台账的关系**：**相容且互补。** 台账"SEIT（行人事件移植增广）已被证明关键"—— SEIT 增加的是**实例位置多样性**，MixUp3D 增加的是**外观重叠多样性**，两者作用在不同轴上。MonoLSS 的超可加性正是"增广解锁长训练、长训练放大其他机制"这个链条。
- **事件域的额外论据（这是我方可写的新颖点）**：事件流是亮度变化事件的集合，两个独立场景的事件在体素网格上的叠加**就是加法**，不需要 alpha 混合这种物理上站不住的操作。也就是说 **MixUp3D 在事件域比在 RGB 域更有物理依据**。约束条件也更容易满足：我方 manifest 只有 **4 个 calibration id**，按 calibration id 分组混合即可严格满足"同焦距同主点"。
- **移植难度**：**中。改 dataloader / collate**（`lib/datasets/dsec3dod/` 一侧），不动模型。需要新增按 calibration id 分组的采样器。
- **与 Ev-Stereo3D 相似度：1/5。** 竞品未报告任何实例级增广。

### 4.2 遮挡感知放置：Real3D-Aug / CA-aug / DR.CPO

| 论文 | 机制 | 定量【收据】 |
|---|---|---|
| **Real3D-Aug** (CEUR/ICCVW 2022) | 复用已标注真实物体，自动找合法放置点（预计算地平面），球面投影显式处理遮挡 | PV-RCNN 行人：**Easy +15.4% / Mod. +10.96% / Hard +7.87%**；对照 GT-Aug 只有 **+7.52 / +3.74 / …**。摘要另报 "Hard" 行人 **+6.65% AP** 超 SOTA |
| **CA-aug** (2022) | 把点云分成地面点/障碍点，计算 "Validspace" 保证放置合理，可控遮挡程度 | 对行人/骑车人显著超 GT-sample |
| **DR.CPO** (AAAI 2023) | 迭代构造整体物体 + 随机放置 + HPR（Hidden Point Removal）做自遮挡与外遮挡 | 用 **4.60% / 37.60%** 的训练数据即达到无增广 / CDA 增广的水平 |

- **机制一句话（合并）**：copy-paste 的收益主要不来自"多贴几个"，而来自**放置的物理合法性（地平面 + 无碰撞）与遮挡的显式建模**；Real3D-Aug 对 GT-Aug 的 **2.9 倍**行人增益差（10.96 vs 3.74）就是这个差别的价钱。
- **映射瓶颈**：行人 134 身份稀缺。
- **与台账的关系**：**相容，是 SEIT 的升级路径而非替代。** SEIT 已证明关键 ⇒ 移植的增量在于给 SEIT 加两件事：(a) 地平面约束的放置采样；(b) 事件域的 HPR —— 即"不要把事件贴到已有更近深度的像素后面"。后者在事件域比在点云域更简单：我方有视差/深度估计，可以直接做深度缓冲测试。
- **移植难度**：**中。改增广模块 + 需要地平面估计**（DSEC 有标定外参，地平面可从标定 + 简单拟合得到）。
- **与 Ev-Stereo3D 相似度：1/5。**

### 4.3 事件域专用增广（列作背景）

EventRPG（ICLR 2024，LRP 显著性引导的事件混合）、ShapeAug++（2024，随机多边形 + Bézier 曲线运动模拟遮挡，DVS 分类 top-1 **+3.7%**）、EventAug（2024，多尺度时空掩码）、ControlEvents（WACV 2026，扩散模型条件生成带标事件）。**全部是分类任务或无 3D 标注**，与我方 3D 框回归的目标不对齐。ShapeAug++ 的"多边形遮挡体"倒是可以作为一个零成本的遮挡增广，但预期收益小。

---

## 方向 5 — 单目深度先验（行人）

### 5.1 几何误差深度 —— 见 §1.1（本方向的第一名就是它）

§0.3 已经给出这条路的物理预算表与它的天花板（H_3D 类内方差在 30–40m 封死在 1.8–2.4m）。补充 MonoDGP 附录 Table 8 的 oracle【收据】：**把 H_3D 与 h_bbox 同时换成真值，moderate AP3D 提升至多 26.21%**；单独替换任一个都远不如同时替换，说明两者存在耦合。这条 oracle 对我方的意义是：**尺寸头（H_3D）与 2D 框头（h_2D）的改进是相乘而非相加的** —— 这为"§1.2 尺寸嵌入 + §1.1 几何误差深度"的组合提供了论文级依据。

### 5.2 MonoCD 互补深度（CVPR 2024）

- **机制一句话**：预测 Horizon Heatmap 得到全局线索的互补深度 `z_comp`，与局部线索的 `z_dir` / `z_key` **构造成误差异号**（`e_key · e_comp < 0`），使加权平均真的能相互抵消。
- **对我方**：MonoCD 指出的问题（多深度加权平均在所有分支同号偏差时无效）正是 MonoDGP 用几何误差取代多深度的动机。**取 MonoDGP 即可，不必再叠 MonoCD**，两者是竞争关系不是互补关系。

### 5.3 地平面约束：MonoGround / Ground-aware Convolution / GAC3D

- **MonoGround (CVPR 2022)**：从 3D 框标注推出物体底面的稠密"grounded depth"，把病态的 2D→3D 映射变成"相机射线 ∩ 地平面"的唯一解，且**与物体高度无关**（规避了 §0.3 的 H_3D 方差地板！）。
- **定量**【收据】：KITTI test 行人类别第二名，比除 GUPNet 外的方法高约 **2% / 1% / 1.5%**（easy/mod/hard）。作者自陈行人收益小于车："pedestrians' sizes (width and length) are relatively small... the bottom rectangle of the 3D bounding box is small and the projected area on the ground is small. It would be hard to conduct random sampling on this small area."
- **Ground-aware Convolution (RA-L 2021)**：让 anchor 中心的特征能"向下看"到接地点。
- **映射瓶颈**：行人深度，且**是唯一一条绕开 H_3D 方差地板的路** —— 接地点深度不依赖身高。
- **与台账的关系**：**相容，但预期收益被论文自己的行人分析压低。** 我方还有一个额外风险：行人的脚部在事件相机里事件密度低（脚接触地面时相对运动小），接地点定位可能比 RGB 更难。
- **移植难度**：**中。加辅助稠密监督头（训练期）+ 需要地平面**。
- **与 Ev-Stereo3D 相似度：1/5。**

---

## 方向 6 — DETR 迭代 refine 与辅助监督

### 6.1 MonoDLGD：难度感知标签引导去噪（AAAI 2026）★ 本报告 Top-2

- **论文**：*Difficulty-Aware Label-Guided Denoising for Monocular 3D Object Detection*, **AAAI 2026**（arXiv 2511.13195）。**baseline 就是 MonoDGP，而 MonoDGP 就是 MonoDETR 的后继 —— 与我方同一血统。**
- **机制一句话**：用 3D-DAB（3D dynamic anchor box）query + 把 GT 标签（含**深度**）做**按实例难度自适应缩放的扰动**后当作去噪 query 送进 decoder，用 Laplacian 不确定度损失重建；难度由 stage-1 用干净标签 query 估的预测不确定度给出。
- **论文定量收益**【收据】，KITTI val Car AP3D|R40：

| 配置（Table 3） | 3D-DAB | 扰动 | 重建损失 | Easy | **Mod.** | Hard |
|---|---|---|---|---:|---:|---:|
| (a) MonoDGP baseline | ✗ | ✗ | ✗ | 30.76 | 22.34 | 19.02 |
| (b) | ✓ | ✗ | ✗ | 27.82 | **20.64** | 17.78 |
| (c) | ✓ | 均匀噪声(=DN-DETR) | L1 | 31.99 | 23.82 | 20.65 |
| (d) | ✓ | 均匀噪声 | Laplacian | 33.82 | 24.70 | 21.19 |
| **(e) MonoDLGD** | ✓ | **难度感知 DAP** | Laplacian | **34.89** | **25.19** | **21.78** |

  去噪目标消融（Table 4）**这一条是关键**【收据】：

| 去噪对象 | Easy | **Mod.** | Hard |
|---|---:|---:|---:|
| Baseline (MonoDGP) | 30.76 | 22.34 | 19.02 |
| 投影框 + 类别 | 30.93 | 23.36 | 20.30 |
| **投影框 + 类别 + 深度** | 34.89 | **25.19** | 21.78 |

  **只去噪框和类别 = +1.02；把深度加进去噪目标 = 再 +1.83**（总 +2.85，+12.8% 相对）。GFLOPs 69.0 → 69.3，推理 42.4ms → 42.7ms，**推理开销几乎为零，全部代价在训练**。移植到 MonoDETR 也有一致提升（Table 2）。

  超参消融（附录）【收据】：扰动组数 N=7 最优（1/3/5/7/8 分别 23.75/24.37/24.02/**25.19**/23.93）；深度扰动尺度 γ_d=0.8、框扰动尺度 γ_b=0.4 最优；**stage-1 必须喂干净 GT 标签，喂加噪标签会掉到 23.85**；难度归一化的 min/max 用 EMA(β=0.8) 维护，不用 EMA 掉到 24.32。

- **映射瓶颈**：**行人 134 身份稀缺 + 车辆框紧度 + 行人深度**，一个机制吃三个。N=7 组正负扰动 query 意味着每个 GT 产生 `2×7=14` 份监督 —— 对只有 134 个身份的行人，这是 **14× 的监督放大**，而且是几何一致的放大（扰动的是标签几何量，不是像素）。
- **与台账的关系**：
  - **相容**：训练期 only，与"召回不是问题"相容（去噪 query 不参与推理）；深度扰动的是**几何误差残差**（数值范围约 −2~2）而非绝对深度，这与 §1.1 的几何误差头是同一套参数化 —— **两者必须一起上**。
  - **明确冲突（必须写进风险栏）**：**(b) 行 3D-DAB 单独用会掉 1.70 moderate AP**（22.34 → 20.64）。这是一个全有或全无的移植：3D-DAB + 标签 query + DAP + Laplacian 损失必须一次全部落地，缺任一件就是负收益。见 battle log #2。
- **移植难度**：**中–高。改 query 参数化 + decoder 自注意力掩码 + 两阶段训练流程。** 这是本报告里唯一需要动 decoder 结构的推荐项。
  一条现实的减负论据：`repo_contract.md` §7.2 记录 R1 门 checkpoint `epoch_012.pth` 已确认丢失且远端恢复路线关闭 ⇒ **任何新臂本来就要从头训**，所以"破坏 state_dict 身份"这个代价在当前状态下**已经付过了**，不是增量成本。
- **与 Ev-Stereo3D 相似度：1/5。** 竞品是 anchor-based dense head，没有 query，没有去噪，结构上无法产生这个模块。

### 6.2 Mono3DV：3D-aware 二分匹配 + 变分 query 去噪（2026）

- **论文**：*Mono3DV: Monocular 3D Object Detection with 3D-Aware Bipartite Matching and Variational Query DeNoising*（arXiv 2601.01036），baseline MonoDETR。
- **定量**【收据】：Forward-Looking Distillation 单独 **+0.62 / +0.87**（mod/hard）；3D-Aware Bipartite Matching 单独几乎无效；3D-Denoising 单独≈(b)；**但 matching + denoising 合用 +0.41/+1.24/+1.18**；再加 Variational Query Denoising **+1.66/+0.77/+0.66**。
- **对我方**：与 MonoDLGD 同类且更弱，**取 MonoDLGD 即可**。但它的"单独无效、合用才有效"模式独立复现了 §6.1 的全有或全无风险，是一条支撑证据。

### 6.3 DN-DETR / DINO（背景）

DN-DETR（TPAMI 2023）：ResNet-50 上 12/50 epoch 分别 46.0 / 49.5 AP，"achieves comparable performance with 50% training epochs"【收据】。DINO 的对比去噪（CDN）喂难负样本训模型拒绝。**注意**：ConQueR（3D LiDAR DETR）报告过一条反面观察 —— 单独的去噪辅助损失在**行人类别上甚至掉点**，作者猜测是"模型只学会从加噪 GT 恢复，却不知道怎么处理完美定位的原始 GT 框"。**这条必须记进风险栏**：它与 MonoDLGD 的 (b) 行是同一个失效模式的两次独立观测。ConQueR 的解法是 query contrast（InfoNCE 对齐 GT-query 相似度），并报告"引入更稳定的 EMA decoder 编码 GT 框，对**实例更少的类别**（骑车人）提升尤其明显"—— 这条对我方 134 身份的行人是直接对口的补丁。

---

## 方向 7 — 4D / 时序（无跟踪 ID 兼容）

**先给结论：这个方向对我方是低优先级，但台账那条否决需要收窄措辞。**

### 7.1 StreamPETR 物体中心时序传播（ICCV 2023）+ RoPETR（2025）

- **机制一句话**：不做 BEV 特征堆叠，把长期历史直接编码进**稀疏物体 query**，经 memory queue 逐帧传播；motion-aware LayerNorm 建模自车与物体运动。**全程不需要跟踪 ID**（query 传播是隐式关联）。
- **定量**【收据】：nuScenes **67.6% NDS / 65.3% AMOTA**，首个与 LiDAR 方法可比的在线多视图方法；轻量版 45.0% mAP @ 31.7 FPS，比 SOLOFusion **+2.3% mAP 且快 1.8×**。RoPETR（2025）加时空 RoPE 后 ViT-L 达 **70.86% NDS**，明确指出 StreamPETR 的瓶颈是速度估计而非 mAP。
- **映射瓶颈**：任务书问的是"对分数/召回稳定性呢？"——**答案是：这两个都不是我方瓶颈。** 台账"召回天花板是目标的 4.9 倍"直接排除召回；分数稳定性归入 §2 的校准，而校准的绝对上限只有 +0.53 行人 AP，用一个 memory queue 去争这 0.53 是极差的性价比。
- **移植难度**：**高。需要 decoder 结构改造 + 流式 dataloader + caller-owned state**（`lib/models/rep4d/state.py::Rep4DStreamState` 倒是已有骨架）。
- **与 Ev-Stereo3D 相似度：3/5。** 竞品标题就是 "Unleashing the **Temporal** Potential"，时序是他们的卖点。往这个方向走等于在他们主场比。
- **判定：不进 Top-10。**

### 7.2 台账那条否决应当收窄

台账写"时序聚合对深度已被实测无效（恒速拟合 AP 零变化）"。TESNet（ECCV 2024）的 MVSEC 消融是一条边界反例【收据】：single 15.2cm → +feature warping 14.7 → **+cost volume warping 13.6** → full 13.0cm 平均深度误差，即 **cost-volume 层的时序 warp 单独值 −1.1cm（−7.5% 相对）**。

**建议措辞修订**：把否决从"时序聚合对深度无效"收窄为"**输出层的恒速框拟合对深度无效**"。理由：我方测的是输出层的运动学外推，TESNet 测的是**代价体层的特征对齐**，两者是不同层级的机制。这个收窄不改变结论（我方 DETR 无 cost volume，且相似度 5/5，仍然不做），但避免了一条过宽的否决在未来误伤别的提案。见 battle log #5。

---

## 方向 8 — 训练配方

### 8.1 长训练 + 增广解锁（受 §4.1 约束）

- **MonoLSS**【收据】：无 MixUp3D → 150 epoch 即过拟合；有 MixUp3D → **600 epoch 不过拟合**。
- **含义**：长训练**不是一个可以单独打开的开关**，它是 MixUp3D 的下游收益。我方目前 12 epoch 的配方，如果先落地 MixUp3D，才有资格谈长训练。**这两项必须捆绑成一个臂。**

### 8.2 EMA

- **MonoDLGD**【收据】：EMA 动量 β 的消融，无 EMA（batch-wise min/max）24.32 mod → β=0.7 → 24.23 → **β=0.8 → 25.19** → β=0.9 → 24.29。注意这是 EMA 用在**难度分数归一化的全局 min/max 统计量**上，不是权重 EMA。**+0.87 moderate AP**，且对 β 敏感（0.7/0.9 都掉近 1 点）。
- **OD-DETR**（2024）：用 EMA 累积的教师做**在线自蒸馏**稳定 DETR 训练。三个组件消融【收据】：**matching distillation +1.4 AP**、prediction distillation +0.5 AP、auxiliary group +0.4 AP，**且不增加参数量**。matching distillation 的机制是"用教师的 query-GT 匹配关系指导学生的标签分配"，直接对治 DETR 的匹配不稳定 —— 这与 §2.2 Align-DETR 指出的"跨层目标错配"是同一个病的两种药。
- **ConQueR**【收据】：EMA decoder 编码 GT 框，"especially on categories with fewer instances (i.e., cyclists)"。**对 134 身份的行人对口。**
- **移植难度**：**很低（权重/统计量 EMA，改训练循环）到 中（OD-DETR 在线蒸馏，加 EMA 教师前向）**。
- **相似度：1/5。**

### 8.3 梯度裁剪与调度（社区共识，非机制）

3DETR（ICCV 2021）、3DET-Mamba（NeurIPS 2024）、SEED（ECCV 2024）三篇 3D DETR 的实现细节高度一致【收据】：AdamW + cosine 退火到 1e-6 + weight decay 0.1 + **梯度裁剪 ℓ2 norm = 0.1**。3DETR 另有一条反面记录："使用 cosine schedule、更长训练、或 AdamW 对 **VoteNet baseline** 没有显著差别"—— 即这套配方的收益是 **DETR 结构特有的**，不是普适的。

**对我方**：`grad_clip = 0.1`（ℓ2 norm）是 3D DETR 的社区默认值，我方若当前不是这个值，这是一次零成本的对齐。

---

## Top-10 排序表

排序分 = **期望 AP 增益（Veh+Ped 中值，AP 点）× 可行性(1–5) ÷ 与竞品相似度(1–5)**。

期望增益列全部是**【估计】**，推算方式：把论文的相对增益映射到我方误差预算（§0.3 的物理预算表 + 台账的 22.6%@IoU0.65、+79% 排序 oracle、85% 系统项），并按"跨数据集跨架构"打折。**区间是诚实的不确定度，不是保守报数。**

| # | 机制（论文） | 期望 Veh | 期望 Ped | 可行 | 相似 | **分** | 一句话 |
|---:|---|---:|---:|:---:|:---:|---:|---|
| 1 | **几何误差深度头**（MonoDGP, CVPR 2025） | +0.1~0.4 | **+0.8~2.2** | 4 | 1 | **7.0** | 把台账"行人深度来自身高先验"这句话变成显式的 `Z=f·H/h + Z_err`，论文行人 mod +2.51 |
| 2 | **深度参与的难度感知去噪**（MonoDLGD, AAAI 2026） | +0.3~0.8 | +0.3~1.0 | 3 | 1 | **3.6** | 训练期 only，推理 +0.3ms；深度进去噪目标值 +1.83，对 134 身份是 14× 监督放大 |
| 3 | **MixUp3D + 长训练**（MonoLSS, 3DV 2024） | +0.3~0.9 | +0.2~0.8 | 3 | 1 | **3.3** | 事件叠加就是加法，物理正当性强于 RGB；解锁 4× 训练轮次 |
| 4 | **EMA + cosine + grad-clip 0.1**（MonoDLGD / 3DETR / SEED） | +0.1~0.4 | +0.05~0.3 | 5 | 1 | **2.13** | 配置级；EMA 统计量 +0.87，但对 β 敏感（0.7/0.9 掉近 1 点） |
| 5 | **遮挡感知放置的 SEIT 升级**（Real3D-Aug / DR.CPO） | +0.05~0.2 | +0.2~0.8 | 3 | 1 | **1.88** | 地平面放置 + 事件域深度缓冲遮挡；Real3D-Aug 行人 mod +10.96 vs GT-Aug +3.74 |
| 6 | **尺寸嵌入 + 形状模板**（DimEmbed, CVPR 2022） | **+0.4~1.2** | +0.05~0.2 | 4 | 2 | **1.85** | 直击"斜率 0.24"塌缩；+3ms；只在匹配 query 上算 log-ratio 以避塌缩 |
| 7= | **Align Loss（行人换 2D-IoU 变体）**（BMVC 2024 / ICCV 2023） | +0.15~0.35 | −0.2~+0.3 | 5 | 1 | **1.50** | 只改分类损失；**行人必须用 2D IoU 不能用 3D IoU**，否则远程行人目标塌到 0 |
| 7= | **OD-DETR EMA 在线自蒸馏**（2024） | +0.2~0.4 | +0.1~0.3 | 3 | 1 | **1.50** | matching distillation +1.4 AP 且零新增参数；对匹配不稳定对症 |
| 9 | **IoU-guided Uncertainty-Confidence**（GUPNet++, TPAMI） | +0.1~0.4 | +0.1~0.5 | 4 | 2 | **1.10** | 不是 IoU3D 损失（已否决项）；远程行人自动降权，正是 §0.3 需要的 |
| 10 | **RGB→事件训练期蒸馏**（EA-DETR IV'25 / ICCV'25 cross-sensor KD） | +0.1~0.5 | +0.1~0.4 | 2 | 2 | **0.55** | 竞品已公开否决推理期融合，这扇门是干净的；但教师只覆盖 10.3% 的 query |

> #5 与 #6 的分差（1.88 vs 1.85）远小于期望增益区间的宽度，应视为并列；两者也不竞争同一块预算（一个在 dataloader，一个在检测头），可以同时上。

**落在线下的（记录理由，避免重复讨论）**：

| 机制 | 分 | 出局理由 |
|---|---:|---|
| MonoGround 地平面稠密深度 | 0.38 | 唯一绕开 H_3D 方差地板的路，但论文自陈行人收益小（底面投影面积小）；事件域脚部事件稀疏，风险更高 |
| StereoDistill XGD（LiDAR 教师版） | 0.50 | LIGA 谱系 = 竞品家谱；且监督量不对等的公平性质疑。换成 EMA 自教师则并入 #7= |
| OCRA 式 ROI 精修 | 0.36 | 相似度 5/5，字面上是竞品模块 |
| TESNet cost-volume warping | 0.06 | 竞品同组前作，相似度 5/5；我方无 cost volume |
| StreamPETR query 传播 | — | 召回与分数稳定性都不是我方瓶颈；时序是竞品主场 |
| GFL/GFLv2/VFNet | — | **Align-DETR Table 3 明确显示 QFL/VFL 在 DETR 上是负收益**（47.6 / 48.7 vs focal 49.0） |
| NorCal / FRACAL / C2AM / RS Loss | — | 长尾方法；我方是 2 类 3.6:1，不是长尾，是少身份 |
| 事件域分类增广（EventRPG/EventAug/ShapeAug++） | — | 无 3D 标注，目标不对齐 |

### 建议的臂序（不是排序分的直接顺序 —— 有依赖关系）

```
臂 A（地基，必须先做）:  #1 几何误差深度头  +  #4 训练配方对齐
   └─ 理由: #2 的深度扰动作用在几何误差残差上，没有 #1 就没有可扰动的量;
            #9 的不确定度也依赖 #1 的 h_2D/h_3D 分布。
臂 A2（紧随 A，车辆专线）: #6 尺寸嵌入 + 形状模板
   └─ 理由: 与 #1 同在检测头但输出通道不同（尺寸 vs 深度），机制上不耦合;
            排在 A 之后而非并行，只是为了让"斜率 0.24 是否被拉起"这个
            指标的归因保持干净。车辆缺口 3.01 AP 是两个缺口里更大的那个,
            这条臂是唯一直击它的模型级机制，不能因为排名第 6 就往后排。
臂 B（并行，与 A/A2 无耦合）: #3 MixUp3D + 长训练  →  #5 SEIT 遮挡升级
   └─ 理由: 都在 dataloader 侧，不碰模型，可与 A 同时跑。
臂 C（依赖 A 落地）:      #2 MonoDLGD 全套（全有或全无）
臂 D（最后做）:           #9 IoUnC  +  #7= Align Loss 行人 2D-IoU 变体
   └─ 理由: 校准的 oracle 上限随框质量抬升而抬升;
            在 A/B/C 之前做，等于在 +0.53 的天花板下争。
```

---

## Battle Log

参与：事件综述、双目3D、单目3D、DETR系、深度估计、场景流、打分校准、数据增广、4D时序、蒸馏、红队、可移植性工程师（12 人）。

**多数派立场**：Top-10 表的排序，臂序 A→B→C→D。

---

### 反对意见 #1 — 红队质疑者（反对把 #1 排在第一）

> "多数派把几何误差深度头排第一，靠的是 MonoDGP 行人 +2.51 那个数。我承认那个数是真的。但**我方的行人处境和 KITTI 的行人不是一回事**。
>
> MonoDGP 的 KITTI 行人 baseline 是 7.55 moderate，我方是 **0.6688**。差 11 倍。一个在 7.55 上值 +33% 的机制，在 0.6688 上未必值 +33% —— 也可能值 +300%（因为 0.6688 说明有一个 dominant failure mode 完全没被处理），也可能值 0（因为在 0.6688 这个水平上，瓶颈根本不在深度参数化，而在更前面的地方，比如事件表征根本没编码到行人）。**我们不知道是哪一种，而多数派的估计区间 +0.8~2.2 假装我们知道。**
>
> 更要命的是我自己算出来的这条：§0.3 的表说 H_3D 类内 σ ≈ 5.9%，30m 处深度地板 1.77m。而我方 gated median 深度误差是 **0.2388m**。**0.2388 远小于 1.77。** 这意味着我方现在的深度**不可能主要来自身高先验**，否则误差会是米级。台账那句"行人深度实际主要来自身高先验"要么是只对远程成立（而 gated median 是全距离的），要么这条收据的推导有问题。**在把整个 Top-1 押在这句话上之前，必须先把 gated median 按距离分箱重算。** 这是零 GPU 的，现有预测 pickle 就够。
>
> 我的替代排序：把 **#4 训练配方 + #3 MixUp3D 提到最前**，它们不依赖任何关于失效模式的假设，是纯粹的方差削减；同时并行跑那个分距离分箱的诊断。诊断出来之后再决定 #1 的排位。"

**多数派回应（单目3D + 深度估计专家）**：分距离分箱的诊断被接受，且升级为**臂 A 的前置 Gate**（零 GPU、当天可出）。但排序不改，理由有二：(a) 即便身高先验只在中远程主导，中远程正是 moderate 难度的主体，也正是 AP 的主要贡献区；(b) 几何误差头**不是**"改用身高先验"，它是"保留任意深度来源 + 学一个透视不变的残差"，MonoDGP Table 4 里 `Geometric Depth (h_bbox)` 单独只有 7.99 而 `GD + Depth Error` 有 22.34 —— 收益来自残差项，不是来自身高项。所以红队的物理地板论证攻击的是一个我们没有采用的方案。**但红队的第二段被记为一条必须回答的诊断，未回答前不得开臂 A。**

---

### 反对意见 #2 — 可移植性工程师（反对 #2 进 Top-3）

> "MonoDLGD 我不反对它的科学性，我反对它的**工程风险定价**。
>
> 看 Table 3 的 (b) 行：**3D-DAB 单独用，moderate 从 22.34 掉到 20.64**。掉 1.70。这不是'收益小'，这是**负收益**。而 Mono3DV 独立复现了同一模式（3D-aware matching 单独无效、3D-denoising 单独≈无效、合用才有效），ConQueR 更是报告过去噪辅助损失**在行人类别上掉点**。三篇论文，三次同样的观测。
>
> 这意味着 #2 是一个**四件套的全有或全无移植**：3D-DAB query 参数化 + 标签 query + 难度感知扰动 + Laplacian 不确定度损失。四个都对了，+2.85；错一个，−1.70。而我们要改的是 decoder 的 query 参数化和自注意力掩码 —— 这是这份 Top-10 里**唯一动 decoder 结构**的项。我方的 monodetr decoder 是 `repo_contract.md` §9 明确记为'冻结主干'的东西，里面还有 29 处 `.cuda()` 硬编码，新代码禁止那种写法但改它会破坏 checkpoint 身份。
>
> 而且这里有一个多数派没说的账：MonoDLGD 的 N=7 扰动组意味着 decoder 每步要多处理 `2×7×K` 个 query。论文说推理不变（对，去噪 query 推理时丢掉），但**训练显存和时间会显著上涨**，而我们是 12 epoch × 4 卡的预算。
>
> 我的立场：**#2 降到第 7 位，排在 #6 尺寸嵌入之后。** 先做完所有'只改头和损失'的项（#1/#6/#7=/#9），把它们的增益吃干净，再评估是否值得动 decoder。"

**多数派回应（DETR 系专家）**：显存/时间的账被接受，需在预注册里给出实测预算。但"破坏 checkpoint 身份"这条**不成立**：`repo_contract.md` §7.2 已判定 R1 门 checkpoint `epoch_012.pth` 丢失且远端恢复路线关闭，§8 的三条约束里明确写了"不得声称任何权重与 R1 的原 artifact 同一"。**也就是说任何新臂都必须从头训，改 query 参数化的边际成本是零。** 至于全有或全无 —— 这恰恰是论文已经替我们做完消融的好处，我们知道要一次落哪四件。排序维持，但采纳"臂 C 排在 A 之后"的依赖约束（已在臂序里）。

---

### 反对意见 #3 — 蒸馏专家（反对自己方向的 #10，主动降权）

> "我是这个方向的负责人，我建议把 **#10 RGB→事件蒸馏从 Top-10 里拿掉**。
>
> 多数派喜欢它是因为 §0.2 那个叙事很漂亮：竞品公开否决了推理期融合，我们做训练期蒸馏就避开了。叙事是漂亮，但数据不支持。
>
> manifest 是 `manual 5,518 / blind 48,060`。RGB 只在 active time 有。所以教师信号覆盖 **10.3%** 的 query。而且这 10.3% **不是随机抽样** —— 它恰好是同步传感器有效、没有 blind-time 漂移的那一批，也就是**系统性最容易的那一批**。在这批上蒸馏骨干，等于把骨干往 active-time 的统计分布上拉。而 active time 正是 Ev-3DOD（有 LiDAR）碾压我们的地方，也是我们差异化最弱的地方。**我们会花预算把模型推向自己最没优势的分布。**
>
> 第二条：EA-DETR 自己的结果里 **APS 从 7.5 掉到 6.3**。作者的解释是 BEM 掩码集中在事件活跃度高的区域，也就是中大目标。**我方的行人就是小目标。** 要移植就得重写掩码策略（GT 框内 + 按类别面积归一化），而那个变体没有任何论文验证过。
>
> 把这份预算给 #5（遮挡感知的 SEIT 升级）。Real3D-Aug 的行人 moderate +10.96 vs GT-Aug +3.74 是**同一张表里的对照**，比我这条路的证据强得多。"

**多数派回应**：接受降权论证的两条事实，但保留 #10 在第 10 位（而非移除），理由是它是**唯一一条能在论文里正面回应"你们为什么不用 DSEC 的 RGB"这个必然会被问到的审稿问题**的机制 —— 即使最终报告的是负结果，那也是一段有价值的消融。**标记为"低优先级 / 可作为消融而非主臂"。**

---

### 反对意见 #4 — 数据增广专家（反对 #3 只排第三）

> "**#3 MixUp3D 应该是第一，不是第三。**
>
> 理由一：134 个训练身份是**唯一一个没有任何损失函数能解决的约束**。#1 改深度参数化、#2 加去噪监督、#6 改尺寸头 —— 这三个都是在同一批 134 个人身上换角度榨汁。榨到极限还是 134 个人。只有增广能造出新的样本分布。
>
> 理由二：MonoLSS 的超可加性不是巧合。LSS 单独 +3.06，MixUp3D 单独 +3.8，合用 **+11.74** —— 远超相加的 6.68。作者的解释是 LSS 依赖 object-level 特征而训练数据里物体数量有限。**这个因果结构和我方一模一样**：#1/#2/#6 全都是 object-level 机制，全都受限于物体数量。**先把物体数量的天花板抬起来，后面每一项的收益都会跟着涨。** 多数派的臂序把 B 和 A 并行是对的，但排序分把 #3 压在 #1 后面，低估了这个乘数效应。
>
> 理由三，这是我方独有的：**事件流的叠加就是加法。** RGB 的 MixUp 要做 alpha 混合，那在物理上是编造的（两个场景的光子不会那样混合）。事件体素的叠加是两个独立亮度变化场的真实叠加 —— **我们的 MixUp3D 比 MonoLSS 的更有物理依据**。而且 MonoLSS 那四条约束（同焦距、同主点、同分辨率、同视角）在我方是**免费满足**的：manifest 只有 4 个 calibration id，按 id 分组即可。这在论文里是一个干净的、可写的贡献点，而不是'我们搬了 MonoLSS'。"

**多数派回应（红队 + 单目3D）**：第三条论据被完全接受并采纳为论文卖点。排序分不改，理由是一条对冲：**我方 SEIT 已经在做行人事件移植**，MixUp3D 与 SEIT 在"增加实例多样性"上有重叠，边际收益不等于 MonoLSS 报告的 +3.8（那是从零增广起步的数）。另外 MonoLSS 的 +3.8 是 KITTI Car easy，Car 在 KITTI 训练集有 1.4 万实例，不是 134 —— **在 134 个身份上做 mixup，混出来的组合数虽然大，但底层身份的信息量没有增加**，可能很快饱和。**折中：#3 保持第 3 位，但臂 B 与臂 A 严格并行（不排队），且臂 B 的 Gate 独立设定。**

---

### 反对意见 #5 — 场景流专家（反对台账时序否决的措辞，不反对排序）

> "我不反对把时序排在线下 —— 相似度 5/5 这个理由我完全接受。我反对的是**台账那条否决的措辞**。
>
> 台账写的是'时序聚合对深度已被实测无效（恒速拟合 AP 零变化）'。但我们实测的是**输出层的恒速运动学外推**。TESNet 测的是**代价体层的特征时序对齐**，MVSEC 消融：single 15.2cm → +feature warp 14.7 → **+cost volume warp 13.6** → full 13.0。cost-volume warp 单独 −1.1cm，−7.5% 相对深度误差。这是同一个数据集家族（事件立体）、同一个量（深度）上的**正结果**。
>
> 两者的差别是层级：输出层外推假设物体做匀速直线运动，那个假设在 DSEC 的城市驾驶里当然不成立（行人转向、车辆刹车）。特征层 warp 不假设运动模型，它学一个稠密位移场。**把前者的失败推广成后者的失败，是一个过宽的否决。**
>
> 我要求的不是开一个时序臂 —— 我方没有 cost volume，且这是竞品同组前作，不该做。我要求的是**把台账那条改成'输出层的恒速框拟合对深度无效'**。因为一条过宽的否决会在未来误伤别的提案：比如有人提'在 event voxelizer 里做跨窗口的特征对齐'，那和恒速框拟合毫无关系，但会被现在这条措辞挡掉。"

**多数派回应**：**完全接受。** 措辞修订已写入 §7.2。这是本次 battle log 里唯一一条被无条件采纳的反对意见。

---

## 附：本报告引用的论文清单（含出处）

**方向 1 — 框紧度**
1. Pu, Wang, Deng, Yang. *MonoDGP: Monocular 3D Object Detection with Decoupled-Query and Geometry-Error Priors.* **CVPR 2025**. [openaccess](https://openaccess.thecvf.com/content/CVPR2025/papers/Pu_MonoDGP_Monocular_3D_Object_Detection_with_Decoupled-Query_and_Geometry-Error_Priors_CVPR_2025_paper.pdf) / [arXiv:2410.19590](https://arxiv.org/html/2410.19590v2)
2. Zhang, Zheng, Zhu, Huang, Du, Zhou, Lu. *Dimension Embeddings for Monocular 3D Object Detection.* **CVPR 2022**. [openaccess](https://openaccess.thecvf.com/content/CVPR2022/papers/Zhang_Dimension_Embeddings_for_Monocular_3D_Object_Detection_CVPR_2022_paper.pdf)
3. Liu, Ye, Tan, Ding, Bai. *StereoDistill: Pick the Cream from LiDAR for Distilling Stereo-based 3D Object Detection.* **AAAI 2023**. [arXiv:2301.01615](https://arxiv.org/abs/2301.01615)
4. Yan et al. *MonoCD: Monocular 3D Object Detection with Complementary Depths.* **CVPR 2024**.
5. *Real-time Stereo-based 3D Object Detection for Streaming Perception* (StreamDSGN). **NeurIPS 2024**. [arXiv:2410.12394](https://arxiv.org/abs/2410.12394)
6. Chen, Huang, Liu, Yu, Jia. *DSGN++.* **TPAMI 2022**, 45(4):4416-4429.
7. *Decoupled and Interactive Regression Modeling (DIRM).* 2024. [arXiv:2409.00690](https://arxiv.org/abs/2409.00690)

**方向 2 — 校准 / IoU-aware**
8. Lu, Ma, Yang, Zhang, Liu, Chu, Yan, Ouyang. *GUPNet++: Geometry Uncertainty Propagation Network.* **TPAMI**. [arXiv:2310.15624](https://arxiv.org/html/2310.15624v2)（会议版 GUPNet, **ICCV 2021**）
9. Liu et al. *Detection Transformer with Stable Matching* (Stable-DINO). **ICCV 2023**. [openaccess](https://openaccess.thecvf.com/content/ICCV2023/papers/Liu_Detection_Transformer_with_Stable_Matching_ICCV_2023_paper.pdf)
10. Cai, Liu, Wang, Li, Ge, Zhang, Huang. *Align-DETR: Enhancing End-to-end Object Detection with Aligned Loss.* **BMVC 2024**. [bmvc2024/211](https://bmvc2024.org/proceedings/211/)
11. Li et al. *Generalized Focal Loss V2.* **CVPR 2021**. / Zhang et al. *VarifocalNet.* **CVPR 2021**.
12. Oksuz et al. *Rank & Sort Loss.* **ICCV 2021**. / Alexandridis et al. *Fractal Calibration for Long-tailed Object Detection.* **CVPR 2025**. / Pan et al. *NorCal.* **NeurIPS 2021**. / Wang et al. *C2AM Loss.* **CVPR 2022**.

**方向 3 — 事件相机**
13. Kang, Cho, Yoon. *Unleashing the Temporal Potential of Stereo Event Cameras for Continuous-Time 3D Object Detection* (Ev-Stereo3D). **ICCV 2025**, pp. 6869-6881. [openaccess](https://openaccess.thecvf.com/content/ICCV2025/papers/Kang_Unleashing_the_Temporal_Potential_of_Stereo_Event_Cameras_for_Continuous-Time_ICCV_2025_paper.pdf) / [代码](https://github.com/mickeykang16/Ev-Stereo3D)
14. Kang et al. *Ev-3DOD: Pushing the Temporal Boundaries of 3D Object Detection with Event Cameras.* **CVPR 2025**.
15. Cho, Kang, Yoon. *Temporal Event Stereo via Joint Learning with Stereoscopic Flow.* **ECCV 2024**. [ecva](https://www.ecva.net/papers/eccv_2024/papers_ECCV/papers/05185.pdf)
16. Nam et al. *Stereo Depth From Events Cameras: Concentrate and Focus on the Future* (Se-CFF). **CVPR 2022**.
17. Zhang et al. *URNet: uncertainty-aware refinement network for event-based stereo depth estimation.* **Visual Intelligence 2025**. doi:10.1007/s44267-025-00090-1
18. *EV-MGDispNet: Motion-Guided Event-Based Stereo Disparity Estimation with Left-Right Consistency.* 2024. [arXiv:2408.05452](https://arxiv.org/html/2408.05452v1)
19. Rossi, Vasseur, Morbidi, Demonceaux, Rameau. *Event-Aware Distilled DETR for Object Detection in an Automotive Context* (EA-DETR). **IEEE IV 2025**. [pdf](https://home.mis.u-picardie.fr/~fabio/Eng/documenti/articoli/RoVaMoDeRa_IV25.pdf) / [代码](https://github.com/djessy1998/EA-DETR)
20. Zhang, Zhang, Li, Zhu, Lv, Zhu, Liu, Ji. *Enhanced Event-based Dense Stereo via Cross-Sensor Knowledge Distillation.* **ICCV 2025**.
21. *EventVGGT: Cross-Modal Distillation for Consistent Event-based Depth Estimation.* 2026. arXiv:2603.09385
22. *No Dense Tensors Needed: Fully Sparse Object Detection on Event-Camera Voxel Grids* (SparseVoxelDet). 2026. [arXiv:2603.21638](https://arxiv.org/html/2603.21638)

**方向 4 — 增广**
23. Li, Li, et al. *MonoLSS: Learnable Sample Selection For Monocular 3D Detection* (含 MixUp3D). **3DV 2024**. [arXiv:2312.14474](https://arxiv.org/html/2312.14474v1)
24. Šebek, Pokorný, Vacek, Svoboda. *Real3D-Aug: Point Cloud Augmentation by Placing Real Objects with Occlusion Handling.* CEUR Vol-3349 / **arXiv:2206.07634**
25. *DR.CPO: Diversified and Realistic 3D Augmentation via iterative Construction, random Placement, and HPR occlusion.* **AAAI 2023**.
26. *CA-aug: Context-Aware Data Augmentation for LiDAR 3D Object Detection.* arXiv:2211.10850
27. Sun et al. *EventRPG.* **ICLR 2024**. / *ShapeAug++.* 2024. / *EventAug.* 2024. / *ControlEvents.* **WACV 2026**.

**方向 5 — 深度先验**
28. Qin, Li. *MonoGround: Detecting Monocular 3D Objects from the Ground.* **CVPR 2022**.
29. Liu, Yixuan, Liu. *Ground-aware Monocular 3D Object Detection for Autonomous Driving.* **RA-L 2021**.
30. *GAC3D: improving monocular 3D object detection with ground-guide model and adaptive convolution.* PeerJ CS 2021.

**方向 6 — DETR 去噪 / refine**
31. *Difficulty-Aware Label-Guided Denoising for Monocular 3D Object Detection* (MonoDLGD). **AAAI 2026**. [arXiv:2511.13195](https://arxiv.org/html/2511.13195v1) / doi:10.1609/aaai.v40i8.37514
32. *Mono3DV: Monocular 3D Object Detection with 3D-Aware Bipartite Matching and Variational Query DeNoising.* 2026. arXiv:2601.01036
33. Li et al. *DN-DETR.* **TPAMI 2023**. doi:10.1109/tpami.2023.3335410
34. Zhu et al. *ConQueR: Query Contrast Voxel-DETR for 3D Object Detection.* **CVPR 2023**. [arXiv:2212.07289](https://arxiv.org/abs/2212.07289)
35. Liu et al. *SEED: A Simple and Effective 3D DETR in Point Clouds.* **ECCV 2024**. [arXiv:2407.10749](https://arxiv.org/html/2407.10749)

**方向 7 — 时序**
36. Wang, Liu, Wang, Li, Zhang. *Exploring Object-Centric Temporal Modeling for Efficient Multi-View 3D Object Detection* (StreamPETR). **ICCV 2023**, pp. 3621-3631.
37. Ji et al. *RoPETR: Improving Temporal Camera-Only 3D Detection by Integrating Enhanced Rotary Position Embedding.* 2025. [arXiv:2504.12643](https://arxiv.org/html/2504.12643)

**方向 8 — 训练配方**
38. *OD-DETR: Online Distillation for Stabilizing Training of Detection Transformer.* 2024. [arXiv:2406.05791](https://arxiv.org/abs/2406.05791)
39. Misra, Girdhar, Joulin. *An End-to-End Transformer Model for 3D Object Detection* (3DETR). **ICCV 2021**.
40. *3DET-Mamba: State Space Model for End-to-End 3D Object Detection.* **NeurIPS 2024**.

---

## 交付给下一阶段的三件事

1. **一个必须先跑的零 GPU 诊断（红队 #1 的要求，臂 A 的前置 Gate）**：用已验身份的 `predictions_model.pkl` 把行人深度误差**按距离分箱**（0-15 / 15-25 / 25-35 / 35+ m）重算 median 与 IQR，并同时算每箱的 2D 框高相对误差。判据：若中远程箱的深度相对误差 > 2D 框高相对误差，则几何误差深度头的假设成立，臂 A 放行；否则臂 A 降级、臂 B 提前。

2. **一条台账措辞修订**：`时序聚合对深度已被实测无效` → `输出层的恒速框拟合对深度无效`（依据 TESNet cost-volume warp 的 −7.5% 反例；见 §7.2 与 battle log #5）。结论不变，否决范围收窄。

3. **一条必须写进任何校准提案的硬上限**：**纯排序改进的绝对天花板是 +0.53 行人 AP**（0.6688 × 0.79）。这个数使"校准优先"的任何论证在数值上不成立，也定量地解释了台账为什么否决"纯重排序臂"。校准应排在框质量改进之后，因为 oracle 会随框质量一起抬升。

# Agent-3：车辆紧度（Veh 3D strict R40 5.0 → >8.0215）的机制诊断与臂设计

日期 2026-08-30。12 人专家小组。**只读分析**：未跑任何 GPU 任务，未改任何一行代码。
唯一新增的计算是一次纯 CPU 的只读统计（读 `dsec_infos_val.pkl` 的标注与冻结标定，`python -` 管道，不落盘），
以及对 `reports/q2/*.json` 与两个仓库源码的阅读。

对照与目标：控制组 `a2_seit` e012 = Veh R40 **5.0077** / Ped R40 0.6688；目标 = 公开权重 **8.0215**；
Q12（a2_seit + 36ep 余弦）正在跑，预注册 H2 = e036 > 6.80。本报告设计 Q12 之后的车臂。

---

## 0. 一页结论

**尺寸头塌缩不是"信息不存在"，也不是"头没吃饱"，是"头被接在了一根没有米制标度的线上"。**

三条互相独立的证据同时指向这一点：

1. **几何**（本报告新测，23,412 个 val 车辆标注）：DSEC 的车绝大多数是**斜侧视**，折叠观测角中位 **74.8°**，
   只有 4.1% 在 10° 以内。车长每变化 1 米，2D 框宽度变化中位 **20.6 px**。
   即"把长度误差从 0.422 m 压到 0.30 m"= 让 2D 框宽度多解释 **6.2 px**。
   **在 2D 框误差 2 px 的假设下，91.5% 的车的长度可由 2D 轮廓解到 0.30 m 以内。**
   → 假设 (a)「特征里没有尺寸信息」**被否决**。

2. **架构**（源码）：当前配置 `decoder_type: "detr"`，`detr_transformer.py` 的 decoder layer **没有 depth cross-attention**，
   `depth_predictor_lightstereo.py:405-417` 在非 `depthaware` 分支直接 `depth_embed = None`。
   query 的唯一 cross-attention 是对 `srcs_left[1:4]`（**左目**骨干 stride 8/16/32）的可变形注意力。
   而 `size3d = inter_references_dim[lvl]` = `dim_embed[lid](output)`，**只吃 query embedding**。
   **尺寸头从未见过右目、相关体、`PSV_features`、稠密深度图，也从未见过它自己那个目标的深度值。**
   它被要求从一个尺度自由的图像码里吐出**米**，而像素→米的唯一通路是 `px × z / f`，`z` 不是它的输入。

3. **同一张表的另外两列**（`FIELD_ERROR_MAGNITUDES.json`）：深度 slope 0.959 / corr **0.978**，
   横向 slope 0.995 / corr **0.994**，两者都判 `calibrated`；而 dim_l 0.237/0.590、dim_w 0.345/0.508、dim_h 0.505/0.744，
   三者全判 `shrinkage`。**被几何解码出来的字段全部标定良好，唯一被自由回归的字段全部塌缩。**
   C87 把这张表读成"逐字段质量按损失系数排序"，但 C92 已经用 12.3 倍梯度实测否决了系数解释
   （slope 只从 0.2373 动到 0.2518）。"解码 vs 自由回归"这个读法同样解释这张表，且没有被任何收据否决。

**所以主假设是 (b)，且 (b) 的具体形式不是"容量不够"或"感受野不够"，是"缺一条米制标度输入"。**
（感受野已核查过：`ms_deform_attn.py:153-155` 在 6 维 reference 下把采样偏移按 `(w/2, h/2)` 缩放，
初始化时 32 个采样点/层刚好铺满预测框；中位车 2D 框宽 88 px = stride-8 上 11 格。覆盖不是问题。）

**并列的第二主因是 (d)，且它至今零测量。** `q12_seit_long36.yaml:111` 的 `iou_thresh: 0.0` 使
`stereodetr.py:626` 硬编码的 `depth_match_type = "filter"` **完全失效**——本项目所有 dsec3dod 配置都是 0.0，
这套过滤机制**从未生效过**。于是 `group_num: 11` 下每个 GT 向 `loss_dims` 喂 **11 对**，
包含 2D IoU≈0 的那几对，全部用同一个尺寸目标，无任何质量门。L1 在这种混合正样本集上的最优解就是条件中位数，
而对定位很差的那几对，长度的条件中位数就是类别众数——**这正是 C87 量到的签名，而且它是一个独立于 (b) 的充分解释。**

(c) 优化：真实但有上界，且已在 Q12 里被测。C99 给降噪类干预在 dim_l 上的天花板 0.92×，
换算到只动形状的收缩面（C90 / §2.18）约 **R40 5.90**，**结构性地够不到 8.02**。(c) 是乘数，不是臂。

---

## 1. 新增的机器可核对事实

编号 M1–M8。每条给出可复核的文件与行号。

### M1 —— query 从未接触立体信息（源码）

`configs/001-final_exp1.yaml:83` `decoder_type: "detr"` → `stereodetr.py:1225-1230` 走 `build_detr_transformer_stereo`。
`detr_transformer.py:449-516` 的 `DecoderLayer.forward` 依次是 self-attn → `MSDeformAttn` cross-attn → FFN，
**没有 `cross_attn_depth`**（`depthaware_transformer.py:457-464` 里那一段在这条路径上不存在）；
签名里只有 `mask_depth`，`depth_pos_embed` 根本没被传进来（`detr_transformer.py:305-316`）。
同时 `depth_predictor_lightstereo.py:405-417`：`decoder_type != "depthaware"` 时
`depth_embed = None; depth_pos_embed_ip = None`。

`configs/001-final_exp1.yaml:84` `num_scale: 3` → `stereodetr.py:392-396` decoder 读 `srcs_left[1:4]`，
即**左目**骨干的 stride 8/16/32。立体分支的产物 `PSV_features`、`feature_depth_dead`、`weighted_depth`
在 `fusion_mode: null`（`001-final_exp1.yaml:80`）下**一个都不进 decoder**。

立体信息到达一个检测的全部通路只有两条：
- `stereodetr.py:463-469`：`depth_map = grid_sample(weighted_depth, 单点)`，在 `one_w_uncertainty`（`:524-526`）下**直接就是** `pred_depth`；
- 共享骨干的梯度（`loss_depth_map` 反传到 `srcs_stereo`，而 `srcs_left` 是它的前半段）。

### M2 —— 尺寸头没有深度输入，也没有迭代精化

`stereodetr.py:497-499`：`size3d = inter_references_dim[lvl]`，来自
`depthaware_transformer.py:618-619`（detr 版同构）：

```
if self.dim_embed is not None:
    reference_dims = self.dim_embed[lid](output)
```

三个事实：
- **输入只有 `output`（query embedding）**。`depth_map` 在 `stereodetr.py:465` 才被采样，位置在**之后**，且从不回灌。
- **非残差、非迭代**：`bbox_embed` 走 `tmp += reference` 的迭代精化链（`:425-433`）并被挂到
  `decoder.bbox_embed`（`:211`）；`dim_embed` 每层从零重新预测，层间不累积。
- **无零初始化**：`init_box: False`，且 `stereodetr.py:90-91` 的零初始化只针对 `bbox_embed`。
  `dim_embed_3d = MLP(256, 256, 3, 2)`（`:73`）用默认初始化，输出是加性残差，
  最终尺寸 = `class_mean_hwl[label] + residual`（见 `loss_dims:910-911` 与 `loss_iou3d:1044-1045`）。

**结论**：这个头要输出米，但它的输入里没有任何米。像素→米只有 `px·z/f` 一条路，`z` 不在它手里。

### M3 —— 匹配代价里没有尺寸、没有深度、没有 3D 中心；而且 IoU 门是死的

`matcherstable_fg_only.py:129-132`：

```
C = cost_bbox·L1(l,r,t,b) + cost_3dcenter·L1(cx,cy) + cost_class·focal + cost_giou·(-GIoU) + cost_depth·L1(z)
```

`001-final_exp1.yaml:130-135`：`set_cost_class: 2`、`set_cost_bbox: 5`、`set_cost_giou: 2`、
**`set_cost_3dcenter: 0`**、**`set_cost_depth: 0`**，`cec_beta: 0.5`。
→ **指派 100% 由 2D 决定**，没有任何 3D 项，更没有尺寸项。

`matcherstable_fg_only.py:153-172` 产出 `indices_filted`（按 `matched_iou >= self.iou_thresh` 过滤）。
`q12_seit_long36.yaml:111` `iou_thresh: 0.0` → **`indices_filted ≡ indices`**。
Grep 全仓：`a2_seit_evalonly / q1 / q2 / q3 / q5 / q6 / q7 / q8 / q11 / q12` 的 `iou_thresh` **全部是 0.0**。
而 `stereodetr.py:626` 把 `depth_match_type` 硬编码为 `"filter"`，
`loss_map`（`:1131-1145`）里 **`'depths' → loss_depths_stable`**，
所以 `dims`、`angles`、`depths`、`iou3d` **四个损失全部走 `indices_filted`，而这个过滤器从未生效**。

叠加 `group_num: 11`：每个 GT 每层得到 **11 个匹配 query**，11 对全部以同一个 `size_3d` 为目标，无质量加权。

### M4 —— DSEC 的车长在 2D 轮廓里，而且信号很强（本报告新测，纯 CPU）

来源：`/data1/lyq/data/EV_3DOD/DSEC/dsec_infos_val.pkl`，全部 1,140 个 interval × 前 10 帧，
23,412 个 Vehicle 标注；`P2[0,0] = f = 583.30812`，`cx = 336.834`；`dimensions = (l, h, w)`（中位 4.523 / 1.640 / 1.932）。
折叠观测角 `s = |sin(alpha)|`、`c = |cos(alpha)|`，`alpha` 直接取标注字段。

| 量 | p10 | p25 | **中位** | p75 | p90 |
|---|---:|---:|---:|---:|---:|
| 折叠 \|alpha\|（度） | 18.9 | 38.8 | **74.8** | 83.3 | 87.5 |
| 可见侧面在图像上的宽度 `L·s·f/z`（px） | 32.8 | 61.1 | **90.6** | 153.3 | 291.2 |
| **`∂w2d/∂L = s·f/z`（px / 米）** | 7.9 | 13.5 | **20.6** | 33.4 | 57.5 |
| 侧面沿视线的深度跨度 `L·c`（m） | 0.18 | 0.53 | 1.30 | 3.40 | 4.27 |
| 该跨度对应的视差跨度（px） | 0.07 | 0.24 | 1.01 | 3.48 | 11.08 |
| 真值 2D 框宽（px） | 36.2 | 51.5 | 88.4 | 156.4 | 310.4 |
| 真值深度（m） | 8.5 | 14.3 | 23.4 | 32.3 | 42.1 |

派生：

- \|alpha\| < 5° / 10° / 20° 的占比 = **0.2% / 4.1% / 10.8%**。**正后视的车在 DSEC 几乎不存在。**
- 可见侧面 < 8 px（stride-8 上不足一格）的占比 = **1.2%**；< 16 px = 5.2%。
- 由 2D 框宽反推长度的隐含精度（逐目标 `err_px / (s·f/z)`）：
  - 2D 框误差 1 px → 中位 **0.049 m**，95.0% 的车 < 0.30 m
  - 2D 框误差 2 px → 中位 **0.097 m**，**91.5%** < 0.30 m
  - 2D 框误差 4 px → 中位 **0.194 m**，75.5% < 0.30 m

**互补性（重要，决定候选排序）**：斜侧视的车（主体）长度写在**图像宽度**里，但它的可见面几乎与视线垂直，
深度跨度小——**49.7% 的车的侧面深度跨度不到 1 px 视差**。正后视的车（少数）反过来。
换言之在这套数据上，**车长主要是一个 2D 轮廓量，不是一个立体深度量**。
再叠加 `correlation_volume(feature_stereo[0], ..., 96//4)`（`depth_predictor_lightstereo.py:366`）
在 stride 4 上只有 24 个视差级、每级 4 个图像像素，
**相关体在其原生采样下本来也分辨不出一辆车自己的深度剖面。**

### M5 —— 已归档的"尺寸可观测性天花板"是**线性模型天花板**，两处系统性低估

`tools/q2_scoring/size_observability_ceiling.py`：

- `_design()`（`:77-107`）给出 14 项：`w2d, h2d, z, log z, w2d·z, h2d·z, (w2d·z)|sinθ|, (w2d·z)|cosθ|, (h2d·z)|sinθ|, sin2θ, cos2θ, w2d/h2d, (w2d·z)(h2d·z), 1`。
  **没有 `1/|sinθ|`。** 而真实几何是 `L = (w2d·z/f − W̄·|cosθ|)/|sinθ|`，一个**除法**。岭回归表达不了它。
- `:209-217` 用 `truth_yaw = annotation["rotation_y"]`，**不是 `alpha`**。
  640 宽的图、`cx = 336.8`，`arctan((u−cx)/f)` 最大到 30°；`rotation_y` 与观测角可差 30°，
  而 `|sinα|` 在小角处正是对这 30° 最敏感的地方。

所以 `SIZE_OBSERVABILITY_CEILING.json` 报的车长天花板 0.2870 m / r 0.9090 是**下界**，不是天花板；
`SIZE_OBSERVABILITY_MODEL_INPUTS.json` 的 0.4036 m / r 0.5670 同理。
**"headroom_error_ratio = 1.047"不能读成"头已经榨干了自己的输入"。**

但这两个收据仍有一个方向是成立且致命的：**头的 0.4224 m 不优于一个 4 标量的线性函数。**
256 维里它什么额外的东西都没读出来。

### M6 —— 重标定的上界只有 12%（`SLOPE_BIAS_BY_FIELD.json` 车/length/correction）

- 原始中位绝对误差 0.42240
- 最优常数去偏（均值/中位）→ 0.37116 / 0.38310
- 最小二乘仿射（slope 1.4685）→ 0.43197，**更差**
- **中位最优仿射（slope 0.66）→ 0.37122，即 12.1%**

→ 收缩面保留 ≈ 0.879 → Veh R40 ≈ **6.36**。
**"用条件先验/分桶均值/去偏把塌缩修回来"这一族的上界是 6.36，够不到 8.02。**
候选 3（尺寸-外观条件化先验）因此**不能作为独立臂**，只能做搭车项。这与 C87 自己的注记一致
（"常数只能修偏移不能修斜率"），本条把它量化了。

### M7 —— 竞品的第二阶段是**纯几何**的，分类权重为 0

`configs/stereo/dsec_models/evstereo.yaml:303-404`，`REGRESSION_HEAD: DetHeadRefineBevEvSem`：

- `ROI_GRID_POOL.GRID_SIZE: 3` → `det_head_refine_bev_ev_sem.py:198-222`：
  27 个网格点按 **proposal 自己的 LWH 缩放、按 proposal 自己的 yaw 旋转、平移到 proposal 中心**，
  即**在候选框自身的定向体内**取点；每点用 `StackSAModuleMSG`（PointNet++ set abstraction，
  `POOL_RADIUS 0.8`、`NSAMPLE 16`）从 BEV `spatial_features_2d_pool` 聚合。
- 规模极小：`POOL_CHANNEL 32`、`SHARED_FC [16]`、`REG_FC [8]`。
- `LOSS_WEIGHTS`（`:397-404`）：**`cls_weight: 0.0`**、`loc_weight: 1.0`、`dir_weight: 0.0`、
  **`iou_weight: 1.0`（IOU3dLoss）**、`code_weights: [1,1,1,0.5,0.5,0.5,1]`（xyz 1.0、**dwl 0.5**、yaw 1.0）。

**这一条直接区分了它与我们失败的 Q3。** Q3 把 `IoU3dLoss` 放在一阶段：
提议常与真值不相交（`loss_iou3d` docstring 自己承认"disjoint 时梯度恰为零"），
且它与 `loss_ce` 抢一个已被瓜分完的预算，结果（C78）是排序效率 50%→77% 而几何池掉 40%。
竞品把同一个项放在**已经匹配上的 ROI**上，并**把分类权重设成 0**，所以它不可能通过改分数来涨 AP。
按 C78 自己立的规矩（机制归类必须由 oracle 臂判定），这是一个**可检验的不同机制**，不是对失败的辩解。

### M8 —— 竞品的 `dense_head_2d` **不回归尺寸**；这条候选双重死亡

`evstereo.yaml:179-231`，`DENSE_HEAD_2D: MMDet2DHead / ATSSAdvHead`，
`:196` **`num_extra_reg_channel: 0`**，文件自己的注释写着 `None: 0, hwl: 3, hwl+roty: 5, hwl+roty+alpha: 7`。
**它是一个纯 2D 框 + centerness 头，一个尺寸通道都没有。**
"公开权重缺的那 35 个 `dense_head_2d.*` 张量"不是尺寸监督。

而且我方的 D1 已经实现过训练期稠密 2D 辅助头，判定 `STOP_VEHICLE_REGRESSION`
（Veh 3D 6.2552 → 5.4986，Veh oracle 11.3907 → 10.0444，C68）。
**候选 4（辅助稠密 2D 尺寸监督）应当从清单上划掉。**

---

## 2. 四个假设的裁决

| 假设 | 裁决 | 支持证据 | 反对证据 | 还缺的测量 |
|---|---|---|---|---|
| **(a) 特征里没有尺寸信息** | **否决** | 无 | M4（20.6 px/米；2 px 框误差 → 91.5% 的车可解到 0.30 m 内）；M5（唯一支持它的收据是线性模型伪影） | P1、P5（把 M5 的两个缺陷补上重跑） |
| **(b) 头容量/结构** | **主因**，但形式是"缺米制标度"而非"容量/感受野" | M1（query 不接触任何立体量）；M2（头没有深度输入、无迭代、无零初始化）；M3 表（被解码的字段全 calibrated，被自由回归的全 shrinkage）；M5（256 维里读出的东西不优于 4 标量线性函数） | 感受野已排除：`ms_deform_attn.py:153-155` 按框缩放采样、中位框 88 px = stride-8 上 11 格 | P1（几何反解在模型自己的输入上能到多少） |
| **(c) 优化（恒定 LR + 200× 裁剪 + 3% 份额）** | **真实但有上界，且不是臂** | C91 / C108 / C88 | C92（付 12.3 倍梯度，slope 0.2373→0.2518，双类 R40 退化）；C99（dim_l 的 `Var(u)` 只占 15.3%，降噪天花板 0.92× → **R40 ≈ 5.90**）；M6（重标定上界 12% → R40 ≈ 6.36） | Q12 正在给这条的答案；不必另开臂 |
| **(d) 监督/匹配** | **并列主因，零测量** | M3（11 对/GT、无质量门、`filter` 从未生效、代价里无尺寸/深度/3D 中心）；L1 在混合质量正样本集上的最优解 = 条件中位数 = 类别众数 | 无 | **P2**（本报告认为最该先跑的那一个） |

**(b) 与 (d) 的关系不是竞争，是叠加。** (b) 说"头拿不到能定尺寸的量"，
(d) 说"就算拿得到，一半的监督对也没有可定尺寸的证据"。两者各自都是充分的，
所以任何单臂实验都必须能把它们分开——这正是 P2 与 V1/V2 拆臂的目的。

---

## 3. 缺失的测量：探针清单（全部零训练，除 P2 外全部纯 CPU）

> 纪律：C99 立的规矩是"任何新臂在启动前必须先报出目标字段的 `Var(u)` 占比"。
> 本清单把这条推广为：**任何新臂在启动前必须先报出它所依赖的那条通路在冻结 dump 上的可达值。**

### P1（纯 CPU，约 10 分钟）—— **决定性**：闭式几何反解在模型自己的输入上能到多少

在 `reports/q2/a2_full/scoring_table.npz` + `dsec_infos_val.pkl` 上，
取 2D IoU ≥ 0.3 关联上的 Vehicle（14,263 个，与全部既有收据同群体），逐目标计算

```
alpha_hat = rotation_y_hat - arctan((box_cx - 336.834) / 583.308)
m_w       = box_width * depth_hat / 583.308
L_geo     = ( m_w - W_bar * |cos alpha_hat| ) / max(|sin alpha_hat|, tau)     # tau = 0.25
L_geo     <- class_mean_l  where |sin alpha_hat| < tau                        # 退化区回落到先验
```

`W_bar = 1.9698`（`class_mean_size_hwl` 的 w）。报 `median |L_geo - L_gt|`、`< 0.30 m` 的占比，
并做**逐输入替换消融**：{模型框, 真值框} × {模型深度, 真值深度} × {模型 alpha, 真值 alpha}，8 格。

- **预注册预测**：真值三输入格中位 ≤ **0.25 m**；模型三输入格中位 ≤ **0.34 m**。
- **V1 的发车门**：模型三输入格中位 **≤ 0.38 m**（即不学习、纯反解就已经比头的 0.4224 好 ≥ 10%）。
  不过门则 **V1 与候选 2/3 全部不发车**，预算改投 V4（两阶段 ROI）。
- 这条同时兑现/证伪 M5：若真值格 ≤ 0.25 而 `SIZE_OBSERVABILITY_CEILING` 报 0.287，
  说明那份收据确实被线性设计与错角度低估了。

### P2（一次**只前向、不反传**的 pass，约 0.3 GPU·h；本 agent 不跑，登记为下一位操作者的第一件事）—— 决定性：(d)

在控制组 checkpoint 上跑 ~200 个**训练**批（`training=True` 以启用 11 组），
对每一个进入 `loss_dims` 的 `(query, target)` 对记录：2D IoU、GT 长度、预测长度、组号。报：

1. 11 组匹配 2D IoU 的直方图与分位（这就是尺寸头实际看到的样本质量分布）；
2. **按 2D IoU 分箱分别拟合 `pred_l ~ gt_l` 的 slope 与 corr**。

- **可证伪**：若最高 IoU 十分位的 slope ≥ **0.55** 而合并 slope 仍是 0.2373，
  塌缩里有很大一块是**监督混合伪影**，V2（质量门控）立刻成为最便宜的修法。
- 若各 IoU 箱的 slope 都在 0.24 附近，**(d) 死亡**，全部预算给 (b)。

### P3（纯 CPU，分钟级）—— 把 C99 的 `Var(u)` 分解在 `L_geo` 的残差上重算

C99 说 dim_l 的误差方差只有 15.3% 落在 `Var(u)`，因此降噪类干预天花板 0.92×。
但那是**对头的输出**做的分解。若 `L_geo` 对真值的 slope 接近 1，
则"系统性那 84.7%"是**可通过重参数化移除的**，而不是"需要更多训练才能移除的"。
这条改变的是 C99 的**适用范围**，不改变 C99 本身。

### P4 / P5（纯 CPU，分钟级）—— 修 `size_observability_ceiling.py` 的两个缺陷后重跑

- P4：加 `--observables mixed:{box|depth|yaw}` 三个中间格，定位真值天花板与模型天花板之间那 0.116 m 是谁贡献的。
- P5：把 `rotation_y` 换成 `alpha`，并在 `_design()` 里加 `1/max(|sinα|, 0.25)` 与 `(w2d·z)/max(|sinα|,0.25)`。
  **预注册预测**：真值天花板从 0.287 降到 **< 0.20 m**。若不降，M4 的敏感度论证有洞，(a) 重新打开。

### P6（纯 CPU，分钟级）—— 立体剖面对哪一部分车有用

把 dim_l 误差按 \|alpha\| 三分位分层报一次。
- 若误差在正后视三分位（\|alpha\| 小）显著更大，立体深度剖面分支有一个明确的目标人群（但只占 ~11%）；
- **若误差在 alpha 上是平的，几何故事整体错了**，因果回到 (c)+(d)。
这一条必须写进后续每个臂的读数里（分层读，不只读合并中位）。

### P7（纯 CPU，分钟级）—— **强制**：把收缩面限定到 `dim` 单字段

C90 的教训是"用全字段收缩面给只改部分头的臂设门会系统性高估"。
§2.18 的 `--shrink-fields shape` **同时缩 dim 和 yaw**，
所以本报告下面所有由"长度中位误差 → 保留系数 → R40"推出的预测**都继承了一个已知方向的乐观偏差**。
发任何臂之前必须先跑 `field_substitution_ap.py --shrink-fields dim`（depth 和 yaw 都固定 1.0）拿到正确的曲线。

**同时必须修正本报告自己的一个方法学错误**（自我红队，见 §6）：
收缩面的参数是**逐目标误差乘子**，而一个去塌缩的干预**主要只改善外侧分位**（大车/小车），
中位那三个分位本来就接近类别众数。所以"中位误差 0.422 → 0.296"**不等于**"保留 0.70"。
臂的落点必须像 C109 定位 Q8 那样，**用逐目标误差比拟合出实际坐标**，
工具是 `common_population_fields.py` + 收缩面，不能用中位数换算。

---

## 4. 机制候选排序

### 换算表（供参考，**已知乐观，P7 之前不得当作门**）

只缩尺寸+朝向的收缩面（C90 / §2.18，depth 固定 1.0）：

| 保留系数 | 1.00 | 0.92 | 0.879 | 0.80 | 0.742 | 0.70 | 0.60 | 0.40 | 0.00 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Veh R40 | 5.0077 | ~5.90 | ~6.36 | 7.2368 | ~8.02 | ~8.49 | 9.9579 | 11.7937 | 12.2443 |
| 对应 dim_l 中位（基 0.4224） | 0.422 | 0.389 | 0.371 | 0.338 | 0.313 | 0.296 | 0.253 | 0.169 | 0 |

（0.92 / 0.879 / 0.742 三格是相邻实测格之间的线性内插；台账自己把 8.0215 的门读作"约 0.70"，本报告采用更保守的 0.70。）

---

### 候选 #1 —— **米制标度重参数化的尺寸头**（首选）

**改法**（约 40 行，全部在 `stereodetr.py` 的 `forward` 与 `depthaware_transformer.py` / `detr_transformer.py` 的
`dim_embed` 调用处；不新增模块、不改 decoder、不改评测路径）：

1. 把 `dim_embed` 的调用从 decoder 内部（`detr_transformer.py`/`depthaware_transformer.py:618-619`）
   移到 `stereodetr.py` 的每层循环里，**放在 `depth_map` 采样之后**，这样它能吃到 `z`。
   （decoder 内部只需保留一个 `output` 的透传；`inter_references_dim` 的接口形状不变，
   评测路径与 checkpoint 迁移由 G2 builder 的 migration report 覆盖。）
2. 输入改为 `[hs[lvl], g]`，`g` 全部用**已经在这个循环里算出来的量**、且**全部 detach**：
   ```
   z   = depth_map.detach()                                # (B,Q,1)  已在 :465 算出
   w2d = (coord[...,2]+coord[...,3]) * W_img               # 归一化 l+r → 像素
   h2d = (coord[...,4]+coord[...,5]) * H_img * scales      # 与 :500-502 同一套缩放
   u   = coord[...,0] * W_img
   a   = heading_from_bins(angle) - atan2(u - cx, fx)      # 观测角
   g   = [ log(w2d*z/fx), log(h2d*z/fy), log z, |sin a|, |cos a|, sin2a, cos2a, w2d/h2d ]
   ```
3. 输出改为 **log-ratio**：`size = class_mean_hwl[label] * exp(dim_embed([hs, g]))`，
   零输出 = 类别均值（C07 早就写过 `mean*exp(residual)` 是正确形式；当前是加性）。
4. **可选强化**（建议同臂启用，因为它是这条机制的核心断言）：
   把闭式反解直接放进头，让 MLP 只学修正量
   ```
   L_geo = ( w2d*z/fx - mean_w * |cos a| ) / clamp(|sin a|, 0.25, 1.0)
   l     = L_geo * exp(delta_l)          # delta_l 由 MLP 出
   ```
5. **必须加的两条合同测试**：
   (i) `z` 与 `a` 进入尺寸头前 **detach**——否则 `loss_dim` 的梯度会流进深度图，
   把 C92 实测过的零和预算战重新打开（C92：抢来的份额让深度中位从 0.4279 退到 0.4809）；
   (ii) 断言 `depth_pre_type == "one_w_uncertainty"`——因为 `stereodetr.py:503` 的
   `depth_geo = size3d[:,:,0]/box2d_height*fx + size3d[:,:,2]/2` 是**反向**耦合 `size → z`。
   当前分支不用它（C106），所以今天没有环；但一旦切回 `avg` 就会形成真实的代数环 `L → z → L`。

**依据**：M4（20.6 px/米，2 px 框误差 → 91.5% 的车 < 0.30 m）+ M2（头现在拿不到 `z`，形不成米制量）
+ M3 表（被解码的字段 corr 0.98/0.99，被自由回归的 corr 0.59）。
预期降幅**下界由 P1 给定**：若 P1 模型输入格是 0.30 m，学习残差应落在 0.26–0.30 → 保留 0.62–0.71 → **R40 9.0–8.4**；
若 P1 是 0.34 m，落在 0.30–0.34 → 保留 0.71–0.80 → **R40 8.4–7.2**。保守下限 **7.2**，中位期望 **8.4–9.0**。

**GPU 成本**：与对照逐位相同的步时。12 ep scout **9.2 h 墙钟 / 36.8 GPU·h**；36 ep **27.6 h / 110.4 GPU·h**。

**Kill 条件**：
- 发车前：P1 模型输入格 > 0.38 m → 不发车。
- e006：`loss_dim` 的自身头梯度份额若超过 15%（说明 detach 没做对，在抢预算）→ 停。
- e012：共同群体上 Vehicle `dim_l` 中位绝对误差 **> 0.36 m** → 杀。
- 任何读数点：Veh **oracle** R40 低于 Q12 同 epoch 的 oracle → 杀（C43、C78：天花板不许跟着塌）。
- 任何读数点：Ped R40 低于 Q12 同 epoch 的 0.85 倍 → 杀（C68 联合门）。
- e012 必须同时报 `dim_l` 按 \|alpha\| 三分位的分层误差（P6 的读法）。

---

### 候选 #2 —— **正样本质量门 + 指派代价里的 3D 项**（最便宜，且能单独证伪 (d)）

**改法**：三个配置级旋钮，**零新增参数**。

- (a) `legacy_overrides.iou_thresh: 0.0 → 0.25`。这一行让 `stereodetr.py:626` 硬编码的 `"filter"` 第一次真正生效。
  **爆炸半径必须写进预注册**：`loss_map` 里 `dims / angles / depths(=loss_depths_stable) / iou3d` 四项**同时**被门控。
  这是一个多变量改动，所以本臂的登记必须写成"给形状与深度损失加同一个质量门"，不能写成"给 dims 加门"。
- (b) 若要单变量，则改用**软门**：在 `loss_dims` 里按 `matched_iou` 加权（不改 `indices_filted`），
  这样只动 dims 一项，是真正的单变量。**推荐走这条**。
- (c) `set_cost_3dcenter: 0 → 2`（`loss_center` 系数已经是 10，指派代价却是 0，这本身就是一处不一致）。
  单独一格，不与 (b) 同臂。

**依据**：M3 + L1 条件中位数论证。**预期降幅完全由 P2 决定**，发车前不给数字（这正是 C99 立的规矩）。

**GPU 成本**：12 ep scout **9.2 h / 36.8 GPU·h**。与 #1 正交，可叠加。

**Kill 条件**：
- 发车前：P2 的最高 IoU 十分位 slope < 0.40 → 不发车（(d) 已被证伪）。
- e006：合并 slope 未达 **0.35** → 杀。
- **Ped 门必读**：质量门会减少正样本，这正是 C18 / C64 的行人失败模式。
  Ped R40 低于 Q12 同 epoch → 杀。这一条对 (a) 硬门版本尤其危险，是推荐软门的原因。

---

### 候选 #3 —— **两阶段 ROI 精化（对标竞品，但落在图像 + 深度图空间）**

**改法**（约 300 行 + 一个 ROIAlign 调用，最重）：
末层 decoder 之后，对每个 query 用 `camera_boxes_from_encoded`（`loss_iou3d` 已经在用这个函数）合成 3D 框，
把 8 个角投影到左目、取轴对齐外壳，然后

- 从 `feature_depth_dead`（`depth_head` 之后的 256 通道立体聚合特征，stride 4；
  目前只有 `sample_cat` 分支用，**当前配置完全没用**）ROIAlign 出 7×7；
- 从 `weighted_depth` ROIAlign 出 7×7，并**按该 proposal 自己的深度归一化**，
  使它是一个*相对*深度剖面（这正是 M4 里正后视少数派需要的那个量）；
- 两者 concat → 2 层 conv + FC → `Δ[log h, log w, log l, Δu, Δv, Δz, Δθ]`；
- 损失 `SmoothL1 + IoU3dLoss`，**`cls_weight = 0` 并写进合同测试**（M7）。

**依据**：M7（这是竞品在 0.65/0.70 上领先的那个部件）+ M1（这是唯一能让 `PSV_features` 参与检测的路径）。
预期：不给数字。这条的价值在于它**同时覆盖 M4 的两个人群**（图像轮廓 + 深度剖面），
而 #1 只覆盖主体人群。

**GPU 成本**：步时 +~15%。12 ep scout **10.6 h / 42.3 GPU·h**；36 ep **31.7 h / 126.9 GPU·h**。

**Kill 条件**：
- Veh oracle R40 不得下降（Q3 就是死在这里，C78/C43）。
- e012：共同群体上精化后框的 3D IoU 中位必须比精化前高 **≥ 0.03 绝对值**。
- `cls_weight == 0` 的合同测试必须在跑之前 PASS，否则任何 AP 变化都无法归因于几何（C78、C120）。

**排序意见**：**第三位，不是第一位**。在 P1 给出答案之前，它的复杂度/信息比最差。

---

### 候选 #4 —— 尺寸-外观条件化先验（分桶均值替代全局类均值）

**降级为搭车项，不做独立臂。** 依据 M6：全局最优仿射重标定的上界是 12%（R40 ≈ 6.36），
而分桶先验是重标定的一个受限子集，上界只会更低。
（C87 自己的注记："常数只能修偏移不能修斜率"。）
作为 #1 的搭车项有意义，因为它给 log-ratio 输出一个更好的零点。

### 候选 #5 —— 匹配代价里加尺寸项

**不推荐单独立项**，理由是代价矩阵在 `@torch.no_grad()` 里、用**当前**的尺寸预测算，
而尺寸预测正在塌缩到类别众数——一个塌缩的量做指派会把所有目标推向同一个代价，几乎是常数项。
先做 #2 的 (c) 格（3D 中心代价），尺寸代价等 #1 把尺寸头修好之后再考虑。

### 候选 #6 —— EMA/SWA + 完整余弦

**不是臂**。C99 天花板 0.92× → R40 ≈ 5.90（M6 换算）。
且 Q12 正在测完整余弦这一半，EMA 是它的边际增量。只能作为 #1 成功后的收尾搭车项。

### 候选 #7（本报告新增，来自源码）—— 三处零成本的静默缺陷

全部作为 #1 的搭车项，各自都有已写好且已被合同测试覆盖的机制：

- **7a `dim_denominator: absolute → class_mean`**。默认值在 `stereodetr.py:603`，
  `build_voxel_event.py:67-73` 从 `losses.dim_denominator` 读取，
  而 `q12_seit_long36.yaml` 的 `losses:` 块**没有这一项**，所以 Q12 跑的是 `absolute`，
  C89 量到的 1.61× 短车偏置**正在生效**，方向与塌缩一致。
  `q5_dim_denominator.yaml` / `q6_shape_budget.yaml` 已经写好了 `class_mean`，
  但 `reports/q5/` 磁盘上没有任何 JSON/MD 收据——**这个问题至今没有答案**。
- **7b 尺寸做成迭代残差**。`bbox_embed` 有迭代精化链，`dim_embed` 没有（M2）。
  改成 `ref_dim_l = ref_dim_{l-1} + MLP_l(·)`、层 0 零初始化（于是第一次预测**恰好**是类别均值），
  约 6 行，与 `with_box_refine: True` 已有的做法同构。
- **7c 轮廓一致性辅助监督**。加 `| log(w2d_from_3Dbox) − log(w2d_gt) |`，
  其中 `w2d_from_3Dbox` 是**合成的 3D 框**投影出的轮廓宽度。
  按 M4 这是一个 20.6 px/米 的约束，而且与 `loss_iou3d` 不同：它没有深度耦合，也没有 disjoint 时的零梯度区。
  权重必须低于 `loss_dim`，否则会被已经很强的 2D 框监督拖着走。
  **这一条也可以做成独立单变量臂**，如果 #1 因为 P1 不过门而不发车。

---

## 5. 预注册草案

### 5.0 通用纪律（每个臂开跑前的 checklist）

1. **C118**：打印本臂配置与**控制组 checkpoint 实际训练配置**（`a2_seit.yaml`）的逐键差集，不是与 eval 配置的差集。
2. **C122**：`world_size = 4`、`loader.batch_size = 64`、657 步/epoch 全部锁死；换卡数即是第二个变量。
3. **C121**：`reports/epst4d_v3/seit_pool/seit_donors.npz` 必须在跑之前确认存在（否则 20 分钟 CPU 重建）。
4. **P7**：`--shrink-fields dim` 的收缩面必须先跑出来，本文件所有 R40 预测按新曲线重算后才生效。
5. 所有读数一律 **R40**（C84、C93）；`oracle` 臂与 model 臂同时报（C78、C43）；
   逐字段误差在**共同群体**上比（C119）；`dim_l` 按 \|alpha\| 三分位分层报（P6）。
6. 对照一律是 **Q12 的同 epoch cell**（e012 对 e012，e036 对 e036），不是台账里的 5.0077。
   若 Q12 的 H1 失败（e012 复现不了控制组），本方案的全部相对门失效，必须先解决那个问题。

### 5.1 四卡成本表（657 步/epoch、4.2 s/step、4×GPU）

| 项目 | epochs | steps | 墙钟 | GPU·h |
|---|---:|---:|---:|---:|
| scout | 12 | 7,884 | **9.20 h** | 36.8 |
| mid | 24 | 15,768 | 18.40 h | 73.6 |
| full | 36 | 23,652 | **27.59 h** | 110.4 |
| V4（步时 +15%）scout | 12 | 7,884 | 10.58 h | 42.3 |
| V4 full | 36 | 23,652 | 31.73 h | 126.9 |

### 5.2 臂与顺序

| # | 臂 | 单变量 | 预算 | 前置门 |
|---|---|---|---|---|
| 0 | **P1 / P3 / P5 / P6 / P7** | — | 纯 CPU，合计 < 1 h，**零 GPU** | 无。**必须先跑完** |
| 0b | **P2** | — | 0.3 GPU·h（只前向） | 无 |
| 1 | **V2**：`loss_dims` 按 `matched_iou` 软加权 | 一处，只动 dims | scout 12 ep = 9.2 h | P2 的高 IoU 箱 slope ≥ 0.40 |
| 2 | **V1**：米制标度尺寸头（含搭车项 7a/7b） | 尺寸头的输入与参数化 | full 36 ep = 27.6 h | P1 模型输入格 ≤ 0.38 m |
| 3 | **V3**：7c 轮廓一致性辅助损失 | 一个新损失项 | scout 12 ep = 9.2 h | 仅当 V1 未发车或 V1 落在 7.2–8.0 之间时启动 |
| 4 | **V4**：两阶段 ROI 精化 | 新的第二阶段 | scout 12 ep = 10.6 h | V1 报出结果之后 |

单卡池串行的最短取胜路径：**P0（0 GPU）→ P2（0.3）→ V2 scout（9.2）→ V1 full（27.6）= 约 37 小时墙钟**。
若 V1 落在 8.4–9.0，第 37 小时就过门；若落在 7.2–8.0，再加 V3 scout 9.2 h 与 V1+V3 的 full 27.6 h。

### 5.3 可证伪的 R40 预测（**P7 重算后生效**；此处为按现有 shape 面的版本）

| 读数点 | V2 | V1 |
|---|---|---|
| e012 Veh R40 | ≥ **5.60**（对 Q12 e012 ≈ 5.01） | ≥ **6.20** |
| e012 `dim_l` 中位（共同群体） | ≤ 0.40 m | ≤ **0.36 m** |
| e012 `pred_l ~ gt_l` slope | ≥ **0.35** | ≥ **0.45** |
| e036 Veh R40 | —（V2 只跑 scout） | ≥ **8.60**（对门 8.0215 留 0.58 的余量，见 §6 统计学家意见） |
| e036 `dim_l` 中位 | — | ≤ **0.30 m** |
| 任意点 Veh oracle R40 | 不得低于 Q12 同 epoch | 不得低于 Q12 同 epoch |
| 任意点 Ped R40 | ≥ Q12 同 epoch | ≥ 0.85 × Q12 同 epoch |

**Kill 一览**（任一触发即停，不做决定性失败后的补跑与阈值调整，C68）：

- V1：P1 不过门 / e006 `loss_dim` 自身头梯度份额 > 15% / e012 `dim_l` > 0.38 m / oracle 下降 / Ped 崩。
- V2：P2 不过门 / e006 slope < 0.35 / Ped R40 低于 Q12。
- V3：e012 `dim_l` 未改善 ≥ 5% / 2D GIoU 退化 > 3%。
- V4：`cls_weight == 0` 合同测试不过 / oracle 下降 / 精化前后 3D IoU 中位提升 < 0.03。

### 5.4 一条必须写进预注册的"预期失败模式"

若 V1 出现 **corr 大涨而误差不动**（C109 在 Q8 上量到的那个签名：corr 0.59→0.84、误差只降 4%），
**判 FAIL，不判部分成功**。C109 立的规矩是"预注册门里若含相关/斜率，必须同时含该字段的绝对误差门"，
上表已经照办：slope 门与 `dim_l` 中位门必须**同时**通过。

---

## 6. Battle log

### 反对意见 1 —— 红队质疑者（对多数派 #1 的核心质疑）

> "M4 是在**真值** 2D 框上算的敏感度。它证明的是'如果你的 2D 框准到 2 px，长度就出来了'。
> 我们的 2D 框准到 2 px 吗？Veh 2D R11 是 24.80 对他们 29.60，我们在 2D 上就已经落后。
> 如果匹配集上的 2D 框误差是 5–8 px，M4 的表格立刻变成'中位 0.24–0.39 m'，V1 的整个前提就没了。
> 更难堪的是：`bbox_loss_coef: 5` + `giou_loss_coef: 2`，2D 重叠在梯度审计里占 ~84%（C88），
> 2D 框**已经是被优化得最狠的那个量**了，它还是不够紧到让 IoU 0.70 过线。
> 你现在提议把尺寸头挂到一个已经被榨干的量上。"

**处理**：接受为**发车门**，不接受为否决。这条质疑被完整地翻译成 P1 的 kill 条件——
P1 的模型输入格用的就是模型自己的 2D 框、自己的深度、自己的 yaw，
如果框真的差到 5–8 px，P1 会直接返回 > 0.38 m，V1 就不发车。
**这是本报告唯一一处允许一个论证在开跑前被一次 CPU 计算杀死的地方，而它应该在。**

补充一条对红队有利的观察：`SLOPE_BIAS_BY_FIELD` 里 lateral 的 corr = 0.9941、
中位误差 0.153 m。lateral 由投影中心 × 深度算出，它的精度反过来说明投影中心（也就是 2D 框的中心）
是准的。但**中心准不等于宽度准**，红队的质疑在宽度上仍然成立。

### 反对意见 2 —— 双目几何专家（方向相反的反对）

> "你正在把一篇双目论文写成单目论文。M4 自己的表里写着：可见侧面的深度跨度中位 1.30 m，
> **49.7% 的车对应不到 1 px 视差**；而 `correlation_volume(feature_stereo[0], ..., 96//4)`
> 在 stride 4 上只有 24 个视差级、每级 4 个图像像素。
> 这不是'头读不到深度剖面'，这是**相关体本身就没构造出深度剖面**。
> 那么真正的发现应该登记在 cost volume 的构造上，不是在头上。
> 而且在你下结论'车长是 2D 量'之前，请先跑 P6：
> **如果 dim_l 误差在 \|alpha\| 上是平的，你的整个几何故事就是错的**，
> 因为按你的说法误差应该集中在正后视那 11%。"

**处理**：**接受，并把 P6 提为强制前置探针，同时写进后续每个臂的读数合同。**
这条反对产生了本报告最有价值的一个可证伪点：几何解释预测误差随 \|alpha\| 单调，
监督/优化解释预测误差在 \|alpha\| 上平坦。两者可以用一次纯 CPU 分层统计分开。
关于 cost volume 的构造：同意这是一个真实的独立发现（24 级 × 4 px，
台账 C73 只讨论过"细化视差采样对深度中位没用"，**没有讨论过它对深度剖面/尺寸的影响**），
但它不改变 V1 的设计——V1 用的是 `weighted_depth`（聚合网络已经插值到亚像素的那个），
不是原始相关体。这条应当作为 V4 的输入选择依据登记：
V4 的深度剖面要从 `weighted_depth` 取，不从 `gwc_volume` 取。

### 反对意见 3 —— 统计学家

> "562 个车辆训练身份，全项目零三 seed 结果，收缩面是对**一个** checkpoint 的确定性重打分。
> 你在 e036 上写 '≥ 8.60' 而门是 8.0215，这个 0.58 的余量是我坚持的，不是保守，
> 是因为**我们不知道 seed 方差有多大**。而且注意 §2.18 的收缩面里 1.00→0.80 一格就值 2.23 分 R40：
> 也就是说 dim_l 中位误差 0.042 m 的差别值 2.2 分 AP。
> 我们从未测过 0.042 m 是不是小于 seed 噪声。任何声称'过门'的结论必须在第二个 seed 上复现。"

**处理**：**接受**。e036 门写成 8.60；并且加一条：**若 V1 在 e036 落在 8.02–8.60 之间，
判 `INCONCLUSIVE` 而非 PASS，必须换 seed 再跑一次 full（+27.6 h）才允许声称。**

### 反对意见 4 —— 实现工程师

> "候选 #1 的第 1 步要把 `dim_embed` 的调用从 decoder 里搬到 `stereodetr.py`。
> `depthaware_transformer.py` 和 `detr_transformer.py` **各有一份**decoder，
> `inter_references_dim` 被 `stack` 后同时喂 `outputs_3d_dims` 和 `_set_aux_loss`，
> 而 `with_box_refine: True` 下 `dim_embed_3d` 被 `_get_clones` 成 3 份挂在 `decoder.dim_embed` 上。
> 搬家会同时改变参数命名（`depthaware_transformer.decoder.dim_embed.*` → `dim_embed_3d.*`），
> 这正是 C36 记过的那个坑（wrapper 静默改名）。而且 `checkpoint.migration_report_required: true`。
> 我要求把它拆成两步：**先做 7b（迭代残差，不搬家、不改名），确认管道健康，再做搬家。**"

**处理**：**部分接受**。改为：`dim_embed` 留在原地，但把 `g` 向量**从 decoder 外面传进 decoder**
（decoder 的 forward 已经在收 `pos_embeds`、`mask_depth` 这类外部张量，多一个 `geom_prior` 参数是同构的）。
这样参数名不变、`state_dict` 键集不变，migration report 只会看到 `dim_embed` 第一层的
`in_features` 从 256 变成 256+8。合同测试要求：**键名集合差集只有这一项**。

### 共识

1. **(a) 被否决**，条件是 P5 复现（真值天花板 < 0.20 m）与 P6 不返回"误差在 alpha 上平坦"。
2. **(b) 是主因，形式是缺米制标度输入**，不是容量、不是感受野。
3. **(d) 是并列主因且零测量**，P2 是全清单里性价比最高的一次测量（0.3 GPU·h 换一个主因的生死）。
4. **(c) 有上界 5.90，不开臂**，Q12 已经在测它。
5. 执行顺序：**P0 全套纯 CPU → P2 → V2 scout → V1 full**。
6. **候选 4（稠密 2D 尺寸监督）从清单上划掉**（M8：竞品那个头 `num_extra_reg_channel: 0`，
   根本不回归尺寸；而且 D1 已经用一个稠密 2D 辅助头拿到过 `STOP_VEHICLE_REGRESSION`）。
7. **候选 3（条件先验）与候选 6（EMA/完整余弦）降级为搭车项**，上界分别是 6.36 与 5.90。

---

## 7. 本报告自身的已知弱点（自我红队）

按本项目的规矩，报告必须自己列出会让它被推翻的地方。

1. **M4 是真值几何，不是模型几何。** 全部由 P1 兑现或证伪。这是最大的一处。
2. **"中位误差 → 保留系数 → R40"的换算是错的量纲。** 收缩面的参数是逐目标误差乘子，
   而去塌缩主要改善外侧分位。本报告表格里的 R40 数字**只能用于路由，不能用于难度估计**——
   这正是 C117 记过的坑，我在自己的表上又犯了一次，已在 §3-P7 写明修法
   （用逐目标误差比拟合落点，像 C109 定位 Q8 那样）。
3. **`--shrink-fields shape` 同时缩 dim 与 yaw**，本报告全部 R40 预测继承一个已知方向的乐观偏差（C90）。
   P7 是强制前置。
4. **Q12 尚未报数。** 全部相对门都挂在 Q12 的 e012/e036 cell 上；若 H1 失败，本方案的比较基线不存在。
5. **`reports/q5/` 磁盘上没有收据**，所以 `dim_denominator: class_mean`（7a）到底动不动指标，
   本报告是在没有证据的情况下把它当搭车项的。若 Q5 其实跑过并且是负结果，7a 必须撤下。
6. **P2 需要一次前向 pass，本 agent 未跑。** 因此"(d) 是并列主因"是一个**基于源码的机制推断**，
   不是一个测量。它的地位低于 (b)，(b) 有三条独立证据。
7. 本报告读的是 `/data1/lyq/code/.ep4d_q1` 的当前工作树，未核对它与
   `ckpt/a2_epoch_012.pth` 训练时的代码是否逐位一致。按 C118 的教训，
   **在写预注册之前必须做一次这个核对**——尤其是 `iou_thresh` 与 `depth_match_type`
   这两个决定 M3 是否成立的量。

---

## 附录 A：可复核清单

| 断言 | 文件 : 行 |
|---|---|
| decoder 无 depth cross-attention | `lib/models/monodetr/detr_transformer.py:449-516` |
| `decoder_type: "detr"` | `configs/001-final_exp1.yaml:83` |
| 非 depthaware 时 `depth_embed = None` | `lib/models/monodetr/depth_predictor/depth_predictor_lightstereo.py:405-417` |
| decoder 只读 `srcs_left[1:4]` | `lib/models/monodetr/stereodetr.py:392-396`；`configs/001-final_exp1.yaml:84` |
| `size3d = inter_references_dim[lvl]` | `lib/models/monodetr/stereodetr.py:497-499` |
| `reference_dims = dim_embed[lid](output)` | `lib/models/monodetr/depthaware_transformer.py:618-619` |
| `dim_embed_3d = MLP(256,256,3,2)` | `lib/models/monodetr/stereodetr.py:73` |
| `depth_map` 单点采样，`one_w_uncertainty` | `lib/models/monodetr/stereodetr.py:463-469`, `:524-526` |
| 可变形采样按 `(w/2, h/2)` 缩放 | `lib/models/monodetr/ops/modules/ms_deform_attn.py:153-155` |
| 匹配代价合成 | `lib/models/monodetr/matcherstable_fg_only.py:129-132` |
| `set_cost_3dcenter/depth = 0` | `configs/001-final_exp1.yaml:130-135` |
| `iou_thresh: 0.0`（全部配置） | `configs/dsec3dod/q12_seit_long36.yaml:111` 等 10 处 |
| `depth_match_type = "filter"` 硬编码 | `lib/models/monodetr/stereodetr.py:626` |
| `'depths' → loss_depths_stable` | `lib/models/monodetr/stereodetr.py:1131-1145` |
| `dim_denominator` 默认 `absolute` | `lib/models/monodetr/stereodetr.py:603`；`lib/models/event4d/build_voxel_event.py:67-73` |
| `depth_geo` 的反向耦合 | `lib/models/monodetr/stereodetr.py:503` |
| 相关体 24 级 × 4 px | `lib/models/monodetr/depth_predictor/depth_predictor_lightstereo.py:366` |
| 竞品 refine：27 点定向 ROI | `Ev-Stereo3D/liga/models/dense_heads/det_head_refine_bev_ev_sem.py:198-222` |
| 竞品 refine：`cls_weight: 0.0` | `Ev-Stereo3D/configs/stereo/dsec_models/evstereo.yaml:397-404` |
| 竞品 dense 2D 头不回归尺寸 | `Ev-Stereo3D/configs/stereo/dsec_models/evstereo.yaml:196` |
| 天花板工具缺 `1/|sinθ|`、用 `rotation_y` | `tools/q2_scoring/size_observability_ceiling.py:77-107`, `:209-217` |

## 附录 B：M4 的复算方式

纯 CPU，无需 GPU，无需模型：

```
读 /data1/lyq/data/EV_3DOD/DSEC/dsec_infos_val.pkl
f  = calib['P2'][0,0] = 583.30812,  cx = 336.834
对每个 interval 的前 10 帧、每个 name == 'Vehicle' 的标注：
    L = dimensions[0], W = dimensions[2], z = location[2], a = alpha
    s = |sin a|, c = |cos a|
    px_side = L*s*f/z ; dw_dL = s*f/z ; dz_side = L*c
    dd_side = 349.5*(1/(z - dz_side/2) - 1/(z + dz_side/2))
n = 23412
```

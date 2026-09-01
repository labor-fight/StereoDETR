# Ev-Stereo3D 逐机制配方差分（12 人专家组 · 只读分析）

- 日期：2026-08-30
- 分析对象：`/data1/lyq/code/Ev-Stereo3D/`（竞品）对照 `/data1/lyq/code/.ep4d_q1/`（我方 StereoDETRVoxelEvent，a2_seit 配方）
- 约束遵守：全程只读；未运行任何 GPU 任务；除本报告外未修改任何文件。
- 引用规范：所有结论后跟 `文件:行号`。凡是没有代码行号支撑的判断，一律显式标注为「推断」并给出验证它所需的收据。

---

## 0. 执行摘要

竞品**不是** DETR。它是 LIGA-Stereo 的一个分叉：全分辨率立体代价体 → 3D 体素 → BEV → **0.2 m 间距的稠密 anchor 格**（每帧约 35 万个 anchor）→ 二阶段 BEV ROI 残差精修。它的每一个几何量都不是自由回归出来的标量，而是**在一个 0.2 m 的格子上选点 + 回归一个残差**。

在这次差分里，最值得注意的**不是**它比我们多了什么模块，而是三件我方代码里已经存在、但被配错了的事：

1. **我方稠密深度 GT 与被查询时刻不同步。** `dsec3dod_dataset.py:283-287` 对一个 interval 内 10 个 `frame_offset` 全部取同一张 `depth_map(official_info_index)`，而框标注 `annos[frame_offset]` 是逐子帧的（`official_protocol.py:127-149`）。竞品在同一份数据上做了两件我们没做的事：随机把 10 帧窗口滑到 interval 末端（`stereo_dsec_dataset.py:293-299`），并在那种情况下把深度 GT 换成**下一次** LiDAR 扫描（`stereo_dsec_dataset.py:399-411`、`depth_loss_head.py:36-40`）。结果是他们的深度监督时间偏移**零均值**，我们的是**单边偏置**。
2. **我方深度分箱在行人尺度上不可用。** 竞品是**均匀 0.2 m** 288 箱（`volume_generation_semantic_feedback_sem_up.py:188-199`）。我方是 LID 80 箱、2.0–56.9 m，在 20/30/40 m 处箱宽 **0.779 / 0.966 / 1.135 m**（由 `001-final_exp1.yaml:70-72` + `a2_seit.yaml:71-72` 的参数按 `dense_depth_loss.py:24-38` 的公式算出）。行人 strict 3D IoU 的纵向余量只有 **0.243 m**（`dense_depth_loss.py:98-99`）——我们 30 m 处单个箱子就是行人整个容差的 **4 倍**，而且 a2_seit 没开软目标（`a2_seit.yaml:74-89` 无 `dense_depth_map_soft_target`，`build_voxel_event.py:104` 默认 False）。
3. **我方主干的第一层是冻结的 ImageNet RGB 权重。** `backbone.py:106-108` 用 torchvision 预训练 resnet34，`backbone.py:71-73` 在 `train_backbone: True` 下仍然把所有非 layer2/3/4 的参数 `requires_grad_(False)`——即 `conv1`+`bn1`+`layer1` 全程冻结在 RGB 域。事件 voxel 被压到 3 通道后要先过这层冻死的 RGB 滤波器。竞品的对应位置是直接换成一个从零训练的 5 通道 `conv1`（`feature_extract_sem_up.py:80-82`），且 `frozen_stages: -1`（`evstereo.yaml:33`、`:86`）。

另外两个需要更正既有理解的事实：

- **竞品没有时序递归。** `VOLUME_MOTION` 配置块（`evstereo.yaml:124-176`）从未被实例化，因为 `module_topology`（`stereo_detector3d_template_separate_train_regression_ours.py:22-25`）里没有它；`prev_volume_features` 被写入（`liga_image_separate_volume_train_regression_ours.py:35`）但无人读取。
- **竞品公开权重是在恒定 1e-3、从未退火、且实际无梯度裁剪的条件下拿到 8.02/3.64 的。** 退火在 epoch 50 才发生（`evstereo.yaml:437-438`），公开 ckpt 是 epoch 22；裁剪那行是注释掉的（`train_utils.py:87-90`）。**退火不是竞品的机制。**

---

## 1. 行人 Ped R40 3.6448 的机制来源排序

按「拿掉它，行人还能剩多少」的机制重要性排序。每条给证据与我方对照。

### 1.1 第一位：几何被烘进特征布局，深度不是回归出来的标量

竞品的 3D 框中心 `z` 来自 **BEV anchor 格的坐标本身**，不是任何头预测的。

- 点云范围 `[2, -30.4, -3, 59.6, 30.4, 1]`、`STEREO_VOXEL_SIZE [0.2, 0.2, 0.2]`（`dsec_dataset_fused_event_10.yaml:12,14`）；
- anchor 的 `feature_map_stride: 1`（`evstereo.yaml:262`、`:272`），即 anchor 直接铺在 0.2 m 的 BEV 网格上：x 方向 288 格 × y 方向 304 格 × 2 个旋转 × 2 个类别 ≈ **35 万 anchor/帧**；
- BEV 特征由 3D 体素高度压缩得到（`MAP_TO_BEV: HeightCompression`，`evstereo.yaml:232-235`），而 3D 体素是把代价体按 `(u, v, d)` 归一化坐标 grid_sample 出来的（`volume_generation_semantic_feedback_sem_up.py:506-507`）；
- 框回归只是相对 anchor 的残差，解码时 `decode_torch(batch_box_preds, batch_anchors)`（`anchor_head_template_refine.py:376`）。

**机制含义**：一个 30 m 处的行人，在竞品那里是「BEV 格 (x, z=30) 的特征是否像行人」这个**分类**问题，深度误差的下界由 0.2 m 的格距 + 一个残差决定。在我方那里是「query → sample point → 双线性读一张深度图 → 得到一个标量」这个**回归**问题（`stereodetr.py` 的 `pred_depth`；解码见 `decode_helper.py:225-239`），深度误差就是深度图的误差。这是行人差距的结构性根因，也解释了台账 §2.14/§2.18（`EXPERIMENTS_AND_PITFALLS.md:312-316,393-410`）为什么在「行人必须配深度」上反复撞墙。

**注意**：这一条**不可移植**（等于重写模型），列在第一位是为了给后面几条定标——后面几条都是在不换框架的前提下，逼近这条所提供的那部分好处。

### 1.2 第二位：逐像素 LiDAR+视差深度 CE，箱宽 0.2 m，三角软目标

这是竞品**唯一**的深度监督，权重 1.0，与检测损失等幅。

- GT 源：`LOSS_LIDAR_DISPARITY: lidar_disparity`（`dsec_dataset_fused_event_10.yaml:37`），即 **LiDAR 点 ∪ 视差点** 拼接后投影成深度图（`stereo_dsec_dataset.py:387-394`）。注意送进网络当输入的那份只用了 `lidar`（`:36`），监督那份才是二者并集——**输入与监督用的点集不同**。
- 损失形式：`LOSS_TYPE: {'ce': 1.0}`、`WEIGHTS: [1.0]`（`evstereo.yaml:406-408`），实现在 `depth_loss_head.py:68-74`：

```68:74:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/depth_loss_head.py
                    elif loss_type == "ce":
                        depth_log_prob = F.log_softmax(depth_cost, dim=1)
                        distance = torch.abs(
                            depth_sample.cuda() - gt.unsqueeze(-1)) / depth_interval
                        probability = 1 - distance.clamp(max=1.0)
                        loss = -(probability * depth_log_prob).sum(-1)
                        loss = loss.mean()
```

  这是**三角形软目标**：以真值深度为中心、宽度一个 bin 的线性插值，正好落在相邻两个箱上。等价于我方 `dense_depth_loss.py:211-239` 的 `_soft_target_loss`——**我们已经实现了这个东西，但 a2_seit 没开**。
- 分箱：`depth_interval = (59.6 − 2)/288 = 0.2 m`，`depth[i] = (i+0.5)·0.2 + 2`（`volume_generation_semantic_feedback_sem_up.py:188-199`），作为 `depth_samples` 交给损失（`:411`）。**均匀 0.2 m，288 箱，覆盖 2.1–59.5 m。**
- 无前景加权、无背景填充：只在 `min_depth < gt < max_depth` 的像素上算（`depth_loss_head.py:46-47`），有点就监督，没点就不监督。

**我方对照（这是差距最大的一处）**：

| 项 | 竞品 | 我方 a2_seit |
|---|---|---|
| 逐像素 LiDAR CE | 有，权重 1.0 | 有，`loss_dense_depth_map` 系数 1.0（`a2_seit.yaml:85-86`） |
| 分箱 | 均匀 0.2 m × 288 | LID × 80，20/30/40 m 处 **0.779 / 0.966 / 1.135 m** |
| 目标形状 | 三角软目标 | **硬目标**（`a2_seit.yaml` 未设 `dense_depth_map_soft_target`；`build_voxel_event.py:104` 默认 False） |
| 额外的框内涂色损失 | **无** | **有**：`depth_map` 在启用列表里（`a2_seit.yaml:84`） |

最后一行是被忽视的冲突源。我方 `DDNLoss` 把整个框内区域涂成**同一个物体中心深度**：

```115:124:/data1/lyq/code/.ep4d_q1/lib/models/monodetr/depth_predictor/ddn_loss/ddn_loss.py
        for b in range(B):
            center_depth_per_batch = gt_center_depth[b]
            if self.depth_sort_reverse:
                center_depth_per_batch, sorted_idx = torch.sort(center_depth_per_batch, dim=0, descending=False)
            else:
                center_depth_per_batch, sorted_idx = torch.sort(center_depth_per_batch, dim=0, descending=True)
            gt_boxes_per_batch = gt_boxes3d[b][sorted_idx]
            for n in range(gt_boxes_per_batch.shape[0]):
                u1, v1, u2, v2 = gt_boxes_per_batch[n]
                depth_maps[b, v1:v2, u1:u2] = center_depth_per_batch[n]
```

（`align_by_3d_center: True`，`001-final_exp1.yaml:75`，所以走的是 `build_target_depth_align_3d_center`，矩形以投影 3D 中心为心。）并且 `Balancer` 把框内像素的权重乘上 `fg_weight`（`balancer.py:19-20,42`）。也就是说：**在框内像素上，两个损失给出互相矛盾的目标**——逐像素项要求「这个像素的真实深度」，涂色项要求「这个物体的中心深度」，而后者在框内还被上权重。对行人这种细长目标，框内相当比例是背景像素，涂色项等于在教深度图「行人框里所有东西都在行人身上」。这与台账 C112（`EXPERIMENTS_AND_PITFALLS.md:600`）「行人深度主要不是匹配器给的，更可能来自身高先验」**在机制上闭环**：一个被训练成「按 2D 框几何涂常数深度」的深度图，其读数当然是身高先验的函数。

### 1.3 第三位：稠密多正例 anchor 分配（对行人尤其重要）

- 逐类别阈值：Vehicle `matched 0.6 / unmatched 0.45`，Pedestrian `matched 0.5 / unmatched 0.35`（`evstereo.yaml:263-264, 273-274`）——**行人阈值被专门放低**。
- `MATCH_HEIGHT: False`（`evstereo.yaml:283`）：用 **BEV IoU** 而不是 3D IoU 做匹配，行人高度维不参与，等于又放宽一档。
- `POS_FRACTION: -1.0`、`SAMPLE_SIZE: 512`、`NORM_BY_NUM_EXAMPLES: False`（`evstereo.yaml:280-282`）：不做正负采样，全 anchor 参与，focal loss 扛不平衡。
- 每个 GT 至少强制一个最高 IoU 的 anchor 为正（`axis_aligned_target_assigner.py` 的 forced-match 逻辑）。

对比我方 DETR 的一对一匈牙利匹配：一个行人 GT 只产生 **1** 个正样本。竞品一个行人 GT 在 0.2 m 的 anchor 格上按 BEV IoU ≥ 0.5 可以产生**几十个**正样本。

**但这条不进 top-5**：我方 D1（`enable_dense_evidence`，`build_voxel_event.py:112-130`）已经试过稠密一对多辅助分支并**决定性 FAIL**（`EXPERIMENTS_AND_PITFALLS.md:457,469`：Ped proposal recall 0.7095 → 0.6688）。用户明确要求不重复已否决路线。

### 1.4 第四位：二阶段 RCNN refine —— 对行人**不是**主要来源

`REGRESSION_HEAD` 的 `cls_weight: 0.0`（`evstereo.yaml:398`），它**完全不改分数**，只改框。竞品自报 `recall_rcnn_0.7 = 0.124`。对行人而言，台账 §2.18（`EXPERIMENTS_AND_PITFALLS.md:410`）已经量过：即使尺寸与朝向完美，Ped R40 也只到 1.1487，远低于 3.6448。所以**二阶段精修不可能是行人 3.64 的主要来源**，它是车的机制（见第 2 节）。

### 1.5 第五位：2D dense head —— 证据上是死的

`DENSE_HEAD_2D: MMDet2DHead / ATSSAdvHead`（`evstereo.yaml:179-231`）确实在 `module_topology` 里（`stereo_detector3d_template_separate_train_regression_ours.py:22-25`）并参与损失（`liga_image_separate_volume_train_regression_ours.py:84-87`），但**公开 checkpoint 缺 35 个 `dense_head_2d.*` 张量**（用户已锁定事实）。加上我方 D1 已经证明同类机制在我们这边伤车回归，这条既无法确认在公开权重里生效、又已被我方否决。**排除。**

### 1.6 分数定义与每帧 9.75 个检测

**竞品分数 = 原始 sigmoid focal 分类分，没有任何质量项、没有校准。**

```289:290:/data1/lyq/code/Ev-Stereo3D/liga/models/detectors_stereo/stereo_detector3d_template_separate_train_regression_ours.py
                if not batch_dict['cls_preds_normalized']:
                    cls_preds = torch.sigmoid(cls_preds)
```

不是 `cls × iou`（没有 IoU 预测头），不是校准过的（没有任何 temperature/isotonic），二阶段也不参与打分（`cls_weight: 0.0`）。

**解码配置**（`evstereo.yaml:410-422`）：`SCORE_THRESH: 0.1`、`MULTI_CLASSES_NMS: True`、`NMS_THRESH: 0.25`、`NMS_PRE_MAXSIZE: 4096`、`NMS_POST_MAXSIZE: 500`；多类 NMS 逐类独立跑（`nms_utils.multi_classes_nms`，经 `:304-307` 调用）。

**我方对照**：`score_threshold: 0.2`、`topk: 50`、无 NMS（`a2_seit.yaml:130-131`）。更关键的是分数定义——

```212:217:/data1/lyq/code/.ep4d_q1/lib/helpers/decode_helper.py
    prob = out_logits.sigmoid()

    topk_values, topk_indexes = torch.topk(prob.view(out_logits.shape[0], -1), topk, dim=1)

    # final scores
    scores = topk_values
```

```226:227:/data1/lyq/code/.ep4d_q1/lib/helpers/decode_helper.py
    sigma = outputs['pred_depth'][:, :, 1: 2]
    sigma = torch.exp(-sigma)
```

```60:60:/data1/lyq/code/.ep4d_q1/lib/helpers/decode_helper.py
            score = score * dets[i, j, -1]
```

即**我方上报分数 = sigmoid(cls) × exp(−log_var)**，其中 `exp(−log_var)` 是深度 Laplacian 的尺度参数，一个**未经校准的质量项**。这直接违反台账 C21（`EXPERIMENTS_AND_PITFALLS.md:500`：「quality/entropy 只有经校准并证明有效才参与排序」），而 C116（`:604`）测到车在真实排序下被这套分数**扣了 15%**（5.0077 → 4.2701 是排序完美的方向，说明当前排序对车有害）。

「9.75 vs 2.25」的机械解释因此是：他们阈值 0.1 且分数不被一个 <1 的因子压缩，我们阈值 0.2 且分数被 `exp(−log_var)` 再乘一次。但**这不是杠杆**——用户已锁定「加宽预算 AP 不升」，与 C98 一致。它只解释计数，不解释 AP。

### 1.7 行人机制来源排序（结论）

| 排名 | 机制 | 证据 | 是否可移植 |
|---|---|---|---|
| 1 | 几何烘进 BEV anchor 格（0.2 m 格 + 残差），深度非标量回归 | `evstereo.yaml:262,272`；`dsec_dataset_fused_event_10.yaml:14`；`anchor_head_template_refine.py:376` | 否（等于换框架） |
| 2 | 逐像素 LiDAR∪视差 CE，均匀 0.2 m 箱，三角软目标，无框内涂色项 | `depth_loss_head.py:36-74`；`volume_generation_semantic_feedback_sem_up.py:188-199` | **是**（我方已有一半） |
| 3 | 稠密多正例分配 + 行人专属低阈值 + BEV IoU 匹配 | `evstereo.yaml:263-283` | 已被 D1 否决 |
| 4 | 二阶段 ROI 精修 | `det_head_refine_bev_ev_sem.py:342-433` | 是，但主要利车 |
| 5 | 2D dense head | `evstereo.yaml:179-231` | 公开权重里缺失 + D1 已否决 |
| — | 分数：裸 sigmoid，无质量项，阈值 0.1 | `stereo_detector3d_template_...py:289-290`；`evstereo.yaml:412` | 是（只能作为组件） |

---

## 2. 车辆 IoU 0.7 紧度的来源

### 2.1 二阶段 ROI refine 的确切实现

流程（`det_head_refine_bev_ev_sem.py`）：

1. **选 proposal**：不按阈值，按 **top-100 的最大类别 logit**。
```342:344:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/det_head_refine_bev_ev_sem.py
        data_dict['box_cls_mask'] = torch.topk(data_dict['batch_cls_preds'].max(dim=-1)[0], 100, dim=-1)[1]
        batch_idx = torch.arange(B).unsqueeze(-1)
        data_dict['rois'] = data_dict['batch_box_preds'][batch_idx, data_dict['box_cls_mask']]
```
   上一行被注释掉的版本是「sigmoid > 0.1 阈值」（`:340`），他们改成了固定 100，**proposal 数量与分数尺度解耦**。

2. **pool 什么特征**：把 3D 语义体素 `Voxel_2D` 沿高度压扁成 BEV 语义图，再按 ROI 周围的球邻域采样。
```354:359:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/det_head_refine_bev_ev_sem.py
        B, C, Z, X, Y = data_dict['Voxel_2D'].shape
        sem_bev_feat = self.height_compress(data_dict['Voxel_2D'].reshape(B, -1, X, Y))
        data_dict['spatial_features_2d_pool'] = sem_bev_feat.permute(0, 2, 3, 1).reshape([valid.shape[0], -1])[valid]
        
        pooled_features, global_roi_grid_points, local_roi_grid_points, ball_idxs = self.roi_grid_pool(data_dict)  # (BxN, 6x6x6, C)
```
   池化配置：`FEATURE_LOCATIONS: [spatial_features_2d_pool]`、`GRID_SIZE: 3`（即 3×3×3 = 27 个 grid point，不是注释里写的 6³）、`POOL_RADIUS: [0.8]`、`NSAMPLE: [16]`、`POOL_METHOD: max_pool`、`USE_DENSITY: True`（`evstereo.yaml:351-365`）。注意 `ATTENTION.ENABLED: False`（`:373`）与 `DENSITYQUERY.ENABLED: False`（`:384`）——那两个花哨模块在发布配方里**是关的**，实际生效的只是「以预测框为中心、半径 0.8 m 的 27 点球查询 max-pool」。

3. **回归什么残差**：一个极小的 MLP，`SHARED_FC: [16]` → `REG_FC: [8]` → 7 维。
```420:433:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/det_head_refine_bev_ev_sem.py
        shared_features = self.shared_fc_layer(pooled_features.view(batch_size_rcnn, -1, 1))
        rcnn_reg = self.reg_layers(shared_features).transpose(1, 2).contiguous().squeeze(dim=1)  # (N, 7)
        
        # change_mask = data_dict['box_cls_mask'].reshape([*box_preds.shape[:3], -1]) # (B, X, Y, 4)
        
        # import pdb; pdb.set_trace()
        
        reg_refine = torch.zeros_like(data_dict['batch_box_preds'])
        
        batch_idx = torch.arange(B).unsqueeze(-1)
        
        reg_refine[batch_idx, data_dict['box_cls_mask']] = rcnn_reg.to(reg_refine.dtype)
        
        box_preds = reg_refine.reshape(box_preds.shape)
```

   **关键细节**：`rcnn_reg` 不是「在一阶段框上再加一个小偏移」，而是**用 ROI 池化特征重新预测同一套 anchor 相对编码**，然后 `decode_torch(box_preds, anchors)`（`anchor_head_template_refine.py:376`）从 anchor 解码。一阶段的框只用来决定**去哪里取特征**，不进入二阶段的输出通路。未被选中的 anchor 残差为 0，解码出来就是 anchor 本身（分数低，会被阈值滤掉）。这是一个干净的「重新预测 + 新证据」结构，不是「残差的残差」。

4. **损失**：`cls_weight: 0.0`、`loc_weight: 1.0`、`dir_weight: 0.0`、`iou_weight: 1.0`、`code_weights: [1,1,1,0.5,0.5,0.5,1]`（`evstereo.yaml:397-404`）。
```301:308:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/anchor_head_template_refine.py
        iou_loss_weight = self.model_cfg.LOSS_CONFIG.LOSS_WEIGHTS.get('iou_weight', 0.)
        if iou_loss_weight > 0:
            decoded_box_preds = self.box_coder.decode_torch(box_preds[pos_inds], anchors[pos_inds])
            decoded_reg_targets = self.box_coder.decode_torch(box_reg_targets[pos_inds], anchors[pos_inds])
            iou_loss_src = self.iou_loss_func(decoded_box_preds, decoded_reg_targets, weights=reg_weights[pos_inds])
            iou_loss = iou_loss_src.sum() / batch_size
            iou_loss = iou_loss * iou_loss_weight
            box_loss = box_loss + iou_loss
```
   即：**SmoothL1(残差) + 3D IoU(解码框)**，两者等幅，且 IoU 只在正样本上算。

### 2.2 size/dim 的监督形式与权重

- 编码：`ResidualCoder` + `div_by_diagonal: True`（`evstereo.yaml:285-288`）。尺寸残差是 `log(size / anchor_size)`，中心残差除以 anchor 对角线。anchor 尺寸逐类固定：Vehicle `[4.28, 1.86, 1.79]`、Pedestrian `[0.8, 0.6, 1.73]`（`evstereo.yaml:258, 268`）。
- 一阶段权重：`loc_weight: 0.5`、`code_weights` 全 1（`evstereo.yaml:296, 300`）→ 尺寸三维各拿 0.5。
- 二阶段权重：`loc_weight: 1.0`，但 `code_weights` 把尺寸三维**降到 0.5**（`evstereo.yaml:399, 403`）→ 尺寸各拿 0.5，与一阶段等幅；而中心与朝向拿 1.0。
- 两阶段都叠加 `IOU3dLoss`，权重 1.0（`evstereo.yaml:298, 401`；实现 `loss_utils.IOU3dLoss`）。

**读出来的设计意图**：竞品的二阶段**主要在修平移和朝向，不在修尺寸**（尺寸权重被砍半）。尺寸靠的是「类别 anchor 先验 + log 残差」。

**这一点很重要，因为它同时印证和挑战了我方两条台账**：
- 印证 C92（`EXPERIMENTS_AND_PITFALLS.md:580`）：竞品**也没有**靠「给尺寸头付更多梯度」来解决紧度。Q6 的失败不是因为我们做错了，是这条路本来就不通。
- 挑战我方对 IoU3dLoss 的判断：C78 记录 IoU3dLoss 拉低我方天花板，而竞品在两个阶段都用它、权重 1.0。差别在于**它们的 IoU 损失只作用在 BEV-IoU 已经匹配上的正样本、且框是从 anchor 解码的**（`anchor_head_template_refine.py:303-305`），而我方 `loss_iou3d` 作用在匈牙利匹配的 query 解码框上。这是不同的施加对象。

### 2.3 车紧度的机制归因

按证据强度排序：
1. **0.2 m 的 anchor 平移格**：中心误差的先验下界就是格距，不存在「回归跑偏」的可能。
2. **二阶段用新证据重新预测**：ROI 池化在**预测框位置**取的 BEV 语义特征，是一阶段头从未见过的输入。这不是降噪，是加信息。
3. **anchor 尺寸先验 + log 残差**：让「输出均值尺寸」成为零输出，塌缩到均值不再是误差。（注意：我方 §2.15 测到尺寸头塌缩到均值、斜率 0.2373，`EXPERIMENTS_AND_PITFALLS.md:349`；竞品的参数化并**不能**避免同样的塌缩，只是把塌缩点设成了先验。所以这条不是差异化来源。）
4. **两阶段各叠一个 3D IoU 损失**，只在正样本上。

---

## 3. 事件表示、图像融合与 blind time

### 3.1 他们用图像吗？——完全不用

```347:360:/data1/lyq/code/Ev-Stereo3D/liga/datasets/dsec/stereo_dsec_dataset.py
        left_img, right_img = [], []
        if self.use_events:
            select_event_paths = info['event_paths'][idx_select]
            for t_idx, event_path in enumerate(select_event_paths):              
                event_npz = self.get_event(event_path)
                left_ev, right_ev = event_npz['left'], event_npz['right']
                left_img.append(left_ev.transpose([1, 2, 0]))
                right_img.append(right_ev.transpose([1, 2, 0]))
        else:
            # load images
            left_im = self.get_image(info['image']['image_0_path'])
            right_im = self.get_image(info['image']['image_1_path'])
            left_img.append(left_im)
            right_img.append(right_im)
```

`USE_EVENTS: True`（`dsec_dataset_fused_event_10.yaml:32`）→ **RGB 分支根本不执行**。名字里的 `image` 是 LIGA 遗留命名。

**所以「blind time 怎么处理」这个问题在他们那里不存在**：输入自始至终是 100 Hz 的事件体，没有需要跨越的曝光间隙。这与我方设定一致（我们也是纯事件），所以这条**不是差距来源**——但它推翻了「他们靠 RGB+事件融合」的任何猜测。

他们唯一的「融合」是**左右目之间**的：用预测视差把右目语义特征 warp 到左目，再用一个通道注意力 Transformer 块融合（`volume_generation_semantic_feedback_sem_up.py` 的 `disp_warp` + `feat_attn`）。这是立体语义反馈，不是跨模态融合。

### 3.2 事件表示的差异

| 项 | 竞品 | 我方 a2_seit |
|---|---|---|
| 通道 | **5**（`feature_extract_sem_up.py:82`；`feature_neck.in_dims: [5, 48, 96]`，`evstereo.yaml:51`） | **10** = 5 bins × 2 极性（`a2_seit.yaml:41-43`） |
| 极性 | 合并（有符号累加，5 = 5 个时间 bin） | 分开（negative/positive 各 5 bin） |
| 送入主干 | 直接换掉 `conv1` 成 5 通道，从零训练 | 10 → 32 → **3** 通道适配器（`a2_seit.yaml:51-56`），再送**冻结的 ImageNet RGB conv1** |
| 主干冻结 | `frozen_stages: -1`，全可训（`evstereo.yaml:33, 86`） | `conv1`+`bn1`+`layer1` 冻结（`backbone.py:71-73`） |
| 一个样本覆盖的时刻数 | 10（一个 interval 内连续 10 个子帧，逐帧算全套损失） | 1（`mode: single_query`，`a2_seit.yaml:12`） |

```80:82:/data1/lyq/code/Ev-Stereo3D/liga/models/backbones_3d_stereo/feature_extract_sem_up.py
        self.use_events = getattr(model_cfg, 'use_events', False)
        if self.use_events:
            self.feature_backbone.conv1 = nn.Conv2d(5, model_cfg.feature_backbone.base_channels, kernel_size=(7, 7), stride=(2, 2), padding=(3, 3), bias=False)
```

```71:73:/data1/lyq/code/.ep4d_q1/lib/models/monodetr/backbone.py
        for name, parameter in backbone.named_parameters():
            if not train_backbone or 'layer2' not in name and 'layer3' not in name and 'layer4' not in name:
                parameter.requires_grad_(False)
```

```106:108:/data1/lyq/code/.ep4d_q1/lib/models/monodetr/backbone.py
        backbone = getattr(torchvision.models, name)(
            replace_stride_with_dilation=[False, False, dilation],
            pretrained=is_main_process(), norm_layer=norm_layer)
```

**结论**：我方的事件表示**信息量更大**（分极性 10 通道 > 有符号 5 通道），但随后被一个 3 通道瓶颈 + 一层冻死的 RGB 滤波器截断。竞品信息量更小，但整条通路对事件域自由适应。对行人这种「20–40 m 处只有几十个事件像素」的目标，冻结的 RGB stem 是一个类别特异的信息瓶颈。

### 3.3 blind time 相关的真正差异：深度 GT 的时刻

竞品在 interval 内部做了两件事：

```293:299:/data1/lyq/code/Ev-Stereo3D/liga/datasets/dsec/stereo_dsec_dataset.py
        if (self.mode == 'train') and (N > 1):
            if np.random.randint(2) > 0.5:
                idx_select = np.arange(N)
            else:
                idx_select = np.arange(max_event_num-N, max_event_num)
        else:
            idx_select = np.arange(N)
```

一个 interval 有 11 个子帧（`:290`），训练时随机取前 10 或后 10。当取到后 10（含最后一个子帧）时，加载**下一个 interval** 的 LiDAR 与视差点：

```399:411:/data1/lyq/code/Ev-Stereo3D/liga/datasets/dsec/stereo_dsec_dataset.py
        if (max_event_num-1) in idx_select:
            next_disparity_points = calib.rect_to_lidar_pseudo(next_disp_pts_rect)
            next_input_points = calib.rect_to_lidar_pseudo(next_pts_rect)
            if self.loss_lidar_disparity == 'lidar':
                next_gt_points = next_input_points
            elif self.loss_lidar_disparity == 'disparity':
                next_gt_points = next_disparity_points
            elif self.loss_lidar_disparity == 'lidar_disparity':
                next_gt_points = np.concatenate([next_disparity_points, next_input_points], axis=0)
            else:
                raise NotImplementedError
        else:
            next_gt_points = None
```

深度损失据此切换目标：

```36:40:/data1/lyq/code/Ev-Stereo3D/liga/models/dense_heads/depth_loss_head.py
        if batch_dict['next_depth_gt_img'][0] is not None:
            gt = batch_dict['next_depth_gt_img'].squeeze(1)
        else:
            gt = batch_dict['depth_gt_img'].squeeze(1)
```

**净效果**：前窗时 10 个子帧全部用 t=0 的扫描（滞后 0…+9 帧），后窗时全部用 t=10 的扫描（超前 −9…0 帧）。两种情况各 50%，**时间偏移零均值、±4.5 帧展宽**。

**我方对照**：

```283:287:/data1/lyq/code/.ep4d_q1/lib/datasets/dsec3dod/dsec3dod_dataset.py
        if self._depth_gt is not None:
            target = dict(target)
            target["dense_depth"] = torch.from_numpy(
                self._depth_gt.depth_map(int(record["official_info_index"]))
            )
```

`official_info_index` 是 **interval 索引**，一个 interval 内 10 个 `frame_offset` 共享它（`official_protocol.py:134-148`），而 `depth_map()` 每个 interval 只有一张（`depth_gt_store.py:251-272`，由 `info["lidar_path"]` / `info["disparity_path"]` 两个**单一路径**投影而来，`:200-201`）。同一份 info 里框标注却是逐子帧的 `annos[frame_offset]`（`official_protocol.py:135`）。

**即：我方的稠密深度监督在 interval 内恒定，时间偏移是 0…+9 帧的单边偏置（均值 +4.5 帧 = 45 ms）；竞品是零均值。** 自车前向运动使静止目标持续逼近，因此我方深度目标**系统性偏远**。这个偏置未在台账任何条目中出现过（C33 讲的是「跨窗证据必须与被测时刻同步」，讲的是**输入**证据不是**监督标签**；C101 讲的是时序聚合对深度不是杠杆，`EXPERIMENTS_AND_PITFALLS.md:589`）。C101 顺带给了一个反向佐证：真值深度在 10 帧内是**精确直线**（拟合残差 0.0000），说明 interval 内目标位移是真实、可测、且线性的。

---

## 4. 训练配方差分清单

| 维度 | Ev-Stereo3D | 我方 a2_seit | 证据 |
|---|---|---|---|
| Epochs（配置） | 60 | 12（Q12 在跑 36） | `evstereo.yaml:427`；`a2_seit.yaml:101` |
| Epochs（公开权重实际） | **22** | — | 用户锁定事实 |
| Batch | **1 / GPU**，但每步覆盖 **10 个连续子帧** | **64 帧**（互相独立） | `evstereo.yaml:426`；`a2_seit.yaml:34` |
| 优化器 | AdamW，LR 1e-3，WD 1e-4 | AdamW，LR 5.66e-4，WD 1e-4 | `evstereo.yaml:429-431`；`a2_seit.yaml:92-95` |
| Warmup | 1 个 epoch，CosineWarmupLR，DIV_FACTOR 10 | 500 步 | `evstereo.yaml:435,441-442`；`a2_seit.yaml:94` |
| LR 调度 | 阶梯：epoch 50 处 ×0.1。**epoch 22 时仍是恒定 1e-3，从未退火** | 恒定（Q12 试余弦） | `evstereo.yaml:437-438` |
| 梯度裁剪 | 配置写 10，**实际未执行**（代码被注释） | **0.1**，实际执行 | `train_utils.py:87-90`；`a2_seit.yaml:100` |
| 几何增广 | 立体翻转（左右目对调 + 标定与点云镜像） | 立体翻转 p=0.5 | `stereo_dsec_dataset.py:332-341,365-366`；`a2_seit.yaml:107-108` |
| copy-paste / GT sampling | **无**。`stereo_event_gt_sampling` 存在于增广器但未进配置 | **有 SEIT**（行人 ≤2、车 ≤1 每样本） | `dsec_dataset_fused_event_10.yaml:41-56`；`a2_seit.yaml:110-119` |
| 世界变换（旋转/缩放/平移） | 全部注释掉 | 无 | `dsec_dataset_fused_event_10.yaml:52-56` |
| `random_crop` / `filter_truncated` | 在列表里，但裁剪边界等于整帧 → 实际是 no-op | — | `dsec_dataset_fused_event_10.yaml:41-48` |
| 空帧重采样 | **有**：任一子帧无 GT 就整条重抽 | 无（`empty_gt_safe: true` 是容错不是重采样） | `stereo_dataset_template_dsec.py:152,246-248`；`a2_seit.yaml:89` |
| 时间窗抖动 | **有**：前 10 / 后 10 随机 | 无（单查询时刻） | `stereo_dsec_dataset.py:293-299` |
| 损失权重表 | `loss = loss_rpn + loss_rpn2 + loss_depth + loss_rpn_2d`，**四项各 1.0** | 见下 | `liga_image_separate_volume_train_regression_ours.py:70-88` |
| ├ 一阶段 | cls 1.0 / loc 0.5 / dir 0.2 / iou 1.0 / code 全 1 | — | `evstereo.yaml:294-301` |
| ├ 二阶段 | cls **0.0** / loc 1.0 / dir 0.0 / iou 1.0 / code `[1,1,1,.5,.5,.5,1]` | — | `evstereo.yaml:397-404` |
| └ 深度 | ce 1.0，WEIGHTS `[1.0]` | `depth_map` 1.0 + `dense_depth_map` 1.0；`dim` 0.1、`angle` 0.1 | `evstereo.yaml:406-408`；`a2_seit.yaml:84-86` |

**一个被低估的量级差**：他们 batch=1，一个 epoch 的优化步数 ≈ interval 数 `N`；我们 batch=64 覆盖 10·N 帧，一个 epoch 步数 ≈ `10N/64 = 0.156N`。22 epoch 对 12 epoch，优化步数比约 **22N : 1.88N ≈ 11.7×**。Q12 的 36 epoch 把这个比值降到约 **3.9×**，仍未追平。同时我方 `gradient_clip_norm: 0.1` 是非常激进的裁剪，而他们**完全没有裁剪**。「步数少 × 裁剪狠」是一个复合的欠优化风险，且它与任何结构机制正交。

---

## 5. Top-5 可移植机制

排序依据：**（预期 Ped R40 提升 × 可移植性 ÷ 与竞品框架相似度）**。已刻意避开台账否决路线：C17/C21（重排禁令）、C92（梯度预算无效）、C97（削尾无效）、C112（行人深度来自身高先验，故「更高分辨率相关体」用错对象）、C115（召回路线关闭）、C116（排序类别不对称）、D1（稠密 2D/证据辅助头，决定性 FAIL）。

---

### T1 —— 稠密深度 GT 的时刻对齐（最高优先）

**机制名**：把 `dense_depth` 目标从「interval 锚点扫描」改为「与 `frame_offset` 最近的扫描」。

**竞品证据**：`liga/datasets/dsec/stereo_dsec_dataset.py:293-299`（窗口抖动）、`:321-330`（加载 t+1 扫描）、`:399-411`（构造 `next_gt_points`）、`liga/models/dense_heads/depth_loss_head.py:36-40`（按窗口切换 GT）。

**我方现状**：`lib/datasets/dsec3dod/dsec3dod_dataset.py:283-287` 对 10 个 offset 取同一张图；`lib/datasets/dsec3dod/depth_gt_store.py:251-272` 每 interval 只有一张；框标注却逐 offset（`lib/datasets/dsec3dod/official_protocol.py:134-148`）。

**具体改法**：
1. `lib/datasets/dsec3dod/depth_gt_store.py`：`OfficialDepthGTStore` 已按 `info_index` 缓存，无需改结构。
2. `lib/datasets/dsec3dod/dsec3dod_dataset.py::_target_from_record`：把 `record["official_info_index"]` 换成一个 `_aligned_depth_index(record)`——`frame_offset <= 4` 用 `info_index`，`>= 5` 用 `info_index + 1`。
3. **必须 fail-closed**：`info_index + 1` 必须与当前 `sequence_id` 相同且 `< len(store)`，否则回退到 `info_index` 并在 audit 里计数。竞品这里是裸的字符串拼接加 `# todo`（`stereo_dsec_dataset.py:323,327`），**不要照抄它的边界处理**。
4. 由于 `official_info_index` 也进 audit（`dsec3dod_dataset.py:376`、`:484`），需要同步登记新字段，避免协议指纹漂移。
5. 训练侧单变量：不动 `depth_map`、不动权重、不动 offset 采样。

**预期增益的依据**：行人 strict 3D IoU 纵向余量 0.243 m（`lib/models/event4d/dense_depth_loss.py:98-99`）。当前深度目标的时间偏置均值 +4.5 帧 = 45 ms、最坏 90 ms，方向单一（自车前向 → 目标偏远）。C101（`EXPERIMENTS_AND_PITFALLS.md:589`）证明 interval 内真值深度是**精确直线**（拟合残差 0.0000），即位移真实存在且线性。改成最近端后偏置降为 ±0.5 帧。

**开臂前必须先跑的 CPU 收据（无 GPU）**：在训练集上，对同一 track 比较 `frame_offset=0` 与 `frame_offset=9` 的 GT 中心 `z`，报告 |Δz| 的中位/p90，分车/行人、分 20–40 m。**Kill 条件：若行人 |Δz| 中位 < 0.10 m，本机制无空间，直接放弃，不占臂位。** 这条收据只读标注 pkl，几分钟。

**风险**：
- 序列末尾 interval 无 t+1 → 必须回退且计数（否则是 C30 式「实现存在但生产路径不走」的反面：静默读错文件）。
- 改的是训练分布，评测侧协议不动；必须验证 `official_unfiltered` 视图与冻结评测器指纹不变。
- 与 C123 隔离清单的关系：本臂必须**与 Q12 同配方对照**，不能与被 SEIT 污染的旧控制组比。

---

### T2 —— 解冻事件通路的第一层（`conv1`/`bn1`/`layer1`）

**机制名**：让事件适配器下游的第一层不再是冻结的 ImageNet RGB 滤波器。

**竞品证据**：`liga/models/backbones_3d_stereo/feature_extract_sem_up.py:80-82`（`conv1` 换成 5 通道从零训练）；`configs/stereo/dsec_models/evstereo.yaml:33`、`:86`（`frozen_stages: -1`，全主干可训）。

**我方现状**：`lib/models/monodetr/backbone.py:106-108` 加载 ImageNet 预训练 resnet34；`:71-73` 在 `train_backbone: True`（`configs/001-final_exp1.yaml:62`）下仍冻结所有非 layer2/3/4 参数。事件 voxel 经 10→32→**3** 适配器（`a2_seit.yaml:51-56`）后，第一站就是这层冻死的 RGB 卷积。

**具体改法**：最小单变量版——在 `lib/models/monodetr/backbone.py:71-73` 的冻结判据里增加一个由配置驱动的开关（例如 `train_stem`），置真时不冻结 `conv1`/`bn1`/`layer1`；在 `configs/001-final_exp1.yaml` 增加 `train_stem: true`，其余全部不动。新增可训参数量在 resnet34 上约 0.23 M（conv1 9.4 K + layer1 ≈ 0.22 M），相对 18.4 M 是 +1.3%。

**不要在同一条臂里**同时把适配器输出从 3 通道拓宽（那是第二个变量，留作后续）。

**预期增益的依据**：C112（`EXPERIMENTS_AND_PITFALLS.md:600`）测出行人在 20–60 m 的等效视差 0.05–0.11 px，低于任何匹配器下限，结论是「行人深度主要不靠立体匹配」。但那条同时警告存在选择偏倚（只覆盖过了 2D IoU 0.3 门的 18% 样本）。本机制**不是**在提高匹配精度（那已被 C112/Q4 否决），而是在恢复**特征提取阶段**对稀疏事件的响应能力——冻结的 RGB stem 对「几十个稀疏事件像素」几乎无响应，这与匹配器精度是两个不同的病。§2.8 测到行人证据在 stride-4 特征上的 SNR 掉到 87.3%（C3 门那批数字，`EXPERIMENTS_AND_PITFALLS.md:115`），stem 是这条下采样链的第一环。

**风险 / kill 条件**：
- 训练不稳（BN 统计从 ImageNet 切到事件域）→ 若前 2 个 epoch loss 发散，立刻降 stem 的 LR 到主 LR 的 0.1× 再判一次，仍散则 kill。
- 过拟合：训练集只有 134 个行人身份（T1 记录），多 0.23 M 参数可能只是记住它们。**Kill 条件：训练损失下降但 Ped R40 不动，且车在联合门上退化 > 5%。**
- **必须先确认「冻结」这件事本身**：用户简报把主干描述为「冻结 legacy StereoDETR 主干」，但 `a2_seit.yaml:123` 的 `pretrained_stereodetr: null` 表示没有加载我方自己的预训练权重，`preserve_original_stereo_branch` 在 `build_voxel_event.py:161-162` 只是结构守卫、不设置 `requires_grad`。实际被冻的只有 `backbone.py:71-73` 这一处 ImageNet stem。开臂前用一行 `sum(p.requires_grad)` 的 CPU 断言把这个事实钉死。

---

### T3 —— 深度分箱换成均匀 0.2 m + 三角软目标

**机制名**：把稠密深度 CE 的输出栅格从 LID-80 换成竞品的均匀 0.2 m，并启用已实现的软目标。

**竞品证据**：`liga/models/backbones_3d_stereo/volume_generation_semantic_feedback_sem_up.py:188-199`（`depth_interval = (59.6−2)/288 = 0.2`，`depth[i] = (i+0.5)·0.2 + 2`）、`:411`（作为 `depth_samples` 交付）；`liga/models/dense_heads/depth_loss_head.py:68-74`（三角软目标 CE）。

**我方现状**：LID 80 箱、`depth_min 2.0` / `depth_max 56.9`（`configs/001-final_exp1.yaml:70-72` + `configs/dsec3dod/a2_seit.yaml:71-72`），公式见 `lib/models/event4d/dense_depth_loss.py:24-38`。算出的箱宽：**20 m → 0.779 m，30 m → 0.966 m，40 m → 1.135 m**（竞品同处恒为 0.2 m，比值 3.9–5.7×）。行人容差 0.243 m。软目标已实现（`dense_depth_loss.py:211-239`）且有专门的最优性验证脚本（`tools/ep4d_debug/verify_soft_loss_optimum.py`），但 a2_seit **没开**。

**具体改法**：
1. `lib/models/event4d/dense_depth_loss.py`：`lid_bin_indices` / `lid_continuous_index` 旁边加一个 `uniform_*` 对应物，由一个 `bin_mode` 参数选择；`build_dense_depth_loss`（`:242-252`）透传。
2. 深度预测头的 `bin_value` 反演（LightStereo depth predictor 内）必须同步换成均匀反演，否则读出与监督不自洽——这是本机制最大的实现风险点，必须有一个「注入真值深度 → 读回真值深度」的往返单测。
3. 通道数 80+1 → 288+1，显存与参数上升；若吃不下，先试 144 箱（0.4 m）作为中间档。
4. 同时开 `dense_depth_map_soft_target: true`（`a2_seit.yaml` 的 losses 段）。

**注意这是两个变量**（分箱 + 软目标）。它们必须一起动的理由是台账 §2.7 已经预警过的陷阱：单独把箱变细，可能只是「把弥散摊到更多箱上」（posterior top-1 仅 0.41）。软目标让最小值点落在真值而非箱代表值上（`dense_depth_loss.py:93-104` 的实测：软目标残差 0.002 m，硬目标最大 0.48 m），是把细箱变成收益的必要条件。如果预注册要求严格单变量，则先跑「只开软目标」（零成本、纯配置）作为 T3a，再跑「细箱 + 软目标」作为 T3b。**T3a 应该优先，因为它是一行配置。**

**预期增益的依据**：硬目标 + 0.966 m 箱宽下，深度读出的**理论**最优残差就有约半个箱 = 0.48 m（与 `dense_depth_loss.py:96-97` 记录的实测「硬目标残差最大 0.48 m」吻合），是行人容差 0.243 m 的 2 倍——即当前配置下**行人在深度上永远不可能进 strict IoU**，与实测 2D→3D 存活率 20–40 m 仅 1.4%/0.1% 相符。

**风险 / kill 条件**：
- posterior 弥散不随箱宽改善 → 深度中位误差不动 → kill（用 `field_error_magnitudes.py` 口径量，不看 AP）。
- C16/C57 的告诫（过早 soft-argmin 压掉多峰）在这里**依然适用**：细箱 + 期望读出可能让多峰更容易被平均掉。缓解：同时记录 argmax 读出与期望读出的行人深度误差，若 argmax 明显更好，说明读出方式而非分箱是瓶颈，转向 kill。
- 288 通道的显存 → 若必须降 batch，就引入了第二个混杂变量，宁可先用 144 箱。

---

### T4 —— 二阶段 BEV/ROI 残差精修头（车臂）

**机制名**：在解码框位置池化特征，用一个独立小头重新预测 7 自由度框。

**竞品证据**：`liga/models/dense_heads/det_head_refine_bev_ev_sem.py:342-344`（top-100 proposal）、`:354-359`（BEV 语义特征 + 球查询池化）、`:420-433`（`SHARED_FC [16] → REG_FC [8] → 7` 并散射回去）；`liga/models/dense_heads/anchor_head_template_refine.py:295-308`（SmoothL1 + IoU3d 等幅，只在正样本）；`configs/stereo/dsec_models/evstereo.yaml:351-365, 397-404`。

**我方现状**：单阶段，无精修。

**具体改法**：
1. 在 `lib/models/monodetr/stereodetr.py` 的 `StereoDETR.forward` 末尾，取 top-K（建议 K=50，与解码预算一致）解码框，把它们投影回图像平面，在 `depth_predictor` 的特征图上做一个 3×3 的 ROIAlign。
2. 新增一个 `refine_head`：`Linear(C·9 → 32) → Linear(32 → 7)`，输出对 `(x, y, z, h, w, l, θ)` 的**残差**。
3. 损失：SmoothL1，`code_weights = [1, 1, 1, 0.5, 0.5, 0.5, 1]`（照抄竞品的尺寸减半），在 `SetCriterion` 里新增 `loss_refine`，只在匈牙利匹配上的 query 计算。**先不要叠 IoU3d**（C78 记录它拉低我方天花板）。
4. **池化输入必须 `detach()`**（对应竞品 `det_head_refine_bev_ev_sem.py:360` 的做法）。这是本机制能绕开 C92 的关键：C92（`EXPERIMENTS_AND_PITFALLS.md:580`）证明梯度预算是零和的，抢来的份额让深度中位误差从 0.4279 退到 0.4809。detach 后，精修头**不参与主干梯度竞争**，它是一个纯粹的后处理学习器。
5. 它同样绕开 C99 的 `Var(u)` 上限论证：C99 说降噪类干预封顶 0.92×，但精修头引入的是**新输入**（预测框位置处的特征，一阶段头从未见过），改变的是 `corr × spread` 项而非 `Var(u)`。

**预期增益的依据**：§2.18（`EXPERIMENTS_AND_PITFALLS.md:408`）——车把尺寸与朝向误差收缩到 **0.70×** 即可越过 R40 8.0215 门；车长误差中位需从 0.422 m 到约 0.30 m。竞品在 IoU 0.7 上只领先 1.48 个点（15.28% vs 13.80%，`:105`），而 IoU 0.65 处我方已有 22.60% 的车在排队（`:107`）。这是一个小幅、明确、有可达面支撑的目标。

**风险 / kill 条件**：
- **§2.18 明确说行人这条路封死**（`:410`：尺寸朝向完美，Ped R40 也只到 1.1487）。本臂是**车臂**，不要把它当行人方案。这也是它在「按 Ped 增益排序」里排到第 4 的原因。
- C74/C78：必须在 **oracle-score** 格上判定；若 oracle Veh R40 下降，说明精修头在毁几何、AP 的变化是排序伪迹，kill。
- 与竞品框架相似度最高（这是它们的招牌模块），移植成本也最高：需要新模块 + 新损失 + 新的匹配复用逻辑。
- C123：必须与 Q12 的同配方对照比，不能引用被 SEIT 污染的差值。

---

### T5 —— 从上报分数中移除未校准的 `exp(−log_var)` 因子（**只能作为组件**）

**机制名**：让上报分数回到裸 `sigmoid(cls)`，与竞品一致。

**竞品证据**：`liga/models/detectors_stereo/stereo_detector3d_template_separate_train_regression_ours.py:289-290`（分数 = `sigmoid(cls_preds)`，无质量项）；`configs/stereo/dsec_models/evstereo.yaml:398`（二阶段 `cls_weight: 0.0`，精修完全不改分数）。

**我方现状**：`lib/helpers/decode_helper.py:226-227` 取 `sigma = exp(−log_var)`，`:60` 把它乘进最终分数。这个 `log_var` 是深度 Laplacian 的尺度参数，**从未被校准**。

**具体改法**：`lib/helpers/decode_helper.py:60` 去掉 `* dets[i, j, -1]`，由一个配置开关控制（不要硬删，保留可复现旧行为）。零训练成本，可在已归档的预测 pickle 上纯 CPU 重算。

**预期增益的依据**：C116（`EXPERIMENTS_AND_PITFALLS.md:604`）实测排序价值**类别不对称且方向相反**：原始格上行人 `0.6688 → 1.1992`（+79%），车 `5.0077 → 4.2701`（**−15%**）。「车的分数已经比 2D 重叠度更好」意味着车这边当前排序里有东西在帮忙——但也意味着一个未校准的乘性因子在两个类别上作用相反。C21（`:500`）本来就规定「quality 只有经校准并证明有效才参与排序」，而 `exp(−log_var)` 从未通过这条。**本机制的定位是「移除一个既有规则违例」，不是「引入一种新的重排方法」**，这是它与 C17 禁令（`:496`：「禁止把阈值搜索包装成方法」）的分界线。

**风险 / kill 条件**：
- **C17 仍然生效：不得作为独立臂登记。** 它必须搭在 T1/T2/T3/T4 任一条臂上，作为该臂读出的一个附加格。
- **必须逐类分开报**（C116 的直接要求）。若车升行人降，说明它只是在两个类之间搬运，等价于全局重排，按 C116 判死。
- 可能被 C113（不确定度衰减的实测强度）解释掉：如果 `exp(−log_var)` 在训练后期趋近常数，移除它就是恒等操作，AP 不动。这不算失败，算「机制不存在」，应立即让位。

---

### 5.6 排序汇总

| 名次 | 机制 | 预期 Ped 增益 | 可移植性 | 与竞品框架相似度 | 综合 |
|---|---|---|---|---|---|
| T1 | 稠密深度 GT 时刻对齐 | 高（偏置 2–4× 行人容差） | 极高（数据层十几行） | 极低（我方已有该损失，只换索引） | **最高** |
| T2 | 解冻事件通路第一层 | 中高 | 极高（一个开关） | 极低 | 高 |
| T3 | 均匀 0.2 m 分箱 + 软目标 | 中高（T3a 一行配置） | 中（读出反演须同步） | 低 | 中高 |
| T4 | 二阶段 ROI 残差精修 | **低**（§2.18 对行人封死） | 中 | **高**（招牌模块） | 中（车臂） |
| T5 | 移除未校准 σ 分数因子 | 不确定（+79% 天花板） | 极高（纯解码） | 低 | 组件，不得独立开臂 |

---

## 6. Battle Log（12 位专家）

### 多数派结论（10 人）

行人差距的主因是**深度监督的目标本身有缺陷**（时刻错配 + 箱宽过粗 + 与框内涂色项冲突），而不是召回、不是排序、不是分辨率、不是模块数量。因此 T1/T3 应当优先，T2 作为廉价的并行臂，T4 归入车线。

### 反对意见 1 —— 红队质疑者：T1 的偏置量可能被框内涂色项抵消

> 「你们说深度目标滞后 0…9 帧、单边偏置。但同一份训练里还有 `depth_map` 这个框内涂色损失（`a2_seit.yaml:84`），它用的 `gt_center_depth` 来自**逐子帧**的标注，是**时刻正确的**。也就是说：框内像素同时收到一个时刻正确的常数目标和一个滞后的逐像素目标，框外只有滞后的那个。物体深度的净偏置未必是 45 ms × 车速，可能小得多，甚至方向不定。**在拿到那份 CPU 漂移收据之前，T1 排第一是靠论证而不是靠测量的。**」
>
> 「而且 `Balancer` 给框内像素上了 `fg_weight`（`balancer.py:42`），被上权的恰恰是时刻正确的那一项。你们在第 1.2 节把这称为『冲突』，但它也可以被读成『时刻正确的项占了更大权重』——这两种读法用同一份代码，你们选了对自己论点有利的那种。」

**记录裁决**：反对成立，且改变了执行顺序。T1 不得在 CPU 漂移收据（同 track 的 offset 0 vs 9 中心 z 漂移，分类分距离段）出来之前开臂。同时应补测「框内 vs 框外像素的深度误差差异」——若框内明显更好，红队的读法成立，T1 降级、改为「关掉涂色项」的另一条臂。

### 反对意见 2 —— 复现工程师：你们挑的五条机制，没有一条是最大的配方差

> 「公开权重是 **epoch 22、batch 1、恒定 1e-3、没有梯度裁剪**（`evstereo.yaml:426-438`、`train_utils.py:87-90`）。我们是 **12 epoch、batch 64、5.66e-4、clip 0.1**。按优化步数算，他们比我们多约 **11.7 倍**。Q12 的 36 epoch 也只把差距缩到 3.9 倍。」
>
> 「更要命的是 `clip 0.1`。他们**一次都没裁**。在一个 18.4 M 的模型上把全局梯度范数压到 0.1，配上只有他们 1/12 的步数——你们在讨论深度分箱要不要从 0.98 m 换成 0.2 m，而模型可能根本没走到能表达这个精度的地方。**T1–T5 全都是在『模型已经充分优化』的前提下才成立的机制假设，这个前提没有任何收据。**」
>
> 「反驳我最有力的证据是台账 A0+（`EXPERIMENTS_AND_PITFALLS.md:35,419`）：旧架构长训到 60 epoch，Ped 3D 只有 0.0291。但那是**旧架构**，不是 StereoDETRVoxelEvent，把它当成『长训无用』的通用证据是过度外推。」

**记录裁决**：反对成立且未被现有收据驳倒。行动项：Q12 落地后，第一件事不是读 AP，而是读**梯度范数直方图**——若 clip 0.1 在绝大多数步上都在生效（即裁剪率接近 1），说明有效学习率被这条压着，这时任何结构机制的读数都不可信。此项应写进 Q12 的读出清单，且**不占臂位**（它是诊断，不是干预）。

### 反对意见 3 —— 消融设计师：T4 违反了我们自己的单变量纪律

> 「T4 一条臂里塞了：新的池化算子、新的小 MLP、新的损失项、新的 code_weights、以及一个 detach 决策。这是五个变量。竞品自己都没法告诉我们哪个在起作用——他们的 `ATTENTION` 和 `DENSITYQUERY` 在发布配方里都是关的（`evstereo.yaml:373,384`），说明他们自己也没验证过那些组件。**把一个连原作者都没消融过的复合模块整体移植，是在给我们的台账增加一个无法归因的条目。**」

**记录裁决**：部分成立。T4 若开臂，必须先跑「detach 的池化特征 + 只回归中心平移（3 维）」的最小版本；尺寸与朝向作为第二步。这会降低单臂增益，但保住归因能力。

### 反对意见 4 —— 统计学家：T2 的收益与风险都无法在当前证据下定号

> 「解冻 stem 增加 0.23 M 可训参数。训练集只有 134 个行人身份。这个比例下，『训练损失降、验证不动』是默认预期而不是失败模式。我不反对开这条臂——它便宜——但我反对把它排在第 2 位，因为**它的先验期望值是零附近的对称分布，而 T1/T3 至少有一个已量化的机制量级（0.243 m 容差 vs 0.98 m 箱宽）。**」
>
> 「另外提醒：C118/C123（`EXPERIMENTS_AND_PITFALLS.md:609`）说了，任何『某臂 vs 控制组』的跨臂差值在 Q12 出结果前都不可引用。这份报告里所有 top-5 的『预期增益』引用的是**天花板拆解**（C115/C116/§2.18），那些是在控制组自己的表上做的，不受污染。这一点报告写对了，但读者很容易滑回去拿旧臂的差值当依据。」

**记录裁决**：成立。T2 保留在第 2 位的理由改为「成本极低 + 与 T1/T3 正交，可并行」，而非「期望增益第二高」。报告已按此措辞修正。

### 其余专家的关键补充（无异议）

- **立体匹配专家**：竞品在 stride-1 特征上做亚像素匹配再输出 stride-4 代价体（`liga/ops/build_cost_volume/`、`liga/models/backbones_3d_stereo/cost_volume.py`，`with_upconv: True` 见 `evstereo.yaml:54`）。这条路径**不列入 top-5**，因为 C112 已论证行人深度主要不来自匹配器，且成本最高。
- **LIGA/体素检测专家**：`VOLUME_MOTION`（`evstereo.yaml:124-176`）是死配置，`module_topology`（`stereo_detector3d_template_separate_train_regression_ours.py:22-25`）不含它。此前把「10 帧体积链式传递」当作竞品机制的说法应予更正。
- **事件相机专家**：竞品 5 通道（有符号）信息量**小于**我方 10 通道（分极性）。我方在表示层不落后，落后在表示之后的第一层。
- **深度监督专家**：竞品的深度监督**只有一项**，权重 1.0，无前景加权、无背景填充。我方有两项且互相矛盾，其中一项还带 `fg_weight`。「减一项」比「加一项」更可能是正确方向。
- **数据增广专家**：竞品**没有** copy-paste / GT sampling（`stereo_event_gt_sampling` 在增广器里但未进配置）。**我方的 SEIT 是我方独有的优势，不要因为竞品没有就怀疑它。** 竞品的增广只有立体翻转 + 时间窗抖动 + 空帧重采样。
- **训练配方工程师**：竞品 `DECAY_STEP_LIST: [50]` 而公开权重是 epoch 22 → **竞品的 8.02/3.64 完全在未退火的恒定 1e-3 下取得**。Q12 若靠退火拿到增益，那是我方独立的机制，不是在复现竞品。
- **评测协议专家**：竞品 `SCORE_THRESH: 0.1` + 多类 NMS 0.25 + POST 500；我方 `score_threshold 0.2` + `topk 50` 无 NMS。计数差可解释，但用户已锁定「预算不是杠杆」，与 C98 一致。
- **CUDA/实现细节审计员**：`GRAD_NORM_CLIP: 10` 在竞品配置里存在但代码被注释（`train_utils.py:88-89`）。任何「照抄竞品裁剪值」的提议都是照抄一个不存在的行为。
- **消融设计师**（除上述反对外）：T3 应拆成 T3a（只开软目标，一行配置，零成本）与 T3b（细箱 + 软目标）。T3a 应当最先跑。

### 共识结论

1. **执行顺序**：先跑两份纯 CPU 收据（interval 内 GT 深度漂移；Q12 的梯度裁剪率直方图），再决定 T1 与后续臂位。**不得在收据之前开臂。**
2. **T3a（启用已实现的软目标）是唯一一条零成本、零风险、可立即执行的改动**，应当无条件搭进下一次训练。
3. **T1 的机制论证是本次分析中最强的新发现，但它的量级尚未测量。** 收据一到，若行人 |Δz| 中位 ≥ 0.10 m，T1 立即成为首选臂；若 < 0.10 m，整条放弃并记入台账。
4. **T2 与 T1/T3 正交且成本极低**，可并行，但不得作为主论点。
5. **T4 是车臂**，不要用它去解释行人；若开臂，必须从「detach + 只修平移」的最小版本起步。
6. **T5 永远是组件**，不得独立登记，必须逐类分开报。
7. **必须更正的既有认知三条**：竞品无时序递归；竞品的成绩在未退火、无梯度裁剪、batch=1 下取得；竞品完全不使用 RGB 图像，所以「blind time 处理」不是它的机制。

---

## 附录 A：证据索引（本报告引用的全部文件）

**Ev-Stereo3D**
- `configs/stereo/dsec_models/evstereo.yaml`：7, 13, 20-21, 27, 29-46, 51-56, 64, 73-74, 80, 86, 117, 120, 124-176, 179-231, 232-235, 237-240, 242-301, 255-276, 258, 262, 263-264, 268, 272, 273-274, 278-288, 283, 294-301, 303-404, 351-365, 373, 384, 397-404, 406-408, 410-422, 425-443
- `configs/stereo/dataset_configs/dsec_dataset_fused_event_10.yaml`：12, 13, 14, 32, 34, 36, 37, 41-56
- `liga/datasets/dsec/stereo_dsec_dataset.py`：290, 293-299, 303, 307, 321-330, 332-341, 347-360, 365-366, 387-394, 399-411, 428-429
- `liga/datasets/stereo_dataset_template_dsec.py`：152, 246-248
- `liga/models/detectors_stereo/liga_image_separate_volume_train_regression_ours.py`：26-39, 35, 70-88
- `liga/models/detectors_stereo/stereo_detector3d_template_separate_train_regression_ours.py`：22-25, 250, 289-290, 304-307
- `liga/models/dense_heads/depth_loss_head.py`：36-40, 46-47, 68-74
- `liga/models/dense_heads/det_head_refine_bev_ev_sem.py`：340, 342-344, 354-360, 420-433
- `liga/models/dense_heads/anchor_head_template_refine.py`：295, 301-308, 376
- `liga/models/backbones_3d_stereo/volume_generation_semantic_feedback_sem_up.py`：180-199, 411, 506-507
- `liga/models/backbones_3d_stereo/feature_extract_sem_up.py`：80-82
- `liga/models/backbones_3d_stereo/cost_volume.py`、`liga/ops/build_cost_volume/`
- `tools/train_utils/train_utils.py`：87-90
- `tools/train_utils/optimization/__init__.py`

**我方 `.ep4d_q1`**
- `configs/dsec3dod/a2_seit.yaml`：12, 21, 34, 41-43, 51-56, 71-72, 74-89, 84, 85-86, 89, 92-95, 100-101, 107-119, 123, 130-131
- `configs/001-final_exp1.yaml`：61-62, 70-72, 74-75, 99
- `lib/models/monodetr/backbone.py`：71-73, 106-108
- `lib/models/monodetr/depth_predictor/ddn_loss/ddn_loss.py`：56-86, 88-125, 115-124
- `lib/models/monodetr/depth_predictor/ddn_loss/balancer.py`：19-20, 42
- `lib/models/event4d/dense_depth_loss.py`：24-38, 41-57, 93-104, 98-99, 198-209, 211-239, 242-252
- `lib/models/event4d/build_voxel_event.py`：94-106, 104, 112-130, 161-162
- `lib/datasets/dsec3dod/dsec3dod_dataset.py`：283-287, 376, 484
- `lib/datasets/dsec3dod/depth_gt_store.py`：200-201, 237-249, 251-272
- `lib/datasets/dsec3dod/official_protocol.py`：127-149, 134-148
- `lib/helpers/decode_helper.py`：60, 212-217, 226-227
- `docs/EXPERIMENTS_AND_PITFALLS.md`：35, 102-107, 115, 273, 302, 312-316, 349, 367, 393-410, 419, 457, 469, 496, 500, 580, 585, 589, 600, 603, 604, 608, 609
- `docs/RECIPE_DIFFERENTIAL_EVSTEREO3D.md`（全文）

## 附录 B：开臂前必须产出的纯 CPU 收据

1. **`INTERVAL_DEPTH_DRIFT.json`** —— 同一 track 在 `frame_offset` 0 与 9 之间的 GT 中心 `z` 漂移；分车/行人 × 距离段（0–20 / 20–40 / 40–60 m）；报中位、p90、符号一致性。**决定 T1 是否开臂。**
2. **`FROZEN_PARAM_AUDIT.json`** —— 对构建好的 StereoDETRVoxelEvent 枚举 `named_parameters()`，报告 `requires_grad=False` 的模块名与参数量。**把「主干到底冻了什么」从简报里的说法变成收据。**
3. **`Q12_GRADCLIP_RATE.json`** —— Q12 训练中每步的裁剪前全局梯度范数直方图与实际裁剪率。**若裁剪率接近 1，先修有效学习率，再谈结构机制。**
4. **`DEPTH_ERROR_IN_VS_OUT_BOX.json`** —— 深度图误差在 GT 框内像素与框外像素上的分布对比。**裁决红队反对意见 1。**

（以上四项均只读冻结产物与标注，不需要 GPU。）

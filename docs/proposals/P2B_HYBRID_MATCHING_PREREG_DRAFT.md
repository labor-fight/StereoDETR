# P2(b) 预注册：训练期一对多混合集合匹配（**已执行 = A1 臂，Gate FAIL**）

**执行状态：** 本预注册于 2026-08-25 冻结并作为 A1 臂执行，结果 FAIL
（Veh 6.2552→4.2104、Ped 0.1896→0.7218；oracle 天花板 −32.7% 而排序效率不变）。
结果与归因见 `A1_A2_RESULTS_AND_DEBUG_CONCLUSIONS.md`，已合入
`docs/EXPERIMENTS_AND_PITFALLS.md` §3.7。本文件按预注册惯例只读，不因结果改写。

打击目标 = L2 打分塌缩（C59/C60）。设计原则：只改**训练期匹配与损失
加权**，不加新头、不加新任务、不改推理路径——与 D1 的失败模式
（跨任务辅助头梯度冲突，C67/C70）结构性区分。

## 0. 动机（全部有收据）

- 紧覆盖行人 GT 的最佳预测中位分 0.0126 < 解码阈值 0.1（C2 收据）；
- score-IoU Spearman 0.098（车 0.332）：分数不知道哪个框好；
- oracle 重排序 Veh 6.26→11.39（**超 EvStereo3D 8.02**）、Ped 0.19→1.87：
  车的全部差距在打分/排序内；
- 机制差异（Appendix C）：EvStereo3D 每 GT 数十~数百正锚 + 行人放宽
  阈值 vs 本框架每 GT 每步 1 个正样本。

## 1. 设计

1. **K 组一对多匹配（训练期）**：解码器输出 queries 复制为 1 个主组 +
   K=5 个辅助组（共享全部权重，只是匹配独立）。主组一对一 Hungarian
   （保持推理契约）；辅助组每 GT 匹配 top-m 个查询（m=3，按匹配代价
   排序）。辅助组只回传分类与回归损失，权重 0.5。推理只用主组输出。
   思想来源：Group-DETR/H-DETR 的混合匹配（借"每 GT 多正样本"思想，
   在既有解码器内实现，不搬架构）。
2. **类别自适应匹配代价**（借 EvStereo3D 行人放宽阈值思想在集合匹配内
   实现）：行人的匹配代价中定位项权重 ×0.5（放宽"必须框得极准才配正"），
   分类项不变。仅作用于辅助组。
3. **打分校准损失**：主组匹配上的正样本，分类目标由 1.0 改为
   IoU-aware 软目标（clamp(IoU3D_bev, 0.1, 1.0)），直接优化
   score-IoU 相关性（靶点 Spearman 0.098）。
4. default-off：config 开关 `hybrid_matching.enabled`；所有新代码在
   `lib/models/epst4d_v3/hybrid_matcher.py`，以包装器注入，不修改
   冻结的 `lib/models/monodetr/` 本体（D1 default-off 先例）。

## 2. 与 D1 教训的显式区分

| D1（失败） | P2(b) |
|---|---|
| 新增 dense 辅助头（新任务） | 无新头，复用既有分类/回归头 |
| 辅助梯度经独立分支冲入共享 backbone | 辅助组梯度与主组同构、同头、同尺度 |
| 跨任务梯度冲突（C67/C70） | 单任务内多正样本，无跨任务冲突面 |

残余风险：辅助组可能重塑 Veh 分数分布 → 由门保护；gradient_mass_monitor
（D1 遗产）挂载监控辅助/主组梯度质量比，>3:1 即告警。

## 3. 单变量对照与门

- 基线：R1 冻结配方；唯一变量 = hybrid_matching.enabled。
- **通过门（满足其一）**：(a) Vehicle_3d strict ≥ 8.02（超 EvStereo3D
  checkpoint）；(b) Pedestrian_3d strict ≥ 1.0 且 Vehicle_3d ≥ 6.0。
- **kill 条件**：任一类 strict 相对基线下降 >20%；训练不稳定（loss
  spike >5× 中值）；确定性破坏。
- 预算参考（非承诺）：oracle 上限 Veh 11.39 / Ped 1.87；文献
  （H-DETR/Group-DETR 系）一对多匹配通用 +1~2 AP，稀缺类更大。

## 4. 执行顺序

P2(b) 先行（改动最小、车收益的证据最强）→ SEIT 臂 → 两者联合 →
P3 时序传播。每步单变量、失败即停、不叠加未验证机制。

# H4 尾部补测:待 GPU 窗口的两条命令(零训练,短推理)

> **2026-08-31 18:20 执行状态更新(session f223df):**
> - **R1 侧永久 BLOCKED**:R1 的 `epoch_012.pth` artifact 已在 P0 identity 危机中
>   确认丢失(台账:R1 只能作数字基线引用),H4 的 R1 基线不可补,判 INCONCLUSIVE。
> - **A1 侧执行中**:checkpoint 从归档
>   `/data1/lyq/rep4d_archive/epst4d_v3_20260827/.../epoch_012.pth` 只读恢复
>   (sha256 `59cded10…` 与清单核对 OK),GPU 1 上 `--skip-train` 补测运行中,
>   输出 `reports/epst4d_v3/a1_hybrid_matching/diag_tail/`。
> - **跨树溯源**:`.epst4d_v3` 的 A 系列配置已被"先提交后删除"(bd6ba5e),
>   首次发射因此 FileNotFoundError;重发射从 `.ep4d_q1` 树执行
>   (其 `a1_hybrid_matching.yaml` 与 git 底账逐字节一致,sha256 `9cf0f8f1…`,
>   工具同名同参),日志 `/tmp/a1_diag_tail_f223df.log`。
> - **裁决基准改为 A1 vs A2**:A2 的尾部读数已在
>   `A1_A2_RESULTS_AND_DEBUG_CONCLUSIONS.md` §4 落盘(Veh ≥0.70 档 11.1%、
>   Ped ≥0.50 档 3.8%)。H4 确认条件按原预注册口径改写:A1 的 Veh ≥0.70 档
>   覆盖率相对 A2 下降 >20%(与其 mean IoU 最高并存,即"均值升、尾部薄")。
> - a2/a3 的 e012 checkpoint 仍在 `.ep4d_q1/ckpt/`(后续 ARM-SCORE 的
>   train 侧饱和对照可用,但正式对照须在 Q13 胜者基座上重测)。

**目的:** A1/A2 报告的 H4(高质量 3D IoU 尾部变薄)因 R1 与 A1 缺
`recall_by_iou_3d_threshold` 基线而 OPEN(`A1_A2_RESULTS_AND_DEBUG_CONCLUSIONS.md`
§4)。当时 A2 已落盘,R1/A1 的补测在 2000 query 处被叫停。补齐后 H4 可裁决,
并为 ARM-SCORE 的 G3 天花板守卫提供尾部形状基线。

**装置:** `.epst4d_v3/tools/c2_bottleneck_diagnostic.py`(指标已保留),
`--skip-train` 跳过 1.8h 的 train-split 通道(A3 会话新增并留档)。

**命令(单卡,遵循 C80 调用约定:`CUDA_DEVICE_ORDER=PCI_BUS_ID` +
`CUDA_VISIBLE_DEVICES=<smi编号>` + `--device cuda:0`;预计每次 ~40min):**

```bash
cd /data1/lyq/code/.epst4d_v3
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<空闲smi编号> \
  python tools/c2_bottleneck_diagnostic.py \
  --config configs/dsec3dod/r1_stereo_flip.yaml \
  --checkpoint <R1 正式 checkpoint> --device cuda:0 --skip-train \
  --output reports/r/r1_stereo_flip/diag_tail/

CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=<空闲smi编号> \
  python tools/c2_bottleneck_diagnostic.py \
  --config configs/dsec3dod/a1_hybrid_matching.yaml \
  --checkpoint <A1 正式 checkpoint> --device cuda:0 --skip-train \
  --output reports/epst4d_v3/a1_hybrid_matching/diag_tail/
```

**读数与裁决(预注册):** 比较三臂 `recall_by_iou_3d_threshold`(Vehicle ≥0.70 档、
Pedestrian ≥0.50 档)。H4 确认条件 = A1 的 ≥0.70 档覆盖率相对 R1 下降 >20%
(与其 mean IoU 上升 27% 并存,即"均值升、尾部薄");否则 H4 否决,
A1 的车辆天花板损失需另找解释。诊断口径,不作官方 AP 主张。

---

## 裁决(2026-08-31 18:49,session f223df)

**装置自验证:** 补测 oracle 逐位复现 A1 原始诊断(Veh 4.2104/7.6704、
Ped 0.7218/2.5632)——同把尺子确认。

**H4 = REJECTED(按 A1 vs A2 修订口径):**

| 覆盖视图(best-IoU per truth) | A1(新测) | A2(§4 留档) |
|---|---:|---:|
| Veh ≥0.70 | **10.36%**(2426/23412) | 11.14%(2607/23412) |
| Veh ≥0.50 | 32.9% | 35.7% |
| Veh mean best-IoU | 0.3306 | 0.3454 |
| Ped ≥0.50 | 3.33% | 3.8% |

尾部相对差仅 ~7%(确认线 20%);且覆盖视图的均值 A1 并不更高——原"均值升"
读数是**匹配对均值**(matched-pair mean 0.04388),与覆盖统计不是同一个量,
两者不可混读。

**后继假设速测(同收据):** "分数压缩→解码视图/oracle 预算缩水"也被否决:
A1 解码视图 26,705 框 > A3 22,307 > R1 19,789。

**幸存解释(诊断级,未单变量验证):** 解码视图冗余。A1 每 query ~2.34 框
(A3 ~1.96),oracle 以 IoU 当分数时,同一真值的高 IoU 重复框成为排前列的
假正例,压低 oracle 精度——A2 oracle(11.10)≈ 其覆盖率(11.14%),
A1 oracle(7.67)明显低于其覆盖率(10.36%),与该解释一致。

**计量学警告(载荷性):** oracle 天花板只在相近"框数/视图"下可比;跨臂比较
oracle 必须并报解码视图框数(已回写 ARM-SCORE 预注册 G3)。

**注意:** checkpoint 路径以各臂 diagnostic 收据内记录的 sha256 为准;
运行前核对 `nvidia-smi` 空闲;两条命令勿并行写同一 strata 文件(先后跑)。

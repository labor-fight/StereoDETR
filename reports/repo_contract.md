# R0 — 仓库事实恢复与复现合同

生成时间 2026-08-24。本文回答一个问题：**哪一份代码实际产生了 `docs/EXPERIMENTS_AND_PITFALLS.md` 里的 R1/D1/D2 数字，以及那些产物今天还在不在。** 全部条目给实际路径与 SHA256，或写 `MISSING`；没有一条按文档猜路径。

阶段判定见 §8。结论一句话：**R0 = PASS_WITH_ONE_MISSING_ARTIFACT** —— 源码、配置、评测器、manifest 四方身份全部锁定且 R1 的六个门字段逐一复现，唯一缺口是 R1 最终门 checkpoint `epoch_012.pth`，它不在任何归档、备份或 git 对象中。

---

## 1. 仓库身份

| 项 | 值 |
|---|---|
| remote origin | `git@github.com:labor-fight/StereoDETR.git` |
| remote upstream | `https://github.com/shiyi-mu/StereoDETR-OPEN.git` |
| 主工作树 | `/data1/lyq/code/StereoDETR`，branch `main`，HEAD `0563b6d4559b729cc7ca8544be82b9ab8676d07c` |
| 主树 dirty | 仅 untracked：`.cursor/`、`.serena/`、`lib/datasets/dsec3dod/`（后者是本阶段恢复的 manifest，见 §4） |
| 事件工作树 | `/data1/lyq/code/.epst4d_r1a_frozen`，detached HEAD `9446413a174d7c668a3b1fe8f737259beb548269`，clean |
| 事件提交 | `9446413` 共 93 个提交，其中 **84 个不在 `main` 上**（`main` 只有 10 个）；两者共同祖先 `0dff95b`，同一 root commit `e0b95f7` |
| tags | 无 |
| stash | 无 |
| submodules | 无 |
| Git LFS | 无跟踪文件 |
| 悬空对象 | `git fsck --unreachable --no-reflogs` 输出为空 |

### 1.1 本阶段唯一的写操作：保护引用

侦察发现 `9446413` **不被任何分支或 tag 引用**，仅由 worktree 的 detached HEAD 保活；删除该 worktree 即丢失 84 个事件提交，且 `_git_backup` 里的 bundle 早于它（§6）。因此创建了保护分支：

```
git branch epst4d-archive 9446413
```

工作树内容未被触碰。这是 R0 唯一的 git 写操作。

### 1.2 两棵树的分工

`main` 只有 RGB/KITTI StereoDETR（TCSVT 版）加上 6777 行的中文实验档案 `docs/EXPERIMENTS_AND_PITFALLS.md`。**所有事件实验代码只在 `9446413`**：

| 路径（在 `9446413`） | 内容 |
|---|---|
| `lib/datasets/dsec3dod/` | G1 数据合同：manifest、因果窗口、标定、可见性监督、collate、评测适配器 |
| `lib/models/event4d/` | 事件表示与包装器：`event_voxelizer.py`、`event_input_adapter.py`、`stereodetr_voxel_event.py`、确定性 kernel |
| `lib/models/rep4d/` | 保留的几何/守卫/后验模块：`state.py`、`tensor_guards.py`、`iou3d.py`、`cuboid_geometry.py`、`posterior_losses.py` |
| `lib/models/episet4d/` | D1 的 default-off 实现：`dense_evidence_head.py`、`gradient_mass_monitor.py` |
| `lib/models/monodetr/` | 冻结的 legacy StereoDETR 主干与可变形注意力 CUDA 扩展 |
| `configs/dsec3dod/` | 16 个 yaml（含 `001-final_exp1.yaml`），逐阶段一份 |
| `train_event4d.py` / `eval_event4d.py` | 事件训练/评测入口 |
| `tests/` | `dsec3dod`、`event4d`、`episet4d`、`g3_depth_diagnostic` 四套合同测试 |
| `reports/` | 逐阶段机器收据（41 MB，31 个子目录） |
| `docs/` | 七文件版文档（`ARCHITECTURE_AND_RESEARCH.md`、`PROJECT_HISTORY.md`、`FAILURE_LEDGER.md`、`DATA_CONTRACT.md`、`REPRODUCIBILITY.md`、`RECIPE_DIFFERENTIAL_EVSTEREO3D.md` 与 `docs/episet4d/` 6 份预注册），`main` 上只保留合并后的单文件版 |

### 1.3 文档符号 → 实际路径

| 文档写法 | 实际情况 |
|---|---|
| `src/models/...` | **不存在**。实际根目录是 `lib/models/`（`lib/models/{event4d,rep4d,episet4d,monodetr}`） |
| `reports/...` | 不在 `main`；只在 `9446413` |
| `StreamState` | `lib/models/rep4d/state.py::Rep4DStreamState`（C1 的 caller-owned 不可变 state） |
| `EPiSet4D` | `lib/models/episet4d/`（仅 D1 的 dense 头存活；ERP/APSM/GBHA 从未实现，见 §7.3） |
| `EPST-4D` / `D2` | **源码与收据全部 MISSING**，且在 git 历史里从未出现过（§7.1） |
| `stereo mirror` | `lib/datasets/dsec3dod/stereo_flip.py` + `configs/dsec3dod/r1_stereo_flip.yaml`（R1 臂） |
| `dense training-only head` | `lib/models/episet4d/dense_evidence_head.py` + `configs/dsec3dod/episet4d_d1_dense.yaml`（D1 臂） |
| `R1` | 配置 `configs/dsec3dod/r1_stereo_flip.yaml`，收据 `reports/r/r1_stereo_flip/diagnostic/official_model.json` |
| `D1` | 收据 `reports/episet4d/d1_dense/`（`GATE_D1.json` 本身已被剪除，见 §7.2） |

---

## 2. 五方 hash 锁定

以下路径相对事件工作树 `/data1/lyq/code/.epst4d_r1a_frozen`。评测器与配置的期望值来自该树内已冻结的 `reports/p0/PROTOCOL_FINGERPRINT.json`（`fingerprint_version: rep4d-p0-v1`），本阶段从磁盘重新计算并逐条比对，**6/6 一致**。

### 2.1 评测器（身份与历史一致）

| 文件 | SHA256 | 对照 fingerprint |
|---|---|---|
| `lib/datasets/kitti/kitti_eval_python/eval.py` | `cba91cac54a39182c93546c40f4d3b293459799a92fc4ed742ec957aa09f306c` | 一致 |
| `lib/datasets/dsec3dod/dsec_kitti_eval_adapter.py` | `8c07539a6abf80aab961e44910a7d13bf084102c1905a8c7de08e4609086045d` | 一致 |
| `lib/datasets/dsec3dod/official_eval_worker.py` | `d45569956299f6668135990d6598be74b74c20af9c5e253061dfcc445bada212` | 一致 |
| `lib/datasets/dsec3dod/official_prediction_adapter.py` | `9506c0bc6c72c28074b96eb554baba0efc0a1e7415ac3f59fa5d8c45dfa989d2` | 一致 |
| `configs/dsec3dod/g0_official_protocol.yaml` | `c976eb0b80138cb5309d05036b415acda6ea0908647ad6e08a4179c19f7762b6` | 一致 |

未被 fingerprint 覆盖但同属评测路径的文件，本阶段一并登记：`evaluate.py` `c70a2bfee2336b5c5076fcb18213370d621d2732ee35c2f51e27843eb8c16f9b`、`kitti_common.py` `76f2cb5b00073e06d8bb3f48bd00f12b31d73f604bed1598aa5e16b013df536a`、`rotate_iou.py` `a3e7cd5fedf376d5e4db65e07d26ff8c2a0cc17b7d32b2b25b4503d5bc411f9a`、`kitti_eval_worker.py` `384b673eca516d0f061ef7b73e44ebb8a00e64152a681e317e39269a1cb41bf8`。

**评测器未被修改，类别映射、坐标系与 AP 定义均按 fingerprint 冻结。** 协议要点（引自 fingerprint，非本阶段决定）：类别 `[Vehicle, Pedestrian]`，`Cyclist` 忽略；主内部判据 `AP_R40`，`AP_11` 仅对照且有 `9.0909` 地板；strict 3D IoU `Vehicle 0.7 / Pedestrian 0.5`；解码 `topk=100`、`score_threshold=0.1`、无 NMS、**类别过滤在 global top-k 之前**；官方视图 val 11,400 query / 1,140 interval / 38 sequence，每 interval 取前 10 个 sub-frame。

### 2.2 数据 manifest

| 项 | 值 |
|---|---|
| 路径 | `lib/datasets/dsec3dod/manifest/records.jsonl`（→ symlink 到主树，见 §4） |
| SHA256 | `b2afa842ecff183bdb130d30b4203717e1cf38a1cea8348981e4d5b0fd9b4427`（**与文档 pin 一致**） |
| 大小 | 135,886,083 字节 |
| `summary.json` | `d317052dd9995e851061e52a18c40b94a5901082b1174debd7a1abb2a84e4ac8` |
| `provenance.json` | `471fe6353182def2c82ebdc199710e5e2d53998c67be839a9bff9b55ac185e54`（故意不进 manifest hash） |
| schema | `dsec3dod-g1-v2`，与 `sequence_index.py::MANIFEST_SCHEMA_VERSION` 一致 |
| 身份 | 53,578 query、178 sequence、4 个 calibration id；`manual` 5,518 / `blind` 48,060；class histogram `Vehicle 94,916 / Pedestrian 26,287 / Cyclist 2,509` |
| 构建来源 | `git_commit b5161de977923dce1368bf7afbe22331057e014b`，`data_root /data1/lyq/data/EV_3DOD/DSEC`，`config_sha256 17ccb0d967e3e0cfc9c4eefde4c437d14a370ecdbfa590a3315476da05f744f2` |
| hash 范围 | `records.jsonl exact bytes` |

官方评测 infos：`/data1/lyq/data/EV_3DOD/DSEC/dsec_infos_val.pkl` = `1df3ba49033dabf23c29817f2893e51be9d5dc6d5fdbc216c4c5f72e0e0cae48`，**与 fingerprint 的 `official_view.info_sha256.val` 一致**。`dsec_infos_train.pkl` 存在（60,902,883 字节）。

### 2.3 R1 源码与配置

| 项 | 值 |
|---|---|
| 源码 commit | `9446413a174d7c668a3b1fe8f737259beb548269`（tracked 694 个文件） |
| 臂配置 | `configs/dsec3dod/r1_stereo_flip.yaml` = `0579d583c66b1cc4045be5be1fed0683044b9ce0bd9c38570b3c872156b772d0` |
| legacy 配置 | `configs/001-final_exp1.yaml` = `6081013cafe09806c0938d1a0c280e1618a09d862f41824581fb3316487ca619` |
| 冻结收据 | `reports/r/r1_stereo_flip/diagnostic/official_model.json`（tracked 在 `9446413`） |
| 文档 | 主树 `docs/EXPERIMENTS_AND_PITFALLS.md` = `e17fda52b86e99992d0c42dd8e02d694beeae43e1cf5ddcfffa8ae579b318c3d`；事件树同名文件 = `44f36dcae3ad8580eb5b5e86fc9d2655e5ef38ee622a8c7cc15c45d2624e7b06`（**两份不同**：主树版是 R0' 合并后的单文件版，含附录 B/C） |

### 2.4 R1 checkpoint

11 份归档 checkpoint 与 `/data1/lyq/rep4d_archive/episet4d_p0_20260822/prune_manifest.tsv`（`fb931350e1399d155c6a62beb55cdd1706577ca14bb720a659b9d77d324d4170`）**逐 hash 全部一致**，每份 208,212,110 字节：

| epoch | SHA256 |
|---|---|
| 001 | `69b4c108e9ee72b6900309dda88f60e29f2e49e90676c10d89a7de43fe7c7c92` |
| 002 | `ff880c70303e9846cc479ecbcd1dce713a558b636cfb0e064d4e7649428574e4` |
| 003 | `85c046718705ea30f7ae136baf549f4cc40f851d785f5269fdfcdb13239fa2f4` |
| 004 | `911b839fd2ec76ebc9e9b956d49bf55e26559565291c1d63b70c37e78a0fe6cd` |
| 005 | `7f0fb8444d5c722a3a5dbbe768b1adf89cede73b962183b70d828b4427a88dd7` |
| 006 | `0b0b47a15b73c33123af7c402ab07c03ec001e8de9dd505e04259f5ec30ec4c6` |
| 007 | `38400a26b8a4f1ae9fdb221c670526d5e4940d6cc58e89728904500dfffc8eea` |
| 008 | `08e9bf8a8b3d782f534c78a7ae60caf28abadb7bca2226828966401318db579f` |
| 009 | `349e73a65a64319c70124445a221a26e28bb9cb5b58e70a4da5ef35e13327653` |
| 010 | `0ae3b3d38bd7ea3d68055f3c7d70843073a16009194b175d86e26426603c6967` |
| 011 | `c889d220d7ea8105fb8c332277f6a11afd2b63bb9609177765bdccf7b30bdec6` |
| **012** | **`9e21d6c824199db3846e5d808aba43db9d85505da6ea41e1c34b03152b3561fa` → MISSING** |

`epoch_012.pth` 是 `prune_manifest.tsv` 里唯一标 `KEEP / frozen_gate_artifact` 的一份，也正是 R1 全部报告数字的来源。搜索范围 `/data1/lyq`、`/home/lyq`、`/tmp`：按文件名找到 13 个同名文件（分属 `tsse_b`、`final/a0plus_seed0`、`p2d`、`p1b`、`a0plus`、`episet4d/d1_dense`、`c2/a1|a2|a3` 等其他臂），**逐一 hash 无一匹配** `9e21d6c8…`；按精确大小 208,212,110 字节搜索亦未找到。判定：**该文件已丢失，非移位。**

### 2.5 R1 预测产物

| 项 | 路径 | SHA256 |
|---|---|---|
| model 预测 | `/data1/lyq/rep4d_archive/episet4d_p0_20260822/reports/r/r1_stereo_flip/diagnostic/predictions_model.pkl` | `9f6b8be90fa9aef0956033a7bc64208c09ef7170082586e627dcaa5d85d2613e` |
| oracle 预测 | 同目录 `predictions_oracle.pkl` | `cbf861f7498045f173a8a6e3db1a6ac86380467fe0ccca3b4339a5038584d531` |

`predictions_model.pkl` 的 hash 与冻结收据 `official_model.json` 的 `artifacts.predictions.sha256` **完全一致**，因此它就是 R1 报告数字所依据的那一份预测。这是 §5 复现链能成立的前提。

---

## 3. 环境与硬件

| 项 | 值 |
|---|---|
| 解释器 | `/data1/lyq/miniconda3/envs/stereodetr/bin/python`（Python 3.8）。裸 `python` 无 torch，必须显式给绝对路径 |
| 关键版本 | torch 2.1.2+cu118、torchvision 0.16.2+cu118、scipy 1.10.1、numba 0.58.1 |
| GPU | 8× NVIDIA L20（46 GB），驱动 580.173.02 / CUDA 13.0；本阶段使用 GPU 5 |
| 数据根 | `/data1/lyq/data/EV_3DOD/DSEC`，存在 |
| 磁盘 | `/data1` 29 T，已用 21 T |
| lint/format/typecheck | 仓库未配置任何一项；不在 R0 引入 |

### 3.1 numba CUDA 陷阱（已复现）

非交互 shell 里 numba 的 CUDA 上下文创建**段错误**，与仓库既有记录一致：

```
$ python -c "from numba import cuda; import numpy as np; print(cuda.to_device(np.zeros(4)).copy_to_host())"
段错误（核心已转储）   # 退出码 139
```

torch CUDA 在同一 shell 正常，所以 torch 探针在这里证明不了任何事。生产路径靠子进程隔离（`official_eval_worker.py` / `kitti_eval_worker.py`）绕开，§5 的评测器复现正是走子进程，**未受影响**。

---

## 4. 本阶段恢复的最小可运行布局

两处恢复，都不改任何 tracked 内容，都不进提交：

1. **manifest 实体**。事件树的 `lib/datasets/dsec3dod/manifest/records.jsonl` 是一个指向主树同名路径的 symlink，而主树上该目录根本不存在 → 链接失效。从 `/data1/lyq/stereodetr_docs_backup_20260824/dsec3dod_manifest/records.jsonl`（先验 hash = pin）复制到主树 `lib/datasets/dsec3dod/manifest/`，即 symlink 的目标位置。恢复后经 symlink 读取的 hash 仍为 `b2afa842…`。该目录在主树是 untracked，**不提交**。
2. **R1 预测与 checkpoint**。`reports/episet4d/p0/restored/predictions_model.pkl`（hash 已验）与 `reports/episet4d/p0/restored/epoch_011.pth`。前者是 `tools/episet4d/p0_reeval_r1.py` 约定的恢复位置，该工具会先验 SHA256 再使用；后者仅供 §5.3 的路径存活性验证。

---

## 5. 复现合同

### 5.1 合同测试

| 命令（cwd = 事件工作树） | 结果 |
|---|---|
| `python -m pytest tests/dsec3dod -q` | **84 passed**，29.50 s，无需 deselect |
| `python -m pytest tests/ -q` + 4 项 numba-CUDA deselect | **594 passed / 4 deselected / 2 xfailed / 13 errors**，152.85 s |

13 个 error 全部来自 `tests/episet4d/test_p0_receipt_contract.py`，且**全部由同一个原因引起**：module-scope fixture 调用 `tools/episet4d/p0_protocol_receipt.py::build_receipt()`，后者在 `checkpoint_identity()` 里 fail-closed 抛出

```
ReceiptError: baseline checkpoint reports/r/r1_stereo_flip/epoch_012.pth is absent;
it is a frozen gate input and tools/episet4d/p0_prune_artifacts.sh keeps it on the keep-list
```

即：**整个测试面的失败可归约为 §2.4 的那一个缺失文件**，不是代码漂移。四项 deselect 是 §3.1 的环境陷阱，非代码缺陷。

### 5.2 R1 关键数字复现（决定性证据，无需 GPU）

```
python tools/episet4d/p0_reeval_r1.py evaluator --output-dir <tmp>/p0_reeval   # 退出码 0
```

用固定评测器重评那份已验身份的预测 pickle，与冻结收据逐字段对比。**verdict = PASS**，evaluator 耗时 24.2 s：

- `fields_compared: 84`，`field_differences: []`，容差 `1e-9`（确定性评测器在固定输入上必须精确，不是"容差内"）
- `metric_groups_missing: []`，`metric_groups_unexpected: []`
- `predictions_sha256` 与 `infos_sha256` 均与收据一致

六个门字段逐一复现（收据只记四位小数，故转录容差 `5e-5`）：

| 字段 | metric path | 收据 | 本次评测器 | \|Δ\| |
|---|---|---:|---:|---:|
| Vehicle 3D strict | `Vehicle_3d/moderate_R40` | 6.2552 | 6.255211479481247 | 1.15e-05 |
| Vehicle 3D loose | `Vehicle_3d/moderate_R40_loose` | 25.2045 | 25.20453006354585 | 3.01e-05 |
| Vehicle 2D | `Vehicle_image/moderate_R40` | 16.1715 | 16.171469344894447 | 3.07e-05 |
| Pedestrian 3D strict | `Pedestrian_3d/moderate_R40` | 0.1896 | 0.18956456456456455 | 3.54e-05 |
| Pedestrian 3D loose | `Pedestrian_3d/moderate_R40_loose` | 1.5205 | 1.520456478147211 | 4.35e-05 |
| Pedestrian 2D | `Pedestrian_image/moderate_R40` | 5.7552 | 5.7552462384282945 | 4.62e-05 |

阈值、top-k、类别、坐标与 metric 定义均未改动。**R1 的 `6.2552 / 0.1896` 在当前仓库状态下可复现。**

### 5.3 模型路径存活性（identity 无法验，liveness 可验）

`p0_reeval_r1.py model` 无法执行 —— 它硬编码 `epoch_012.pth`，缺失即 fail-closed：

```
python tools/episet4d/p0_reeval_r1.py model --device cuda:5 --queries 8
FAIL baseline checkpoint absent at reports/r/r1_stereo_flip/epoch_012.pth    # 退出码 1
```

因此改问一个更弱但仍有答案的问题：**模型 + 解码路径本身是否完好。** 用临时驱动把参考 stage 的 checkpoint 常量指向 `epoch_011.pth`（GPU 5，200 个跨步 val query）：

| 项 | 结果 |
|---|---|
| 严格加载 | `strict=True` 通过 |
| queries / objects | 200 query，解码 416 个目标（非空，规避"什么都没测却算通过"） |
| 两遍一致性 | `run_to_run_deterministic: true`，`nondeterministic_count: 0` |
| 与归档预测的差异 | `object_set_mismatch_count: 162`，参考工具判 `FAIL_SELECTION_DIFFERS` |
| liveness 判定 | **PASS** |

162 处差异是**预期结果而非缺陷**：epoch_011 不是产生归档预测的那个 artifact，不同 epoch 就是不同模型。**此处不主张任何 identity。** 该验证只支持一个结论：模型构建、strict 加载、真实数据 forward、协议解码这条链在当前仓库状态下完整且确定性。

### 5.4 state_dict 合同

`epoch_011.pth` 载入按 `configs/dsec3dod/r1_stereo_flip.yaml` 新建的模型（CPU）：

| 项 | 值 |
|---|---|
| model / checkpoint 键数 | 674 / 674 |
| 匹配 | 674，`match_rate = 1.0` |
| missing / unexpected | 0 / 0 |
| shape mismatch | 0 |
| `load_state_dict(strict=True)` | 无异常 |
| 总参数量 | **18,405,547** |

参数量与文档记录的 post-D1 清理后常量 `18,405,547` **完全一致**，即清理未改变模型形状。

---

## 6. 仓库外资产清单

| 资产 | 路径 | 身份 | 作用 |
|---|---|---|---|
| P0 剪除归档 | `/data1/lyq/rep4d_archive/episet4d_p0_20260822/` | `prune_manifest.tsv` = `fb931350e1399d155c6a62beb55cdd1706577ca14bb720a659b9d77d324d4170` | R1 的 001–011 checkpoint、预测 pickle、C2/C3 各臂产物 |
| D1 剪除归档 | `/data1/lyq/rep4d_archive/episet4d_d1_20260823/` | `prune_manifest.tsv` = `dc46f4ef23e9acbeceaa2db213f476b2dea5e23d230d7e8b76f7782a0a514222` | D1 的 12 个 epoch 与诊断产物 |
| REP4D 归档 | `/data1/lyq/rep4d_archive/20260820/` | `archive_manifest.tsv` = `969ffbe720f9b5018f14dbec823c88d2ac43d81dadfe9236e41a3ddbed2ad67b` | a0plus/full60、p1b、p2d、tsse_b、final 等早期臂 |
| 文档与 manifest 备份 | `/data1/lyq/stereodetr_docs_backup_20260824/` | `TRACKED_CLEANUP_20260824.tsv` = `14a3ae3ca8489746181bc676b1ee5635f1d931d380d9e8ebf5d63863e35cec1b` | manifest 实体（§4）、R0' 清理的逐文件 SHA256 |
| 全引用 bundle | `/data1/lyq/code/_git_backup/StereoDETR-allrefs-20260819-1701.bundle` | `5476562b6b9e3da1a08fda296ec65c9e42273397c7b92d09dccb3e546c3e86eb` | 08-19 快照，`main` 停在 `b5161de`；**不含 `9446413`**，故 §1.1 的保护分支不可省 |
| 竞品实现 | `/data1/lyq/code/Ev-Stereo3D/` | 未在 R0 登记 | EvStereo3D 公开实现，R7 对比用 |

---

## 7. 缺失资产与最小恢复动作

### 7.1 EPST-4D D2 装置 — MISSING，且从未被提交

文档 §3.4 记录了 2026-08-24 的 D2 零训练诊断（判 FAIL、路由 `FIX_DATA_CALIBRATION_PRETRAIN`）。其全部引用路径**在整个 git 历史中的提交数为 0**（`git log --all -- <path>` 无输出）：

`tools/epst4d/{d2_gate.py, probe_event_representation.py, audit_event_packets.py, audit_post_d1_gradients.py, ssl_corpus.py, r0_cleanup_audit.sh}`、`tests/epst4d/`（文档称 76 项测试）、`reports/episet4d/d2_audit/D2_AUDIT.json`、`reports/epst4d/**`、`docs/epst4d/{D2_EVIDENCE_AND_GRADIENT_AUDIT_PREREG.md, R1_PREREG.md}`。

结论：**D2 是用从未提交、现已不在磁盘上的代码跑的**，`git fsck` 也无悬空对象。文档里 D2 的数字（合成正控制 1.0000、真实 truth-vs-wrong 0.3590 / 676-1883、噪声负控制约 0.5、K 单调性 0.1328→0.1816→0.3590）**在本仓库内无法验证，只能作为文字记录引用**。

最小恢复动作：**无**。这不阻塞后续阶段 —— R1 阶段本就要求重写升级版探针（对象区域 robust top-K + 运动补偿），并自带合成正控制与留出集负控制。D2 的价值在于它排除的方向（C71–C74 四个装置坑：计数单位未冻结、负对照在训练集上评分、测试断言概率巧合、合成 fixture 只对齐形状），这部分已逐条落在文档里，新探针必须继承这四条。

### 7.2 R1 最终门 checkpoint — MISSING（唯一实质缺口）

`reports/r/r1_stereo_flip/epoch_012.pth`，SHA256 `9e21d6c824199db3846e5d808aba43db9d85505da6ea41e1c34b03152b3561fa`，208,212,110 字节。本地搜索见 §2.4，判定丢失。

它挡住三件事：`p0_reeval_r1.py model` 的 identity 验证、`tests/episet4d/test_p0_receipt_contract.py` 的 13 项、以及任何以 R1 权重为起点的微调。

#### 远端恢复路线已排查并排除

有人提出该文件也许能从 `labor-fight/StereoDETR` 已删除的历史分支里恢复。逐条查证后结论是**不能，而且任何分支都不可能携带它**：

| 检查 | 结果 |
|---|---|
| 远端全部 ref（SSH） | `git ls-remote --refs origin` 只返回一条 `refs/heads/main` → `0563b6d`。无其他分支 |
| 远端 tags | `git ls-remote --tags origin` 为空 |
| GitHub Releases | 每个 Release 必然绑定一个 tag；无 tag ⇒ 无 Release ⇒ 无 Release 附件。（仓库为 private，未认证 REST 返回 404，无法枚举；tag 这一条不需要认证即可闭合该可能） |
| 全历史是否曾跟踪 `.pth` | `git log --all --diff-filter=A --name-only -- '*.pth'` 在 93 个提交、全部 ref 上**输出为空**；`'*.pkl'` 同样为空 |
| `.gitignore` | 事件树第 48–49 行全仓库忽略 `*.pth` 与 `*.pkl`；第 133 行另忽略 `reports/episet4d/p0/restored/` |
| 剪除清单的 `tracked` 列 | `epoch_012.pth` 一行为 **`no`** |
| Git LFS | `git lfs ls-files` 为 0 |
| 按 SHA 直取不可达对象 | 服务端拒绝（未开 `allowAnySHA1InWant`）。且 `9e21d6c8…` 是**文件内容的 SHA256，不是 git object id**，本就不构成可取的 ref |

决定性的一条是「从未被跟踪」：**恢复一个已删除的分支只能恢复源码，不可能恢复一个从未进入过 git 的产物。** 208 MB 的 blob 在没有 LFS 的情况下也过不了 GitHub 的 100 MB 限制。因此远端恢复路线关闭，缺口只能按下面三条路线处理。

最小恢复动作，按代价排序：

1. **接受当前证据链**（零成本）。R1 的报告数字由「已验身份的预测 pickle + 身份已锁的评测器」复现，§5.2 给出 84/84 字段精确一致。若后续阶段只需要 R1 作为**数字基线**（R4 门写的是 `> 6.2552 / > 0.7787`，比的是数字不是权重），这已经足够。**← 项目负责人 2026-08-24 采纳此路线，前置条件是远端恢复不可行，已由上表证实。**
2. **重训 R1 臂**（12 epoch、4 卡、约数小时）。配置、seed（`20260812`）、`deterministic: true`、manifest 与 legacy 配置的 hash 全部锁定，具备可重训条件。但**重训结果不会 bit-identical**，得到的是新 artifact，需要重新登记 hash，并且不能声称等同于原 `epoch_012.pth`。
3. **放弃以 R1 权重为初始化的任何设计**。若某后续阶段需要"从 R1 权重出发"，改为从 `epoch_011.pth`（身份已验）出发并明确记录这是第 11 而非第 12 个 epoch。

### 7.3 从未实现的计划模块（非丢失）

文档引用但在 git 历史中提交数为 0 —— 它们是被 Gate 合法关闭的计划，不是丢失的产物：`lib/models/episet4d/{epipolar_ribbon_posterior, anonymous_posterior_memory, auxiliary_evidence_head, causal_event_pyramid, gbha_assignment}.py`、`lib/datasets/dsec3dod/episet4d_sequence_sampler.py`、`tools/episet4d/{p5a_erp_oracle_probe, t1_transfer_diagnosis}.py`、`configs/dsec3dod/episet4d_p{2,3}_*.yaml`、`docs/episet4d/{P2,P3,P5A,P7,FINAL_EVIDENCE_PACKAGE}*.md`。对应文档里的 `CLOSED_BY_D1` / `CLOSED_BY_D2` 记录。

### 7.4 已按收据剪除的产物（可按 hash 追溯）

`reports/{REP4D_HANDOFF.zip, a0plus/full60/epoch_060.pth, a0plus/full60/eval_epoch060/predictions_official_order.pkl, episet4d/final/SCOREBOARD.json, episet4d/post_d1_cleanup/*.tsv, episet4d/t1/transfer_diagnosis.json, p0/parity/protocol/predictions_official_order.pkl}`。这些在 §6 的三份归档清单里有 SHA256，需要时可定点恢复。

### 7.5 文档路径映射统计

对主树 `docs/EXPERIMENTS_AND_PITFALLS.md` 抽取 215 个反引号内的类路径 token：83 个直接解析（事件树 81 / 主树 2），132 个未直接解析。逐类归因后：

| 类别 | 数量 | 性质 |
|---|---|---|
| 裸文件名（文档只写 basename） | 61（其中 45 个按 basename 在事件树内找到） | 引用风格，非缺失 |
| 非路径 token（比值、metric 字段名、分支名、`pi/2`、`l/r/t/b` 等） | 43 | 正则误捕，非缺失 |
| EPST-4D D2 装置 | 16 | §7.1，真缺失且从未提交 |
| 已剪除产物 | 10 | §7.2 / §7.4 |
| 其他仓库路径（`liga/...`、`numba/...`） | 2 | 非本仓库 |

即 132 个未解析 token 中，只有 §7.1 与 §7.2 的 26 个是真实资产缺口，其余是引用风格或抽取噪声。

---

## 8. R0 Gate 逐条判定

| # | 判据 | 证据 | 判定 |
|---|---|---|---|
| 1 | 找到产生事件实验的真实源码与配置 | `9446413`（84 个独有提交）；`configs/dsec3dod/r1_stereo_flip.yaml` = `0579d583…`；103 个 `lib` 模块全部可导入；16 个 yaml 在拒绝重复键的严格 loader 下全部解析 | **PASS** |
| 2 | 找到或明确恢复 checkpoint | 001–011 全部按归档清单逐 hash 一致并 strict 加载（674/674 键、18,405,547 参数）；**`epoch_012.pth` 确认丢失且远端恢复已排除**（§7.2），按裁决以「预测 + 评测器」复现链替代 | **PARTIAL，已裁决接受** |
| 3 | evaluator 与历史身份一致 | 5/5 fingerprint 覆盖文件 hash 精确一致，另 4 个评测路径文件一并登记；官方 val infos hash 与 fingerprint 一致；评测器源码未改 | **PASS** |
| 4 | 能复现 R1 关键数字 | 84/84 字段在 `1e-9` 内一致，6 个门字段（含 `6.2552` / `0.1896`）转录容差内全部复现；`tests/dsec3dod` 84 项全通过 | **PASS** |
| 5 | 文档、源码、配置、checkpoint 四者 hash 已锁定 | §2 全表；`main` HEAD、事件树 HEAD、两份文档、manifest、四份归档清单、bundle 均已登记 SHA256 | **PASS** |

**阶段判定：`PASS`（记录为 `PASS_WITH_ONE_MISSING_ARTIFACT`）。** 五条中四条 PASS，第 2 条 PARTIAL 但已裁决接受。该 PARTIAL 是单点缺口 —— 它同时是 13 个测试 error 的唯一原因（§5.1），不牵涉代码漂移、协议漂移或数据漂移。

裁决过程留档，因为它决定了后续阶段能引用什么：

1. 先排查远端恢复。`epoch_012.pth` 从未进入 git，远端只有一条 `refs/heads/main`、无 tag 因而无 Release 附件，恢复已删除分支只能恢复源码 —— 路线关闭（§7.2）。
2. 项目负责人据此采纳"接受当前证据链"：**"R1 关键数字可复现"由「身份已验的预测 pickle + 身份已锁的评测器」独立满足**（§5.2，84/84 字段在 `1e-9` 内一致），而后续阶段的门写的是数字而非权重（R4 门为 `> 6.2552 / > 0.7787`）。
3. 被放弃的路线是 12 epoch 重训。它代价高，且产物不会 bit-identical —— 会得到一个需要重新登记 hash 的新 artifact，无法声称等同于原件，因此换不来 identity。

随之而来的三条约束，后续阶段必须遵守：

- **不得声称任何权重与 R1 的原 artifact 同一。** 需要"从 R1 权重出发"时改用 `epoch_011.pth`（身份已验）并显式标注这是第 11 而非第 12 个 epoch。
- **R1 只能作为数字基线引用**，引用时指向 §5.2 的复现表，而不是指向一个 checkpoint 文件。
- `tests/episet4d/test_p0_receipt_contract.py` 的 13 项在缺口补上之前持续 error，这是**已知且已归因**的状态，不得被读作新的回归。

---

## 9. 本阶段产物与不进仓库的东西

进仓库（主树 `main`）只有两项：本文件 `reports/repo_contract.md`，以及 `tests/test_strict_yaml_loader.py`（一个小型严格 YAML loader 重复键测试）。

一次性审计脚本按约定留在 `mktemp -d` 中，**不提交**，此处登记身份以便复核：

| 脚本 | SHA256 | 命令 |
|---|---|---|
| `repo_audit.py` | `db6abe9a4eafaa5914144f74a1ebf13740d545de70b451bed60a2d3872be2e22` | `python <tmp>/repo_audit.py --tree /data1/lyq/code/.epst4d_r1a_frozen --main-tree /data1/lyq/code/StereoDETR --stage {imports,yaml,docpaths,hygiene,hashes,statedict} --output <tmp>/AUDIT_<stage>.json` |
| `model_path_liveness.py` | `5421d10004d909d8f74b4394c4ef4dd35cdafde4f5aa88921a7895c353ede10c` | `CUDA_VISIBLE_DEVICES=5 python <tmp>/model_path_liveness.py <tmp>/p0_reeval cuda:0 200` |

审计脚本六个 stage 的结果：`imports` PASS（103/103）、`yaml` PASS（16/16）、`hashes` PASS（6/6）、`statedict` PASS（674/674）、`hygiene` PASS、`docpaths` REPORT_ONLY（§7.5）。

`hygiene` 的判据只覆盖"是否提交了字节码"，结果为 0 个 `.pyc` / `__pycache__` 进入 694 个 tracked 文件。另外两类命中**报告但不判失败**，因为它们出现在合法位置：`.cuda()` 29 处全在 legacy 的 `lib/losses/focal_loss.py`、`lib/models/monodetr/{dn_components,anchor_transformer}.py` 等**冻结主干**内（新代码禁止此写法，但改动冻结主干会破坏 checkpoint 身份，不属 R0 授权范围）；硬编码数据根 5 处全在 `tools/` 与 `tests/` 的 CLI 默认值里，`import pdb` 0 处。

---

## 10. 给下一阶段的交接要点

1. 事件代码在 `/data1/lyq/code/.epst4d_r1a_frozen`（`9446413`，已由 `epst4d-archive` 分支保护），不在 `main`。文档写的 `src/models` 一律读作 `lib/models`。
2. 主 metric 是 moderate R40 strict；`AP11` 有 `9.0909` 地板，仅作对照。类别过滤必须在 global top-k 之前。评测器与解码适配器的 hash 已锁定在 §2.1，**任何后续阶段不得修改**。
3. manifest 是唯一数据入口（`b2afa842…`，53,578 query），dataset 从不扫描数据根。它现在依赖主树 `lib/datasets/dsec3dod/manifest/records.jsonl` 这个 untracked 实体（§4）；换机器或清理主树时必须先从 §6 的备份恢复。
4. numba CUDA 在非交互 shell 段错误（§3.1）。评测一律走子进程；调试时不要用 torch 探针替代 numba 探针。
5. 数据侧的既有约束（后续阶段直接继承，不再重新发现）：val 与 train 共享全部 21 个 drive，实测无共享 chunk、最小时间间隔 8.600341 s；`blind` 标注 48,060 / `manual` 5,518；行人训练实例约 134 个身份簇 —— 这三条同时约束 R1 的可辨识性探针设计与 R2 的泛化判据。
6. EvStereo3D 的对照必须三列分报：论文数字（19.62 / 12.93，不可复现）、公开 checkpoint 在固定评测器下的 strict R40（8.0215 / 3.6448）、本项目内部数字。公开 checkpoint 是 epoch 22 而论文称 60，且缺 35 个 `dense_head_2d.*` 张量。

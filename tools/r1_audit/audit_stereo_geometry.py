#!/usr/bin/env python
"""R1' 零训练立体几何审计探针（debug session b2baf3）。

目的：解释 D2 记录的 below-chance 立体对应（0.3590 < 0.5）与其反直觉的
距离/尺寸相关性（近处/大目标更差）。D2 装置已丢失（repo_contract §7.1），
本探针按 R1_PREREG 的审计条款重写，并继承 C71-C74 装置纪律：
  - C71 计数单位冻结：所有量以"box"为单位记录，不混用 patch/query。
  - C72 负控制不在训练对象上评分：合成控制用自体平移，不用学习模型。
  - C73 合成正控制必须先通过：装置在已知答案上不达标即 FAIL_RIG。
  - C74 fixture 对齐语义而非形状：合成右图由真实左图平移生成。

假设映射（NDJSON hypothesisId 字段）：
  H-A 垂直极线残差：rectify 后左右并非同行对应（标定 ty/cy 差/量化）。
  H-B 视差方向符号错：匹配方向反转导致系统性 below-chance。
  H-C 左右时间基准错位：t_offset 不同步/窗口不对齐，运动大处错得多。
  H-D 视差预测常数错：fx*B/z 缺 (cx_l - cx_r) 修正或用错内参。
  H-E 表征饱和/patch 混合：高密度区计数饱和、前景背景混合无匹配信号。
  H-F 运动混叠：50ms 单窗压扁摧毁物体对应；10ms 短窗对照应显著改善。
      [run1 REJECTED: 10ms within-2px 0.360 < 50ms 0.414]
  H-G 背景主导：patch 峰值来自背景结构视差而非物体（环带对照相同则证实）。
      [run1 REJECTED: 环带一致率仅 0.123]
  H-H 基准误设：ZNCC 匹配的是物体可见表面，中心视差 fB/Z 不是正确真值；
      正确判据是 8 角点投影视差带。run1 事后分析：Vehicle 隐含表面偏移
      中值 2.18m ≈ 车半长，surface-band 命中 0.376→0.613。本轮固化严格
      角点带判据做前后对照。

只读审计：不写任何数据/仓库文件，仅追加 NDJSON 到 debug 日志。
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

EVENT_TREE = "/data1/lyq/code/.epst4d_r1a_frozen"
LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-b2baf3.log"
SESSION = "b2baf3"

sys.path.insert(0, EVENT_TREE)

from lib.datasets.dsec3dod.annotation_store import AnnotationStore  # noqa: E402
from lib.datasets.dsec3dod.calibration import (  # noqa: E402
    load_left_camera_from_lidar,
    load_stereo_calibration,
)
from lib.datasets.dsec3dod.event_store import H5EventStore  # noqa: E402

import lib.datasets.dsec3dod.event_store as _es_mod  # noqa: E402

assert _es_mod.__file__.startswith(EVENT_TREE), (
    "import resolved to wrong tree: %s" % _es_mod.__file__
)


def dlog(hypothesis_id, location, message, data, run_id="run1"):
    entry = {
        "sessionId": SESSION,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=float) + "\n")


def iter_manifest(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def select_records(manifest_path, split, max_records, seed):
    """确定性采样：manual 帧、含目标、按 calibration_id 均衡。"""
    buckets = defaultdict(list)
    for record in iter_manifest(manifest_path):
        if record.get("split") != split:
            continue
        if record.get("annotation_source") != "manual":
            continue
        if not record.get("num_objects"):
            continue
        buckets[record["calibration_id"]].append(record)
    rng = np.random.RandomState(seed)
    selected = []
    per_bucket = max(1, max_records // max(1, len(buckets)))
    for calib_id in sorted(buckets):
        pool = buckets[calib_id]
        order = rng.permutation(len(pool))[:per_bucket]
        selected.extend(pool[i] for i in sorted(order))
    return selected[:max_records], sorted(buckets)


def count_image(events, height, width):
    """极性无关事件计数图，log1p 压缩（同时返回原始计数供 H-E）。"""
    img = np.zeros((height, width), dtype=np.float64)
    if events.shape[0]:
        xs = events[:, 0].astype(np.int64)
        ys = events[:, 1].astype(np.int64)
        np.add.at(img, (ys, xs), 1.0)
    return np.log1p(img), img


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    if denom < 1.0e-9:
        return 0.0
    return float((a * b).sum() / denom)


def scan_disparity(left_img, right_img, x0, x1, y0, y1, shifts, dys):
    """right_x = left_x - s；s>0 为物理正确方向（右相机在 +x 基线上）。

    返回 {(dy): [zncc per s]}；越界候选记 NaN。
    """
    height, width = right_img.shape
    patch = left_img[y0:y1, x0:x1]
    results = {}
    for dy in dys:
        row = np.full(len(shifts), np.nan)
        ry0, ry1 = y0 + dy, y1 + dy
        if ry0 < 0 or ry1 > height:
            results[dy] = row
            continue
        band = right_img[ry0:ry1]
        for idx, s in enumerate(shifts):
            rx0, rx1 = x0 - s, x1 - s
            if rx0 < 0 or rx1 > width:
                continue
            row[idx] = zncc(patch, band[:, rx0:rx1])
        results[dy] = row
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/data1/lyq/data/EV_3DOD/DSEC")
    parser.add_argument(
        "--manifest",
        default="/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl",
    )
    parser.add_argument("--split", default="train")
    parser.add_argument("--max-records", type=int, default=40)
    parser.add_argument("--max-boxes-per-record", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--run-id", default="run1")
    args = parser.parse_args()
    run_id = args.run_id

    data_root = Path(args.data_root)

    # #region agent log (meta: 装置参数与 import 断言)
    dlog(
        "meta",
        "audit_stereo_geometry.py:main",
        "audit start",
        {
            "split": args.split,
            "max_records": args.max_records,
            "seed": args.seed,
            "event_tree": EVENT_TREE,
            "event_store_file": _es_mod.__file__,
        },
        run_id,
    )
    # #endregion

    records, calib_ids = select_records(
        args.manifest, args.split, args.max_records, args.seed
    )
    store = AnnotationStore(data_root)

    calib_cache = {}
    calib_logged = set()
    box_rows = []
    control_pass = 0
    control_total = 0

    for record in records:
        frame = store.frame_record(
            record["annotation_file"], int(record["annotation_record_index"])
        )
        calib_key = record["calibration_id"]
        if calib_key not in calib_cache:
            calib_cache[calib_key] = load_stereo_calibration(
                data_root / record["calibration_file"],
                T_left_camera_from_lidar=load_left_camera_from_lidar(frame),
            )
        calib = calib_cache[calib_key]
        K_l = calib.K_left.numpy()
        K_r = calib.K_right.numpy()
        T_rl = calib.T_right_from_left.numpy()
        fx_l, cx_l, fy_l, cy_l = K_l[0, 0], K_l[0, 2], K_l[1, 1], K_l[1, 2]
        cx_r, cy_r = K_r[0, 2], K_r[1, 2]
        baseline = float(calib.baseline_m)

        if calib_key not in calib_logged:
            calib_logged.add(calib_key)
            # #region agent log (H-A/H-D: 标定分解——ty/tz 残差与 cx/cy 差)
            dlog(
                "H-A",
                "audit_stereo_geometry.py:calib",
                "calibration decomposition",
                {
                    "calibration_id": calib_key[:23],
                    "t_right_from_left": [float(v) for v in T_rl[:3, 3]],
                    "baseline_m": baseline,
                    "fx_left": float(fx_l),
                    "fx_right": float(K_r[0, 0]),
                    "cx_left_minus_cx_right": float(cx_l - cx_r),
                    "cy_left_minus_cy_right": float(cy_l - cy_r),
                    "rectified_flag": bool(calib.rectified),
                },
                run_id,
            )
            # #endregion

        width = int(record["image_width"])
        height = int(record["image_height"])
        origin = int(record["sequence_origin_raw"])
        t_start = int(record["history_start_timestamp_raw"])
        t_end = int(record["query_timestamp_raw"])

        left_store = H5EventStore(
            data_root / record["left_event_file"],
            data_root / record["left_rectify_map_file"],
            origin,
            (width, height),
        )
        right_store = H5EventStore(
            data_root / record["right_event_file"],
            data_root / record["right_rectify_map_file"],
            origin,
            (width, height),
        )
        left_packet = left_store.read_window(t_start, t_end)
        right_packet = right_store.read_window(t_start, t_end)
        left_ev = left_packet.events.numpy()
        right_ev = right_packet.events.numpy()

        # #region agent log (H-C: 左右时间基准与事件量对齐)
        lt = left_packet.t_raw.numpy()
        rt = right_packet.t_raw.numpy()
        dlog(
            "H-C",
            "audit_stereo_geometry.py:window",
            "stereo window timing",
            {
                "sequence_id": record["sequence_id"],
                "query_index": record["query_index"],
                "t_offset_left_minus_right_us": int(
                    left_store.t_offset_raw_us - right_store.t_offset_raw_us
                ),
                "left_count": int(left_ev.shape[0]),
                "right_count": int(right_ev.shape[0]),
                "left_t_range_raw": [int(lt.min()), int(lt.max())] if lt.size else None,
                "right_t_range_raw": [int(rt.min()), int(rt.max())] if rt.size else None,
                "manifest_num_left": int(record["num_left_events"]),
                "manifest_num_right": int(record["num_right_events"]),
                "invalid_rect_left": int(left_packet.invalid_rectification_count),
                "invalid_rect_right": int(right_packet.invalid_rectification_count),
            },
            run_id,
        )
        # #endregion

        left_img, left_raw = count_image(left_ev, height, width)
        right_img, _ = count_image(right_ev, height, width)

        # H-F 对照：仅保留窗口末端 10ms 的事件（seconds 相对 origin）
        sec_end = (t_end - origin) * 1.0e-6
        short_mask_l = left_ev[:, 2] >= sec_end - 0.010
        short_mask_r = right_ev[:, 2] >= sec_end - 0.010
        left_img10, _ = count_image(left_ev[short_mask_l], height, width)
        right_img10, _ = count_image(right_ev[short_mask_r], height, width)

        target = store.target_from_record(record, calib)
        boxes = target["boxes_3d"].numpy()
        labels = target["labels"].numpy()

        order = np.argsort(boxes[:, 2]) if boxes.shape[0] else []
        used = 0
        for box_i in order:
            if used >= args.max_boxes_per_record:
                break
            X, Y, Z, length, h_box, w_box, yaw = [float(v) for v in boxes[box_i]]
            if Z <= 2.0 or Z > 45.0:
                continue
            # H-H: 水平角点的深度范围（长轴沿 heading=(sin yaw,0,cos yaw)）
            z_half_span = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(
                np.sin(yaw)
            )
            z_near_corner = max(Z - z_half_span, 1.0)
            z_far_corner = Z + z_half_span
            u = fx_l * X / Z + cx_l
            v = fy_l * Y / Z + cy_l
            half_w_px = 0.5 * max(w_box, length) * fx_l / Z
            half_h_px = 0.5 * h_box * fy_l / Z
            # 往内收缩 15% 减少背景混入（H-E 对照量仍记录全框密度）
            x0 = int(max(0, np.floor(u - 0.85 * half_w_px)))
            x1 = int(min(width, np.ceil(u + 0.85 * half_w_px)))
            y0 = int(max(0, np.floor(v - 0.85 * half_h_px)))
            y1 = int(min(height, np.ceil(v + 0.85 * half_h_px)))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            if x1 - x0 > 200:
                cx_mid = (x0 + x1) // 2
                x0, x1 = cx_mid - 100, cx_mid + 100
            if y1 - y0 > 200:
                cy_mid = (y0 + y1) // 2
                y0, y1 = cy_mid - 100, cy_mid + 100

            d_geo = fx_l * baseline / Z
            d_exp = d_geo + (cx_l - cx_r)
            d_band_near = fx_l * baseline / z_near_corner + (cx_l - cx_r)
            d_band_far = fx_l * baseline / z_far_corner + (cx_l - cx_r)
            s_max = int(min(240, max(60, abs(d_exp) * 2 + 24)))
            shifts = list(range(-s_max, s_max + 1))
            dys = list(range(-3, 4))

            scan = scan_disparity(left_img, right_img, x0, x1, y0, y1, shifts, dys)
            row0 = scan[0]
            if np.all(np.isnan(row0)):
                continue
            best_idx = int(np.nanargmax(row0))
            d_meas = float(shifts[best_idx])
            peak = float(row0[best_idx])
            pos_mask = np.array(shifts) > 2
            neg_mask = np.array(shifts) < -2
            pos_peak = float(np.nanmax(row0[pos_mask])) if np.any(
                ~np.isnan(row0[pos_mask])
            ) else float("nan")
            neg_peak = float(np.nanmax(row0[neg_mask])) if np.any(
                ~np.isnan(row0[neg_mask])
            ) else float("nan")
            best_dy, best_dy_val = 0, peak
            for dy in dys:
                val = np.nanmax(scan[dy]) if not np.all(np.isnan(scan[dy])) else np.nan
                if np.isfinite(val) and val > best_dy_val:
                    best_dy, best_dy_val = dy, float(val)
            sorted_vals = np.sort(row0[~np.isnan(row0)])
            second = float(sorted_vals[-2]) if sorted_vals.size >= 2 else float("nan")
            density = float(left_raw[y0:y1, x0:x1].mean())
            sat_frac = float((left_raw[y0:y1, x0:x1] > 8).mean())

            # H-F: 10ms 短窗对照扫描（同 patch、同 shifts、dy=0）
            row10 = scan_disparity(
                left_img10, right_img10, x0, x1, y0, y1, shifts, [0]
            )[0]
            if np.all(np.isnan(row10)):
                d_meas_10, err_10, peak_10 = None, None, None
            else:
                i10 = int(np.nanargmax(row10))
                d_meas_10 = float(shifts[i10])
                err_10 = float(d_meas_10 - d_exp)
                peak_10 = float(row10[i10])

            # H-G: 误差大时扫描环带（box 外扩 40% 减内框），看背景视差
            ring_d = None
            if abs(d_meas - d_exp) > 3.0:
                gx0 = int(max(0, x0 - 0.4 * (x1 - x0)))
                gx1 = int(min(width, x1 + 0.4 * (x1 - x0)))
                gy0 = int(max(0, y0 - 0.4 * (y1 - y0)))
                gy1 = int(min(height, y1 + 0.4 * (y1 - y0)))
                ring_left = left_img.copy()
                ring_right = right_img.copy()
                ring_left[y0:y1, x0:x1] = 0.0
                ring_row = scan_disparity(
                    ring_left, ring_right, gx0, gx1, gy0, gy1, shifts, [0]
                )[0]
                if not np.all(np.isnan(ring_row)):
                    ring_d = float(shifts[int(np.nanargmax(ring_row))])

            surface_hit = bool(d_band_far - 2.0 <= d_meas <= d_band_near + 2.0)
            surface_hit_10 = (
                bool(d_band_far - 2.0 <= d_meas_10 <= d_band_near + 2.0)
                if d_meas_10 is not None
                else None
            )
            row = {
                "sequence_id": record["sequence_id"],
                "query_index": record["query_index"],
                "class": int(labels[box_i]),
                "z_m": Z,
                "yaw": yaw,
                "dims_lhw": [length, h_box, w_box],
                "center_uv": [float(u), float(v)],
                "d_band_far": float(d_band_far),
                "d_band_near": float(d_band_near),
                "surface_band_hit": surface_hit,
                "surface_band_hit_10ms": surface_hit_10,
                "patch_w": x1 - x0,
                "patch_h": y1 - y0,
                "d_geometric": float(d_geo),
                "d_expected_with_cx": float(d_exp),
                "d_measured": d_meas,
                "err_vs_geo": float(d_meas - d_geo),
                "err_vs_cx": float(d_meas - d_exp),
                "zncc_peak": peak,
                "pos_dir_peak": pos_peak,
                "neg_dir_peak": neg_peak,
                "direction_correct": bool(pos_peak >= neg_peak)
                if np.isfinite(pos_peak) and np.isfinite(neg_peak)
                else None,
                "best_dy": best_dy,
                "best_dy_gain": float(best_dy_val - peak),
                "peak_margin": float(peak - second) if np.isfinite(second) else None,
                "event_density_mean": density,
                "saturated_pixel_frac": sat_frac,
                "d_measured_10ms": d_meas_10,
                "err_10ms_vs_cx": err_10,
                "zncc_peak_10ms": peak_10,
                "ring_d_measured": ring_d,
            }
            box_rows.append(row)
            # #region agent log (H-B/H-D/H-E: 逐 box 视差扫描)
            dlog("H-B", "audit_stereo_geometry.py:box", "box disparity scan", row, run_id)
            # #endregion
            used += 1

            if used == 1:
                control_total += 1
                shift_true = int(round(d_exp))
                synth_right = np.zeros_like(left_img)
                if shift_true >= 0:
                    synth_right[:, : width - shift_true] = left_img[:, shift_true:]
                else:
                    synth_right[:, -shift_true:] = left_img[:, : width + shift_true]
                cscan = scan_disparity(
                    left_img, synth_right, x0, x1, y0, y1, shifts, [0]
                )[0]
                if not np.all(np.isnan(cscan)):
                    c_meas = float(shifts[int(np.nanargmax(cscan))])
                    ok = abs(c_meas - shift_true) <= 1
                    control_pass += int(ok)
                    # #region agent log (rig: C73 合成正控制)
                    dlog(
                        "rig",
                        "audit_stereo_geometry.py:control",
                        "synthetic positive control",
                        {
                            "sequence_id": record["sequence_id"],
                            "query_index": record["query_index"],
                            "shift_true": shift_true,
                            "shift_measured": c_meas,
                            "pass": ok,
                        },
                        run_id,
                    )
                    # #endregion

        left_store.close()
        right_store.close()

    # 汇总
    if box_rows:
        z_arr = np.array([r["z_m"] for r in box_rows])
        err = np.array([r["err_vs_cx"] for r in box_rows])
        err_geo = np.array([r["err_vs_geo"] for r in box_rows])
        dir_ok = np.array(
            [r["direction_correct"] for r in box_rows if r["direction_correct"] is not None],
            dtype=bool,
        )
        dy_arr = np.array([r["best_dy"] for r in box_rows])
        err10_rows = [r for r in box_rows if r["err_10ms_vs_cx"] is not None]
        err10 = np.array([r["err_10ms_vs_cx"] for r in err10_rows])
        ring_rows = [r for r in box_rows if r["ring_d_measured"] is not None]
        ring_agree = (
            float(
                np.mean(
                    [
                        abs(r["ring_d_measured"] - r["d_measured"]) <= 2
                        for r in ring_rows
                    ]
                )
            )
            if ring_rows
            else None
        )
        surf = np.array([r["surface_band_hit"] for r in box_rows], dtype=bool)
        cls_arr = np.array([r["class"] for r in box_rows])
        surf10_rows = [
            r["surface_band_hit_10ms"]
            for r in box_rows
            if r["surface_band_hit_10ms"] is not None
        ]
        surface_stats = {
            "global_rate": float(surf.mean()),
            "vehicle_rate": float(surf[cls_arr == 0].mean())
            if (cls_arr == 0).any()
            else None,
            "pedestrian_rate": float(surf[cls_arr == 1].mean())
            if (cls_arr == 1).any()
            else None,
            "rate_10ms": float(np.mean(surf10_rows)) if surf10_rows else None,
            "depth_buckets": {},
        }
        for lo, hi in [(0, 10), (10, 20), (20, 30), (30, 100)]:
            mask = (z_arr >= lo) & (z_arr < hi)
            if mask.sum():
                surface_stats["depth_buckets"]["%d-%dm" % (lo, hi)] = {
                    "n": int(mask.sum()),
                    "surface_band_rate": float(surf[mask].mean()),
                }
        buckets = {}
        for lo, hi in [(0, 10), (10, 20), (20, 30), (30, 100)]:
            mask = (z_arr >= lo) & (z_arr < hi)
            if mask.sum():
                buckets["%d-%dm" % (lo, hi)] = {
                    "n": int(mask.sum()),
                    "median_abs_err_cx_px": float(np.median(np.abs(err[mask]))),
                    "median_err_cx_px": float(np.median(err[mask])),
                    "median_abs_err_geo_px": float(np.median(np.abs(err_geo[mask]))),
                    "within_2px_rate": float((np.abs(err[mask]) <= 2).mean()),
                }
        # #region agent log (summary: 全假设汇总)
        dlog(
            "summary",
            "audit_stereo_geometry.py:summary",
            "audit summary",
            {
                "boxes_scanned": len(box_rows),
                "control_pass": control_pass,
                "control_total": control_total,
                "direction_correct_rate": float(dir_ok.mean()) if dir_ok.size else None,
                "best_dy_histogram": {
                    str(k): int((dy_arr == k).sum()) for k in range(-3, 4)
                },
                "depth_buckets": buckets,
                "calibration_ids_seen": [c[:23] for c in calib_ids],
                "global_within_2px_rate": float((np.abs(err) <= 2).mean()),
                "global_median_err_cx_px": float(np.median(err)),
                "global_median_err_geo_px": float(np.median(err_geo)),
                "hf_10ms_within_2px_rate": (
                    float((np.abs(err10) <= 2).mean()) if err10.size else None
                ),
                "hf_10ms_n": int(err10.size),
                "hg_ring_agreement_rate": ring_agree,
                "hg_ring_n": len(ring_rows),
                "hh_surface_band": surface_stats,
            },
            run_id,
        )
        # #endregion
        print(
            "audit done: %d boxes, control %d/%d, center within-2px %.3f, "
            "surface-band %.3f"
            % (
                len(box_rows),
                control_pass,
                control_total,
                float((np.abs(err) <= 2).mean()),
                float(surf.mean()),
            )
        )
    else:
        # #region agent log (summary: 空结果)
        dlog(
            "summary",
            "audit_stereo_geometry.py:summary",
            "audit produced no boxes",
            {"records_selected": len(records)},
            run_id,
        )
        # #endregion
        print("audit done: no eligible boxes")


if __name__ == "__main__":
    main()

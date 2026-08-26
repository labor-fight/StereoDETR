#!/usr/bin/env python
"""亚像素物体级视差精度普查（debug session 522f14）。

问题：行人 strict 3D(IoU 0.5) 要求 |δz| ≤ l·(1-t)/(1+t)（10-20 m 处折合
亚 0.5 px 视差精度，附录 D §2.3 权威表），而现有 LightStereo 稠密图已被
P4A 判 MAP_LIMITED。R1' (C76) 证明 ±2px 角点表面带判据下朴素 ZNCC 对应
命中 0.63-0.78，但没有回答"能精确到多少 px"。本探针给出这个数字。

假设映射（NDJSON hypothesisId 字段）：
  H2a  物体级事件视差可达 strict 容差精度：以两个不相交 25ms 半窗的独立
       ZNCC+抛物线亚像素估计之差 |d_A - d_B| 作为精度上界（含真实物体
       运动与半量事件噪声，双重保守），与逐 box 容差 tol_d = f·B·tol_z/Z²
       比较。若 10-25 m 行人有可观比例满足 |d_A-d_B| ≤ 2·tol_d，则
       "对象条件稀疏匹配可支撑行人 strict 深度"物理可行。
  H2b  装置健康：全窗峰值落在角点表面带 ±2px 的比例应复现 C76 的
       0.63(train)/0.65(val)；显著低于则本轮读数不可用。
  CTRL 装置功效：
       - 合成分数位移正控制（C73/C76 纪律）：注入已知 0.30/0.70 px 分数
         视差，抛物线估计须恢复到 ≤0.25 px 误差，否则 FAIL_RIG；
       - 错行负控制：dy=+40 行扫描的带命中率须显著低于 dy=0，否则
         命中来自非极线结构，探针无效。

继承 C71-C74 纪律：以 box 为计数单位；控制不在学习模型上评分；正负控制
都给数字；fixture 对齐语义（分数位移用线性插值合成，不是整数 roll）。
只读审计：不写数据/仓库文件，仅追加 NDJSON 到 debug 日志。
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

EVENT_TREE = "/data1/lyq/code/.epst4d_r1a_frozen"
LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-522f14.log"
SESSION = "522f14"

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

STRICT_IOU = {0: 0.7, 1: 0.5, 2: 0.5}  # Car/Vehicle, Pedestrian, Cyclist
CLASS_NAME = {0: "Vehicle", 1: "Pedestrian", 2: "Cyclist"}


def dlog(hypothesis_id, location, message, data, run_id):
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
    return selected[:max_records]


def count_image(events, height, width):
    img = np.zeros((height, width), dtype=np.float64)
    if events.shape[0]:
        xs = events[:, 0].astype(np.int64)
        ys = events[:, 1].astype(np.int64)
        np.add.at(img, (ys, xs), 1.0)
    return np.log1p(img)


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    if denom < 1.0e-9:
        return float("nan")
    return float((a * b).sum() / denom)


def scan_row(left_img, right_img, x0, x1, y0, y1, shifts, dy=0):
    height, width = right_img.shape
    patch = left_img[y0:y1, x0:x1]
    row = np.full(len(shifts), np.nan)
    ry0, ry1 = y0 + dy, y1 + dy
    if ry0 < 0 or ry1 > height:
        return row
    band = right_img[ry0:ry1]
    for idx, s in enumerate(shifts):
        rx0, rx1 = x0 - s, x1 - s
        if rx0 < 0 or rx1 > width:
            continue
        row[idx] = zncc(patch, band[:, rx0:rx1])
    return row


def subpixel_peak(shifts, row):
    """整数峰 + 三点抛物线细化。返回 (d_sub, peak_val, curvature) 或 None。"""
    if np.all(np.isnan(row)):
        return None
    i = int(np.nanargmax(row))
    if i == 0 or i == len(row) - 1:
        return float(shifts[i]), float(row[i]), float("nan")
    y0, y1, y2 = row[i - 1], row[i], row[i + 1]
    if not (np.isfinite(y0) and np.isfinite(y1) and np.isfinite(y2)):
        return float(shifts[i]), float(row[i]), float("nan")
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1.0e-12:
        return float(shifts[i]), float(row[i]), 0.0
    frac = 0.5 * (y0 - y2) / denom
    frac = float(np.clip(frac, -1.0, 1.0))
    return float(shifts[i]) + frac, float(y1), float(-denom)


def synth_fractional_right(left_img, d_int, frac):
    """合成 right(y,x) = left(y, x + d_int + frac)，线性插值（语义级 fixture）。"""
    height, width = left_img.shape
    out = np.zeros_like(left_img)
    a = np.zeros_like(left_img)
    b = np.zeros_like(left_img)
    if d_int + 1 < width:
        a[:, : width - d_int] = left_img[:, d_int:]
        b[:, : width - d_int - 1] = left_img[:, d_int + 1:]
    out = (1.0 - frac) * a + frac * b
    return out


def band_distance(d, band_far, band_near):
    if d is None:
        return None
    if band_far <= d <= band_near:
        return 0.0
    return float(min(abs(d - band_far), abs(d - band_near)))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default="/data1/lyq/data/EV_3DOD/DSEC")
    parser.add_argument(
        "--manifest",
        default="/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl",
    )
    parser.add_argument("--split", default="train")
    parser.add_argument("--max-records", type=int, default=40)
    parser.add_argument("--max-boxes-per-record", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20260824)
    parser.add_argument("--run-id", default="runA")
    args = parser.parse_args()
    run_id = args.run_id

    data_root = Path(args.data_root)

    # #region agent log (meta: 装置参数)
    dlog(
        "meta",
        "probe_subpixel_disparity.py:main",
        "probe start",
        {
            "split": args.split,
            "max_records": args.max_records,
            "max_boxes_per_record": args.max_boxes_per_record,
            "seed": args.seed,
            "event_tree": EVENT_TREE,
        },
        run_id,
    )
    # #endregion

    records = select_records(args.manifest, args.split, args.max_records, args.seed)
    store = AnnotationStore(data_root)
    calib_cache = {}

    rows = []
    ctrl_pos_errs = []
    n_ctrl_neg_hit = 0
    n_ctrl_neg_total = 0

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
        fx_l, cx_l, fy_l, cy_l = K_l[0, 0], K_l[0, 2], K_l[1, 1], K_l[1, 2]
        cx_r = K_r[0, 2]
        baseline = float(calib.baseline_m)
        fB = fx_l * baseline

        width = int(record["image_width"])
        height = int(record["image_height"])
        origin = int(record["sequence_origin_raw"])
        t_start = int(record["history_start_timestamp_raw"])
        t_end = int(record["query_timestamp_raw"])
        t_mid = (t_start + t_end) // 2

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
        left_ev = left_store.read_window(t_start, t_end).events.numpy()
        right_ev = right_store.read_window(t_start, t_end).events.numpy()

        sec_mid = (t_mid - origin) * 1.0e-6
        lmA = left_ev[:, 2] < sec_mid
        rmA = right_ev[:, 2] < sec_mid

        left_full = count_image(left_ev, height, width)
        right_full = count_image(right_ev, height, width)
        left_a = count_image(left_ev[lmA], height, width)
        right_a = count_image(right_ev[rmA], height, width)
        left_b = count_image(left_ev[~lmA], height, width)
        right_b = count_image(right_ev[~rmA], height, width)

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
            z_half_span = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(
                np.sin(yaw)
            )
            z_near_corner = max(Z - z_half_span, 1.0)
            z_far_corner = Z + z_half_span
            u = fx_l * X / Z + cx_l
            v = fy_l * Y / Z + cy_l
            half_w_px = 0.5 * max(w_box, length) * fx_l / Z
            half_h_px = 0.5 * h_box * fy_l / Z
            x0 = int(max(0, np.floor(u - 0.85 * half_w_px)))
            x1 = int(min(width, np.ceil(u + 0.85 * half_w_px)))
            y0 = int(max(0, np.floor(v - 0.85 * half_h_px)))
            y1 = int(min(height, np.ceil(v + 0.85 * half_h_px)))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            if x1 - x0 > 200:
                cmid = (x0 + x1) // 2
                x0, x1 = cmid - 100, cmid + 100
            if y1 - y0 > 200:
                cmid = (y0 + y1) // 2
                y0, y1 = cmid - 100, cmid + 100

            d_exp = fB / Z + (cx_l - cx_r)
            d_band_near = fB / z_near_corner + (cx_l - cx_r)
            d_band_far = fB / z_far_corner + (cx_l - cx_r)
            s_max = int(min(240, max(60, abs(d_exp) * 2 + 24)))
            shifts = list(range(-s_max, s_max + 1))
            sh_arr = np.array(shifts)

            row_full = scan_row(left_full, right_full, x0, x1, y0, y1, shifts, 0)
            pk_full = subpixel_peak(shifts, row_full)
            if pk_full is None:
                continue
            d_full, peak_val, curv = pk_full

            # 半窗估计限制在全窗峰 ±10px（两半窗同一范围，可比）
            nb_mask = np.abs(sh_arr - d_full) <= 10
            nb_shifts = [int(s) for s in sh_arr[nb_mask]]
            row_a = scan_row(left_a, right_a, x0, x1, y0, y1, nb_shifts, 0)
            row_b = scan_row(left_b, right_b, x0, x1, y0, y1, nb_shifts, 0)
            pk_a = subpixel_peak(nb_shifts, row_a)
            pk_b = subpixel_peak(nb_shifts, row_b)

            # 错行负控制（同全范围）
            row_neg = scan_row(left_full, right_full, x0, x1, y0, y1, shifts, 40)
            pk_neg = subpixel_peak(shifts, row_neg)
            neg_hit = None
            if pk_neg is not None:
                neg_hit = bool(d_band_far - 2.0 <= pk_neg[0] <= d_band_near + 2.0)
                n_ctrl_neg_total += 1
                n_ctrl_neg_hit += int(neg_hit)

            cls = int(labels[box_i])
            t_iou = STRICT_IOU.get(cls, 0.5)
            tol_z = length * (1.0 - t_iou) / (1.0 + t_iou)
            tol_d = fB * tol_z / (Z * Z)

            repeat = None
            if pk_a is not None and pk_b is not None:
                repeat = float(abs(pk_a[0] - pk_b[0]))

            row_out = {
                "sequence_id": record["sequence_id"],
                "query_index": record["query_index"],
                "class": cls,
                "class_name": CLASS_NAME.get(cls, str(cls)),
                "z_m": Z,
                "length_m": length,
                "patch_wh": [x1 - x0, y1 - y0],
                "d_expected": float(d_exp),
                "band": [float(d_band_far), float(d_band_near)],
                "d_full_subpx": d_full,
                "zncc_peak": peak_val,
                "peak_curvature": curv,
                "band_hit_2px": bool(
                    d_band_far - 2.0 <= d_full <= d_band_near + 2.0
                ),
                "band_dist_subpx": band_distance(d_full, d_band_far, d_band_near),
                "d_half_a": pk_a[0] if pk_a else None,
                "d_half_b": pk_b[0] if pk_b else None,
                "repeatability_px": repeat,
                "tol_d_px": float(tol_d),
                "tol_z_m": float(tol_z),
                "strict_iou": t_iou,
                "meets_tol": bool(repeat is not None and repeat <= tol_d),
                "meets_2tol": bool(repeat is not None and repeat <= 2.0 * tol_d),
                "neg_ctrl_band_hit": neg_hit,
            }
            rows.append(row_out)
            # #region agent log (H2a: 逐 box 亚像素精度)
            dlog("H2a", "probe_subpixel_disparity.py:box", "box subpixel census", row_out, run_id)
            # #endregion
            used += 1

            if used == 1:
                # 合成分数位移正控制：0.30 与 0.70 px
                d_int = int(round(abs(d_exp)))
                for frac in (0.30, 0.70):
                    synth = synth_fractional_right(left_full, d_int, frac)
                    crow = scan_row(left_full, synth, x0, x1, y0, y1, shifts, 0)
                    cpk = subpixel_peak(shifts, crow)
                    if cpk is not None:
                        err = abs(cpk[0] - (d_int + frac))
                        ctrl_pos_errs.append(err)
                        # #region agent log (CTRL: 合成分数位移正控制)
                        dlog(
                            "CTRL",
                            "probe_subpixel_disparity.py:ctrl",
                            "fractional synthetic control",
                            {
                                "sequence_id": record["sequence_id"],
                                "injected": d_int + frac,
                                "recovered": cpk[0],
                                "abs_err_px": err,
                            },
                            run_id,
                        )
                        # #endregion

    # 汇总
    def bucket(z):
        if z < 10:
            return "0-10"
        if z < 20:
            return "10-20"
        if z < 30:
            return "20-30"
        return "30-45"

    summary = defaultdict(lambda: defaultdict(list))
    for r in rows:
        key = (r["class_name"], bucket(r["z_m"]))
        summary[key]["repeat"].append(r["repeatability_px"])
        summary[key]["tol"].append(r["tol_d_px"])
        summary[key]["meets"].append(r["meets_tol"])
        summary[key]["meets2"].append(r["meets_2tol"])
        summary[key]["hit2"].append(r["band_hit_2px"])
        summary[key]["bdist"].append(r["band_dist_subpx"])

    print("\n=== subpixel disparity census (%s) ===" % args.split)
    print(
        "%-11s %-6s %4s %9s %9s %7s %7s %7s %7s"
        % ("class", "z", "n", "med|dA-dB|", "med tol_d", "≤tol", "≤2tol", "hit@2", "med bdist")
    )
    summary_rows = []
    for (cls, zb) in sorted(summary):
        d = summary[(cls, zb)]
        reps = [v for v in d["repeat"] if v is not None]
        med_rep = float(np.median(reps)) if reps else float("nan")
        med_tol = float(np.median(d["tol"]))
        n = len(d["meets"])
        meets = float(np.mean([1.0 if m else 0.0 for m in d["meets"]]))
        meets2 = float(np.mean([1.0 if m else 0.0 for m in d["meets2"]]))
        hit2 = float(np.mean([1.0 if m else 0.0 for m in d["hit2"]]))
        bd = [v for v in d["bdist"] if v is not None]
        med_bd = float(np.median(bd)) if bd else float("nan")
        print(
            "%-11s %-6s %4d %9.3f %9.3f %6.1f%% %6.1f%% %6.1f%% %8.3f"
            % (cls, zb, n, med_rep, med_tol, 100 * meets, 100 * meets2, 100 * hit2, med_bd)
        )
        summary_rows.append(
            {
                "class": cls,
                "z_bucket": zb,
                "n": n,
                "median_repeatability_px": med_rep,
                "median_tol_d_px": med_tol,
                "frac_meets_tol": meets,
                "frac_meets_2tol": meets2,
                "band_hit_2px": hit2,
                "median_band_dist_subpx": med_bd,
            }
        )

    ctrl_pos = {
        "n": len(ctrl_pos_errs),
        "median_abs_err_px": float(np.median(ctrl_pos_errs)) if ctrl_pos_errs else None,
        "p90_abs_err_px": float(np.percentile(ctrl_pos_errs, 90)) if ctrl_pos_errs else None,
        "pass": bool(ctrl_pos_errs and np.median(ctrl_pos_errs) <= 0.25),
    }
    ctrl_neg = {
        "n": n_ctrl_neg_total,
        "band_hit_rate": (n_ctrl_neg_hit / n_ctrl_neg_total) if n_ctrl_neg_total else None,
    }
    print("positive control (fractional shift):", ctrl_pos)
    print("negative control (wrong row dy=40):", ctrl_neg)

    # #region agent log (H2b/CTRL: 汇总)
    dlog(
        "H2b",
        "probe_subpixel_disparity.py:summary",
        "census summary",
        {
            "split": args.split,
            "n_boxes": len(rows),
            "buckets": summary_rows,
            "ctrl_pos": ctrl_pos,
            "ctrl_neg": ctrl_neg,
        },
        run_id,
    )
    # #endregion


if __name__ == "__main__":
    main()

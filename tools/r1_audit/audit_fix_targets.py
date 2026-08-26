#!/usr/bin/env python
"""修复方案的零训练验证（debug session b2baf3）。

H-I（L2 打分缺陷可修性）不在此脚本：R1 归档收据 C2_BOTTLENECK.json 已含
全量查询级审计与 oracle 重打分（Veh 6.26->11.39 超 EvStereo3D 8.02；
Ped 0.19->1.87 上限），直接引用。

本脚本验证剩余两个修复靶点：

  H-J SEIT 立体一致事件实例移植的物理可行性。
      事件级提取行人双视图事件管 -> 变换（T1 换位置 / T2 换深度缩放）->
      粘贴到其他场景 -> 用已验证的表面带判据审计移植后的立体对应。
      判据：移植样本命中率与真实行人基准（train 0.667 / val 0.778）同级。
      装置控制（C73 纪律）：T0 恒等移植（原场景原位贴回）命中率必须与
      donor 原位审计一致。
  H-K 跨窗查询传播先验强度。
      相邻 manual 帧（100ms）经 obj_ids 关联（仅审计用，不进模型），统计
      同一物体的 3D 位移与图像投影位移，折半估计 50ms 窗口间运动幅度。
      判据：中位位移足够小（数 px 量级）则查询传播先验强。
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from audit_stereo_geometry import (  # noqa: E402
    EVENT_TREE,
    LOG_PATH,
    SESSION,
    count_image,
    iter_manifest,
    scan_disparity,
)

sys.path.insert(0, EVENT_TREE)

from lib.datasets.dsec3dod.annotation_store import AnnotationStore  # noqa: E402
from lib.datasets.dsec3dod.calibration import (  # noqa: E402
    load_left_camera_from_lidar,
    load_stereo_calibration,
)
from lib.datasets.dsec3dod.event_store import H5EventStore  # noqa: E402

DATA_ROOT = Path("/data1/lyq/data/EV_3DOD/DSEC")
MANIFEST = "/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl"
RUN_ID = "run4-fix"


def dlog(hypothesis_id, location, message, data):
    entry = {
        "sessionId": SESSION,
        "runId": RUN_ID,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=float) + "\n")


def load_scene(record, store):
    """读取一条 record 的左右事件数组与标定。"""
    frame = store.frame_record(
        record["annotation_file"], int(record["annotation_record_index"])
    )
    calib = load_stereo_calibration(
        DATA_ROOT / record["calibration_file"],
        T_left_camera_from_lidar=load_left_camera_from_lidar(frame),
    )
    width = int(record["image_width"])
    height = int(record["image_height"])
    origin = int(record["sequence_origin_raw"])
    kwargs = dict(sequence_origin_raw_us=origin, image_size=(width, height))
    ls = H5EventStore(
        DATA_ROOT / record["left_event_file"],
        DATA_ROOT / record["left_rectify_map_file"],
        **kwargs,
    )
    rs = H5EventStore(
        DATA_ROOT / record["right_event_file"],
        DATA_ROOT / record["right_rectify_map_file"],
        **kwargs,
    )
    t0 = int(record["history_start_timestamp_raw"])
    t1 = int(record["query_timestamp_raw"])
    ev_l = ls.read_window(t0, t1).events.numpy()
    ev_r = rs.read_window(t0, t1).events.numpy()
    ls.close()
    rs.close()
    return frame, calib, ev_l, ev_r, width, height


def ped_geometry(box, K, baseline):
    """行人 box 的投影中心、2D 框、视差与表面带。"""
    X, Y, Z, length, h_box, w_box, yaw = [float(v) for v in box]
    fx, cx = K[0, 0], K[0, 2]
    fy, cy = K[1, 1], K[1, 2]
    u = fx * X / Z + cx
    v = fy * Y / Z + cy
    half_w = 0.5 * max(w_box, length) * fx / Z
    half_h = 0.5 * h_box * fy / Z
    span = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(np.sin(yaw))
    d_c = fx * baseline / Z
    d_near = fx * baseline / max(Z - span, 1.0)
    d_far = fx * baseline / (Z + span)
    return {
        "u": u, "v": v, "z": Z, "span": span,
        "x0": u - half_w, "x1": u + half_w,
        "y0": v - half_h, "y1": v + half_h,
        "d_c": d_c, "d_near": d_near, "d_far": d_far,
        "fxB": fx * baseline,
    }


def audit_patch(img_l, img_r, g, width, height):
    """在给定几何 g 上跑表面带扫描，返回 (hit, d_meas, peak)。"""
    x0 = int(max(0, np.floor(g["x0"])))
    x1 = int(min(width, np.ceil(g["x1"])))
    y0 = int(max(0, np.floor(g["y0"])))
    y1 = int(min(height, np.ceil(g["y1"])))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    s_max = int(min(240, max(60, g["d_c"] * 2 + 24)))
    shifts = list(range(-s_max, s_max + 1))
    row = scan_disparity(img_l, img_r, x0, x1, y0, y1, shifts, [0])[0]
    if np.all(np.isnan(row)):
        return None
    idx = int(np.nanargmax(row))
    d_meas = float(shifts[idx])
    hit = bool(g["d_far"] - 2.0 <= d_meas <= g["d_near"] + 2.0)
    return hit, d_meas, float(row[idx])


def extract_tube(ev_l, ev_r, g):
    """按左右投影区提取事件管（含区内背景，SEIT 生产版需前景分割）。"""
    pad = 2.0
    ml = (
        (ev_l[:, 0] >= g["x0"] - pad) & (ev_l[:, 0] <= g["x1"] + pad)
        & (ev_l[:, 1] >= g["y0"] - pad) & (ev_l[:, 1] <= g["y1"] + pad)
    )
    rx0 = g["x0"] - g["d_near"] - 3.0
    rx1 = g["x1"] - g["d_far"] + 3.0
    mr = (
        (ev_r[:, 0] >= rx0) & (ev_r[:, 0] <= rx1)
        & (ev_r[:, 1] >= g["y0"] - pad) & (ev_r[:, 1] <= g["y1"] + pad)
    )
    return ev_l[ml].copy(), ev_r[mr].copy()


def transform_tube(tube_l, tube_r, g, du, alpha):
    """位置平移 du + 深度缩放 alpha（z'=alpha*z, 图像/视差缩放 1/alpha）。"""
    u_new = g["u"] + du
    d_new = g["d_c"] / alpha
    tl = tube_l.copy()
    tr = tube_r.copy()
    tl[:, 0] = u_new + (tl[:, 0] - g["u"]) / alpha
    tl[:, 1] = g["v"] + (tl[:, 1] - g["v"]) / alpha
    right_center_old = g["u"] - g["d_c"]
    right_center_new = u_new - d_new
    tr[:, 0] = right_center_new + (tr[:, 0] - right_center_old) / alpha
    tr[:, 1] = g["v"] + (tr[:, 1] - g["v"]) / alpha
    z_new = g["z"] * alpha
    g_new = {
        "u": u_new, "v": g["v"], "z": z_new, "span": g["span"],
        "x0": u_new + (g["x0"] - g["u"]) / alpha,
        "x1": u_new + (g["x1"] - g["u"]) / alpha,
        "y0": g["v"] + (g["y0"] - g["v"]) / alpha,
        "y1": g["v"] + (g["y1"] - g["v"]) / alpha,
        "d_c": d_new,
        "d_near": g["fxB"] / max(z_new - g["span"], 1.0),
        "d_far": g["fxB"] / (z_new + g["span"]),
        "fxB": g["fxB"],
    }
    return tl, tr, g_new


def paste(scene_l, scene_r, tube_l, tube_r, g_new):
    """遮挡语义粘贴：清空目标区内场景事件（移植体为前景），再合并。"""
    pad = 2.0
    kl = ~(
        (scene_l[:, 0] >= g_new["x0"] - pad) & (scene_l[:, 0] <= g_new["x1"] + pad)
        & (scene_l[:, 1] >= g_new["y0"] - pad) & (scene_l[:, 1] <= g_new["y1"] + pad)
    )
    rx0 = g_new["x0"] - g_new["d_near"] - 3.0
    rx1 = g_new["x1"] - g_new["d_far"] + 3.0
    kr = ~(
        (scene_r[:, 0] >= rx0) & (scene_r[:, 0] <= rx1)
        & (scene_r[:, 1] >= g_new["y0"] - pad) & (scene_r[:, 1] <= g_new["y1"] + pad)
    )
    out_l = np.concatenate([scene_l[kl], tube_l], axis=0)
    out_r = np.concatenate([scene_r[kr], tube_r], axis=0)
    return out_l, out_r


def clip_events(ev, width, height):
    ev = ev.copy()
    ev[:, 0] = np.rint(ev[:, 0])
    ev[:, 1] = np.rint(ev[:, 1])
    keep = (
        (ev[:, 0] >= 0) & (ev[:, 0] < width)
        & (ev[:, 1] >= 0) & (ev[:, 1] < height)
    )
    return ev[keep]


def run_seit():
    store = AnnotationStore(DATA_ROOT)
    donors = []
    targets = []
    seen_seq = set()
    rng = np.random.RandomState(20260824)

    candidates = []
    for record in iter_manifest(MANIFEST):
        if record.get("split") != "train":
            continue
        if record.get("annotation_source") != "manual":
            continue
        hist = record.get("class_histogram", {})
        if hist.get("Pedestrian", 0) > 0 and record["base_sequence_id"] not in seen_seq:
            candidates.append(record)
            seen_seq.add(record["base_sequence_id"])
        if len(candidates) >= 24:
            break

    # donor 筛选：原位表面带审计命中的行人
    for record in candidates:
        if len(donors) >= 6:
            break
        try:
            frame, calib, ev_l, ev_r, width, height = load_scene(record, store)
        except Exception as exc:  # 数据缺失即跳过
            dlog("H-J", "audit_fix_targets.py:donor", "scene load failed",
                 {"sequence_id": record["sequence_id"], "error": str(exc)})
            continue
        target = store.target_from_record(record, calib)
        boxes = target["boxes_3d"].numpy()
        labels = target["labels"].numpy()
        K = calib.K_left.numpy()
        baseline = float(calib.baseline_m)
        img_l, _ = count_image(ev_l, height, width)
        img_r, _ = count_image(ev_r, height, width)
        for i in np.where(labels == 1)[0]:
            g = ped_geometry(boxes[i], K, baseline)
            if not (8.0 <= g["z"] <= 25.0):
                continue
            if g["x1"] - g["x0"] < 14 or g["x0"] < 10 or g["x1"] > width - 10:
                continue
            res = audit_patch(img_l, img_r, g, width, height)
            if res is None:
                continue
            hit, d_meas, peak = res
            # #region agent log (H-J: donor 原位预审计)
            dlog("H-J", "audit_fix_targets.py:donor", "donor in-situ audit", {
                "sequence_id": record["sequence_id"], "z": g["z"],
                "hit": hit, "d_meas": d_meas, "d_c": g["d_c"], "peak": peak,
            })
            # #endregion
            if hit:
                donors.append({
                    "record": record, "g": g, "ev_l": ev_l, "ev_r": ev_r,
                    "width": width, "height": height, "peak": peak,
                })
                break

    # target 场景：与 donor 不同的 base_sequence
    donor_bases = {d["record"]["base_sequence_id"] for d in donors}
    for record in candidates:
        if record["base_sequence_id"] in donor_bases:
            continue
        if len(targets) >= 3:
            break
        try:
            _, _, ev_l, ev_r, width, height = load_scene(record, store)
        except Exception:
            continue
        targets.append({
            "record": record, "ev_l": ev_l, "ev_r": ev_r,
            "width": width, "height": height,
        })

    t0_pass = t0_total = 0
    tx_hits = defaultdict(lambda: [0, 0])
    for donor in donors:
        g = donor["g"]
        width, height = donor["width"], donor["height"]
        tube_l, tube_r = extract_tube(donor["ev_l"], donor["ev_r"], g)
        if tube_l.shape[0] < 50 or tube_r.shape[0] < 50:
            continue

        # T0 恒等移植（装置控制）
        s_l, s_r = paste(donor["ev_l"], donor["ev_r"], tube_l, tube_r, g)
        img_l, _ = count_image(clip_events(s_l, width, height), height, width)
        img_r, _ = count_image(clip_events(s_r, width, height), height, width)
        res = audit_patch(img_l, img_r, g, width, height)
        t0_total += 1
        ok = bool(res and res[0])
        t0_pass += int(ok)
        # #region agent log (rig: T0 恒等移植控制)
        dlog("rig", "audit_fix_targets.py:t0", "identity transplant control", {
            "sequence_id": donor["record"]["sequence_id"],
            "pass": ok, "d_meas": res[1] if res else None,
        })
        # #endregion

        # T1 换位置 / T2 换深度，贴到异景
        for tgt in targets:
            for name, du, alpha in (
                ("T1_shift", float(rng.choice([-120, 120])), 1.0),
                ("T2_nearer", 0.0, 0.75),
                ("T2_farther", 0.0, 1.5),
            ):
                tl, tr, g_new = transform_tube(tube_l, tube_r, g, du, alpha)
                if g_new["x0"] < 12 or g_new["x1"] > tgt["width"] - 12:
                    continue
                if g_new["x0"] - g_new["d_near"] - 3 < 0:
                    continue
                s_l, s_r = paste(tgt["ev_l"], tgt["ev_r"], tl, tr, g_new)
                img_l, _ = count_image(
                    clip_events(s_l, tgt["width"], tgt["height"]),
                    tgt["height"], tgt["width"],
                )
                img_r, _ = count_image(
                    clip_events(s_r, tgt["width"], tgt["height"]),
                    tgt["height"], tgt["width"],
                )
                res = audit_patch(img_l, img_r, g_new, tgt["width"], tgt["height"])
                if res is None:
                    continue
                hit, d_meas, peak = res
                tx_hits[name][0] += int(hit)
                tx_hits[name][1] += 1
                # #region agent log (H-J: 移植后立体一致性审计)
                dlog("H-J", "audit_fix_targets.py:transplant", "transplant audit", {
                    "donor": donor["record"]["sequence_id"],
                    "target": tgt["record"]["sequence_id"],
                    "transform": name, "du": du, "alpha": alpha,
                    "z_new": g_new["z"], "d_expected": g_new["d_c"],
                    "d_meas": d_meas, "hit": hit, "peak": peak,
                })
                # #endregion

    summary = {
        "donors_selected": len(donors),
        "targets": len(targets),
        "t0_identity_control": {"pass": t0_pass, "total": t0_total},
        "transplant_hit_rates": {
            k: {"hit": v[0], "n": v[1], "rate": (v[0] / v[1]) if v[1] else None}
            for k, v in tx_hits.items()
        },
        "real_pedestrian_baseline": {"train": 0.667, "val": 0.778},
    }
    # #region agent log (H-J: summary)
    dlog("H-J", "audit_fix_targets.py:seit_summary", "SEIT feasibility summary",
         summary)
    # #endregion
    print("SEIT:", json.dumps(summary, ensure_ascii=False))


def run_temporal_prior():
    store = AnnotationStore(DATA_ROOT)
    calib_cache = {}
    disp_3d = {"Vehicle": [], "Pedestrian": []}
    disp_px = {"Vehicle": [], "Pedestrian": []}
    files_seen = {}
    for record in iter_manifest(MANIFEST):
        if record.get("split") != "train":
            continue
        if record.get("annotation_source") != "manual":
            continue
        key = record["annotation_file"]
        if key not in files_seen:
            files_seen[key] = record
        if len(files_seen) >= 30:
            break

    for rel_path, record in files_seen.items():
        try:
            infos = store._load(rel_path)
        except Exception:
            continue
        frame0 = infos[0]
        calib_key = record["calibration_id"]
        if calib_key not in calib_cache:
            calib_cache[calib_key] = load_stereo_calibration(
                DATA_ROOT / record["calibration_file"],
                T_left_camera_from_lidar=load_left_camera_from_lidar(frame0),
            )
        calib = calib_cache[calib_key]
        T = calib.T_left_camera_from_lidar.numpy()
        K = calib.K_left.numpy()
        for i in range(len(infos) - 1):
            a0, a1 = infos[i]["annos"], infos[i + 1]["annos"]
            dt_s = (infos[i + 1]["time_stamp"] - infos[i]["time_stamp"]) * 1e-6
            if not (0.05 < dt_s < 0.2):
                continue
            ids0 = {int(x): j for j, x in enumerate(np.asarray(a0["obj_ids"]))}
            ids1 = {int(x): j for j, x in enumerate(np.asarray(a1["obj_ids"]))}
            for oid in set(ids0) & set(ids1):
                j0, j1 = ids0[oid], ids1[oid]
                name = str(np.asarray(a0["name"])[j0])
                if name not in disp_3d:
                    continue
                c0 = np.asarray(a0["gt_boxes_lidar"])[j0, :3]
                c1 = np.asarray(a1["gt_boxes_lidar"])[j1, :3]
                move_m = float(np.linalg.norm(c1 - c0)) / dt_s * 0.05
                p0 = T @ np.append(c0, 1.0)
                p1 = T @ np.append(c1, 1.0)
                if p0[2] <= 1.0 or p1[2] <= 1.0 or p0[2] > 50.0:
                    continue
                u0 = K[0, 0] * p0[0] / p0[2] + K[0, 2]
                v0 = K[1, 1] * p0[1] / p0[2] + K[1, 2]
                u1 = K[0, 0] * p1[0] / p1[2] + K[0, 2]
                v1 = K[1, 1] * p1[1] / p1[2] + K[1, 2]
                move_px = float(np.hypot(u1 - u0, v1 - v0)) / dt_s * 0.05
                disp_3d[name].append(move_m)
                disp_px[name].append(move_px)

    summary = {}
    for name in disp_3d:
        m = np.array(disp_3d[name])
        p = np.array(disp_px[name])
        if m.size == 0:
            continue
        summary[name] = {
            "n_pairs": int(m.size),
            "move_per_50ms_m": {
                "median": float(np.median(m)),
                "p90": float(np.percentile(m, 90)),
                "max": float(m.max()),
            },
            "move_per_50ms_px": {
                "median": float(np.median(p)),
                "p90": float(np.percentile(p, 90)),
                "max": float(p.max()),
            },
        }
    # #region agent log (H-K: 时序传播先验强度)
    dlog("H-K", "audit_fix_targets.py:temporal", "query propagation prior",
         summary)
    # #endregion
    print("TEMPORAL:", json.dumps(summary, ensure_ascii=False))


def main():
    # #region agent log (meta)
    dlog("meta", "audit_fix_targets.py:main", "fix-target audit start",
         {"manifest": MANIFEST, "data_root": str(DATA_ROOT)})
    # #endregion
    run_seit()
    run_temporal_prior()
    print("fix-target audit done")


if __name__ == "__main__":
    main()

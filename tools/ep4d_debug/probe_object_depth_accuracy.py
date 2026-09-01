#!/usr/bin/env python
"""Does an object-conditioned epipolar estimator collect the depth headroom? (session 38825a)

The binding constraint on Pedestrian strict AP is the *ceiling*, not the score:
even with perfect ranking, A3's Pedestrian oracle is 3.6530 while the target is
3.6448, so ranking alone cannot win. The ceiling is set by how many objects have
a box inside strict 3D IoU, which for a pedestrian means |dz| <= 0.243 m.

Two receipts bracket the opportunity and disagree by 3.7x:
  - P4A: the dense LightStereo map puts 18.9% of 10-20 m pedestrians inside that
    tolerance, and the error is MAP_LIMITED (map error ~4x sampling error), so a
    better sample point cannot help.
  - C79: object-level event disparity self-consistency is 0.203 px median for the
    same band against a 0.489 px tolerance, i.e. ~70% is physically available.

C79 measured *precision* (two half-windows agreeing with each other). It never
measured *accuracy* against ground truth. This probe closes that gap: it runs a
straightforward object-conditioned ZNCC with parabolic subpixel refinement on the
GT box, converts to metric centre depth, and compares against GT.

Hypotheses (NDJSON hypothesisId):
  H-E  An object-conditioned subpixel epipolar estimator lands a materially larger
       fraction of pedestrians inside strict tolerance than the dense map's 18.9%.
       This is the pass/fail that decides whether any architecture plan can raise
       the ceiling, or whether only data and ranking remain.
  H-F  The surface-to-centre conversion is the accuracy bottleneck, not the
       disparity estimate. ZNCC matches the visible surface (C76 fingerprint:
       vehicle offset median 2.18 m ~ half-length), so centre depth needs an
       explicit offset. Reported with and without it to separate the two.

Controls:
  CTRL-POS  synthetic fractional shift injected into a real left patch must be
            recovered to <=0.25 px, else the subpixel stage is FAIL_RIG.
  CTRL-NEG  wrong-row (dy=+40) scan must miss tolerance far more often.

Read-only: appends NDJSON only.
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

EVENT_TREE = "/data1/lyq/code/.epst4d_r1a_frozen"
LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-38825a.log"
SESSION = "38825a"

sys.path.insert(0, EVENT_TREE)

from lib.datasets.dsec3dod.annotation_store import AnnotationStore  # noqa: E402
from lib.datasets.dsec3dod.calibration import (  # noqa: E402
    load_left_camera_from_lidar,
    load_stereo_calibration,
)
from lib.datasets.dsec3dod.event_store import H5EventStore  # noqa: E402

import lib.datasets.dsec3dod.event_store as _es_mod  # noqa: E402

assert _es_mod.__file__.startswith(EVENT_TREE), "wrong tree: %s" % _es_mod.__file__

CLASS_NAME = {0: "Vehicle", 1: "Pedestrian", 2: "Cyclist"}
# strict 3D IoU per class, and the longitudinal tolerance it implies via
# |dz| <= l * (1-t)/(1+t) with l the class mean length (appendix D 2.3)
STRICT_IOU = {0: 0.7, 1: 0.5, 2: 0.5}
TOL_Z = {0: 0.798, 1: 0.243, 2: 0.558}


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


def iter_manifest(path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def count_image(events, height, width):
    img = np.zeros((height, width), dtype=np.float64)
    if events.shape[0]:
        np.add.at(
            img, (events[:, 1].astype(np.int64), events[:, 0].astype(np.int64)), 1.0
        )
    return img


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return 0.0 if den < 1e-9 else float((a * b).sum() / den)


def gaussian_blur(img, sigma=1.0):
    """Separable Gaussian. A sparse count image has a ~1 px wide autocorrelation,
    which makes a 3-point parabola an invalid peak model; smoothing first is what
    makes subpixel interpolation well posed."""
    if sigma <= 0:
        return img
    radius = max(1, int(round(3.0 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    pad = radius
    tmp = np.pad(img, ((0, 0), (pad, pad)), mode="edge")
    out = np.empty_like(img)
    for i, w in enumerate(k):
        out += w * tmp[:, i : i + img.shape[1]] if i else w * tmp[:, : img.shape[1]]
    tmp = np.pad(out, ((pad, pad), (0, 0)), mode="edge")
    out2 = np.zeros_like(img)
    for i, w in enumerate(k):
        out2 += w * tmp[i : i + img.shape[0], :]
    return out2


def sample_shifted(right, x0, x1, y0, y1, s, dy=0):
    """Right patch sampled at a fractional disparity s: right_x = left_x - s."""
    H, W = right.shape
    ry0, ry1 = y0 + dy, y1 + dy
    if ry0 < 0 or ry1 > H:
        return None
    base = int(np.floor(s))
    frac = s - base
    a, b = x0 - base, x1 - base
    if a - 1 < 0 or b + 1 > W:
        return None
    p0 = right[ry0:ry1, a:b]
    pm = right[ry0:ry1, a - 1 : b - 1]
    return (1.0 - frac) * p0 + frac * pm


def refine_subpixel(left, right, x0, x1, y0, y1, d_int, dy=0, step=0.05, span=1.0):
    """Direct fractional search around the integer peak, no parabola assumption."""
    patch = left[y0:y1, x0:x1]
    best_s, best_v = d_int, -2.0
    s = d_int - span
    while s <= d_int + span + 1e-9:
        cand = sample_shifted(right, x0, x1, y0, y1, s, dy)
        if cand is not None and cand.shape == patch.shape:
            v = zncc(patch, cand)
            if v > best_v:
                best_v, best_s = v, s
        s += step
    return float(best_s), float(best_v)


def shift_subpixel(img, frac):
    """Shift columns right by a fractional amount via linear interpolation."""
    if abs(frac) < 1e-9:
        return img.copy()
    out = np.empty_like(img)
    out[:, 0] = img[:, 0]
    out[:, 1:] = (1.0 - frac) * img[:, 1:] + frac * img[:, :-1]
    return out


def scan(left, right, x0, x1, y0, y1, shifts, dy=0):
    H, W = right.shape
    patch = left[y0:y1, x0:x1]
    row = np.full(len(shifts), np.nan)
    ry0, ry1 = y0 + dy, y1 + dy
    if ry0 < 0 or ry1 > H:
        return row
    band = right[ry0:ry1]
    for i, s in enumerate(shifts):
        a, b = x0 - s, x1 - s
        if a < 0 or b > W:
            continue
        row[i] = zncc(patch, band[:, a:b])
    return row


def parabola_peak(shifts, row):
    """Integer argmax plus parabolic vertex on its two neighbours."""
    if np.all(np.isnan(row)):
        return None, None
    i = int(np.nanargmax(row))
    peak = float(row[i])
    if i <= 0 or i >= len(row) - 1:
        return float(shifts[i]), peak
    ym1, y0_, yp1 = row[i - 1], row[i], row[i + 1]
    if not np.isfinite(ym1) or not np.isfinite(yp1):
        return float(shifts[i]), peak
    den = ym1 - 2.0 * y0_ + yp1
    if abs(den) < 1e-12:
        return float(shifts[i]), peak
    delta = 0.5 * (ym1 - yp1) / den
    delta = float(np.clip(delta, -1.0, 1.0))
    return float(shifts[i]) + delta, peak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data1/lyq/data/EV_3DOD/DSEC")
    ap.add_argument(
        "--manifest",
        default="/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl",
    )
    ap.add_argument("--split", default="val")
    ap.add_argument("--max-records", type=int, default=140)
    ap.add_argument("--max-boxes", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--run-id", default="run3")
    ap.add_argument("--sigma", type=float, default=1.0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--num-shards", type=int, default=1)
    ap.add_argument("--dump-rows", default=None)
    args = ap.parse_args()
    run_id = args.run_id
    data_root = Path(args.data_root)

    buckets = defaultdict(list)
    for r in iter_manifest(args.manifest):
        if r.get("split") != args.split or r.get("annotation_source") != "manual":
            continue
        if r.get("num_objects"):
            buckets[r["calibration_id"]].append(r)
    rng = np.random.RandomState(args.seed)
    records = []
    per = max(1, args.max_records // max(1, len(buckets)))
    for cid in sorted(buckets):
        pool = buckets[cid]
        for i in sorted(rng.permutation(len(pool))[:per]):
            records.append(pool[i])
    records = records[: args.max_records]
    if args.num_shards > 1:
        records = [r for i, r in enumerate(records) if i % args.num_shards == args.shard]

    store = AnnotationStore(data_root)
    calib_cache = {}
    rows = []
    ctrl_pos, ctrl_pos_n = [], 0

    # #region agent log (meta: rig identity for the depth-accuracy probe)
    dlog(
        "meta",
        "probe_object_depth_accuracy.py:main",
        "depth accuracy probe start",
        {"split": args.split, "records": len(records), "seed": args.seed},
        run_id,
    )
    # #endregion

    for rec in records:
        try:
            frame = store.frame_record(
                rec["annotation_file"], int(rec["annotation_record_index"])
            )
            ck = rec["calibration_id"]
            if ck not in calib_cache:
                calib_cache[ck] = load_stereo_calibration(
                    data_root / rec["calibration_file"],
                    T_left_camera_from_lidar=load_left_camera_from_lidar(frame),
                )
            calib = calib_cache[ck]
            W, H = int(rec["image_width"]), int(rec["image_height"])
            K = calib.K_left.numpy()
            fx, cx, fy, cy = K[0, 0], K[0, 2], K[1, 1], K[1, 2]
            fB = fx * float(calib.baseline_m)

            ls = H5EventStore(
                data_root / rec["left_event_file"],
                data_root / rec["left_rectify_map_file"],
                int(rec["sequence_origin_raw"]),
                (W, H),
            )
            rs = H5EventStore(
                data_root / rec["right_event_file"],
                data_root / rec["right_rectify_map_file"],
                int(rec["sequence_origin_raw"]),
                (W, H),
            )
            t0 = int(rec["history_start_timestamp_raw"])
            t1 = int(rec["query_timestamp_raw"])
            left = gaussian_blur(
                np.log1p(count_image(ls.read_window(t0, t1).events.numpy(), H, W)),
                args.sigma,
            )
            right = gaussian_blur(
                np.log1p(count_image(rs.read_window(t0, t1).events.numpy(), H, W)),
                args.sigma,
            )
            ls.close()
            rs.close()

            target = store.target_from_record(rec, calib)
            boxes = target["boxes_3d"].numpy()
            labels = target["labels"].numpy()
        except Exception as exc:  # noqa: BLE001
            # #region agent log (rig: record load failure)
            dlog(
                "rig",
                "probe_object_depth_accuracy.py:load",
                "record load failed",
                {"sequence_id": rec.get("sequence_id"), "error": str(exc)[:180]},
                run_id,
            )
            # #endregion
            continue

        used = 0
        for bi in np.argsort(boxes[:, 2]) if boxes.shape[0] else []:
            if used >= args.max_boxes:
                break
            X, Y, Z, length, h_box, w_box, yaw = [float(v) for v in boxes[bi]]
            cls = int(labels[bi])
            if Z <= 3.0 or Z > 45.0 or cls not in TOL_Z:
                continue
            u = fx * X / Z + cx
            v = fy * Y / Z + cy
            hw = 0.5 * max(w_box, length) * fx / Z
            hh = 0.5 * h_box * fy / Z
            x0, x1 = int(max(0, u - 0.85 * hw)), int(min(W, u + 0.85 * hw))
            y0, y1 = int(max(0, v - 0.85 * hh)), int(min(H, v + 0.85 * hh))
            if x1 - x0 < 6 or y1 - y0 < 8:
                continue

            d_centre = fB / Z
            # the visible surface sits half a span in front of the centre
            span = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(np.sin(yaw))
            z_surface = max(Z - span, 1.0)
            d_surface = fB / z_surface
            smax = int(min(240, max(50, d_surface * 1.8 + 20)))
            shifts = list(range(-smax, smax + 1))

            row = scan(left, right, x0, x1, y0, y1, shifts)
            if np.all(np.isnan(row)):
                continue
            d_int = shifts[int(np.nanargmax(row))]
            d_hat, peak = refine_subpixel(left, right, x0, x1, y0, y1, d_int)
            if d_hat <= 0.5:
                continue
            z_hat_surface = fB / d_hat
            z_hat_centre = z_hat_surface + span

            row_neg = scan(left, right, x0, x1, y0, y1, shifts, dy=40)
            if np.all(np.isnan(row_neg)):
                z_neg = np.nan
            else:
                d_neg = float(shifts[int(np.nanargmax(row_neg))])
                z_neg = (fB / d_neg + span) if d_neg > 0.5 else np.nan

            tol = TOL_Z[cls]
            rows.append(
                {
                    "cls": CLASS_NAME[cls],
                    "z_gt": Z,
                    "tol": tol,
                    "err_centre_corrected": float(z_hat_centre - Z),
                    "err_no_correction": float(z_hat_surface - Z),
                    "hit_corrected": bool(abs(z_hat_centre - Z) <= tol),
                    "hit_no_correction": bool(abs(z_hat_surface - Z) <= tol),
                    "hit_negctrl": bool(np.isfinite(z_neg) and abs(z_neg - Z) <= tol),
                    "zncc_peak": peak,
                    "patch_px": [x1 - x0, y1 - y0],
                }
            )
            used += 1

            if used == 1 and ctrl_pos_n < 60:
                # CTRL-POS: inject a known fractional shift and try to recover it
                for frac in (0.30, 0.70):
                    synth = np.zeros_like(left)
                    base = int(round(d_surface))
                    if base <= 0 or x0 - base < 0:
                        continue
                    shifted = shift_subpixel(left, frac)
                    synth[:, : W - base] = shifted[:, base:]
                    r2 = scan(left, synth, x0, x1, y0, y1, shifts)
                    if np.all(np.isnan(r2)):
                        continue
                    i2 = shifts[int(np.nanargmax(r2))]
                    d2, _ = refine_subpixel(left, synth, x0, x1, y0, y1, i2)
                    # shift_subpixel moves content right by frac, so synth carries
                    # disparity base - frac, not base + frac
                    ctrl_pos.append(abs(d2 - (base - frac)))
                    ctrl_pos_n += 1

    if args.dump_rows:
        with open(args.dump_rows, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows, "ctrl_pos": ctrl_pos}, fh)
        print("shard %d: %d rows, %d ctrl" % (args.shard, len(rows), len(ctrl_pos)))
        return

    if not rows:
        print("no boxes")
        return

    def summarise(sel):
        if not sel:
            return None
        e = np.array([r["err_centre_corrected"] for r in sel])
        return {
            "n": len(sel),
            "hit_rate_centre_corrected": float(np.mean([r["hit_corrected"] for r in sel])),
            "hit_rate_no_correction": float(
                np.mean([r["hit_no_correction"] for r in sel])
            ),
            "hit_rate_negative_control": float(np.mean([r["hit_negctrl"] for r in sel])),
            "median_abs_err_m": float(np.median(np.abs(e))),
            "median_signed_err_m": float(np.median(e)),
        }

    out = {"overall": summarise(rows), "by_class_depth": {}}
    for cname in ("Pedestrian", "Vehicle"):
        for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 45)):
            sel = [
                r for r in rows if r["cls"] == cname and lo <= r["z_gt"] < hi
            ]
            s = summarise(sel)
            if s:
                out["by_class_depth"]["%s_%d-%dm" % (cname, lo, hi)] = s
    ped_1020 = [r for r in rows if r["cls"] == "Pedestrian" and 10 <= r["z_gt"] < 20]
    out["decision_cell_ped_10_20m"] = summarise(ped_1020)
    out["comparators"] = {
        "dense_map_ped_10_20m_within_tol_P4A": 0.189,
        "physically_available_C79": 0.70,
    }
    out["ctrl_pos_subpixel_median_err_px"] = (
        float(np.median(ctrl_pos)) if ctrl_pos else None
    )
    out["ctrl_pos_n"] = len(ctrl_pos)

    # #region agent log (H-E/H-F: object-conditioned depth accuracy vs strict tolerance)
    dlog(
        "H-E",
        "probe_object_depth_accuracy.py:summary",
        "object-conditioned epipolar depth accuracy against strict tolerance",
        out,
        run_id,
    )
    # #endregion

    print("CTRL-POS subpixel median err: %s px (n=%d)" % (
        out["ctrl_pos_subpixel_median_err_px"], out["ctrl_pos_n"]))
    print("%-24s %5s %8s %8s %8s %9s" % (
        "cell", "n", "hit", "no_corr", "negctrl", "med|err|m"))
    for k in sorted(out["by_class_depth"]):
        s = out["by_class_depth"][k]
        print("%-24s %5d %8.3f %8.3f %8.3f %9.3f" % (
            k, s["n"], s["hit_rate_centre_corrected"], s["hit_rate_no_correction"],
            s["hit_rate_negative_control"], s["median_abs_err_m"]))
    d = out["decision_cell_ped_10_20m"]
    if d:
        print("\nDECISION Ped 10-20m: %.3f (dense map 0.189, physics 0.70), n=%d"
              % (d["hit_rate_centre_corrected"], d["n"]))


if __name__ == "__main__":
    main()

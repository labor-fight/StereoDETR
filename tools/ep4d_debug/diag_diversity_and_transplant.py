#!/usr/bin/env python
"""EP4D root-cause diagnostic (debug session 38825a): why StereoDETR cannot pass EvStereo3D.

Prior receipts already excluded the popular explanations (see
docs/EXPERIMENTS_AND_PITFALLS.md):
  - correspondence is NOT broken: surface-band ZNCC hits 0.631 train / 0.649 val (C76),
    D2's 0.359 was a centre-disparity rig artifact;
  - ranking headroom is real but bounded: oracle rescoring gives Veh 6.26 -> 11.39,
    Ped 0.19 -> 1.87 (C2_BOTTLENECK);
  - the failure is a train->val collapse (F31): Ped class probability 0.921 train
    vs 0.004 val at 15-20 m, while train reach rate is 1.000 at every depth.

The competitor's own repository measures the missing ingredient: enabling
stereo-event copy-paste (SECP) on EvStereo3D moved Pedestrian 3D mod from 5.15 to
10.48 on full val, while our recipe carries exactly one augmentation
(stereo mirror p=0.5) and nothing else.

This probe measures, without training, whether instance transplant is available
and physically valid in OUR pipeline.

Hypotheses (NDJSON hypothesisId):
  H-A  Effective sample size, not record count, is what the model sees.
       Records collapse onto far fewer annotated intervals and far fewer object
       identities. Predicts: unique identities per class << record count.
  H-B  Instance transplant is stereo-physically valid on event data: a patch
       lifted from a donor scene and re-pasted at a new (u,v,z) keeps its
       left/right disparity, so ZNCC on the composite peaks inside the target
       surface band. Predicts band-hit comparable to the in-situ 0.63-0.78 (C76).
  H-C  The pedestrian donor pool is large enough to matter (compare against the
       2084 Pedestrian instances in EvStereo3D's secp_database).
  H-D  Rescaling an instance in depth sparsifies its event density (the 9/12
       failure mode recorded for T2 z x0.75); a linear density compensation
       restores the band hit. Predicts compensated > uncompensated.

Controls, inheriting C71-C74 rig discipline:
  CTRL-POS  identity transplant (donor pasted back at its own pose) must
            reproduce the in-situ reading, else FAIL_RIG.
  CTRL-NEG  wrong-row transplant (paste right patch off by +40 rows) must hit
            far less often, else the band hit is not measuring correspondence.

Read-only: touches no dataset or repo file, appends NDJSON only.
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

assert _es_mod.__file__.startswith(EVENT_TREE), (
    "import resolved to wrong tree: %s" % _es_mod.__file__
)

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
            img,
            (events[:, 1].astype(np.int64), events[:, 0].astype(np.int64)),
            1.0,
        )
    return img


def zncc(a, b):
    a = a - a.mean()
    b = b - b.mean()
    denom = np.sqrt((a * a).sum() * (b * b).sum())
    if denom < 1.0e-9:
        return 0.0
    return float((a * b).sum() / denom)


def scan_row(left_img, right_img, x0, x1, y0, y1, shifts, dy=0):
    """right_x = left_x - s. Returns ZNCC per shift, NaN where out of bounds."""
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


def resize_nn(patch, out_h, out_w):
    if out_h < 1 or out_w < 1:
        return None
    ys = np.clip((np.arange(out_h) * patch.shape[0] / out_h).astype(int), 0, patch.shape[0] - 1)
    xs = np.clip((np.arange(out_w) * patch.shape[1] / out_w).astype(int), 0, patch.shape[1] - 1)
    return patch[np.ix_(ys, xs)]


def paste(canvas, patch, x0, y0):
    """Additive paste with clipping; events add, they do not alpha-blend."""
    h, w = patch.shape
    H, W = canvas.shape
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(W, x0 + w), min(H, y0 + h)
    if sx1 <= sx0 or sy1 <= sy0:
        return False
    canvas[sy0:sy1, sx0:sx1] += patch[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
    return True


def survey_identities(manifest_path, run_id):
    """H-A / H-C: effective sample size and donor pool, straight from the manifest."""
    stats = {}
    for split in ("train", "val"):
        records = 0
        intervals = set()
        base_seqs = set()
        ids_by_class = defaultdict(set)
        boxes_by_class = defaultdict(int)
        for r in iter_manifest(manifest_path):
            if r.get("split") != split:
                continue
            records += 1
            intervals.add((r["manual_annotation_file"], r["manual_annotation_record_index"]))
            base_seqs.add(r["base_sequence_id"])
            hist = r.get("class_histogram") or {}
            for cname, cnt in hist.items():
                boxes_by_class[cname] += int(cnt)
            # object identity is only unique within a sequence
            for oid in r.get("source_box_obj_ids") or []:
                ids_by_class[r["sequence_id"]].add(oid)
        identities = sum(len(v) for v in ids_by_class.values())
        stats[split] = {
            "records": records,
            "annotated_intervals": len(intervals),
            "records_per_interval": records / max(1, len(intervals)),
            "base_sequences": len(base_seqs),
            "distinct_object_tracks": identities,
            "boxes_by_class": dict(boxes_by_class),
        }
    # #region agent log (H-A/H-C: effective sample size and donor pool)
    dlog(
        "H-A",
        "diag_diversity_and_transplant.py:survey_identities",
        "effective sample size vs nominal record count",
        stats,
        run_id,
    )
    # #endregion
    return stats


def collect_boxes(manifest_path, data_root, split, max_records, seed):
    buckets = defaultdict(list)
    for r in iter_manifest(manifest_path):
        if r.get("split") != split or r.get("annotation_source") != "manual":
            continue
        if not r.get("num_objects"):
            continue
        buckets[r["calibration_id"]].append(r)
    rng = np.random.RandomState(seed)
    picked = []
    per = max(1, max_records // max(1, len(buckets)))
    for cid in sorted(buckets):
        pool = buckets[cid]
        for i in sorted(rng.permutation(len(pool))[:per]):
            picked.append(pool[i])
    return picked[:max_records]


def load_scene(record, data_root, store, calib_cache):
    frame = store.frame_record(
        record["annotation_file"], int(record["annotation_record_index"])
    )
    ckey = record["calibration_id"]
    if ckey not in calib_cache:
        calib_cache[ckey] = load_stereo_calibration(
            data_root / record["calibration_file"],
            T_left_camera_from_lidar=load_left_camera_from_lidar(frame),
        )
    calib = calib_cache[ckey]
    w, h = int(record["image_width"]), int(record["image_height"])
    ls = H5EventStore(
        data_root / record["left_event_file"],
        data_root / record["left_rectify_map_file"],
        int(record["sequence_origin_raw"]),
        (w, h),
    )
    rs = H5EventStore(
        data_root / record["right_event_file"],
        data_root / record["right_rectify_map_file"],
        int(record["sequence_origin_raw"]),
        (w, h),
    )
    t0 = int(record["history_start_timestamp_raw"])
    t1 = int(record["query_timestamp_raw"])
    left = count_image(ls.read_window(t0, t1).events.numpy(), h, w)
    right = count_image(rs.read_window(t0, t1).events.numpy(), h, w)
    ls.close()
    rs.close()
    target = store.target_from_record(record, calib)
    return calib, left, right, target, w, h


def project(calib, X, Y, Z):
    K = calib.K_left.numpy()
    return K[0, 0] * X / Z + K[0, 2], K[1, 1] * Y / Z + K[1, 2]


def box_pixel_extent(calib, X, Y, Z, length, h_box, w_box, yaw):
    K = calib.K_left.numpy()
    fx, fy = K[0, 0], K[1, 1]
    u, v = project(calib, X, Y, Z)
    half_w = 0.5 * max(w_box, length) * fx / Z
    half_h = 0.5 * h_box * fy / Z
    return u, v, half_w, half_h


def surface_band(calib, Z, length, w_box, yaw):
    K = calib.K_left.numpy()
    fB = K[0, 0] * float(calib.baseline_m)
    span = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(np.sin(yaw))
    return fB / (Z + span), fB / max(Z - span, 1.0)


def run_transplants(args, run_id):
    data_root = Path(args.data_root)
    store = AnnotationStore(data_root)
    calib_cache = {}

    records = collect_boxes(
        args.manifest, data_root, args.split, args.max_records, args.seed
    )
    rng = np.random.RandomState(args.seed)

    # Cache a handful of scenes so donors and targets come from different scenes.
    scenes = []
    for rec in records[: args.max_scenes]:
        try:
            scenes.append((rec,) + load_scene(rec, data_root, store, calib_cache))
        except Exception as exc:  # noqa: BLE001
            # #region agent log (rig: scene load failure)
            dlog(
                "rig",
                "diag_diversity_and_transplant.py:load_scene",
                "scene load failed",
                {"sequence_id": rec.get("sequence_id"), "error": str(exc)[:200]},
                run_id,
            )
            # #endregion
    if len(scenes) < 2:
        return None

    # Build donor list: pedestrians (and vehicles) with usable pixel extent.
    donors = []
    for si, (rec, calib, left, right, target, w, h) in enumerate(scenes):
        boxes = target["boxes_3d"].numpy()
        labels = target["labels"].numpy()
        K = calib.K_left.numpy()
        fB = K[0, 0] * float(calib.baseline_m)
        for bi in range(boxes.shape[0]):
            X, Y, Z, length, h_box, w_box, yaw = [float(v) for v in boxes[bi]]
            if Z <= 3.0 or Z > 40.0:
                continue
            u, v, hw, hh = box_pixel_extent(calib, X, Y, Z, length, h_box, w_box, yaw)
            if hw < 4 or hh < 6 or hw > 100 or hh > 100:
                continue
            x0, x1 = int(u - hw), int(u + hw)
            y0, y1 = int(v - hh), int(v + hh)
            d = fB / Z
            if x0 < 0 or y0 < 0 or x1 > w or y1 > h:
                continue
            if x0 - int(round(d)) < 0:
                continue
            donors.append(
                {
                    "scene": si,
                    "cls": int(labels[bi]),
                    "Z": Z,
                    "yaw": yaw,
                    "dims": (length, h_box, w_box),
                    "uv": (u, v),
                    "bbox": (x0, y0, x1, y1),
                    "disp": d,
                    "fB": fB,
                }
            )

    ped_pool = [d for d in donors if d["cls"] == 1]
    veh_pool = [d for d in donors if d["cls"] == 0]
    # #region agent log (H-C: donor pool actually extractable from sampled scenes)
    dlog(
        "H-C",
        "diag_diversity_and_transplant.py:donors",
        "extractable donor instances in sampled scenes",
        {
            "scenes": len(scenes),
            "donors_total": len(donors),
            "pedestrian": len(ped_pool),
            "vehicle": len(veh_pool),
            "ped_depth_median": float(np.median([d["Z"] for d in ped_pool]))
            if ped_pool
            else None,
        },
        run_id,
    )
    # #endregion

    arms = defaultdict(lambda: {"hit": 0, "n": 0, "err": []})
    per_case = []

    for donor in donors:
        if len(per_case) >= args.max_cases:
            break
        d_rec, d_calib, d_left, d_right, d_tgt, dw, dh = scenes[donor["scene"]]
        x0, y0, x1, y1 = donor["bbox"]
        dshift = int(round(donor["disp"]))
        patch_l = d_left[y0:y1, x0:x1].copy()
        patch_r = d_right[y0:y1, x0 - dshift : x1 - dshift].copy()
        if patch_l.size == 0 or patch_r.size == 0:
            continue
        if patch_l.sum() < args.min_events:
            continue

        # target scene: a different scene, same calibration family
        cand = [i for i in range(len(scenes)) if i != donor["scene"]]
        if not cand:
            continue
        ti = int(cand[rng.randint(len(cand))])
        t_rec, t_calib, t_left, t_right, t_tgt, tw, th = scenes[ti]
        t_fB = t_calib.K_left.numpy()[0, 0] * float(t_calib.baseline_m)

        for arm_name, z_scale, compensate, dy_err in (
            ("T0_identity", 1.0, False, 0),
            ("T1_reposition_additive", 1.0, False, 0),
            ("T1c_reposition_cleared", 1.0, False, 0),
            ("T1f_reposition_freespace", 1.0, False, 0),
            ("T2_farther_x1.5_cleared", 1.5, False, 0),
            ("T3_nearer_x0.75_cleared", 0.75, False, 0),
            ("T3c_nearer_x0.75_compensated", 0.75, True, 0),
            ("CTRL_NEG_wrongrow", 1.0, False, 40),
        ):
            Zt = donor["Z"] * z_scale
            s = donor["Z"] / Zt  # pixel magnification
            oh = int(round((y1 - y0) * s))
            ow = int(round((x1 - x0) * s))
            pl = resize_nn(patch_l, oh, ow)
            pr = resize_nn(patch_r, oh, ow)
            if pl is None or pr is None or oh < 6 or ow < 4:
                continue
            if compensate and s > 1.0:
                # events live on contours: total count grows ~linearly with s,
                # while area grows as s^2, so per-pixel density falls as 1/s.
                pl = pl * s
                pr = pr * s

            if arm_name == "T0_identity":
                ut, vt = donor["uv"]
                canvas_l = d_left.copy()
                canvas_r = d_right.copy()
                cal = d_calib
                fB = donor["fB"]
                W, H = dw, dh
            else:
                canvas_l = t_left.copy()
                canvas_r = t_right.copy()
                cal = t_calib
                fB = t_fB
                W, H = tw, th
                if arm_name == "T1f_reposition_freespace":
                    # pick the quietest of several candidate sites: a transplant
                    # should land where the scene has little competing evidence
                    best, best_site = None, None
                    for _ in range(12):
                        cu = float(rng.uniform(0.2 * tw, 0.8 * tw))
                        cv = float(rng.uniform(0.35 * th, 0.75 * th))
                        a0, b0 = int(cu - ow / 2.0), int(cv - oh / 2.0)
                        if a0 < 0 or b0 < 0 or a0 + ow > W or b0 + oh > H:
                            continue
                        dens = float(canvas_l[b0 : b0 + oh, a0 : a0 + ow].mean())
                        if best is None or dens < best:
                            best, best_site = dens, (cu, cv)
                    if best_site is None:
                        continue
                    ut, vt = best_site
                else:
                    ut = float(rng.uniform(0.2 * tw, 0.8 * tw))
                    vt = float(rng.uniform(0.35 * th, 0.75 * th))

            dt = fB / Zt
            px0 = int(round(ut - ow / 2.0))
            py0 = int(round(vt - oh / 2.0))
            rx0 = int(round(px0 - dt))
            if px0 < 0 or py0 < 0 or px0 + ow > W or py0 + oh > H or rx0 < 0:
                continue
            bg_density = float(canvas_l[py0 : py0 + oh, px0 : px0 + ow].mean())
            if arm_name not in ("T0_identity", "T1_reposition_additive"):
                # an opaque object occludes what is behind it in BOTH views
                canvas_l[py0 : py0 + oh, px0 : px0 + ow] = 0.0
                canvas_r[py0 + dy_err : py0 + dy_err + oh, rx0 : rx0 + ow] = 0.0
            ok_l = paste(canvas_l, pl, px0, py0)
            ok_r = paste(canvas_r, pr, rx0, py0 + dy_err)
            if not (ok_l and ok_r):
                continue

            length, h_box, w_box = donor["dims"]
            d_far, d_near = surface_band(cal, Zt, length, w_box, donor["yaw"])
            s_max = int(min(240, max(60, abs(dt) * 2 + 24)))
            shifts = list(range(-s_max, s_max + 1))
            li = np.log1p(canvas_l)
            ri = np.log1p(canvas_r)
            row = scan_row(li, ri, px0, px0 + ow, py0, py0 + oh, shifts)
            if np.all(np.isnan(row)):
                continue
            d_meas = float(shifts[int(np.nanargmax(row))])
            hit = bool(d_far - 2.0 <= d_meas <= d_near + 2.0)
            arms[arm_name]["hit"] += int(hit)
            arms[arm_name]["n"] += 1
            arms[arm_name]["err"].append(float(d_meas - dt))
            per_case.append(
                {
                    "arm": arm_name,
                    "cls": CLASS_NAME.get(donor["cls"], "?"),
                    "z_donor": donor["Z"],
                    "z_target": Zt,
                    "disp_target": dt,
                    "disp_measured": d_meas,
                    "band": [d_far, d_near],
                    "hit": hit,
                    "patch_px": [ow, oh],
                    "events_in_patch": float(pl.sum()),
                    "bg_density": bg_density,
                }
            )

    summary = {}
    for arm, v in arms.items():
        if not v["n"]:
            continue
        e = np.array(v["err"])
        summary[arm] = {
            "n": v["n"],
            "band_hit_rate": v["hit"] / v["n"],
            "median_abs_disp_err_px": float(np.median(np.abs(e))),
        }
    # per-class breakdown on the production arm (cleared reposition)
    prod = "T1c_reposition_cleared"
    ped_rows = [c for c in per_case if c["arm"] == prod and c["cls"] == "Pedestrian"]
    veh_rows = [c for c in per_case if c["arm"] == prod and c["cls"] == "Vehicle"]

    # #region agent log (H-B/H-D: transplant validity per arm, with pos/neg controls)
    dlog(
        "H-B",
        "diag_diversity_and_transplant.py:transplant",
        "instance transplant stereo validity by arm",
        {
            "arms": summary,
            "cases": len(per_case),
            "reposition_pedestrian": {
                "n": len(ped_rows),
                "band_hit_rate": float(np.mean([r["hit"] for r in ped_rows]))
                if ped_rows
                else None,
            },
            "reposition_vehicle": {
                "n": len(veh_rows),
                "band_hit_rate": float(np.mean([r["hit"] for r in veh_rows]))
                if veh_rows
                else None,
            },
            "reference_in_situ_C76": {"train": 0.631, "val": 0.649, "ped_val": 0.778},
        },
        run_id,
    )
    # #endregion
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default="/data1/lyq/data/EV_3DOD/DSEC")
    ap.add_argument(
        "--manifest",
        default="/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl",
    )
    ap.add_argument("--split", default="train")
    ap.add_argument("--max-records", type=int, default=60)
    ap.add_argument("--max-scenes", type=int, default=24)
    ap.add_argument("--max-cases", type=int, default=600)
    ap.add_argument("--min-events", type=int, default=30)
    ap.add_argument("--seed", type=int, default=20260827)
    ap.add_argument("--run-id", default="run1")
    ap.add_argument("--skip-survey", action="store_true")
    args = ap.parse_args()

    # #region agent log (meta: rig identity)
    dlog(
        "meta",
        "diag_diversity_and_transplant.py:main",
        "diagnostic start",
        {
            "split": args.split,
            "seed": args.seed,
            "event_tree": EVENT_TREE,
            "event_store_file": _es_mod.__file__,
        },
        args.run_id,
    )
    # #endregion

    if not args.skip_survey:
        stats = survey_identities(args.manifest, args.run_id)
        for split, s in stats.items():
            print(
                "%-5s records=%d intervals=%d (%.1f per interval) base_seq=%d tracks=%d %s"
                % (
                    split,
                    s["records"],
                    s["annotated_intervals"],
                    s["records_per_interval"],
                    s["base_sequences"],
                    s["distinct_object_tracks"],
                    s["boxes_by_class"],
                )
            )

    summary = run_transplants(args, args.run_id)
    if summary:
        for arm in sorted(summary):
            v = summary[arm]
            print(
                "%-30s n=%3d band_hit=%.3f med|err|=%.2f px"
                % (arm, v["n"], v["band_hit_rate"], v["median_abs_disp_err_px"])
            )
    else:
        print("transplant produced no cases")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Q2: measurement-layer temporal accumulation probe (zero GPU, CPU only).

Prereg: docs/proposals/Q2_TEMPORAL_ACCUMULATION_PROBE_PREREG.md (+ amendment
001). Population: train split, manual records, GT pedestrians 15-30 m, C79
caliber (patch construction, log1p count images, ZNCC + parabola subpixel,
split-half repeatability). All gates are within-instrument ratios frozen in
the prereg BEFORE this run:

  G-mechanism   median_C / median_A (20-30 m)  <= 0.65  -> alignment gain real
  G-close       median_C / median_A (20-30 m)  >  0.85  -> channel closed
  G-extend      median_Cprime (20-25 m)        <= 0.18 px -> OERD ~25 m arm
  G-null        median_N / median_B (20-30 m)  <= 0.95  -> INVALID (artifact)
  B-identity    median_B / median_A in [0.9, 1.1] expected (report; far off
                -> TOOL_SUSPECT)
  A-anchor      median_A (20-30 m) in [0.35, 0.85] px (C79 anchor caliber)

Arms (all split-half repeatability |d(first half) - d(second half)| in px):
  A   full-window halves (25 ms count images), C79 protocol
  B   10 x 5 ms slices, UNALIGNED average of ZNCC rows, halves = slices 0-4/5-9
  C   as B but each slice's patch re-anchored by left-patch FFT registration
  C'  as C on a 145 ms causal window (29 slices, halves 15/14)
  N   as C but each object uses the PREVIOUS object's alignment sequence
  D   GT-trajectory alignment: NOT_RUN in v1 (diagnostic-only per prereg)

Instrument self-checks before any data row (C32/C73 discipline):
  R1  registration sign check on a synthetic roll (must recover (du, dv))
  R2  scan_row/subpixel fractional-shift control reused from the C79 tool's
      semantics is NOT re-run here (C79 already validated it); instead A must
      land in the anchor window, which is this probe's positive control.
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.signal import fftconvolve

sys.path.insert(0, "/data1/lyq/code/StereoDETR/tools/r1_audit")
import probe_subpixel_disparity as psd  # noqa: E402  (frozen C79 tool, read-only reuse)

DATA_ROOT = Path("/data1/lyq/data/EV_3DOD/DSEC")
MANIFEST = "/data1/lyq/code/StereoDETR/lib/datasets/dsec3dod/manifest/records.jsonl"
RECEIPT = "/data1/lyq/code/StereoDETR/reports/ep4d_debug/Q2_TEMPORAL_ACCUMULATION.json"
MAX_RECORDS = 2400
MAX_PED_PER_RECORD = 4
TARGET_PEDS = 300
SEED = 20260831
K_SLICES = 10
SLICE_US = 5000
EXT_US = 145000
REG_SEARCH = 12
REG_MIN_EVENTS = 12
PAD = 16

# #region agent log
DEBUG_LOG = "/data1/lyq/code/StereoDETR/.cursor/debug-142ed9.log"


def log(message, data, hyp="Q2"):
    entry = {"sessionId": "142ed9", "runId": "q2-temporal", "hypothesisId": hyp,
             "location": "tools/ep4d_debug/q2_temporal_accumulation_probe.py",
             "message": message, "data": data, "timestamp": int(time.time() * 1000)}
    with open(DEBUG_LOG, "a") as handle:
        handle.write(json.dumps(entry, default=float) + "\n")
# #endregion


def slice_images(events, height, width, t0_s, t1_s, n_slices):
    """One bincount pass -> (n_slices, H, W) raw count images."""
    out = np.zeros((n_slices, height, width), dtype=np.float64)
    if events.shape[0] == 0:
        return out
    t = events[:, 2]
    keep = (t >= t0_s) & (t < t1_s)
    ev = events[keep]
    if ev.shape[0] == 0:
        return out
    sl = np.minimum(((ev[:, 2] - t0_s) / ((t1_s - t0_s) / n_slices)).astype(np.int64),
                    n_slices - 1)
    xs = ev[:, 0].astype(np.int64)
    ys = ev[:, 1].astype(np.int64)
    flat = sl * (height * width) + ys * width + xs
    counts = np.bincount(flat, minlength=n_slices * height * width)
    return counts.reshape(n_slices, height, width).astype(np.float64)


def register(anchor_patch, slice_patch):
    """Displacement (du, dv): read the slice at (x0+du, y0+dv) to match anchor.

    Sign convention verified by the R1 self-check in main().
    """
    a = anchor_patch - anchor_patch.mean()
    s = slice_patch - slice_patch.mean()
    if float(np.abs(s).sum()) < 1e-9 or float(np.abs(a).sum()) < 1e-9:
        return 0, 0
    corr = fftconvolve(a, s[::-1, ::-1], mode="same")
    ch, cw = corr.shape[0] // 2, corr.shape[1] // 2
    y0 = max(0, ch - REG_SEARCH)
    x0 = max(0, cw - REG_SEARCH)
    win = corr[y0:ch + REG_SEARCH + 1, x0:cw + REG_SEARCH + 1]
    ij = np.unravel_index(np.argmax(win), win.shape)
    # correlation peak gives the displacement of the anchor relative to the
    # slice; we want where to READ the slice, i.e. the negation (R1-verified).
    dv = ch - (ij[0] + y0)
    du = cw - (ij[1] + x0)
    return int(du), int(dv)


def crop(img, x0, x1, y0, y1):
    h, w = img.shape
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or x1 <= x0 or y1 <= y0:
        return None
    return img[y0:y1, x0:x1]


def arm_estimate(rows_list, shifts):
    """Average a list of ZNCC rows (nan-aware) and take the subpixel peak."""
    if not rows_list:
        return None
    stack = np.stack(rows_list, axis=0)
    if np.all(np.isnan(stack)):
        return None
    mean_row = np.nanmean(stack, axis=0)
    peak = psd.subpixel_peak(shifts, mean_row)
    return None if peak is None else float(peak[0])


def slice_rows(log_imgs_l, log_imgs_r, indices, coords, offsets, nb_shifts):
    """Per-slice ZNCC rows with per-slice (du, dv) patch offsets."""
    x0, x1, y0, y1 = coords
    rows = []
    for k in indices:
        du, dv = offsets[k]
        patch_l = crop(log_imgs_l[k], x0 + du, x1 + du, y0 + dv, y1 + dv)
        if patch_l is None:
            continue
        row = psd.scan_row(log_imgs_l[k], log_imgs_r[k],
                           x0 + du, x1 + du, y0 + dv, y1 + dv, nb_shifts, 0)
        rows.append(row)
    return rows


def split_half_repeat(log_l, log_r, offsets, coords, nb_shifts, n_slices):
    half = n_slices // 2
    d1 = arm_estimate(slice_rows(log_l, log_r, range(half), coords, offsets, nb_shifts),
                      nb_shifts)
    d2 = arm_estimate(slice_rows(log_l, log_r, range(half, n_slices), coords, offsets,
                                 nb_shifts), nb_shifts)
    if d1 is None or d2 is None:
        return None
    return abs(d1 - d2)


def main():
    t_begin = time.time()
    # R1 instrument self-check: synthetic roll must be recovered exactly.
    rng = np.random.RandomState(0)
    base = rng.rand(64, 96)
    rolled = np.roll(np.roll(base, 3, axis=0), -5, axis=1)
    du, dv = register(base, rolled)
    sign_ok = (du, dv) == (-5, 3)
    log("R1 registration self-check", {"du": du, "dv": dv, "pass": sign_ok}, "R1")
    if not sign_ok:
        raise SystemExit("R1 FAIL: registration sign convention broken: %s" % [du, dv])

    records = psd.select_records(MANIFEST, "train", MAX_RECORDS, SEED)
    store = psd.AnnotationStore(DATA_ROOT)
    calib_cache = {}
    rows_out = []
    prev_offsets = None
    peds = 0

    for rec_i, record in enumerate(records):
        if peds >= TARGET_PEDS:
            break
        frame = store.frame_record(record["annotation_file"],
                                   int(record["annotation_record_index"]))
        ck = record["calibration_id"]
        if ck not in calib_cache:
            calib_cache[ck] = psd.load_stereo_calibration(
                DATA_ROOT / record["calibration_file"],
                T_left_camera_from_lidar=psd.load_left_camera_from_lidar(frame))
        calib = calib_cache[ck]
        K_l = calib.K_left.numpy()
        K_r = calib.K_right.numpy()
        fx_l, cx_l, fy_l, cy_l = K_l[0, 0], K_l[0, 2], K_l[1, 1], K_l[1, 2]
        cx_r = K_r[0, 2]
        fB = fx_l * float(calib.baseline_m)
        width = int(record["image_width"])
        height = int(record["image_height"])
        origin = int(record["sequence_origin_raw"])
        t_start = int(record["history_start_timestamp_raw"])
        t_end = int(record["query_timestamp_raw"])
        t0_s = (t_start - origin) * 1e-6
        t1_s = (t_end - origin) * 1e-6
        ext0_s = (t_end - EXT_US - origin) * 1e-6

        left_store = psd.H5EventStore(DATA_ROOT / record["left_event_file"],
                                      DATA_ROOT / record["left_rectify_map_file"],
                                      origin, (width, height))
        right_store = psd.H5EventStore(DATA_ROOT / record["right_event_file"],
                                       DATA_ROOT / record["right_rectify_map_file"],
                                       origin, (width, height))
        try:
            left_ext = left_store.read_window(t_end - EXT_US, t_end).events.numpy()
            right_ext = right_store.read_window(t_end - EXT_US, t_end).events.numpy()
            ext_ok = True
        except Exception:
            left_ext = left_store.read_window(t_start, t_end).events.numpy()
            right_ext = right_store.read_window(t_start, t_end).events.numpy()
            ext_ok = False

        in50_l = left_ext[left_ext[:, 2] >= t0_s]
        in50_r = right_ext[right_ext[:, 2] >= t0_s]
        t_mid_s = 0.5 * (t0_s + t1_s)

        left_full = psd.count_image(in50_l, height, width)
        right_full = psd.count_image(in50_r, height, width)
        left_a = psd.count_image(in50_l[in50_l[:, 2] < t_mid_s], height, width)
        right_a = psd.count_image(in50_r[in50_r[:, 2] < t_mid_s], height, width)
        left_b = psd.count_image(in50_l[in50_l[:, 2] >= t_mid_s], height, width)
        right_b = psd.count_image(in50_r[in50_r[:, 2] >= t_mid_s], height, width)

        raw_l = slice_images(in50_l, height, width, t0_s, t1_s, K_SLICES)
        raw_r = slice_images(in50_r, height, width, t0_s, t1_s, K_SLICES)
        log_l = np.log1p(raw_l)
        log_r = np.log1p(raw_r)
        n_ext = int(round(EXT_US / SLICE_US))
        if ext_ok:
            raw_le = slice_images(left_ext, height, width, ext0_s, t1_s, n_ext)
            raw_re = slice_images(right_ext, height, width, ext0_s, t1_s, n_ext)
            log_le = np.log1p(raw_le)
            log_re = np.log1p(raw_re)

        target = store.target_from_record(record, calib)
        boxes = target["boxes_3d"].numpy()
        labels = target["labels"].numpy()
        order = np.argsort(boxes[:, 2]) if boxes.shape[0] else []
        used = 0
        for box_i in order:
            if used >= MAX_PED_PER_RECORD or peds >= TARGET_PEDS:
                break
            if int(labels[box_i]) != 1:
                continue
            X, Y, Z, length, h_box, w_box, yaw = [float(v) for v in boxes[box_i]]
            if Z < 15.0 or Z > 30.0:
                continue
            z_half = 0.5 * length * abs(np.cos(yaw)) + 0.5 * w_box * abs(np.sin(yaw))
            u = fx_l * X / Z + cx_l
            v = fy_l * Y / Z + cy_l
            half_w = 0.5 * max(w_box, length) * fx_l / Z
            half_h = 0.5 * h_box * fy_l / Z
            x0 = int(max(0, np.floor(u - 0.85 * half_w)))
            x1 = int(min(width, np.ceil(u + 0.85 * half_w)))
            y0 = int(max(0, np.floor(v - 0.85 * half_h)))
            y1 = int(min(height, np.ceil(v + 0.85 * half_h)))
            if x1 - x0 < 8 or y1 - y0 < 8:
                continue
            d_exp = fB / Z + (cx_l - cx_r)
            s_max = int(min(240, max(60, abs(d_exp) * 2 + 24)))
            shifts = list(range(-s_max, s_max + 1))
            row_full = psd.scan_row(left_full, right_full, x0, x1, y0, y1, shifts, 0)
            pk_full = psd.subpixel_peak(shifts, row_full)
            if pk_full is None:
                continue
            d_full = pk_full[0]
            sh_arr = np.array(shifts)
            nb_shifts = [int(s) for s in sh_arr[np.abs(sh_arr - d_full) <= 10]]
            if len(nb_shifts) < 5:
                continue

            # ARM A (C79 protocol)
            pk_a = psd.subpixel_peak(nb_shifts, psd.scan_row(
                left_a, right_a, x0, x1, y0, y1, nb_shifts, 0))
            pk_b = psd.subpixel_peak(nb_shifts, psd.scan_row(
                left_b, right_b, x0, x1, y0, y1, nb_shifts, 0))
            a_rep = abs(pk_a[0] - pk_b[0]) if (pk_a and pk_b) else None

            # registration against the full-window anchor patch
            ax0, ax1 = max(0, x0 - PAD), min(width, x1 + PAD)
            ay0, ay1 = max(0, y0 - PAD), min(height, y1 + PAD)
            anchor = left_full[ay0:ay1, ax0:ax1]
            offsets = []
            fallbacks = 0
            for k in range(K_SLICES):
                region_events = float(raw_l[k, ay0:ay1, ax0:ax1].sum())
                if region_events < REG_MIN_EVENTS:
                    offsets.append((0, 0))
                    fallbacks += 1
                    continue
                offsets.append(register(anchor, log_l[k, ay0:ay1, ax0:ax1]))
            zero_offsets = [(0, 0)] * K_SLICES
            coords = (x0, x1, y0, y1)

            b_rep = split_half_repeat(log_l, log_r, zero_offsets, coords,
                                      nb_shifts, K_SLICES)
            c_rep = split_half_repeat(log_l, log_r, offsets, coords,
                                      nb_shifts, K_SLICES)
            n_rep = None
            if prev_offsets is not None and len(prev_offsets) == K_SLICES:
                n_rep = split_half_repeat(log_l, log_r, prev_offsets, coords,
                                          nb_shifts, K_SLICES)
            cp_rep = None
            if ext_ok:
                offs_e = []
                for k in range(n_ext):
                    region_events = float(raw_le[k, ay0:ay1, ax0:ax1].sum())
                    if region_events < REG_MIN_EVENTS:
                        offs_e.append((0, 0))
                        continue
                    offs_e.append(register(anchor, log_le[k, ay0:ay1, ax0:ax1]))
                cp_rep = split_half_repeat(log_le, log_re, offs_e, coords,
                                           nb_shifts, n_ext)

            tol_z = length * (1.0 - 0.5) / (1.0 + 0.5)
            tol_d = fB * tol_z / (Z * Z)
            row_out = {
                "z_m": Z, "tol_d_px": tol_d, "d_full": d_full,
                "a_rep": a_rep, "b_rep": b_rep, "c_rep": c_rep,
                "n_rep": n_rep, "cp_rep": cp_rep,
                "reg_fallbacks": fallbacks, "ext_ok": ext_ok,
                "patch_wh": [x1 - x0, y1 - y0],
                "sequence_id": record["sequence_id"],
            }
            rows_out.append(row_out)
            prev_offsets = list(offsets)
            used += 1
            peds += 1
        if rec_i % 20 == 0:
            log("progress", {"records_done": rec_i + 1, "peds": peds,
                             "elapsed_s": round(time.time() - t_begin, 1)})

    def med(key, lo, hi):
        vals = [r[key] for r in rows_out
                if r[key] is not None and lo <= r["z_m"] < hi]
        return (float(np.median(vals)), len(vals)) if vals else (None, 0)

    bins = {"15-20": (15, 20), "20-25": (20, 25), "25-30": (25, 30), "20-30": (20, 30)}
    summary = {}
    for name, (lo, hi) in bins.items():
        summary[name] = {k: med(k, lo, hi) for k in
                         ("a_rep", "b_rep", "c_rep", "n_rep", "cp_rep")}

    a20 = summary["20-30"]["a_rep"][0]
    b20 = summary["20-30"]["b_rep"][0]
    c20 = summary["20-30"]["c_rep"][0]
    n20 = summary["20-30"]["n_rep"][0]
    cp2025 = summary["20-25"]["cp_rep"][0]
    gates = {}
    gates["A_anchor_in_window"] = (a20 is not None and 0.35 <= a20 <= 0.85)
    gates["B_identity_ratio"] = (b20 / a20) if (a20 and b20) else None
    gates["C_over_A"] = (c20 / a20) if (a20 and c20) else None
    gates["N_over_B"] = (n20 / b20) if (b20 and n20) else None
    gates["Cprime_20_25_px"] = cp2025
    if gates["N_over_B"] is not None and gates["N_over_B"] <= 0.95:
        verdict = "INVALID_ALIGNMENT_GAIN"
    elif gates["C_over_A"] is None:
        verdict = "INCONCLUSIVE_COVERAGE"
    elif gates["C_over_A"] <= 0.65:
        verdict = "MECHANISM_CONFIRMED"
    elif gates["C_over_A"] > 0.85:
        verdict = "CHANNEL_CLOSED"
    else:
        verdict = "INCONCLUSIVE_BAND"
    extend = bool(cp2025 is not None and cp2025 <= 0.18
                  and verdict == "MECHANISM_CONFIRMED")

    receipt = {
        "probe": "q2_temporal_accumulation", "date": "2026-08-31",
        "session": "142ed9", "population": "train GT pedestrians 15-30m "
        "(prereg amendment 001)", "n_objects": len(rows_out),
        "records_used": rec_i + 1, "self_check_R1": sign_ok,
        "summary_median_px": summary, "gates": gates,
        "verdict": verdict, "oerd_extension_authorized": extend,
        "arm_D": "NOT_RUN (diagnostic-only, v1 scope)",
        "elapsed_s": round(time.time() - t_begin, 1),
    }
    Path(RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    with open(RECEIPT, "w") as handle:
        json.dump(receipt, handle, indent=2, default=float)
    log("VERDICT " + verdict, {"gates": gates, "n": len(rows_out),
                               "extend": extend}, "Q2-VERDICT")
    print(json.dumps(receipt, indent=2, default=float))


if __name__ == "__main__":
    main()

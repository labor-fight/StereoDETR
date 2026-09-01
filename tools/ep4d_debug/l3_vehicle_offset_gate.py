#!/usr/bin/env python3
"""L3 CPU pre-launch gate: is a CONDITIONAL surface-to-center offset head able
to turn the vehicle epipolar measurement into a usable center depth?

Context: Z5b killed vehicle OERD with a CONSTANT offset (+1.5 m best, brittle
to +-0.5 m). The QC-EER design answers with a conditioned offset
f(class, dims, z, orientation). Framework group L3 froze this gate: fit the
offset offline, apply out-of-fold; the corrected vehicle depth residual median
must beat the model baseline by >=10%, else the vehicle-side offset head does
NOT launch (no GPU arm).

PRE-REGISTERED PROTOCOL (frozen before reading any number):
  Table: q12e012_full.npz (fresh base, 24,572 rows).
  Population: class_id==0, gt_class_match==1, iou3d_gt>=0.10, finite
              d_peak>1.5 px, 2<z_gt<=45.
  Baseline A: median |z_pred - z_gt|.
  Raw meas B: median |fB/d_peak - z_gt|  (Z5b expectation: ~1 m worse, biased).
  Constant C0: fold-fit constant offset (Z5b semantics, cross-fold).
  Conditional C: two-fold (query_index % 2) ridge fit of
              offset := z_gt - fB/d_peak on
              [l, w, h, z_meas, |sin a|, |cos a|, l*|cos a|, 1],
              a = rotation_y - arctan((u_center - 336.834)/583.308);
              applied out-of-fold; median |z_meas + offset_hat - z_gt|.
  GATE (launch): C <= 0.90 * A  -> vehicle offset head arm may launch.
  KILL:          C >  0.90 * A  -> vehicle-side offset head closed (no arm);
                 pedestrian-side QC-EER unaffected.
  Report-only: coverage (resolvable-peak fraction), R^2 of the offset fit,
              depth-binned medians. DIAGNOSTIC_FINDING; no AP claim.
"""
import json
import time
from pathlib import Path

import numpy as np

TABLE = "/data1/lyq/code/.epitube4d/reports/ep4d_evidence/rescore/q12e012_full.npz"
RECEIPT = "/data1/lyq/code/StereoDETR/reports/ep4d_debug/L3_VEHICLE_OFFSET_GATE.json"
CX, FX = 336.834, 583.308

# #region agent log
DEBUG_LOG = "/data1/lyq/code/StereoDETR/.cursor/debug-142ed9.log"


def log(message, data, hyp="L3"):
    entry = {"sessionId": "142ed9", "runId": "l3-veh-offset", "hypothesisId": hyp,
             "location": "tools/ep4d_debug/l3_vehicle_offset_gate.py",
             "message": message, "data": data, "timestamp": int(time.time() * 1000)}
    with open(DEBUG_LOG, "a") as handle:
        handle.write(json.dumps(entry, default=float) + "\n")
# #endregion


def main():
    d = np.load(TABLE, allow_pickle=True)
    cols = {str(c): i for i, c in enumerate(d["columns"])}
    t = d["table"]

    def col(name):
        return t[:, cols[name]].astype(np.float64)

    keep = ((col("class_id") == 0)
            & (col("gt_class_match") == 1)
            & (col("iou3d_gt") >= 0.10)
            & np.isfinite(col("d_peak")) & (col("d_peak") > 1.5)
            & (col("z_gt") > 2.0) & (col("z_gt") <= 45.0))
    n_all_veh = int((col("class_id") == 0).sum())
    n = int(keep.sum())
    z_gt = col("z_gt")[keep]
    z_pred = col("z_pred")[keep]
    z_meas = (col("focal_baseline") / col("d_peak"))[keep]
    u_c = 0.5 * (col("bbox_x1") + col("bbox_x2"))[keep]
    ry = col("rotation_y")[keep]
    alpha = ry - np.arctan((u_c - CX) / FX)
    length = col("length")[keep]
    width = col("width")[keep]
    height = col("height")[keep]
    qidx = col("query_index")[keep].astype(np.int64)

    baseline = float(np.median(np.abs(z_pred - z_gt)))
    raw_meas = float(np.median(np.abs(z_meas - z_gt)))
    offset_true = z_gt - z_meas

    feats = np.stack([length, width, height, z_meas,
                      np.abs(np.sin(alpha)), np.abs(np.cos(alpha)),
                      length * np.abs(np.cos(alpha)),
                      np.ones_like(z_gt)], axis=1)

    fold = qidx % 2
    err_cond = np.zeros_like(z_gt)
    err_const = np.zeros_like(z_gt)
    r2s = []
    for f in (0, 1):
        tr, te = fold == f, fold != f
        X, y = feats[tr], offset_true[tr]
        lam = 1.0
        w = np.linalg.solve(X.T @ X + lam * np.eye(X.shape[1]), X.T @ y)
        pred_te = feats[te] @ w
        err_cond[te] = np.abs(z_meas[te] + pred_te - z_gt[te])
        err_const[te] = np.abs(z_meas[te] + np.median(y) - z_gt[te])
        ss_res = float(((feats[tr] @ w - y) ** 2).sum())
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2s.append(1.0 - ss_res / max(ss_tot, 1e-9))

    cond = float(np.median(err_cond))
    const = float(np.median(err_const))

    def binned(err):
        out = {}
        for name, lo, hi in (("0-15", 0, 15), ("15-25", 15, 25), ("25-45", 25, 45)):
            m = (z_gt >= lo) & (z_gt < hi)
            out[name] = [float(np.median(err[m])), int(m.sum())] if m.any() else [None, 0]
        return out

    gate_pass = bool(cond <= 0.90 * baseline)
    receipt = {
        "probe": "l3_vehicle_offset_gate", "date": "2026-09-01",
        "session": "142ed9", "table": TABLE,
        "population": {"matched_vehicles": n, "all_vehicle_rows": n_all_veh,
                       "resolvable_peak_coverage": round(n / max(n_all_veh, 1), 4)},
        "medians_m": {"A_model_baseline": baseline, "B_raw_measurement": raw_meas,
                      "C0_constant_offset_crossfold": const,
                      "C_conditional_offset_crossfold": cond},
        "offset_fit": {"r2_per_fold": [round(r, 4) for r in r2s],
                       "offset_true_median": float(np.median(offset_true)),
                       "offset_true_iqr": [float(np.percentile(offset_true, 25)),
                                           float(np.percentile(offset_true, 75))]},
        "binned_conditional_error": binned(err_cond),
        "binned_baseline_error": binned(np.abs(z_pred - z_gt)),
        "frozen_gate": "C <= 0.90 * A launches the arm; else vehicle offset head closed",
        "gate_pass": gate_pass,
        "verdict": "LAUNCH_AUTHORIZED" if gate_pass else "VEHICLE_OFFSET_HEAD_CLOSED",
        "scope": "DIAGNOSTIC_FINDING; no AP claim; pedestrian-side QC-EER unaffected",
    }
    Path(RECEIPT).parent.mkdir(parents=True, exist_ok=True)
    with open(RECEIPT, "w") as handle:
        json.dump(receipt, handle, indent=2, default=float)
    log("VERDICT " + receipt["verdict"], {**receipt["medians_m"],
        "n": n, "coverage": receipt["population"]["resolvable_peak_coverage"],
        "r2": r2s}, "L3-VERDICT")
    print(json.dumps(receipt, indent=2, default=float))


if __name__ == "__main__":
    main()

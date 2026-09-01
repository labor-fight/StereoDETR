#!/usr/bin/env python
"""Aggregate sharded object-depth-accuracy rows and emit one NDJSON verdict."""

import glob
import json
import sys
import time

import numpy as np

LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-38825a.log"
SESSION = "38825a"


def dlog(hypothesis_id, location, message, data, run_id):
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "sessionId": SESSION,
                    "runId": run_id,
                    "hypothesisId": hypothesis_id,
                    "location": location,
                    "message": message,
                    "data": data,
                    "timestamp": int(time.time() * 1000),
                },
                ensure_ascii=False,
                default=float,
            )
            + "\n"
        )


def summarise(sel):
    if not sel:
        return None
    e = np.array([r["err_centre_corrected"] for r in sel])
    e2 = np.array([r["err_no_correction"] for r in sel])
    return {
        "n": len(sel),
        "hit_centre_corrected": float(np.mean([r["hit_corrected"] for r in sel])),
        "hit_no_correction": float(np.mean([r["hit_no_correction"] for r in sel])),
        "hit_negative_control": float(np.mean([r["hit_negctrl"] for r in sel])),
        "median_abs_err_m": float(np.median(np.abs(e))),
        "median_signed_err_m": float(np.median(e)),
        "median_signed_err_no_corr_m": float(np.median(e2)),
    }


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ep4d_shards/val_*.json"
    run_id = sys.argv[2] if len(sys.argv) > 2 else "run4-val-full"
    rows, ctrl = [], []
    for p in sorted(glob.glob(pattern)):
        with open(p, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        rows.extend(d["rows"])
        ctrl.extend(d["ctrl_pos"])

    out = {
        "total_boxes": len(rows),
        "ctrl_pos_subpixel_median_err_px": float(np.median(ctrl)) if ctrl else None,
        "ctrl_pos_n": len(ctrl),
        "ctrl_pos_threshold_px": 0.25,
        "ctrl_pos_pass": bool(ctrl and float(np.median(ctrl)) <= 0.25),
        "overall": summarise(rows),
        "by_class_depth": {},
        "comparators": {
            "dense_map_ped_10_20m_within_tol_P4A": 0.189,
            "physically_available_C79": 0.70,
        },
    }
    for cname in ("Pedestrian", "Vehicle"):
        for lo, hi in ((0, 10), (10, 20), (20, 30), (30, 45)):
            sel = [r for r in rows if r["cls"] == cname and lo <= r["z_gt"] < hi]
            s = summarise(sel)
            if s:
                out["by_class_depth"]["%s_%d-%dm" % (cname, lo, hi)] = s
    ped_all = [r for r in rows if r["cls"] == "Pedestrian"]
    out["pedestrian_all"] = summarise(ped_all)
    out["decision_cell_ped_10_20m"] = out["by_class_depth"].get("Pedestrian_10-20m")

    # #region agent log (H-E/H-F verdict on the full val split)
    dlog(
        "H-E",
        "aggregate_depth_probe.py:main",
        "object-conditioned subpixel epipolar depth accuracy, full val",
        out,
        run_id,
    )
    # #endregion

    print("boxes=%d  CTRL-POS=%.3f px (n=%d) pass=%s"
          % (out["total_boxes"], out["ctrl_pos_subpixel_median_err_px"],
             out["ctrl_pos_n"], out["ctrl_pos_pass"]))
    print("%-22s %6s %9s %9s %9s %10s" % (
        "cell", "n", "hit", "no_corr", "negctrl", "med|err|m"))
    for k in sorted(out["by_class_depth"]):
        s = out["by_class_depth"][k]
        print("%-22s %6d %9.3f %9.3f %9.3f %10.3f" % (
            k, s["n"], s["hit_centre_corrected"], s["hit_no_correction"],
            s["hit_negative_control"], s["median_abs_err_m"]))
    d = out["decision_cell_ped_10_20m"]
    if d:
        print("\nDECISION Ped 10-20m: %.3f  (dense map 0.189 | physics 0.70)  n=%d"
              % (d["hit_centre_corrected"], d["n"]))


if __name__ == "__main__":
    main()

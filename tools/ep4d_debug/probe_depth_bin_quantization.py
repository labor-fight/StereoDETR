"""Does the LID depth-bin cross entropy quantize away the pedestrian strict tolerance?

Background.  ``lib/models/event4d/dense_depth_loss.py`` supervises the dense
depth head with a focal cross entropy whose target is a *hard* LID bin index,
and ``depth_predictor_lightstereo.py`` reads the map back as the soft
expectation over ``depth_bin_values``.  A model that perfectly minimises that
loss puts all mass on the target bin, so its depth output is the bin
representative value, and its residual against the true depth is bounded by
half a bin width.  The frozen recipe uses ``num_depth_bins=80`` over
``[2.0, 56.9] m``, which is a 0.53 m bin at 10 m and a 0.79 m bin at 20 m,
while strict 3D IoU allows a pedestrian only 0.243 m of longitudinal error.

Hypotheses under test.

  H-K  The bin-centre ceiling for Pedestrian at 10-20 m is far below the 0.70
       that the event data physically supports, and of the same order as the
       0.189 the trained dense map actually delivers (P4A).  If so the
       pedestrian depth wall is a supervision-design artefact, not a limit of
       the event representation.
  H-L  The Vehicle/Pedestrian AP asymmetry follows the ratio
       tolerance / bin-width crossing 1: vehicles (0.798 m tolerance) sit above
       it everywhere, pedestrians (0.243 m) sit below it everywhere.
  H-O  The fix lives inside the current design: refining the binning lifts the
       pedestrian ceiling back to ~1.0.

Controls.

  CTRL-POS  num_bins=320 must drive the pedestrian ceiling to ~1.0, otherwise
            this probe is not measuring quantisation at all.
  CTRL-NEG  num_bins=20 must collapse *both* classes, otherwise the probe is
            insensitive to the knob it claims to measure.
  CTRL-VEH  vehicles at the production 80 bins must already be ~1.0, otherwise
            the tolerance model is wrong.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import time
from collections import defaultdict

import numpy as np

# Longitudinal slack that keeps a correctly sized, correctly placed box inside
# the strict 3D IoU threshold, per class.  Same table as
# tools/ep4d_debug/probe_object_depth_accuracy.py so the two probes are
# directly comparable.
TOL_Z = {"Vehicle": 0.798, "Car": 0.798, "Pedestrian": 0.243, "Cyclist": 0.558}

RANGES = [(0.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, 1e9)]

LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-38825a.log"
SESSION = "38825a"


def emit(run_id: str, hypothesis: str, message: str, data: dict) -> None:
    # #region agent log (H-K/H-L/H-O: LID bin quantisation vs strict tolerance)
    rec = {
        "sessionId": SESSION,
        "runId": run_id,
        "hypothesisId": hypothesis,
        "location": "tools/ep4d_debug/probe_depth_bin_quantization.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with open(LOG_PATH, "a") as handle:
        handle.write(json.dumps(rec, default=float) + "\n")
    # #endregion


def bin_values(depth_min: float, depth_max: float, num_bins: int) -> np.ndarray:
    """Representative depth of every bin, exactly as the predictor builds it."""

    bin_size = 2.0 * (depth_max - depth_min) / (num_bins * (1 + num_bins))
    idx = np.linspace(0, num_bins - 1, num_bins)
    values = (idx + 0.5) ** 2 * bin_size / 2.0 - bin_size / 8.0 + depth_min
    return np.concatenate([values, np.array([depth_max])])


def bin_index(depth: np.ndarray, depth_min: float, depth_max: float, num_bins: int) -> np.ndarray:
    """Target index, exactly as ``lid_bin_indices`` computes it."""

    bin_size = 2.0 * (depth_max - depth_min) / (num_bins * (1 + num_bins))
    with np.errstate(invalid="ignore"):
        idx = -0.5 + 0.5 * np.sqrt(np.clip(1.0 + 8.0 * (depth - depth_min) / bin_size, 0.0, None))
    bad = (idx < 0) | (idx > num_bins) | (~np.isfinite(idx))
    idx = np.where(bad, float(num_bins), idx)
    return idx.astype(np.int64)


def bin_width_at(depth: float, depth_min: float, depth_max: float, num_bins: int) -> float:
    bin_size = 2.0 * (depth_max - depth_min) / (num_bins * (1 + num_bins))
    i = (-1.0 + math.sqrt(1.0 + 8.0 * (depth - depth_min) / bin_size)) / 2.0
    return bin_size * (i + 1.0)


def collect_objects(infos_path: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (class name, true depth) for every annotated object."""

    with open(infos_path, "rb") as handle:
        infos = pickle.load(handle)
    names: list[str] = []
    depths: list[float] = []
    for info in infos:
        annos = info.get("annos")
        entries = annos if isinstance(annos, list) else [annos]
        for anno in entries:
            if not isinstance(anno, dict):
                continue
            name = np.asarray(anno.get("name", []))
            loc = np.asarray(anno.get("location", []))
            if name.size == 0 or loc.size == 0:
                continue
            loc = loc.reshape(-1, 3)
            for cls, xyz in zip(name.tolist(), loc):
                names.append(str(cls))
                depths.append(float(xyz[2]))
    return np.asarray(names), np.asarray(depths, dtype=np.float64)


def ceiling_table(
    names: np.ndarray,
    depths: np.ndarray,
    depth_min: float,
    depth_max: float,
    num_bins: int,
) -> dict:
    """Strict-tolerance hit rate of a model that perfectly learns the CE target."""

    values = bin_values(depth_min, depth_max, num_bins)
    idx = bin_index(depths, depth_min, depth_max, num_bins)
    predicted = values[np.clip(idx, 0, len(values) - 1)]
    residual = np.abs(predicted - depths)

    out: dict = {}
    for cls in sorted(set(names.tolist())):
        tol = TOL_Z.get(cls)
        if tol is None:
            continue
        cls_mask = names == cls
        per_range = {}
        for lo, hi in RANGES:
            sel = cls_mask & (depths >= lo) & (depths < hi)
            n = int(sel.sum())
            if n == 0:
                continue
            label = f"{int(lo)}-{'inf' if hi > 1e8 else int(hi)}m"
            per_range[label] = {
                "n": n,
                "ceiling_hit_rate": float((residual[sel] <= tol).mean()),
                "median_abs_residual_m": float(np.median(residual[sel])),
                "bin_width_m": round(bin_width_at(float(np.median(depths[sel])), depth_min, depth_max, num_bins), 3),
                "tolerance_m": tol,
            }
        if per_range:
            out[cls] = {
                "n_total": int(cls_mask.sum()),
                "ceiling_hit_rate_all": float((residual[cls_mask] <= tol).mean()),
                "by_range": per_range,
            }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--infos", default="/data1/lyq/data/EV_3DOD/DSEC/dsec_infos_val.pkl")
    parser.add_argument("--depth-min", type=float, default=2.0)
    parser.add_argument("--depth-max", type=float, default=56.9)
    parser.add_argument("--bins", type=int, nargs="+", default=[20, 80, 160, 320])
    parser.add_argument("--production-bins", type=int, default=80)
    parser.add_argument("--run-id", default="runQ")
    args = parser.parse_args()

    names, depths = collect_objects(args.infos)
    finite = np.isfinite(depths) & (depths > 0)
    names, depths = names[finite], depths[finite]

    emit(
        args.run_id,
        "H-K",
        "object inventory for the quantisation ceiling probe",
        {
            "infos": os.path.basename(args.infos),
            "objects": int(names.size),
            "per_class": {c: int((names == c).sum()) for c in sorted(set(names.tolist()))},
            "depth_min": args.depth_min,
            "depth_max": args.depth_max,
        },
    )

    tables = {}
    for nb in args.bins:
        tables[nb] = ceiling_table(names, depths, args.depth_min, args.depth_max, nb)

    prod = tables.get(args.production_bins, {})
    ped = prod.get("Pedestrian", {}).get("by_range", {}).get("10-20m", {})
    veh = prod.get("Vehicle", prod.get("Car", {})).get("by_range", {}).get("10-20m", {})

    emit(
        args.run_id,
        "H-K",
        "production binning ceiling vs what the trained map delivers and what physics allows",
        {
            "num_bins": args.production_bins,
            "pedestrian_10_20m": ped,
            "vehicle_10_20m": veh,
            "dense_map_realised_ped_10_20m_P4A": 0.189,
            "physically_available_ped_10_20m": 0.70,
        },
    )

    emit(
        args.run_id,
        "H-L",
        "tolerance over bin width, the ratio that should separate the two classes",
        {
            str(nb): {
                cls: {
                    rng: round(v["tolerance_m"] / v["bin_width_m"], 3)
                    for rng, v in tab.get(cls, {}).get("by_range", {}).items()
                }
                for cls in ("Pedestrian", "Vehicle", "Car")
                if cls in tab
            }
            for nb, tab in tables.items()
        },
    )

    emit(
        args.run_id,
        "H-O",
        "CTRL-POS/CTRL-NEG/CTRL-VEH: does the ceiling move with the binning knob",
        {
            "ped_10_20m_ceiling_by_bins": {
                str(nb): tab.get("Pedestrian", {}).get("by_range", {}).get("10-20m", {}).get("ceiling_hit_rate")
                for nb, tab in tables.items()
            },
            "veh_10_20m_ceiling_by_bins": {
                str(nb): (tab.get("Vehicle") or tab.get("Car") or {}).get("by_range", {}).get("10-20m", {}).get("ceiling_hit_rate")
                for nb, tab in tables.items()
            },
        },
    )

    emit(args.run_id, "H-K", "full ceiling table for every binning tried", {"tables": tables})

    print(json.dumps({"bins": args.bins, "production": prod}, indent=2, default=float))


if __name__ == "__main__":
    main()

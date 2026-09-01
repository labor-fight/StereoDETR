"""Which soft LID target actually puts its optimum on the true depth?

The dense depth head is read back as the expectation over bin representatives,
but it is trained with a focal cross entropy whose target is a hard bin index.
The optimum of that loss is the bin representative, so the read-out inherits a
half-bin error: 0.34 m at 15 m against a 0.243 m pedestrian tolerance.

Splitting the target across the two neighbouring bins in proportion to the
sub-bin position makes the *plain* cross-entropy optimum reproduce the true
depth. Whether it survives the focal modulation is the open question, because
focal deliberately flattens confident predictions and that flattening pulls the
two-bin split back towards 0.5/0.5.

This script minimises each candidate loss numerically over the two-bin simplex
and reports the depth error at the optimum, so the training change is chosen on
measured behaviour rather than on the algebra of the un-modulated case.

  CTRL-POS  the hard target must reproduce the known half-bin error, otherwise
            the harness does not model the loss that is actually in the tree.
  CTRL-NEG  a target placed exactly on a bin centre (frac = 0) must give zero
            error for every candidate, otherwise the read-out is mismodelled.
"""

from __future__ import annotations

import json
import time

import numpy as np

LOG_PATH = "/data1/lyq/code/StereoDETR/.cursor/debug-38825a.log"
DEPTH_MIN, DEPTH_MAX, NUM_BINS = 2.0, 56.9, 80
BIN_SIZE = 2.0 * (DEPTH_MAX - DEPTH_MIN) / (NUM_BINS * (1 + NUM_BINS))
ALPHA, GAMMA = 0.25, 2.0
TOL_PED = 0.243


def emit(hypothesis: str, message: str, data: dict) -> None:
    # #region agent log (H-R: does the soft target's optimum land on the true depth)
    record = {
        "sessionId": "38825a",
        "runId": "runS",
        "hypothesisId": hypothesis,
        "location": "tools/ep4d_debug/verify_soft_depth_target.py",
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    with open(LOG_PATH, "a") as handle:
        handle.write(json.dumps(record, default=float) + "\n")
    # #endregion


def bin_value(index: np.ndarray | float) -> np.ndarray:
    return (np.asarray(index) + 0.5) ** 2 * BIN_SIZE / 2.0 - BIN_SIZE / 8.0 + DEPTH_MIN


def continuous_index(depth: float) -> float:
    return -0.5 + 0.5 * np.sqrt(1.0 + 8.0 * (depth - DEPTH_MIN) / BIN_SIZE)


def optimum_probability(weight_high: float, mode: str) -> float:
    """Probability the loss wants on the upper bin, found by dense search."""

    grid = np.linspace(1e-6, 1 - 1e-6, 200001)
    p_high, p_low = grid, 1.0 - grid
    if mode == "hard":
        # Hard target puts everything on the nearer bin.
        return 1.0 if weight_high >= 0.5 else 0.0
    if mode == "soft_plain":
        loss = -(1.0 - weight_high) * np.log(p_low) - weight_high * np.log(p_high)
    elif mode == "soft_focal":
        loss = ALPHA * (
            (1.0 - weight_high) * (1.0 - p_low) ** GAMMA * -np.log(p_low)
            + weight_high * (1.0 - p_high) ** GAMMA * -np.log(p_high)
        )
    else:
        raise ValueError(mode)
    return float(grid[int(np.argmin(loss))])


def leaky_readout(low: int, frac: float, mode: str) -> float:
    """Read-out when the softmax also leaks mass onto the bins either side.

    The two-outcome model above assumes the network can put every last unit of
    probability on the target pair. It cannot: focal stops pushing long before
    that, and the leftover mass lands on neighbouring bins, which drags the
    expectation. This searches the four-bin simplex (low-1, low, high, high+1)
    that a smooth logit field actually produces.
    """

    values = bin_value(np.array([low - 1, low, low + 1, low + 2], dtype=float))
    mass = np.linspace(0.30, 1.0, 141)[:, None]
    split = np.linspace(0.0, 1.0, 401)[None, :]
    p_low = np.clip(mass * (1.0 - split), 1e-9, None)
    p_high = np.clip(mass * split, 1e-9, None)
    leak = np.clip((1.0 - mass) / 2.0, 1e-9, None) * np.ones_like(split)

    if mode == "soft_plain":
        loss = -(1.0 - frac) * np.log(p_low) - frac * np.log(p_high)
    elif mode == "soft_focal":
        loss = ALPHA * (
            (1.0 - frac) * (1.0 - p_low) ** GAMMA * -np.log(p_low)
            + frac * (1.0 - p_high) ** GAMMA * -np.log(p_high)
        )
    elif mode == "soft_focal_grouped":
        pair = p_low + p_high
        loss = (
            ALPHA
            * (1.0 - pair) ** GAMMA
            * (-(1.0 - frac) * np.log(p_low) - frac * np.log(p_high))
        )
    elif mode == "hard":
        probability = p_high if frac >= 0.5 else p_low
        loss = ALPHA * (1.0 - probability) ** GAMMA * -np.log(probability)
    else:
        raise ValueError(mode)

    flat = int(np.argmin(loss))
    row, column = divmod(flat, loss.shape[1])
    probabilities = np.array(
        [leak[row, column], p_low[row, column], p_high[row, column], leak[row, column]]
    )
    return float((probabilities / probabilities.sum() * values).sum())


def main() -> None:
    depths = np.arange(6.0, 30.01, 0.13)
    modes = ("hard", "soft_plain", "soft_focal", "soft_focal_grouped")
    results: dict = {}

    for mode in modes:
        errors = []
        leaky_errors = []
        for depth in depths:
            index = continuous_index(float(depth))
            low = int(np.floor(index))
            frac = float(index - low)
            if mode != "soft_focal_grouped":
                p_high = optimum_probability(frac, mode)
                readout = (1.0 - p_high) * bin_value(low) + p_high * bin_value(low + 1)
                errors.append(abs(float(readout) - float(depth)))
            leaky_errors.append(abs(leaky_readout(low, frac, mode) - float(depth)))
        leaky_array = np.asarray(leaky_errors)
        entry = {
            "leaky_median_abs_error_m": float(np.median(leaky_array)),
            "leaky_max_abs_error_m": float(leaky_array.max()),
            "leaky_within_pedestrian_tolerance": float((leaky_array <= TOL_PED).mean()),
        }
        if errors:
            errors_array = np.asarray(errors)
            entry.update(
                {
                    "median_abs_error_m": float(np.median(errors_array)),
                    "p95_abs_error_m": float(np.percentile(errors_array, 95)),
                    "max_abs_error_m": float(errors_array.max()),
                    "within_pedestrian_tolerance": float((errors_array <= TOL_PED).mean()),
                }
            )
        results[mode] = entry

    # CTRL-NEG: a depth sitting exactly on a bin centre has to come back exact
    # under every candidate, or the read-out itself is mismodelled.
    on_centre = float(bin_value(40))
    centre_index = continuous_index(on_centre)
    centre_low = int(np.floor(centre_index))
    centre_frac = float(centre_index - centre_low)
    control = {
        mode: abs(leaky_readout(centre_low, centre_frac, mode) - on_centre)
        for mode in modes
    }

    emit(
        "H-R",
        "depth error at the optimum of each candidate dense-depth target, 6-30 m",
        {
            "bin_size": BIN_SIZE,
            "pedestrian_tolerance_m": TOL_PED,
            "results": results,
            "ctrl_neg_depth_on_bin_centre_error_m": control,
            "ctrl_pos_note": "hard must show the half-bin error the offline ceiling probe already measured",
        },
    )
    print(json.dumps({"results": results, "ctrl_neg": control}, indent=2))


if __name__ == "__main__":
    main()

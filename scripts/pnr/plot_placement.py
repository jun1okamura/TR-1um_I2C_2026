#!/usr/bin/env python3
"""plot_placement.py -- 配置 4 STEP の可視化（目視確認用。フロー外）。

  usage: python3 scripts/pnr/plot_placement.py [-o layout/placement_steps.png]

ラベルは ASCII のみ。日本語フォントの無い環境（クラウド側）で豆腐になるため。
"""
from __future__ import annotations
import argparse, json, os, sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

STEPS = [(1, "rows"), (2, "ordered"), (3, "tap"), (4, "fill")]
COL = {"TAP2": "#e74c3c", "FILL1": "#f5b7b1", "FILL2": "#f5b7b1",
       "FILL3": "#f5b7b1"}
TITLE = {1: "step1  row assignment (FM partition)",
         2: "step2  intra-row ordering (barycentre)",
         3: "step3  TAP insertion",
         4: "step4  FILL insertion  [final]"}


def draw(ax, d, step):
    cw, ch = d["core_w"], d["core_h"]
    mx0, my0, mx1, my1 = d["macro"]["box"]
    ax.add_patch(Rectangle((0, my0), cw, ch - my0, fc="#fcfcfc", ec="#2c3e50", lw=1.4))
    # channels
    y = 0.0
    for i, h in enumerate(d["ch_heights"]):
        ax.add_patch(Rectangle((0, y), d["row_width"], h, fc="#f4f8fb",
                               ec="none"))
        ax.text(d["row_width"] / 2, y + h / 2, f"ch{i} {h:.0f}", ha="center",
                va="center", fontsize=5.5, color="#95a5a6")
        y += h + (cfg.ROW_HEIGHT_UM if i < len(d["row_y"]) else 0)
    for r, row in enumerate(d["rows"]):
        ry = d["row_y"][r]
        for c in row:
            col = COL.get(c["cell"], "#aed6f1")
            if c.get("pri"):
                col = "#f9e79f"
            ax.add_patch(Rectangle((c["x"], ry), c["w"], cfg.ROW_HEIGHT_UM,
                                   fc=col, ec="#5499c7", lw=0.25))
    ax.add_patch(Rectangle((mx0, my0), mx1 - mx0, my1 - my0, fc="#f8c471",
                           ec="#ca6f1e", lw=1.1))
    ax.text((mx0 + mx1) / 2, (my0 + my1) / 2, d["macro"]["cell"],
            ha="center", va="center", fontsize=8)
    # MEMPORT's 21 signal pads are on its TOP edge (exaggerated)
    ax.add_patch(Rectangle((mx0, my1 - 14.0), mx1 - mx0, 14.0, fc="#8e44ad",
                           ec="none"))
    ax.set_xlim(-40, cw + 40)
    ax.set_ylim(my0 - 40, ch + 40)
    ax.set_aspect("equal")
    ax.set_title(TITLE[step], fontsize=8.5)
    ax.tick_params(labelsize=6)


def main(out=None):
    out = out or os.path.join(cfg.LAYOUT, "placement_steps.png")
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 12.0))
    for ax, (s, tag) in zip(axes.ravel(), STEPS):
        p = os.path.join(cfg.LAYOUT, f"step{s}", f"place_step{s}_{tag}.json")
        if not os.path.exists(p):
            ax.set_axis_off()
            continue
        draw(ax, json.load(open(p)), s)
    cw, ch = cfg.core_size()
    h, op, marg = cfg.check_opening()
    fig.suptitle(f"TD4 placement  --  router area {cw:.1f} x {ch:.1f} um, "
                 f"chip core {cw:.1f} x {h:.1f} um (pre-squeeze; opening {op:.0f})   "
                 f"{cfg.N_ROWS} rows x {cfg.ROW_WIDTH_UM:.1f} um", fontsize=11)
    fig.text(0.5, 0.015,
             "red = TAP2 (M2 power column)   yellow = priority M2 corridor "
             "(FILL2 right after each TAP)   pink = FILL   blue = logic   "
             "orange = MEMPORT (REG8x16 rotated 90 deg + M1/M2 fan-out)   "
             "purple = its 21 signal pads (all on the TOP edge, drawn thick)",
             ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=130)
    print(f"wrote {os.path.relpath(out, cfg.ROOT)}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=None)
    main(ap.parse_args().out)

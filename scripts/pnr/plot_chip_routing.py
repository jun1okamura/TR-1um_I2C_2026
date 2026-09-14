#!/usr/bin/env python3
"""plot_chip_routing.py -- チップ配線の確認図（step2）。

  usage: python3 scripts/pnr/plot_chip_routing.py [GDS] [-o PNG]

`route_chip.py` が**トップセル直下に置いた図形だけ**を描く。コアとフレームの
中身は描かない（数万個あって潰れる）ので、チャネルに引いたものだけが見える。
M1 は青、M2 は赤、via は黒。ラベルは ASCII のみ。
"""
from __future__ import annotations

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                             # noqa: E402
from matplotlib.patches import Rectangle                    # noqa: E402

# **チップ組み立ては縦置き専用。** `TD4_MACRO_MODE` の既定は landscape で、
# 付け忘れると `FINAL_GDS` が step10 を指し、`MACRO_CELL` も MEMPORT になる
# （2026-09-14: マクロ電源の入っていないコアを載せたチップを作ってしまった）。
# ここで固定する。コア側を landscape で作り直したいときはコア側のスクリプトで。
os.environ.setdefault("TD4_MACRO_MODE", "portrait")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402
import klayout.db as db                                     # noqa: E402

STYLE = {(13, 0): ("#1f6fb4", "M1"), (20, 0): ("#c0392b", "M2"),
         (19, 0): ("#111111", "V1")}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds", nargs="?",
                    default=os.path.join(cfg.CHIP, "step2_routed.gds"))
    ap.add_argument("-o", "--out", default=os.path.join(cfg.CHIP, "routing.png"))
    a = ap.parse_args()

    ly = db.Layout()
    ly.read(a.gds)
    top = ly.cell(cfg.CHIP_TOP_CELL)
    u = ly.dbu
    geom = cfg.chip_geometry()
    x0, y0, x1, y1 = geom["core_chip_bbox"]
    die = geom["die"]
    h = die / 2

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.add_patch(Rectangle((-h, -h), die, die, facecolor="none",
                           edgecolor="#333", lw=1.2))
    lo, hi = cfg.frame_opening()
    ax.add_patch(Rectangle((lo, lo), hi - lo, hi - lo, facecolor="none",
                           edgecolor="#2e7d32", lw=1.4))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="#dfe8f3",
                           edgecolor="#2e6fb7", lw=1.0))

    n = {}
    for lay, (col, name) in STYLE.items():
        # **トップセル直下だけ**。再帰するとコアとフレームの中身が出る。
        idx = ly.layer(*lay)
        cnt = 0
        for s in top.shapes(idx).each():
            if not (s.is_box() or s.is_polygon() or s.is_path()):
                continue
            b = s.polygon.bbox().to_dtype(u)
            ax.add_patch(Rectangle((b.left, b.bottom), b.width(), b.height(),
                                   facecolor=col, edgecolor="none", alpha=0.75))
            cnt += 1
        # via は PCell のインスタンスなので、インスタンス側からも拾う。
        # **コアとフレームは名前で弾く**（大きさで弾くと、コア内部の小さな
        # 図形が数千個そのまま出てきてチャネルが見えなくなる）。
        for inst in top.each_inst():
            if inst.cell.name in (cfg.TOP_CELL_NAME, cfg.FRAME_CELL,
                                  cfg.FRAME_CELL_CHIP):
                continue
            for s in inst.cell.shapes(idx).each():
                if not (s.is_box() or s.is_polygon() or s.is_path()):
                    continue
                b = s.polygon.transformed(inst.trans).bbox().to_dtype(u)
                ax.add_patch(Rectangle((b.left, b.bottom), b.width(), b.height(),
                                       facecolor=col, edgecolor="none", alpha=0.9))
                cnt += 1
        n[name] = cnt

    ax.set_xlim(-h - 40, h + 40)
    ax.set_ylim(-h - 40, h + 40)
    ax.set_aspect("equal")
    ax.set_title(f"{cfg.CHIP_TOP_CELL}  chip routing (top-level shapes only)\n"
                 + "   ".join(f"{k} {v}" for k, v in n.items()),
                 fontsize=10, loc="left")
    ax.tick_params(labelsize=7)
    fig.text(0.5, 0.012,
             "blue = M1 (horizontal)   red = M2 (vertical)   black = V1   "
             "green = opening 1840   blue box = core",
             ha="center", fontsize=8, color="#555")
    fig.tight_layout(rect=(0.01, 0.035, 0.99, 1))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.savefig(a.out, dpi=150)
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}  {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

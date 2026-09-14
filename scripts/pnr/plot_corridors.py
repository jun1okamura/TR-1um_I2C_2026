#!/usr/bin/env python3
"""plot_corridors.py -- 優先 M2 コリドー（全行同じ x に縦へ抜ける列）の確認用。

  usage: python3 scripts/pnr/plot_corridors.py
         python3 scripts/pnr/plot_corridors.py -g layout/step10/route_step_6_squeezed.gds \\
                                               -o layout/corridors.png

左: コア全体。コリドーの x に縦の帯を重ねる（全行で同じ x なのが見える）。
右: 1 本を拡大。`FILL3` (16.2 µm = 3 トラック) の**真ん中**が両側とも空くので
    そこを行またぎの via が通る。

コリドーの x は配置 JSON の `FILLPRI_*` インスタンスから取る
（ルータの `priority_corridor_x` と同じ導出）。ラベルは ASCII のみ
（日本語フォントの無いクラウド側で豆腐になるため）。
"""
from __future__ import annotations
import argparse
import json
import os
import sys

import gdstk
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

STYLE = {
    (235, 0): ("#e2e2e2", 0.55, 1),
    (13, 0):  ("#2e6fb7", 0.75, 3),
    (20, 0):  ("#d95f02", 0.60, 4),
    (19, 0):  ("#111111", 0.95, 5),
}
X_GRID = 5.4


def corridor_blocks(place_json):
    """[(x0, width)] -- FILLPRI_* の実体（トラックではなくセル枠）。"""
    pl = json.load(open(place_json))
    out = []
    for inst in pl["rows"][0]:
        if inst["type"].startswith("FILL") and inst["name"].startswith("FILLPRI_"):
            out.append((inst["x"], inst["width"]))
    return sorted(out)


def draw_gds(ax, path, xlim=None, ylim=None):
    lib = gdstk.read_gds(path)
    tops = [c for c in lib.cells if c.name == cfg.TOP_CELL_NAME] or lib.top_level()
    top = tops[0]
    for p in top.get_polygons(depth=None):
        st = STYLE.get((p.layer, p.datatype))
        if st is None:
            continue
        if xlim is not None:
            xs = p.points[:, 0]
            if xs.max() < xlim[0] or xs.min() > xlim[1]:
                continue
        fc, a, z = st
        ax.add_patch(Polygon(p.points, closed=True, facecolor=fc, alpha=a,
                             edgecolor="none", zorder=z))
    return top.bounding_box()


def main(gds=None, place_json=None, out=None, zoom=None):
    gds = gds or cfg.SQUEEZED_GDS
    place_json = place_json or cfg.PLACEMENT_JSON
    out = out or os.path.join(cfg.LAYOUT, "corridors.png")
    blocks = corridor_blocks(place_json)

    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(15.0, 9.0), gridspec_kw=dict(width_ratios=[2.1, 1.0]))

    bus = cfg.side_bus_x() if hasattr(cfg, "side_bus_x") else []
    bb = draw_gds(axL, gds)
    (x0, y0), (x1, y1) = bb
    for bx, bw in blocks:
        axL.add_patch(Rectangle((bx, y0), bw, y1 - y0, facecolor="#ffd54f",
                                alpha=0.42, edgecolor="#f39c12", lw=0.6,
                                zorder=8))
    for bx in bus:                       # コア右の縦 M2 バス
        axL.add_patch(Rectangle((bx - X_GRID / 2, y0), X_GRID, y1 - y0,
                                facecolor="#4dd0e1", alpha=0.5,
                                edgecolor="#00838f", lw=0.5, zorder=8))
    axL.set_xlim(x0 - 20, x1 + 20)
    axL.set_ylim(y0 - 10, y1 + 10)
    axL.set_aspect("equal")
    axL.set_title(f"{os.path.relpath(gds, cfg.ROOT)}   "
                  f"{x1-x0:.1f} x {y1-y0:.1f} um   "
                  f"{len(blocks)} priority corridors ({cfg.PRI_CELL}, "
                  f"{cfg.PRI_W} um = {round(cfg.PRI_W/X_GRID)} tracks)",
                  fontsize=9.5, loc="left")
    axL.tick_params(labelsize=7)

    # 右: いちばん中寄りのコリドーを拡大
    if bus and zoom is None:
        lo, hi = bus[0] - 3 * X_GRID, bus[-1] + 3 * X_GRID + 40.0
        draw_gds(axR, gds, xlim=(lo, hi))
        for bx in bus:
            axR.add_patch(Rectangle((bx - X_GRID / 2, y0), X_GRID, y1 - y0,
                                    facecolor="#4dd0e1", alpha=0.5,
                                    edgecolor="#00838f", lw=0.5, zorder=8))
        axR.set_xlim(lo, hi); axR.set_ylim(y0 - 10, y1 + 10)
        axR.set_aspect("equal"); axR.tick_params(labelsize=7)
        axR.set_title(f"zoom: side M2 bus  {len(bus)} tracks  "
                      f"x {bus[0]:.1f}...{bus[-1]:.1f}", fontsize=9.5, loc="left")
        fig.text(0.5, 0.012,
                 "cyan = side M2 bus (no cells there, so it crosses no row)   "
                 "yellow = priority M2 corridor   blue = M1   orange = M2   black = V1",
                 ha="center", fontsize=8.5, color="#555")
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        fig.savefig(out, dpi=135)
        print(f"wrote {os.path.relpath(out, cfg.ROOT)}  "
              f"({len(blocks)} corridors + {len(bus)} bus tracks)")
        return out
    cx = zoom if zoom is not None else min(
        blocks, key=lambda b: abs(b[0] + b[1] / 2 - (x0 + x1) / 2))[0]
    blk = min(blocks, key=lambda b: abs(b[0] - cx))
    lo, hi = blk[0] - 60.0, blk[0] + blk[1] + 60.0
    draw_gds(axR, gds, xlim=(lo, hi))
    axR.add_patch(Rectangle((blk[0], y0), blk[1], y1 - y0, facecolor="#ffd54f",
                            alpha=0.42, edgecolor="#f39c12", lw=0.8, zorder=8))
    for k in range(round(blk[1] / X_GRID)):
        tx = blk[0] + X_GRID / 2.0 + k * X_GRID
        axR.axvline(tx, color="#c0392b", lw=0.7, ls=":", zorder=9)
    axR.set_xlim(lo, hi)
    axR.set_ylim(y0 - 10, y1 + 10)
    axR.set_aspect("equal")
    axR.set_title(f"zoom  x {blk[0]:.1f}...{blk[0]+blk[1]:.1f}   "
                  f"(dotted = track centres)", fontsize=9.5, loc="left")
    axR.tick_params(labelsize=7)

    fig.text(0.5, 0.012,
             "yellow = priority M2 corridor (FILLPRI_* reserved filler, same X in every row)   "
             "blue = M1   orange = M2   black = V1   grey = cell",
             ha="center", fontsize=8.5, color="#555")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    fig.savefig(out, dpi=135)
    print(f"wrote {os.path.relpath(out, cfg.ROOT)}  "
          f"({len(blocks)} corridors, {cfg.PRI_CELL} {cfg.PRI_W} um)")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-g", "--gds", default=None)
    ap.add_argument("-p", "--placement", default=None)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--zoom", type=float, default=None, help="拡大するコリドーの x")
    a = ap.parse_args()
    main(a.gds, a.placement, a.out, a.zoom)

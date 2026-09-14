#!/usr/bin/env python3
"""plot_chip_floorplan.py -- チップ組み立ての確認図。

  usage: python3 scripts/pnr/plot_chip_floorplan.py [-o layout/chip/floorplan.png]

`assemble_top.py` が置いたものを俯瞰する:

  * ダイ枠（2500 x 2500）と `OSS_FRAME_GIO` の OBS（= パッドとコーナー）
  * 端子リング（`GIO_PIN_RADIUS` = 921.7）
  * コアの bbox と、**コアのトップピン 14 本 + VDD/GND の実位置**

チップ配線はこのピンからパッドの端子まで引くので、どの辺に何本出ているかを
先に見ておく。ラベルは ASCII のみ（クラウド側に日本語フォントが無い）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                             # noqa: E402
from matplotlib.patches import Rectangle                    # noqa: E402

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import klayout.db as db                                     # noqa: E402


def core_port_pins(gds, dx, dy):
    """[(name, x, y)] -- コアのピンラベル（M1PIN/M2PIN のテキスト）をチップ座標で。"""
    ly = db.Layout()
    ly.read(gds)
    top = ly.cell(cfg.TOP_CELL_NAME)
    out = []
    for lay, dt in ((49, 0), (48, 0)):
        for s in top.shapes(ly.layer(lay, dt)).each():
            if s.is_text():
                out.append((s.text.string, s.text.x * ly.dbu + dx, s.text.y * ly.dbu + dy))
    return out


def ring_s(x, y, r):
    """`gen_top_routing_plan.ring_s` と同じ物差し（右下角から反時計回り、0…8r）。"""
    if abs(x) >= abs(y):
        return (y + r) if x > 0 else (4 * r + (r - y))
    return (2 * r + (r - x)) if y > 0 else (6 * r + (x + r))


def ring_xy(s, r):
    """周長座標 -> 座標。`ring_s` の逆。"""
    s = s % (8 * r)
    if s <= 2 * r:
        return (r, s - r)                       # 右辺（下 -> 上）
    if s <= 4 * r:
        return (r - (s - 2 * r), r)             # 上辺（右 -> 左）
    if s <= 6 * r:
        return (-r, r - (s - 4 * r))            # 左辺（上 -> 下）
    return (-r + (s - 6 * r), -r)               # 下辺（左 -> 右）


def ring_path(s0, s1, r):
    """s0 -> s1 を**近い方の回り**でたどる折れ線。途中の角を頂点にする。"""
    per = 8 * r
    fwd = (s1 - s0) % per
    d = fwd if fwd <= per - fwd else -(per - fwd)
    key = (lambda c: (c - s0) % per) if d > 0 else (lambda c: (s0 - c) % per)
    # 角は s = 0 / 2r / 4r / 6r（r, 3r… は辺の**中点**。ここを間違えると
    # 角を突っ切る直線になってコアを横断する）
    cand = [0, 2 * r, 4 * r, 6 * r, 8 * r]
    corners = sorted((c for c in cand if 0 < key(c) < abs(d)), key=key)
    return [ring_xy(s, r) for s in [s0] + corners + [s1]]


def stub_to_ring(x, y, r):
    """コアピン（辺の上）からリングまでの垂線の足。"""
    if abs(x) >= abs(y):
        return (r if x > 0 else -r, y)
    return (x, r if y > 0 else -r)


def draw_connections(ax, plan_path, r):
    """パッド <-> コアピンの対応を、リングを回り込む折れ線で描く。"""
    if not os.path.exists(plan_path):
        print(f"  （{os.path.relpath(plan_path, cfg.ROOT)} が無いので対応線は描かない）")
        return 0
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)
    sigs = plan["signals"]
    cmap = plt.get_cmap("tab20")
    for i, s in enumerate(sigs):
        col = cmap(i % 20)
        fx, fy = s["from"]["x"], s["from"]["y"]
        tx, ty = s["to"]["x"], s["to"]["y"]
        # リングを少しずつずらして、重なりが目で数えられるようにする
        rr = r - 4.0 - (i % 7) * 5.4
        sx, sy = stub_to_ring(fx, fy, rr)
        ex, ey = stub_to_ring(tx, ty, rr)
        pts = ring_path(ring_s(sx, sy, rr), ring_s(ex, ey, rr), rr)
        xs = [fx, sx] + [p[0] for p in pts] + [ex, tx]
        ys = [fy, sy] + [p[1] for p in pts] + [ey, ty]
        ax.plot(xs, ys, color=col, lw=1.0, alpha=0.85, zorder=5)
        ax.plot([tx], [ty], marker="s", ms=3.4, color=col, zorder=6)
        # パッド側にロール名
        off = 14
        ha, va, dx_, dy_ = "center", "center", 0, 0
        if abs(tx) > abs(ty):
            dx_ = off if tx > 0 else -off
            ha = "left" if tx > 0 else "right"
        else:
            dy_ = off if ty > 0 else -off
            va = "bottom" if ty > 0 else "top"
        ax.annotate(f"P{s['pad']} {s['role']}", (tx, ty), fontsize=6,
                    color=col, xytext=(dx_, dy_), textcoords="offset points",
                    ha=ha, va=va, zorder=6)
    return len(sigs)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=os.path.join(cfg.CHIP, "floorplan.png"))
    ap.add_argument("--core-gds", default=None)
    ap.add_argument("--plan", default=os.path.join(cfg.CHIP, "signal_routing_plan.json"),
                    help="パッド <-> コアピンの対応線を描く（既定は gen_top_routing_plan の出力）")
    ap.add_argument("--no-connections", action="store_true")
    a = ap.parse_args()

    core_gds = a.core_gds or cfg.CHIP_CORE_GDS
    geom = cfg.chip_geometry(core_gds)
    die, rects = cfg.frame_obs_rects()
    h = die / 2
    x0, y0, x1, y1 = geom["core_chip_bbox"]
    dx, dy = geom["core_offset"]

    fig, ax = plt.subplots(figsize=(9.5, 9.5))
    ax.add_patch(Rectangle((-h, -h), die, die, facecolor="none",
                           edgecolor="#333", lw=1.4))
    for p in rects:
        ax.add_patch(Rectangle((p[0], p[1]), p[2] - p[0], p[3] - p[1],
                               facecolor="#dedede", edgecolor="#b5b5b5",
                               lw=0.4, alpha=0.8, hatch="////"))
    # 実ジオメトリの内壁（= 本当の開口）。OBS の四隅の宣言は粗いので、
    # そちらはハッチだけにして、こちらを実線で出す。
    lo, hi = cfg.frame_opening()
    ax.add_patch(Rectangle((lo, lo), hi - lo, hi - lo, facecolor="none",
                           edgecolor="#2e7d32", lw=1.6))
    r = cfg.GIO_PIN_RADIUS
    ax.add_patch(Rectangle((-r, -r), 2 * r, 2 * r, facecolor="none",
                           edgecolor="#00838f", lw=0.9, ls="--"))
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor="#2e6fb7",
                           alpha=0.18, edgecolor="#2e6fb7", lw=1.2))

    pins = core_port_pins(core_gds, dx, dy)
    seen = {}
    for name, px, py in pins:
        seen.setdefault(name, []).append((px, py))
    for name, pts in seen.items():
        for px, py in pts:
            ax.plot([px], [py], marker="o", ms=2.6,
                    color="#c0392b" if name not in ("VDD", "GND") else "#e67e22")
        px, py = pts[0]
        if name not in ("VDD", "GND"):
            ax.annotate(name, (px, py), fontsize=6.5, color="#c0392b",
                        xytext=(0, 6 if py > 0 else -10), textcoords="offset points",
                        ha="center")

    nconn = 0
    if not a.no_connections:
        nconn = draw_connections(ax, a.plan, r)

    ax.set_xlim(-h - 60, h + 60)
    ax.set_ylim(-h - 60, h + 60)
    ax.set_aspect("equal")
    ax.set_title(
        f"{cfg.CHIP_TOP_CELL}   die {die:.0f} x {die:.0f} um\n"
        f"core {cfg.TOP_CELL_NAME} @ ({dx}, {dy})  "
        f"[{x1-x0:.1f} x {y1-y0:.1f}]   "
        f"opening {hi-lo:.0f} x {hi-lo:.0f} (measured)\n"
        f"channel T/B {geom['channel_top'][0]:.1f}  L/R {geom['channel_left'][0]:.1f} um",
        fontsize=9, loc="left")
    ax.tick_params(labelsize=7)
    fig.text(0.5, 0.030,
             "hatched grey = LEF OBS (coarse)   green = measured opening 1840x1840   "
             "dashed cyan = pin ring 921.7   blue = core bbox   "
             "red = core port pins   orange = VDD/GND",
             ha="center", fontsize=7.5, color="#555")
    if nconn:
        fig.text(0.5, 0.012,
                 "coloured lines = pad <-> core-pin assignment, the short way round "
                 "the ring (radius staggered for legibility; squares = pad terminals)",
                 ha="center", fontsize=7.5, color="#555")
    fig.tight_layout(rect=(0.01, 0.045, 0.99, 1))
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.savefig(a.out, dpi=140)
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}  "
          f"({len(seen)} 個のピン名、{len(pins)} 個のマーカ、{nconn} 本の対応線)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

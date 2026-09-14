#!/usr/bin/env python3
"""plot_floorplan.py -- フロアプラン案の可視化。

  usage: python3 scripts/plot_floorplan.py [-o out.png] [--frame lef/TR-1um_frame.lef]

フレームの開口は `MACRO OSS_FRAME_GIO` の OBS から実測する（手書きしない）。
コア枠・行・チャネル・TAP 列・マクロの寸法は下の FLOORPLAN で与える。
"""
from __future__ import annotations
import argparse, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

DIE = 2500.0
C = DIE / 2                     # LEF 原点（左下）→ ダイ中心へのオフセット

# ---------------------------------------------------------------- 案の寸法
FLOORPLAN = dict(
    core_w   = 1620.0,          # コア幅（= x -810 .. +810）
    row_w    = 1198.8,          # 行スタックの幅（222 サイト）
    row_h    = 59.4,
    n_row    = 5,
    ch       = [156.0, 100.0, 100.0, 100.0, 100.0, 80.0],   # 下から。行の間に入る
    tap_x    = [0.0, 534.6, 1069.2, 1188.0],                # 行ローカル
    tap_w    = 10.8,
    pri_w    = 10.8,            # TAP 直後の優先 M2 コリドー（FILL2）
    macro    = "REG8x16",
    macro_w  = 399.6,
    macro_h  = 933.0,
    macro_gap= 21.6,            # 行スタックとマクロの隙間
)
SITE = 5.4
# VDD の M1 タップ（コア境界に出ている 1 本のバー、ダイ中心基準）
VDD_TAP = (50.0, 350.0, 920.0, 933.0)


def frame_obs(path):
    txt = open(path).read()
    body = re.search(r"MACRO OSS_FRAME_GIO(.*?)END OSS_FRAME_GIO", txt, re.S).group(1)
    obs = re.search(r"OBS(.*?)END", body, re.S).group(1)
    r = re.findall(r"RECT\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*;", obs)
    return sorted({tuple(float(v) - C for v in q) for q in r})


def opening(rects, w):
    """幅 w のコアが収まる最大の y 帯（ダイ中心基準）。"""
    x0, x1 = -w / 2, w / 2
    ys = [(a, b) for (p, a, q, b) in rects if q > x0 + 1e-9 and p < x1 - 1e-9]
    pts = sorted({-C, C} | {v for p in ys for v in p})
    best = (0.0, 0.0)
    for a, b in zip(pts, pts[1:]):
        m = (a + b) / 2
        if not any(lo < m < hi for lo, hi in ys) and b - a > best[1] - best[0]:
            best = (a, b)
    return best


def bands(fp):
    """コアローカル y での [(種別, y0, y1), ...] を下から。"""
    out, y = [], 0.0
    for i in range(fp["n_row"]):
        out.append(("ch", y, y + fp["ch"][i])); y += fp["ch"][i]
        out.append(("row", y, y + fp["row_h"])); y += fp["row_h"]
    out.append(("ch", y, y + fp["ch"][-1])); y += fp["ch"][-1]
    return out, y


def draw(ax, rects, fp, zoom):
    core_w = fp["core_w"]
    lo, hi = opening(rects, core_w)
    bnd, core_h = bands(fp)
    cx0, cx1 = -core_w / 2, core_w / 2
    cy0 = -core_h / 2                      # コアは上下中央に置く
    mx0 = cx0 + fp["row_w"] + fp["macro_gap"]

    if not zoom:
        ax.add_patch(Rectangle((-C, -C), DIE, DIE, fc="#fafafa", ec="#999", lw=1.0))
        for x0, y0, x1, y1 in rects:
            ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                                   fc="#d8d8d8", ec="#b0b0b0", lw=0.4))
        for y in (lo, hi):
            ax.plot([cx0, cx1], [y, y], color="#c0392b", lw=1.0, ls=(0, (5, 3)), zorder=5)
        ax.text(0, hi + 24, f"幅 {core_w:.0f} µm のときの開口 = {hi - lo:.0f} µm",
                ha="center", va="bottom", fontsize=7.5, color="#c0392b")

    # --- コア枠 ---
    ax.add_patch(Rectangle((cx0, cy0), core_w, core_h,
                           fc="none", ec="#2c3e50", lw=1.6, zorder=6))

    # --- 行 / チャネル ---
    for kind, y0, y1 in bnd:
        yy = cy0 + y0
        if kind == "row":
            ax.add_patch(Rectangle((cx0, yy), fp["row_w"], y1 - y0,
                                   fc="#aed6f1", ec="#5499c7", lw=0.6, zorder=3))
        else:
            ax.add_patch(Rectangle((cx0, yy), fp["row_w"], y1 - y0,
                                   fc="#fdfefe", ec="#d5dbdb", lw=0.4, zorder=2))
            if zoom and y1 - y0 > 60:
                ax.text(cx0 + fp["row_w"] / 2, yy + (y1 - y0) / 2,
                        f"ch {y1-y0:.0f}", ha="center", va="center",
                        fontsize=6, color="#7f8c8d", zorder=4)

    # --- TAP 列（全行同じ x なので縦一直線）+ 優先コリドー ---
    for tx in fp["tap_x"]:
        ax.add_patch(Rectangle((cx0 + tx, cy0), fp["tap_w"], core_h,
                               fc="#e74c3c", ec="none", alpha=0.75, zorder=4))
        if tx != fp["tap_x"][-1]:
            ax.add_patch(Rectangle((cx0 + tx + fp["tap_w"], cy0), fp["pri_w"], core_h,
                                   fc="#f5b7b1", ec="none", alpha=0.7, zorder=4))

    # --- マクロ ---
    ax.add_patch(Rectangle((mx0, cy0), fp["macro_w"], fp["macro_h"],
                           fc="#f8c471", ec="#ca6f1e", lw=1.2, zorder=5))
    ax.text(mx0 + fp["macro_w"] / 2, cy0 + fp["macro_h"] / 2,
            f"{fp['macro']}\n{fp['macro_w']:.1f} × {fp['macro_h']:.1f}",
            ha="center", va="center", fontsize=7.5 if zoom else 6.5, zorder=7)
    # 21 本の信号ピンは全部下辺 (y 1.1..4.5)。見えないので誇張して描く
    hh = 10.0 if zoom else 18.0
    ax.add_patch(Rectangle((mx0, cy0 + 1.1), fp["macro_w"], hh,
                           fc="#8e44ad", ec="none", zorder=8))
    if zoom:
        ax.annotate("信号ピン 21 本は全部この下辺\n(ADD/D/Q/WEB, M2, y 1.1–4.5, 図は誇張)",
                    xy=(mx0 + fp["macro_w"] / 2, cy0 + 4.5),
                    xytext=(mx0 + fp["macro_w"] / 2, cy0 - 105), fontsize=6.5,
                    color="#6c3483", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#6c3483", lw=0.8))
        # 行スタックとマクロの隙間
        ax.annotate("", xy=(mx0, cy0 + core_h * 0.72),
                    xytext=(mx0 - fp["macro_gap"], cy0 + core_h * 0.72),
                    arrowprops=dict(arrowstyle="<->", color="#34495e", lw=0.8))
        ax.text(mx0 - fp["macro_gap"] / 2, cy0 + core_h * 0.72 + 12,
                f"{fp['macro_gap']} µm\n(M2 4 本)", fontsize=6, ha="center",
                va="bottom", color="#34495e")
        ax.text(cx0 + fp["row_w"] / 2, cy0 + core_h + 22,
                f"行スタック {fp['row_w']:.1f} µm", fontsize=7.5, ha="center",
                color="#21618c")
        ax.text(mx0 + fp["macro_w"] / 2, cy0 + core_h + 22,
                f"x {mx0:.1f} … {cx1:.1f}", fontsize=7.5, ha="center", color="#ca6f1e")

    # --- VDD の M1 タップ ---
    x0, x1, y0, y1 = VDD_TAP
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0,
                           fc="#27ae60", ec="#1e8449", lw=0.8, zorder=6))
    ax.annotate("VDD M1 タップ 300 µm\n(コアへの唯一の入口)",
                xy=((x0 + x1) / 2, y0), xytext=((x0 + x1) / 2, cy0 + core_h + 120),
                fontsize=6.5, color="#1e8449", ha="center",
                arrowprops=dict(arrowstyle="->", color="#1e8449", lw=0.8))

    return lo, hi, core_h, cy0, mx0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="reference/floorplan.png")
    ap.add_argument("--frame", default="lef/TR-1um_frame.lef")
    a = ap.parse_args()
    import matplotlib.font_manager as fm
    have = {f.name for f in fm.fontManager.ttflist}
    for f in ("Hiragino Sans", "Noto Sans CJK JP", "IPAGothic", "IPAexGothic"):
        if f in have:
            matplotlib.rcParams["font.family"] = f
            break
    matplotlib.rcParams["axes.unicode_minus"] = False
    rects = frame_obs(a.frame)
    fp = FLOORPLAN

    fig, axes = plt.subplots(1, 2, figsize=(15, 7.6))
    for ax, zoom in zip(axes, (False, True)):
        lo, hi, core_h, cy0, mx0 = draw(ax, rects, fp, zoom)
        ax.set_aspect("equal")
        if zoom:
            m = 150
            ax.set_xlim(-fp["core_w"] / 2 - m, fp["core_w"] / 2 + m)
            ax.set_ylim(cy0 - m, cy0 + core_h + m)
            ax.set_title("コア拡大", fontsize=10)
        else:
            ax.set_xlim(-C - 40, C + 40); ax.set_ylim(-C - 40, C + 40)
            ax.set_title("ダイ全体 2500 × 2500 µm（OSS_FRAME_GIO）", fontsize=10)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("x [µm]", fontsize=8); ax.set_ylabel("y [µm]", fontsize=8)

    _, core_h = bands(fp)
    lo, hi = opening(rects, fp["core_w"])
    usable = fp["row_w"] - len(fp["tap_x"]) * fp["tap_w"] - (len(fp["tap_x"]) - 1) * fp["pri_w"]
    txt = (f"コア {fp['core_w']:.0f} × {core_h:.0f} µm  "
           f"(幅 {fp['core_w']:.0f} での開口 {hi-lo:.0f} µm に対し {hi-lo-core_h:.0f} µm の余裕)   |   "
           f"行 {fp['n_row']} 本 × {fp['row_h']} µm、行幅 {fp['row_w']:.1f} µm "
           f"({fp['row_w']/SITE:.0f} サイト)、実効 {usable:.1f} µm/行 "
           f"→ セル幅総和 3,964 µm で充填率 {3964/(fp['n_row']*usable)*100:.0f} %   |   "
           f"TAP2 列 x = {', '.join(f'{t:.1f}' for t in fp['tap_x'])} (行ローカル)")
    fig.suptitle("TD4 フロアプラン案", fontsize=13, y=0.985)
    fig.text(0.5, 0.035, txt, ha="center", fontsize=8.2)
    fig.text(0.5, 0.010,
             "赤 = TAP2（M2 電源コラム） / 薄赤 = TAP 直後の優先 M2 コリドー(FILL2) / "
             "青 = 標準セル行 / 橙 = REG8x16 / 紫 = マクロの信号ピン / 緑 = VDD M1 タップ",
             ha="center", fontsize=7.5, color="#555")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    fig.subplots_adjust(bottom=0.10, top=0.93)
    fig.savefig(a.out, dpi=150)
    print(f"wrote {a.out}")
    print(f"  コア {fp['core_w']:.0f} x {core_h:.0f}   開口 {lo:.0f}..{hi:.0f} ({hi-lo:.0f})")
    print(f"  行スタック x {-fp['core_w']/2:.1f}..{-fp['core_w']/2+fp['row_w']:.1f}  "
          f"マクロ x {-fp['core_w']/2+fp['row_w']+fp['macro_gap']:.1f}..{fp['core_w']/2:.1f}")
    print(f"  実効幅 {usable:.1f} um/行 x {fp['n_row']} = {usable*fp['n_row']:.1f} um  "
          f"(必要 3,964 um, 充填率 {3964/(fp['n_row']*usable)*100:.0f}%)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""place_logo.py -- 空いているところに OpenSUSI のロゴを置く（チップ step4）。

    layout/chip/step3_top_pins.gds + lef/opensusi_logo.txt
 -> layout/chip/step4_final.gds

## 塗りつぶしではなく**独立したドット**で描く

5.0 µm 格子の ON セルを 1 個ずつ **3.0 x 3.0 µm の M2** にする。隣とは:

    ドット 3.0 µm          = M2 の最小幅ちょうど
    上下左右の隣            = 5.0 - 3.0 = 2.0 µm = M2 の最小間隔ちょうど
    斜めの隣                = sqrt(2) x 2.0 = 2.83 µm、十分

どちらの検査も「**未満**」を違反とするので、ちょうどは通る（配線と同じ流儀）。
移植元（I2C）は最初 5 µm の塗りつぶしで描いて斜めの角が触れ、手で直している。
ドットならその場合が原理的に無い。

## 置き場所と縮尺

TD4 のコアは開口をほぼ埋めているので、移植元（SCLK_SPI）のように
1,583 x 313 µm のロゴ全体を置く余白は無い。チップ全体で**いちばん広い空き**は
コア右下の **380 x 210 µm**（マクロ REG8x16 の下、行の右側）で、実測で求めた。

そこに収まるよう、ビットマップから**紋章だけ**（0〜64 列）を切り出して
**2:1 に縮約**する（2x2 のどれかが ON なら ON）。結果 33 x 32 セル =
165 x 160 µm。文字の "OpenSUSI" まで入れると 5:1 まで縮めることになり、
その縮尺では字が潰れて読めない（実験済み）。

ロゴ単体で DRC を掛けてから置き、置いたあとにチップ全体をもう一度見て
**新しい違反が 1 件も出ていない**ことを確かめる。ロゴは違反 1 件の価値も無い。

  usage: python3 scripts/pnr/place_logo.py [--scale 2] [--cols 0:64] [-o OUT]
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("TD4_MACRO_MODE", "portrait")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402

IN_GDS = os.path.join(cfg.CHIP, "step3_top_pins.gds")
OUT_GDS = os.path.join(cfg.CHIP, "step4_final.gds")
BITMAP = os.path.join(cfg.ROOT, "lef", "opensusi_logo.txt")

M2_LAYER = (20, 0)
M2_WMIN, M2_SMIN = 3.0, 2.0
PITCH = M2_WMIN + M2_SMIN        # 5.0 µm
DOT = M2_WMIN                    # 3.0 µm
LOGO_CELL = "OPENSUSI_LOGO"

# チップでいちばん広い空き（`step3` に対する実測。最大長方形は
# 380 x 210 µm）。マクロの下、行の右側、GND ライザ 2 本（x 405.45 と
# 794.25）の間。
AREA = (410.0, -680.0, 790.0, -470.0)


def read_bitmap(path):
    """`#` = ON、`.` = OFF。コメントは `%`（`#` は ON セルなので使えない）。"""
    rows = [l.rstrip("\n") for l in open(path, encoding="utf-8")
            if not l.startswith("%") and l.strip()]
    bad = {ch for r in rows for ch in r} - {"#", "."}
    if bad:
        raise SystemExit(f"{path}: 想定外の文字 {sorted(bad)}")
    w = max(len(r) for r in rows)
    return [r.ljust(w, ".") for r in rows], w, len(rows)


def crop_scale(rows, w, h, c0, c1, k):
    """列 c0..c1 を切り出して k:1 に縮約（2x2 のどれかが ON なら ON）。"""
    out = []
    for j in range(0, h, k):
        out.append("".join(
            "#" if any(rows[jj][cc] == "#"
                       for jj in range(j, min(j + k, h))
                       for cc in range(c, min(c + k, c1 + 1)))
            else "."
            for c in range(c0, c1 + 1, k)))
    while out and "#" not in out[-1]:
        out.pop()
    while out and "#" not in out[0]:
        out.pop(0)
    return out, len(out[0]), len(out)


def build_logo_cell(layout, rows, w, h):
    cell = layout.create_cell(LOGO_CELL)
    li = layout.layer(*M2_LAYER)
    dbu = layout.dbu
    m = (PITCH - DOT) / 2.0
    n = 0
    for r, line in enumerate(rows):
        y = (h - 1 - r) * PITCH + m
        for c, ch in enumerate(line):
            if ch != ".":
                x = c * PITCH + m
                cell.shapes(li).insert(db.DBox(x, y, x + DOT, y + DOT).to_itype(dbu))
                n += 1
    return cell, n


def drc(region, dbu, label):
    bad = []
    for kind, minv in (("width", M2_WMIN), ("space", M2_SMIN)):
        res = (region.width_check(int(round(minv / dbu))) if kind == "width"
               else region.space_check(int(round(minv / dbu))))
        for e in res.each():
            b = e.bbox()
            bad.append((kind, round((b.left + b.right) / 2 * dbu, 2),
                        round((b.bottom + b.top) / 2 * dbu, 2)))
    print(f"  {'ok  ' if not bad else 'FAIL'} {label}: M2 の幅/間隔違反 {len(bad)} 件"
          + (f"（例 {bad[:3]}）" if bad else ""))
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--in-gds", default=IN_GDS)
    ap.add_argument("-o", "--out", default=OUT_GDS)
    ap.add_argument("-b", "--bitmap", default=BITMAP)
    ap.add_argument("--scale", type=int, default=2, help="k:1 に縮約（既定 2）")
    ap.add_argument("--cols", default="0:64",
                    help="切り出す列（既定 0:64 = 紋章。全部なら 0:316）")
    a = ap.parse_args()

    c0, c1 = (int(v) for v in a.cols.split(":"))
    raw, rw, rh = read_bitmap(a.bitmap)
    rows, w, h = crop_scale(raw, rw, rh, c0, c1, a.scale)
    lw, lh = (w - 1) * PITCH + DOT, (h - 1) * PITCH + DOT
    print(f"ビットマップ {rw} x {rh} -> 列 {c0}..{c1} を {a.scale}:1 で "
          f"{w} x {h} セル = {lw:.1f} x {lh:.1f} µm")

    ly = db.Layout()
    ly.read(a.in_gds)
    top = ly.cell(cfg.CHIP_TOP_CELL)
    if top is None:
        raise SystemExit(f"{cfg.CHIP_TOP_CELL} が {a.in_gds} に無い")
    if ly.cell(LOGO_CELL) is not None:
        raise SystemExit(f"{LOGO_CELL} が {a.in_gds} に既にある")

    m2 = ly.layer(*M2_LAYER)
    before = db.Region(top.begin_shapes_rec(m2)).merged()
    cell, ndots = build_logo_cell(ly, rows, w, h)
    print(f"{LOGO_CELL}: {DOT} x {DOT} µm のドット {ndots} 個（{PITCH} µm 格子）")
    print("\nロゴ単体")
    bad = drc(db.Region(cell.begin_shapes_rec(m2)), ly.dbu, LOGO_CELL)

    ax0, ay0, ax1, ay1 = AREA
    if lw > ax1 - ax0 or lh > ay1 - ay0:
        raise SystemExit(f"ロゴ {lw:.1f} x {lh:.1f} µm が空き "
                         f"{ax1-ax0:.1f} x {ay1-ay0:.1f} µm に入らない")
    x = (ax0 + ax1) / 2.0 - lw / 2.0
    y = (ay0 + ay1) / 2.0 - lh / 2.0
    top.insert(db.CellInstArray(cell.cell_index(),
                                db.Trans(db.Vector(int(round(x / ly.dbu)),
                                                   int(round(y / ly.dbu))))))
    print(f"\n置いた場所 ({x:.1f}, {y:.1f}) - ({x+lw:.1f}, {y+lh:.1f})"
          f"   空き {AREA}")

    # 置いたあと、チップ全体で**新しい**違反が出ていないこと
    after = db.Region(top.begin_shapes_rec(m2)).merged()
    print("\nチップ全体（置く前 / 置いた後）")
    b0 = drc(before, ly.dbu, "step3")
    b1 = drc(after, ly.dbu, "step4")
    new = [v for v in b1 if v not in b0]
    if bad or new:
        for v in new:
            print(f"  PROBLEM: 新しい違反 {v}")
        raise SystemExit("ロゴのせいで DRC が増えた -- 何も書かない")

    ly.write(a.out)
    print(f"\nwrote {os.path.relpath(a.out, cfg.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

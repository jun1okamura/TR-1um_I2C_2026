#!/usr/bin/env python3
"""セル境界（prBoundary）とピンが配置グリッドに乗っているかを確認する

  usage: python3 scripts/pin_grid_check.py lef/TR-1um_STDCELL.gds [--pitch 5.4] [--offset 2.7]

確認するもの:

  1. **M2 ピンの x 座標**が prBoundary の左端から
     `offset + n*pitch` に乗っているか（既定 2.7 + n*5.4）。
     M2 は縦配線なので、この x がそのまま配線トラックになる。
  2. prBoundary の**幅と高さがピッチの倍数**か。
     幅が倍数でないと、隣に置いたセルの原点がグリッドから外れ、
     そのセルのピンが全部トラックから落ちる。
     **これを合否に数えるのは「標準セル行に置くセル」（高さ = 行高）だけ。**
     行高と違うセルはマクロ／アレイとみなし、座標を明示して置くので情報として出すだけ。
  3. 標準セル行の**高さが揃っている**か（最頻値を行高とみなす）。
  4. ピン図形の幅が揃っているか。

レイヤ: prBoundary = (235,0) / M2 ピン = (49,1) / M2 = (20,0)
"""
from __future__ import annotations
import argparse, sys
from collections import Counter, defaultdict

try:
    import gdstk
except ImportError:
    sys.exit("pip install gdstk --break-system-packages")

BOUND, PINL = (235, 0), (49, 1)
SKIP_PREFIX = ("$$$",)
SKIP_EXACT = {"cont_n", "via_1", "via_1$1"}
EPS = 1e-6


def boundary(cell, name):
    """自前に無ければ配下を展開して prBoundary を求める。"""
    src = [p for p in cell.polygons if (p.layer, p.datatype) == BOUND]
    if not src:
        flat = cell.copy("_f_" + name)
        flat.flatten()
        src = [p for p in flat.polygons if (p.layer, p.datatype) == BOUND]
    if not src:
        return None
    xs = [v for p in src for v in (p.bounding_box()[0][0], p.bounding_box()[1][0])]
    ys = [v for p in src for v in (p.bounding_box()[0][1], p.bounding_box()[1][1])]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("--pitch", type=float, default=5.4)
    ap.add_argument("--offset", type=float, default=2.7, help="prBoundary 左端からの最初のトラック")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}

    def on_track(v):
        k = (v - a.offset) / a.pitch
        return abs(k - round(k)) < EPS

    def on_pitch(v):
        return abs(v / a.pitch - round(v / a.pitch)) < EPS

    heights = defaultdict(list)
    pin_w = Counter()
    no_bound = []
    rows = []
    cells_info = []      # (name, box, w, h, rel, off, size_ok)

    for name in sorted(cells):
        if name.startswith(SKIP_PREFIX) or name in SKIP_EXACT:
            continue
        cell = cells[name]
        b = boundary(cell, name)
        if b is None:
            no_bound.append(name)
            continue
        w, h = b[2] - b[0], b[3] - b[1]
        heights[round(h, 3)].append(name)

        pins = [p for p in cell.polygons if (p.layer, p.datatype) == PINL]
        rel = set()
        for p in pins:
            bb = p.bounding_box()
            rel.add(round((bb[0][0] + bb[1][0]) / 2 - b[0], 4))
            pin_w[round(bb[1][0] - bb[0][0], 2)] += 1
        off = sorted(v for v in rel if not on_track(v))
        size_ok = on_pitch(w) and on_pitch(h)
        cells_info.append((name, b, w, h, rel, off, size_ok))
        rows.append((name, w, h, len(rel), not off, size_ok))

    print(f"{a.gds}   トラック = {a.offset} + n x {a.pitch} um")
    print("=" * 78)
    if a.verbose:
        print(f"{'cell':12} {'W':>8} {'H':>8} {'M2pin':>5}  ピン  寸法")
        for n, w, h, np_, pok, sok in rows:
            print(f"{n:12} {w:8.1f} {h:8.1f} {np_:5}  {'OK' if pok else '× '}   {'OK' if sok else '×'}")
        print("-" * 78)

    row_h = max(heights, key=lambda k: len(heights[k]))
    # 行高と一致するセルだけを「行に置くセル」として合否に数える
    bad_pin, bad_size, info_pin, info_size = [], [], [], []
    for name, b, w, h, rel, off, size_ok in cells_info:
        in_row = abs(h - row_h) < EPS
        if off:
            (bad_pin if in_row else info_pin).append((name, b, off))
        if not size_ok:
            (bad_size if in_row else info_size).append((name, w, h))
    print(f"標準セル行高（最頻値）: {row_h} um = {row_h / a.pitch:.3f} x pitch"
          f"   … {len(heights[row_h])} セル")
    other = {k: v for k, v in heights.items() if k != row_h}
    if other:
        print("行高が違うセル:")
        for k in sorted(other):
            tag = "★ 行に置けない" if len(other[k]) <= 2 and k < 100 else "（マクロ／アレイ）"
            print(f"   {k:8.1f} um : {other[k]}   {tag}")
    print()
    print(f"M2 ピン幅: {dict(sorted(pin_w.items()))}")
    print()

    ng = 0
    print(f"--- 行に置くセル（高さ {row_h}）: {len(heights[row_h])} 個 ---")
    if bad_pin:
        ng += len(bad_pin)
        print("★ M2 ピンがトラックから外れている")
        for n, b, off in bad_pin:
            print(f"   {n:12} prBoundary x0={b[0]:7.2f}   外れている相対 x = {off}")
    else:
        print("  M2 ピン: 全部トラックに乗っている")
    if bad_size:
        print("★ prBoundary の寸法がピッチの倍数でない")
        for n, w, h in bad_size:
            wt = "" if on_pitch(w) else f" 幅 {w}({w/a.pitch:.3f}x) ★ 隣接セルのトラックが崩れる"
            ht = "" if on_pitch(h) else f" 高 {h}({h/a.pitch:.3f}x)"
            print(f"   {n:12}{wt}{ht}")
            ng += 1
    else:
        print("  prBoundary 寸法: 全部ピッチの倍数")

    if info_pin or info_size:
        print()
        print("--- マクロ／アレイ（行高と違うので座標指定で置く。合否には数えない）---")
        for n, b, off in info_pin:
            print(f"   {n:12} M2 ピンの相対 x = {off}（prBoundary x0={b[0]}）")
        for n, w, h in info_size:
            wt = "" if on_pitch(w) else f" 幅 {w}({w/a.pitch:.3f}x)"
            ht = "" if on_pitch(h) else f" 高 {h}({h/a.pitch:.3f}x)"
            print(f"   {n:12}{wt}{ht}")
    if no_bound:
        print()
        print(f"prBoundary が見つからないセル: {no_bound}")

    print()
    print("=" * 78)
    print("判定: OK（作り直してよい）" if ng == 0 else f"判定: 要修正 {ng} 件")
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()

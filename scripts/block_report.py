#!/usr/bin/env python3
"""階層セル（REG4x16 など）を GDS から実測してレポートする。

  usage: python3 scripts/block_report.py lef/TR-1um_STDCELL.gds REG4x16

- 参照を再帰展開して葉セルの員数・配置を数える
- セル境界 (235,0) の和からブロックの実フットプリントを出す（N-well のはみ出しは除く）
- 列（ビット線）と行（ワードライン）の整合をチェックする
- Tr 数と bit 単価を出す
"""
from __future__ import annotations
import argparse, collections, sys

try:
    import gdstk, numpy as np
except ImportError:
    sys.exit("pip install gdstk numpy --break-system-packages")

BOUND, NWELL, POLY, PIMP, NIMP, PIN = (235, 0), (140, 0), (8, 1), (3, 1), (3, 2), (49, 1)


def sel(cell, ld):
    return [p for p in cell.polygons if (p.layer, p.datatype) == ld]


def devices(cell):
    poly, nw = sel(cell, POLY), sel(cell, NWELL)
    n = 0
    for ld, op in ((PIMP, "and"), (NIMP, "not")):
        act = gdstk.boolean(sel(cell, ld), nw, op, precision=1e-3)
        n += len(gdstk.boolean(poly, act, "and", precision=1e-3))
    return n


def walk(cells, cell, M=None, out=None):
    M = np.eye(3) if M is None else M
    out = [] if out is None else out
    for r in cell.references:
        rep = r.repetition
        offs = list(rep.get_offsets()) if rep is not None else []
        if not offs:
            offs = [(0.0, 0.0)]
        for ox, oy in offs:
            a = r.rotation or 0.0
            c, s = np.cos(a), np.sin(a)
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
            F = np.diag([1.0, -1.0, 1.0]) if r.x_reflection else np.eye(3)
            T = np.array([[1, 0, r.origin[0] + ox], [0, 1, r.origin[1] + oy], [0, 0, 1]])
            M2 = M @ T @ R @ F
            if r.cell.references:
                walk(cells, r.cell, M2, out)
            else:
                out.append((r.cell.name, M2))
    # 自前ポリゴンを持つ中間セル（ADDBUF など）も葉として数える
    return out


def placed_box(cells, name, M):
    c = cells[name]
    ps = sel(c, BOUND)
    bb = ps[0].bounding_box() if ps else c.bounding_box()
    pts = np.array([[bb[0][0], bb[0][1], 1], [bb[1][0], bb[0][1], 1],
                    [bb[1][0], bb[1][1], 1], [bb[0][0], bb[1][1], 1]]).T
    q = (M @ pts)[:2]
    return q[0].min(), q[1].min(), q[0].max(), q[1].max()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds"); ap.add_argument("block")
    ap.add_argument("--bits", type=int, default=64, help="ブロックのビット数（単価計算用）")
    a = ap.parse_args()

    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}
    if a.block not in cells:
        sys.exit(f"{a.block} not found")
    top = cells[a.block]

    # 直下の構成
    print(f"=== {a.block} の構成 ===")
    for r in top.references:
        bb = r.cell.bounding_box()
        print(f"  {r.cell.name:<10} org=({r.origin[0]:7.1f},{r.origin[1]:7.1f}) "
              f"rot={np.degrees(r.rotation or 0):4.0f} xrefl={str(r.x_reflection):<5} "
              f"({bb[1][0]-bb[0][0]:6.1f} x {bb[1][1]-bb[0][1]:6.1f})")

    leaves = [(n, M) for n, M in walk(cells, top) if not n.startswith("via")]
    boxes = collections.defaultdict(list)
    for n, M in leaves:
        boxes[n].append(placed_box(cells, n, M))

    # 自前ポリゴンだけを持つ中間セル（ADDBUF 等）を拾う
    for r in top.references:
        if r.cell.polygons and sel(r.cell, BOUND):
            a_ = r.rotation or 0.0
            c, s = np.cos(a_), np.sin(a_)
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
            F = np.diag([1.0, -1.0, 1.0]) if r.x_reflection else np.eye(3)
            T = np.array([[1, 0, r.origin[0]], [0, 1, r.origin[1]], [0, 0, 1]])
            boxes[r.cell.name].append(placed_box(cells, r.cell.name, T @ R @ F))

    print(f"\n=== 葉セル員数と占有範囲 ===")
    xs, ys, tr_tot = [], [], 0
    for n in sorted(boxes):
        bs = boxes[n]
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
        xs += [x0, x1]; ys += [y0, y1]
        tr = devices(cells[n]); tr_tot += tr * len(bs)
        print(f"  {n:<9} x{len(bs):3d}  {tr:3d}Tr  x {x0:8.1f}..{x1:7.1f}  y {y0:8.1f}..{y1:7.1f}")

    W, H = max(xs) - min(xs), max(ys) - min(ys)
    print(f"\n=== フットプリント（セル境界 235/0 基準、N-well のはみ出しは含まない）===")
    print(f"  {min(xs):.1f}..{max(xs):.1f} x {min(ys):.1f}..{max(ys):.1f}"
          f"  = {W:.1f} x {H:.1f} um = {W*H:,.0f} um2 = {W*H/1e6:.3f} mm2")
    print(f"  Tr 合計 {tr_tot:,}  ->  {tr_tot/a.bits:.1f} Tr/bit")
    print(f"  {a.bits}bit -> {W*H/a.bits:,.0f} um2/bit")

    # 列・行の整合
    def col(n): return sorted({round(b[0], 1) for b in boxes.get(n, [])})
    def rowc(n): return sorted(round((b[1] + b[3]) / 2, 2) for b in boxes.get(n, []))
    print(f"\n=== 整合チェック ===")
    cells_cols, buf_cols = col("TLAT"), col("REGBUF")
    if cells_cols and buf_cols:
        ok = cells_cols == buf_cols
        print(f"  ビット列 x: セル {cells_cols}")
        print(f"            バッファ {buf_cols}   -> {'一致' if ok else '★不一致（ビット線が通らない）'}")
    ra, rd = rowc("TLAT"), rowc("DEC0")
    if ra and rd:
        ra = sorted(set(ra))
        d = [round(rd[i] - ra[i], 2) for i in range(min(len(ra), len(rd)))]
        pa = round(ra[1] - ra[0], 2) if len(ra) > 1 else 0
        pd = round(rd[1] - rd[0], 2) if len(rd) > 1 else 0
        print(f"  行 {len(ra)} 行 / デコーダ {len(rd)} 行、ピッチ {pa} / {pd}")
        print(f"  行中心のずれ {min(d)}..{max(d)} um  -> "
              f"{'全行そろっている' if max(d)-min(d) < 0.01 and abs(d[0]) < 0.01 else '★ずれあり'}")

    # ピン
    print(f"\n=== ピン ===")
    lbl = [l.text for l in top.labels]
    print(f"  {a.block} 直下のラベル: {lbl if lbl else '(なし) ★トップのピン未定義'}")
    for r in top.references:
        p = [l.text for l in r.cell.labels if l.layer == PIN[0]]
        print(f"  {r.cell.name:<10} (49,1)ラベル: {p if p else '(なし)'}")


if __name__ == "__main__":
    main()

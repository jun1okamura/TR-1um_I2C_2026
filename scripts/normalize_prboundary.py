#!/usr/bin/env python3
"""normalize_prboundary.py -- セルの中身ごと平行移動して prBoundary の左下を
原点 (0,0) に合わせる。

  usage: python3 scripts/normalize_prboundary.py lef/TR-1um_STDCELL.gds REG8x16 REG4x16
         python3 scripts/normalize_prboundary.py lef/TR-1um_STDCELL.gds --all -n

なぜ要るか: `REG8x16` / `REG4x16` の prBoundary は (-86.4, -54.6) から始まって
いた。セル原点と境界の左下がずれていると、

  * 配置スクリプトが「(x, y) に置けば prBoundary が (x, y) に来る」と
    素直に書けず、セルごとのオフセット表を持ち回ることになる
  * LEF は `FOREIGN <name> 86.400 54.600 ;` でずれを表現するが、
    **これを読み落とすツールは 86 µm ずれた場所にセルを描く**
  * 階層の親から見て子の原点がばらばらだと、目視での突き合わせが効かない

やること: 対象セル**自身の**ポリゴン・ラベル・パス・参照を (dx, dy) だけ動かす。
**子セルの中身は触らない**（親の参照原点が動くので相対位置は保たれる）。
回路は変わらない。変わるのは座標系だけ。

検証: 移動前に平坦化した全ポリゴン／全ラベルを (dx, dy) ずらしたものと、
移動後に平坦化したものが**完全に一致する**ことを確かめてから書く。
"""
from __future__ import annotations
import argparse, collections, sys

import gdstk

BOUND = (235, 0)


def prb(cell):
    p = [q for q in cell.polygons if (q.layer, q.datatype) == BOUND]
    if not p:
        return None
    xs = [v for q in p for v in (q.bounding_box()[0][0], q.bounding_box()[1][0])]
    ys = [v for q in p for v in (q.bounding_box()[0][1], q.bounding_box()[1][1])]
    return (round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4))


def fingerprint(cell):
    """平坦化した幾何とラベルの指紋。平行移動の検証だけに使う。"""
    polys = collections.Counter()
    for q in cell.get_polygons():
        b = q.bounding_box()
        polys[(q.layer, q.datatype, round(b[0][0], 4), round(b[0][1], 4),
               round(b[1][0], 4), round(b[1][1], 4), len(q.points))] += 1
    labs = collections.Counter()
    for l in cell.get_labels():
        labs[(l.layer, l.texttype, l.text,
              round(l.origin[0], 4), round(l.origin[1], 4))] += 1
    return polys, labs


def shifted(fp, dx, dy):
    polys, labs = fp
    p2 = collections.Counter({(l, d, x0 + dx, y0 + dy, x1 + dx, y1 + dy, n): k
                              for (l, d, x0, y0, x1, y1, n), k in polys.items()})
    l2 = collections.Counter({(l, t, s, x + dx, y + dy): k
                              for (l, t, s, x, y), k in labs.items()})
    return p2, l2


def round_counter(c, nd=4):
    return collections.Counter({tuple(round(v, nd) if isinstance(v, float) else v
                                      for v in k): n for k, n in c.items()})


def move(cell, dx, dy):
    for q in cell.polygons:
        q.translate(dx, dy)
    for l in cell.labels:
        l.origin = (l.origin[0] + dx, l.origin[1] + dy)
    for p in cell.paths:
        p.translate(dx, dy)
    for r in cell.references:
        r.origin = (r.origin[0] + dx, r.origin[1] + dy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("cells", nargs="*", help="対象セル名。--all で prBoundary が "
                                             "原点にない全セル")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("-o", "--out", default=None, help="既定は上書き")
    ap.add_argument("-n", "--dry-run", action="store_true")
    a = ap.parse_args()

    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}

    # **親を持つセルは動かせない。** 中身をずらすと親から見た位置がその分
    # 動いてしまう（親の参照原点を逆にずらせば相殺できるが、同じセルを複数の
    # 親が違う向きで参照していることがあるので、黙ってやるべき話ではない）。
    parents = collections.defaultdict(set)
    for c in lib.cells:
        for r in c.references:
            parents[r.cell.name].add(c.name)

    targets = list(a.cells)
    if a.all:
        targets = sorted(n for n, c in cells.items()
                         if prb(c) and (abs(prb(c)[0]) > 1e-6 or abs(prb(c)[1]) > 1e-6))
    if not targets:
        print("対象なし（すべて原点に乗っている）")
        return 0

    ng = 0
    for name in targets:
        c = cells.get(name)
        if c is None:
            print(f"  ! {name} が GDS に無い")
            ng += 1
            continue
        if parents.get(name):
            print(f"  ! {name} は {sorted(parents[name])} から参照されている。"
                  f"中身をずらすと親の中で位置が動くので触らない")
            ng += 1
            continue
        b = prb(c)
        if b is None:
            print(f"  ! {name} は自前の prBoundary (235,0) を持たない。"
                  f"中身をずらすと親から見た位置が変わるので触らない")
            ng += 1
            continue
        dx, dy = -b[0], -b[1]
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            print(f"  {name:10s} すでに原点 (0,0)。そのまま")
            continue

        before = fingerprint(c)
        move(c, dx, dy)
        after = fingerprint(c)
        want = shifted(before, dx, dy)
        if round_counter(after[0]) != round_counter(want[0]):
            print(f"  ! {name}: 移動後の幾何が一致しない")
            ng += 1
            continue
        if round_counter(after[1]) != round_counter(want[1]):
            print(f"  ! {name}: 移動後のラベルが一致しない")
            ng += 1
            continue
        nb = prb(c)
        if abs(nb[0]) > 1e-9 or abs(nb[1]) > 1e-9:
            print(f"  ! {name}: 移動後も prBoundary が {nb[:2]}")
            ng += 1
            continue
        print(f"  {name:10s} ({b[0]:+.1f}, {b[1]:+.1f}) → (0, 0)   "
              f"移動量 ({dx:+.1f}, {dy:+.1f})   "
              f"{nb[2]-nb[0]:.1f} x {nb[3]-nb[1]:.1f} µm   "
              f"参照 {len(c.references)} / ポリゴン {len(c.polygons)} / "
              f"ラベル {len(c.labels)}")

    if ng:
        print(f"  ** {ng} 件 NG。書かない")
        return 1
    if a.dry_run:
        print("（--dry-run なので書いていない）")
        return 0
    out = a.out or a.gds
    lib.write_gds(out)
    print(f"wrote {out}")
    print("  ** LEF は座標が変わる（FOREIGN が 0 になる）ので "
          "scripts/mklef.py を回し直すこと")
    return 0


if __name__ == "__main__":
    sys.exit(main())

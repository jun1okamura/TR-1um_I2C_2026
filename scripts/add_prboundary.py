#!/usr/bin/env python3
"""add_prboundary.py -- 階層マクロのトップに prBoundary (235,0) を入れる。

  usage: python3 scripts/add_prboundary.py lef/TR-1um_STDCELL.gds REG8x16 REG4x16
         python3 scripts/add_prboundary.py lef/TR-1um_STDCELL.gds --all   # 候補を列挙のみ

配下のセルが持つ (235,0) を展開してマージし、**穴の無い矩形 1 枚**になることを
確かめたうえで、同じ矩形をトップセル自身に 1 枚描く。

なぜ要るか
  `scripts/mklef.py` の `hier_bound()` は配下から外形を合成するので LEF の SIZE は
  自前の (235,0) が無くても正しい。しかし
    * それ以外のツール（KLayout の素の cell.bbox() など）は全レイヤ bbox を採る。
      REG8x16 では N-well (140,0) が左 6.3 / 下 4.0 um はみ出すので 405.9 x 937.0 と
      6.3 x 4.0 um 大きく見積もる
    * 子セルを差し替えて (235,0) が落ちても、合成された和は黙って縮む。
      トップに 1 枚あれば「トップ == 子の和」が検査可能な不変条件になる
  子セル側は単体でも行に置くので残す。完全一致の矩形なので重複の副作用は無い。
"""
from __future__ import annotations
import argparse, sys
import klayout.db as db

BOUND = (235, 0)


def union(ly, cell, li):
    r = db.Region(cell.begin_shapes_rec(li))
    r.merge()
    return r


def check(ly, cell, li):
    """(矩形, 理由) — 入れて良いなら矩形、駄目なら None と理由。"""
    u = ly.dbu
    own = cell.shapes(li).size()
    if own:
        return None, f"既にトップに (235,0) が {own} 個ある"
    r = union(ly, cell, li)
    if r.count() == 0:
        return None, "配下にも (235,0) が無い"
    if r.count() != 1:
        return None, f"配下の和がポリゴン {r.count()} 枚で矩形 1 枚にならない"
    b = r.bbox()
    if abs(r.area() - b.area()) > 0:
        return None, (f"配下の和に穴/欠けがある "
                      f"(面積 {r.area()*u*u:.1f} != bbox {b.area()*u*u:.1f} um2)")
    return b, (f"{b.width()*u:.1f} x {b.height()*u:.1f} um "
               f"@ ({b.left*u:.1f}, {b.bottom*u:.1f})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("cells", nargs="*")
    ap.add_argument("--all", action="store_true", help="候補を列挙して終わる")
    ap.add_argument("-o", "--out", default=None, help="既定は上書き")
    a = ap.parse_args()

    ly = db.Layout(); ly.read(a.gds); u = ly.dbu
    li = ly.layer(*BOUND)

    if a.all or not a.cells:
        print("--- 配下にだけ (235,0) がある階層セル ---")
        for ci in ly.each_cell():
            if ci.is_leaf() or ci.name.startswith(("$$$", "via")):
                continue
            b, why = check(ly, ci, li)
            if b is not None:
                print(f"  {ci.name:<12} {why}")
        return

    changed = []
    for name in a.cells:
        c = ly.cell(name)
        if c is None:
            sys.exit(f"{name} が {a.gds} に無い")
        b, why = check(ly, c, li)
        if b is None:
            print(f"  skip {name:<12} {why}")
            continue
        c.shapes(li).insert(b)
        print(f"  add  {name:<12} {why}")
        changed.append(name)

    if not changed:
        print("変更なし")
        return
    out = a.out or a.gds
    ly.write(out)

    # 書いたものを読み直して「トップ == 配下の和」を確かめる。
    # 配下だけの和は、コピーの上でトップ自身の図形を消してから取る
    # （begin_shapes_rec は自前の図形も含むため）。
    for name in changed:
        v = db.Layout(); v.read(out); vli = v.layer(*BOUND)
        c = v.cell(name)
        own = db.Region(c.shapes(vli)); own.merge()
        c.shapes(vli).clear()
        kids = union(v, c, vli)
        ok = (own ^ kids).is_empty()
        print(f"  検証 {name:<12} トップ {own.count()} 枚 / 配下の和 {kids.count()} 枚 "
              f"-> {'一致' if ok else '不一致'}")
        if not ok:
            sys.exit(f"{name}: トップの (235,0) が配下の和と一致しない")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""2 つのマップ後ネットリストのセル構成を突き合わせる。

  usage: python3 scripts/cmp_cells.py <基準.v> <比較.v>

何のためか: 今回の再合成が V10（実際にテープアウトして SPICE 14/14 PASS した版）
から**どう変わったか**を一目で見るため。セル種ごとの個数と面積の差分を出す。

数が増えていること自体は悪ではない（`.lib` が変わり、RSLATCH が入り、ABC の
ゲートサイジングが効く）。**見るべきは種類の消長**:

  * `RSLATCH` / `MUXDFFRB` が V10 と同じ数あるか
    → 無ければ merge_muxdffrb_rslatch.py がパターンを見つけられていない
  * 同じセルが何十個も増えていないか
    → dedup_gates.py の掛け忘れか、ABC が重複を撒いた（design_notes 108.37）
"""
from __future__ import annotations
import argparse, collections, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def cells_of(path, known):
    txt = re.sub(r"//[^\n]*", "", open(path).read())
    c = collections.Counter()
    for m in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+\\?\S+\s*\(", txt, re.M):
        if m.group(1) in known:
            c[m.group(1)] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref")
    ap.add_argument("new")
    ap.add_argument("--areas", default=f"{HERE}/cell_area.json")
    a = ap.parse_args()
    areas = json.load(open(a.areas))["cells"]
    known = set(areas)
    for p in (a.ref, a.new):
        if not os.path.exists(p):
            print(f"  ** {p} が無いので比較を飛ばす")
            return 0
    r, n = cells_of(a.ref, known), cells_of(a.new, known)
    print(f"  基準 {a.ref}")
    print(f"  比較 {a.new}")
    print(f"  {'セル':<10}{'基準':>6}{'比較':>6}{'差':>6}   {'面積差 [um2]':>12}")
    tot_r = tot_n = 0.0
    for cell in sorted(set(r) | set(n)):
        ar = areas[cell]["area"]
        tot_r += ar * r.get(cell, 0)
        tot_n += ar * n.get(cell, 0)
        d = n.get(cell, 0) - r.get(cell, 0)
        if d == 0 and cell in r:
            print(f"  {cell:<10}{r.get(cell,0):>6}{n.get(cell,0):>6}{'':>6}")
        else:
            print(f"  {cell:<10}{r.get(cell,0):>6}{n.get(cell,0):>6}{d:>+6}   {ar*d:>+12.1f}")
    print(f"  {'計':<10}{sum(r.values()):>6}{sum(n.values()):>6}"
          f"{sum(n.values())-sum(r.values()):>+6}   {tot_n-tot_r:>+12.1f}")
    print(f"  セル面積 {tot_r:,.0f} -> {tot_n:,.0f} um2 "
          f"({(tot_n/tot_r-1)*100:+.1f}%)" if tot_r else "")
    # 気をつけるべき消長
    for cell in ("RSLATCH", "MUXDFFRB"):
        if r.get(cell, 0) and not n.get(cell, 0):
            print(f"  ** {cell} が 1 個も無い。merge_muxdffrb_rslatch.py が"
                  f"パターンを見つけられていない（基準は {r[cell]} 個）")
    for cell in sorted(set(n)):
        d = n.get(cell, 0) - r.get(cell, 0)
        if d >= 10:
            print(f"  ** {cell} が {d} 個増えている。dedup_gates.py の掛け忘れか、"
                  f"ABC が重複を撒いた可能性（design_notes 108.37）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

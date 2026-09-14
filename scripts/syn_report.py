#!/usr/bin/env python3
"""マッピング後のネットリストから面積と所要コア面積を出す。

  usage: python3 scripts/syn_report.py <top> [-n out/<top>.v] [-s out/<top>.stat]

`area_estimate.py` との違い:
  あちらは `abc -g simple` の**抽象ゲート**（`$_AND_` など）を実セルに読み替える
  **見積り**。こちらは `.lib` でマッピングした**実セルそのもの**を数えるので
  読み替えが要らない。ライブラリに無いゲートを勝手に当てはめる余地が無い。

面積の出どころは `scripts/cell_area.json`（GDS の (235,0) abutment box 実測）で
`area_estimate.py` と同じ。Yosys の `stat -liberty` が出す面積とも一致するはず
（`.lib` の area も同じ json から書いている）。
"""
from __future__ import annotations
import argparse, collections, json, os, re, sys

# OSS_FRAME_GIO のコア。パッド内側 1840 x 1840 から四隅の OSS_FRAME_CNR
# （120 x 120 um x 4）を欠いた分が実際に置ける面積。
CORE_W = CORE_H = 1840.0
CORE_AREA = CORE_W * CORE_H - 4 * 120.0 * 120.0      # = 3,328,000 um2
ROW_H = 59.4
HERE = os.path.dirname(os.path.abspath(__file__))


def cells_of(net):
    """マップ後 Verilog からセルのインスタンスを数える"""
    txt = open(net).read()
    txt = re.sub(r"//[^\n]*", "", txt)
    known = set(json.load(open(f"{HERE}/cell_area.json"))["cells"])
    c = collections.Counter()
    for m in re.finditer(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+\\?\S+\s*\(", txt, re.M):
        if m.group(1) in known:
            c[m.group(1)] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("top")
    ap.add_argument("-n", "--net", default=None)
    ap.add_argument("--areas", default=f"{HERE}/cell_area.json")
    ap.add_argument("--brief", action="store_true", help="1 行にまとめる")
    a = ap.parse_args()
    net = a.net or f"out/{a.top}.v"
    A = json.load(open(a.areas))
    areas = A["cells"]
    c = cells_of(net)
    if not c:
        sys.exit(f"{net} に既知のセルが見つからない")

    seq = {"DFF", "DFFRB", "DFFS", "MUXDFFRB", "RSLATCH"}
    tot = sum(areas[k]["area"] * v for k, v in c.items())
    wid = sum(areas[k]["w"] * v for k, v in c.items())
    nff = sum(v for k, v in c.items() if k in seq)
    ncomb = sum(v for k, v in c.items() if k not in seq)

    if a.brief:
        print(f"  {a.top:<16}{sum(c.values()):>4} セル "
              f"(FF {nff} / 組合せ {ncomb})  {tot:>10,.0f} um2 = {tot/1e6:.3f} mm2")
        return
    print(f"--- {a.top}: マッピング後の実セル（{net}）---")
    for k, v in sorted(c.items(), key=lambda x: -areas[x[0]]["area"] * x[1]):
        print(f"  {k:<10}{v:>5}  x {areas[k]['area']:>8.1f} = {areas[k]['area']*v:>10,.0f} um2")
    print(f"  {'合計':<10}{sum(c.values()):>5}     "
          f"{'':>10}   {tot:>10,.0f} um2 = {tot/1e6:.3f} mm2")
    print(f"FF {nff} / 組合せ {ncomb} / "
          f"NAND2 換算 {tot/areas['NAND2']['area']:.0f} ゲート")
    print(f"セル幅の総和 {wid:,.0f} um  (行高 {ROW_H} um → 1 行 1840um なら "
          f"{wid/1840:.1f} 行ぶん)")
    core = CORE_AREA
    print(f"コア {CORE_W:.0f} x {CORE_H:.0f} um から四隅を欠いて {core/1e6:.3f} mm2")
    for u in (0.5, 0.6, 0.7, 0.8):
        need = tot / u
        print(f"  util {u:.0%}: {need/1e6:6.3f} mm2  {'OK' if need <= core else 'NG'}")


if __name__ == "__main__":
    main()

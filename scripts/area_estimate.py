#!/usr/bin/env python3
"""Yosys の `stat` 出力を TR-1um STDCELL の実測セル面積に換算する。

usage:
  yowasp-yosys -p "read_verilog *.v; hierarchy -check -top TOP; synth -top TOP -flatten; \
                   abc -g simple; opt_clean; tee -o stat.txt stat"
  python3 scripts/area_estimate.py stat.txt --top TOP [--areas scripts/cell_area.json]

**面積は自前の表を持たない。**`scripts/cell_area.json`（= `scripts/cellinfo.py --areas`
が GDS の (235,0) abutment box から書き出したもの）を読む。ライブラリを直したら

  python3 scripts/cellinfo.py lef/TR-1um_STDCELL.gds \
          --genlib scripts/tr1um.genlib --areas scripts/cell_area.json

を流し直すだけで、この見積りも自動で追従する。
（行高 64.8→59.4 の変更でこのファイルの表だけが取り残され、
  組合せセルの面積を 8.3% 過大に見積もっていたのを直したときの反省。）
"""
from __future__ import annotations
import argparse, collections, json, os, re, sys

# OSS_FRAME_GIO のコア。パッドの内側は 1840 x 1840 だが、四隅の OSS_FRAME_CNR が
# 120 x 120 um ずつ食うので実際に置けるのは 3.33 mm2（内接する最大の正方形は
# 1600 x 1600 = 2.56 mm2）。数字の出どころは scripts/mkleffrm.py が実形状から出したもの。
CORE_W = CORE_H = 1840.0
CORE_AREA = CORE_W * CORE_H - 4 * 120.0 * 120.0      # = 3,328,000 um2
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_AREAS = os.path.join(HERE, "cell_area.json")

# Yosys の内部セル名 -> 実セル名（複数なら合計面積）
MAP = {
    "$_NOT_":    ["INV_X1"],
    "$_BUF_":    ["BUF_X1"],
    "$_NAND_":   ["NAND2"],
    "$_NOR_":    ["NOR2"],
    "$_AND_":    ["AND2_X1"],
    "$_OR_":     ["OR2"],
    "$_XOR_":    ["XOR2"],
    "$_XNOR_":   ["XNOR2"],
    "$_MUX_":    ["MUX2"],
    "$_ANDNOT_": ["INV_X1", "AND2_X1"],
    "$_ORNOT_":  ["INV_X1", "OR2"],
    "$_AOI3_":   ["AND2_X1", "NAND2"],
    "$_OAI3_":   ["OR2", "NAND2"],
    "$_AOI4_":   ["AND2_X1", "NAND2"],
    "$_OAI4_":   ["OR2", "NAND2"],
}
FALLBACK = "AND2_X1"        # 表に無い組合せセルはこれで代用
FF_PLAIN = "DFFRB"          # リセット付き FF
FF_EN = "MUXDFFRB"          # イネーブル付き FF（単一セルで存在する）


def load_areas(path):
    if not os.path.exists(path):
        sys.exit(f"{path} が無い。先に\n"
                 f"  python3 scripts/cellinfo.py lef/TR-1um_STDCELL.gds "
                 f"--genlib scripts/tr1um.genlib --areas scripts/cell_area.json\n"
                 f"を流すこと。")
    doc = json.load(open(path))
    return ({k: v["area"] for k, v in doc["cells"].items()},
            doc.get("row_height", 59.4), doc.get("source", path))


def parse(path: str) -> dict[str, dict[str, int]]:
    txt = open(path).read()
    mods = {}
    for name, body in re.findall(r"=== (\S+) ===\n(.*?)(?=\n===|\Z)", txt, re.S):
        d = {k: int(v) for k, v in re.findall(r"^\s+(\$\S+)\s+(\d+)\s*$", body, re.M)}
        # newer yosys prints "<count>   <cellname>"
        d.update({k: int(v) for v, k in re.findall(r"^\s+(\d+)\s+(\$?[A-Za-z_]\S*)\s*$", body, re.M)
                  if not k.endswith(("wires", "bits", "ports", "cells", "memories"))})
        mods[name] = d
    return mods


def expand(mods, name, mult=1, acc=None):
    acc = collections.Counter() if acc is None else acc
    for k, v in mods.get(name, {}).items():
        if k in mods:
            expand(mods, k, mult * v, acc)
        else:
            acc[k] += mult * v
    return acc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("statfile")
    ap.add_argument("--top", required=True)
    ap.add_argument("--areas", default=DEFAULT_AREAS)
    a = ap.parse_args()

    A, row_h, src = load_areas(a.areas)
    need = {n for v in MAP.values() for n in v} | {FALLBACK, FF_PLAIN, FF_EN}
    missing = sorted(need - set(A))
    if missing:
        print(f"** {a.areas} に無いセル: {', '.join(missing)}", file=sys.stderr)

    def area_of(names):
        return sum(A.get(n, A[FALLBACK]) for n in names)

    mods = parse(a.statfile)
    if a.top not in mods:
        sys.exit(f"top module '{a.top}' not found in {a.statfile}")
    cells = expand(mods, a.top)

    ff = comb = 0
    area = 0.0
    detail = collections.Counter()
    for k, n in cells.items():
        if k == "$scopeinfo":
            continue
        if "DFF" in k or "LATCH" in k:
            ff += n
            names = [FF_EN] if ("DFFE" in k or "CE_" in k) else [FF_PLAIN]
        else:
            comb += n
            names = MAP.get(k, [FALLBACK])
        area += n * area_of(names)
        for nm in names:
            detail[nm] += n

    nand2 = A.get("NAND2", 1.0)
    print(f"--- 面積の出どころ: {a.areas}  (GDS {os.path.basename(src)}, 行高 {row_h} um) ---")
    print(f"--- cell mix ({a.top}) ---")
    for k, n in sorted(cells.items(), key=lambda x: -x[1]):
        if k == "$scopeinfo":
            continue
        nm = "+".join(MAP.get(k, [FALLBACK])) if not ("DFF" in k or "LATCH" in k) else \
             (FF_EN if ("DFFE" in k or "CE_" in k) else FF_PLAIN)
        print(f"  {k:18} {n:6d}  -> {nm}")
    print(f"\n実セル内訳      : " + ", ".join(f"{k} x{v}" for k, v in sorted(detail.items())))
    print(f"FF              : {ff}")
    print(f"combinational   : {comb}")
    print(f"raw cell area   : {area:,.0f} um2 = {area/1e6:.3f} mm2")
    print(f"NAND2 equiv     : {area/nand2:,.0f} gates  (NAND2 = {nand2:.1f} um2)")
    print(f"total cell width: {area/row_h:,.0f} um (row h={row_h} um)")
    core = CORE_AREA
    print(f"\ncore available  : {CORE_W:.0f} x {CORE_H:.0f} um から四隅を欠いて "
          f"{core/1e6:.3f} mm2")
    for u in (0.5, 0.6, 0.7, 0.8):
        need = area / u
        print(f"  util {u:.0%}: {need/1e6:6.3f} mm2  {'OK' if need <= core else 'NG'}")


if __name__ == "__main__":
    main()

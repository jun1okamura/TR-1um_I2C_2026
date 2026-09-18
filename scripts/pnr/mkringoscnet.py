#!/usr/bin/env python3
"""mkringoscnet.py -- RING_OSC の **LVS ソースネットリスト**を書き出す。

  usage: python3 scripts/pnr/mkringoscnet.py [-o OUT]
         # -> layout/chip/simulation/RING_OSC.spice

RING_OSC は RTL から合成したものではなく **xschem の回路図から手で描いた**
ブロックなので、ソース側は回路図を読み下して組み立てる。出どころは

    TR-1um_Async_I2C/ring_osc/RING_OSC.sch   （xschem。V10 で LVS 済み）
    TR-1um_Async_I2C/ring_osc/INV3D.sch      （同）

の 2 つで、**レイアウト抽出は一切見ていない**（FILL2 だけは例外。下記）。

## 回路図（RING_OSC.sch）

リングが 2 本。速い方（R）と遅い方（D）で、段のセルだけが違う:

    x1[0:94]   INV_X1  入力 {FB, R[0:93]} -> 出力 R[0:94]     速いリング
    x1         AND2_X1 (R[94], ENB) -> FB                     発振を止める AND
    x3         INV_X1  FB -> OUT                              出力バッファ
    x54[0:94]  INV3D   入力 {FD, D[0:93]} -> 出力 D[0:94]     遅いリング
    x2         AND2_X1 (D[94], ENB) -> FD
    x4         INV_X1  FD -> OUTD
    x3[0:189] + x5[0:15]   FILL2 x 206                        デキャップ

つまり 1 リング 95 段 + AND 1 段 = 96 段の奇数閉ループ。ENB=0 で FB/FD が
0 に固定されて止まり、ENB=1 で発振する。

## レイアウトの階層との関係

レイアウトは `RING_OSC {INVALL, INVALLD}` -> `INVALL {INV48, INV49}` …と
タイル状に積んであって、回路図には無い中間セルがある。`INV3` は
「INV_X1 1 個 + FILL2 2 個」の 3 サイト幅のタイルで、**論理段としては
インバータ 1 個**。実体数を数えると回路図とぴったり合う:

    INV_X1  97 = 95（速いリング）+ x3 + x4
    INV3D   95 =    （遅いリング）
    AND2_X1  2 = x1 + x2
    FILL2  206 = x3[0:189] + x5[0:15]
    TAP2     8  デバイスを持たない（基板/ウェルのタップだけ）

`lvs_pnr.py` は既定で両側を平坦化して比べるので、こちらは中間セルを作らず
**1 つの `.subckt RING_OSC` に素で並べる**。

## FILL2 の数だけはレイアウトから数える

FILL2 はデキャップで、論理には効かない詰め物。回路図にも 206 個と書いて
あるが、レイアウトを積み直したら数が変わりうるので GDS の実体数を数えて
突き合わせ、食い違ったら止める（`mklvsnet.py` の物理セルと同じ考え方）。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402

SIM_DIR = os.path.join(cfg.ROOT, "lef", "simulation")
OUT_PATH = os.path.join(cfg.CHIP, "simulation", "RING_OSC.spice")

N_STAGE = 95              # 1 リングのインバータ段数（回路図 x1[0:94]）
CELLS = ("INV_X1", "AND2_X1", "FILL2")

# INV3D は回路図から直接。`INV3D.sch` は MP.sym(w=10.2u l=1u) と
# MN.sym(w=3.4u l=1u) を 1 個ずつ、A -> Y のインバータ。ポート順は
# レイアウト側のピン名の並び（A Y gnd vdd）に合わせてある。
INV3D = """.subckt INV3D A Y gnd vdd
MP0 Y A vdd vdd PMOS W=10.2u L=1.0u
MN0 Y A gnd gnd NMOS W=3.4u L=1.0u
.ends INV3D"""


def subckt(cell):
    """`lef/simulation/<cell>.spice` の `.subckt` ブロックをそのまま。"""
    path = os.path.join(SIM_DIR, cell + ".spice")
    txt = open(path, encoding="utf-8").read()
    m = re.search(rf"^\.subckt\s+{cell}\b.*?^\.ends.*$", txt, re.S | re.M)
    if not m:
        raise SystemExit(f".subckt {cell} が {path} に無い")
    return m.group(0).rstrip()


def ports(block):
    """`.subckt` 行のポート列。"""
    return block.splitlines()[0].split()[2:]


def gds_counts(gds=None, cell=None):
    """GDS の実体数（再帰、配列も展開）。"""
    ly = db.Layout()
    ly.read(gds or cfg.RING_OSC_GDS)
    cnt = Counter()

    def walk(c, mult=1):
        for inst in c.each_inst():
            n = inst.cell_inst.size()
            sub = ly.cell(inst.cell_index)
            cnt[sub.name] += mult * n
            walk(sub, mult * n)

    walk(ly.cell(cell or cfg.RING_OSC_CELL))
    return cnt


def build(n_fill):
    """`.subckt RING_OSC …` の本体。"""
    blocks = {c: subckt(c) for c in CELLS}
    p = {c: ports(blocks[c]) for c in CELLS}
    p["INV3D"] = ports(INV3D)

    def call(inst, cell, net):
        """ポート名 -> ネット の辞書から、その subckt の順番で並べる。"""
        return f"{inst} " + " ".join(net[q] for q in p[cell]) + f" {cell}"

    body = []
    for tag, stage_cell, ring, fb, out in (("r", "INV_X1", "R", "FB", "OUT"),
                                           ("d", "INV3D", "D", "FD", "OUTD")):
        body.append(f"* --- {'速い' if tag == 'r' else '遅い'}リング"
                    f"（{stage_cell} x {N_STAGE}）---")
        for k in range(N_STAGE):
            a = fb if k == 0 else f"{ring}{k - 1}"
            y = f"{ring}{k}"
            net = {"A": a, "Y": y, "vdd": "VDD", "vss": "VSS", "gnd": "VSS"}
            body.append(call(f"x{tag}{k}", stage_cell, net))
        body.append(call(f"xand_{tag}", "AND2_X1",
                         {"Y": fb, "A": f"{ring}{N_STAGE - 1}", "B": "ENB",
                          "vdd": "VDD", "vss": "VSS"}))
        body.append(call(f"xbuf_{tag}", "INV_X1",
                         {"A": fb, "Y": out, "vdd": "VDD", "vss": "VSS"}))
        body.append("")

    body.append(f"* --- デキャップ（FILL2 x {n_fill}）---")
    for k in range(n_fill):
        body.append(call(f"xf{k}", "FILL2", {"vdd": "VDD", "vss": "VSS"}))

    return blocks, body


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=OUT_PATH)
    ap.add_argument("--gds", default=None)
    a = ap.parse_args()

    cnt = gds_counts(a.gds)
    want = {"INV_X1": 2 * N_STAGE + 2 - N_STAGE, "INV3D": N_STAGE, "AND2_X1": 2}
    want["INV_X1"] = N_STAGE + 2        # 速いリング 95 + 出力バッファ 2 個
    problems = [f"{c}: GDS {cnt.get(c, 0)} 個 / 回路図 {n} 個"
                for c, n in want.items() if cnt.get(c, 0) != n]
    if problems:
        for q in problems:
            print("  PROBLEM: " + q)
        raise SystemExit("レイアウトと回路図で実体数が合わない")
    n_fill = cnt.get("FILL2", 0)

    blocks, body = build(n_fill)
    header = [
        "* RING_OSC -- LVS ソースネットリスト（設計意図側）",
        "* scripts/pnr/mkringoscnet.py が生成。手で編集しないこと。",
        "*",
        "*   回路図 : TR-1um_Async_I2C/ring_osc/RING_OSC.sch / INV3D.sch",
        f"*   セル   : {os.path.relpath(SIM_DIR, cfg.ROOT)}/*.spice"
        "（INV3D だけ回路図から直接）",
        f"*   FILL2 の個数だけ {os.path.relpath(cfg.RING_OSC_GDS, cfg.ROOT)} から数えた",
        "*",
        f"* 1 リング {N_STAGE} 段 + AND 1 段 = {N_STAGE + 1} 段の奇数閉ループが 2 本。",
        "* 速い方は INV_X1、遅い方は INV3D（同じ 2T だがレイアウトが違う）。",
        "* ENB=0 で FB/FD が 0 に固定されて止まり、ENB=1 で発振する。",
        "* TAP2 はデバイスを持たないので出していない。",
        "",
    ]
    lines = header + [blocks[c] for c in CELLS] + ["", INV3D, "",
                      ".subckt RING_OSC ENB OUT OUTD VDD VSS"] + body + \
        [".ends RING_OSC", ""]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    print(f"  段数      : {N_STAGE} x 2 リング（+ AND 各 1 段）")
    print(f"  INV_X1 {cnt['INV_X1']:4d}  INV3D {cnt['INV3D']:4d}  "
          f"AND2_X1 {cnt['AND2_X1']:3d}  FILL2 {n_fill:4d}  "
          f"TAP2 {cnt.get('TAP2', 0):3d}（デバイス無し）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

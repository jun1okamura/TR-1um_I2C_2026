#!/usr/bin/env python3
"""書き出した .spice がレイアウトと一致するかを、KLayout の比較器で確かめる。

  usage: python3 scripts/lvs_check.py <gds> <top> <spice>

`scripts/mkframespice.py` が出した .spice は「抽出して凍結したもの」なので、
**書き出しの過程でネットやピンを取り違えていないか**を必ず確かめる。
やることは PDK の LVS ランセット（`tech/lvs/05_Compare.lvs`）と同じ:
レイアウトから抽出した網と、.spice を読んだ網を `NetlistComparer` で照合する。

これは「レイアウトが正しいこと」の証明ではない（元が同じなので当然一致する）。
証明するのは**この .spice がレイアウトを取りこぼしなく写していること**。

階層の切り方が両者で違うことがある（REG8x16 は抽出が TLAT8 / TLAT8B /
TLAT128 / REGBUF8 / DEC16 という中間階層を作るのに対し、設計側は
TLAT / DEC2 / REGBUF / ADDBUF の 4 段しか持たない）。そのままでは
circuit 数が合わず不一致になるので `--flat` で両方を潰してから比べる。
"""
from __future__ import annotations
import argparse, sys

import klayout.db as db
import klayout_extract


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds"); ap.add_argument("top"); ap.add_argument("spice")
    ap.add_argument("--flat", action="store_true",
                    help="両方を平坦化してから比較する（階層の切り方が違うとき）")
    a = ap.parse_args()

    l2n = klayout_extract.build(a.gds, a.top)
    lay = l2n.netlist().dup()
    lay.make_top_level_pins()
    lay.combine_devices()
    lay.purge()
    lay.purge_nets()
    if a.flat:
        lay.flatten()

    sch = db.Netlist()
    sch.read(a.spice, db.NetlistSpiceReader())
    sch.make_top_level_pins()
    sch.combine_devices()
    sch.purge()
    sch.purge_nets()
    if a.flat:
        sch.flatten()

    cmp_ = db.NetlistComparer()
    ok = cmp_.compare(lay, sch)

    def count(nl):
        c = nl.circuit_by_name(a.top)
        return (sum(1 for _ in nl.each_circuit()),
                sum(1 for _ in c.each_pin()),
                sum(len(list(x.each_device())) for x in nl.each_circuit()))
    print(f"  レイアウト: circuit {count(lay)[0]} / top pin {count(lay)[1]} / device {count(lay)[2]}")
    print(f"  .spice    : circuit {count(sch)[0]} / top pin {count(sch)[1]} / device {count(sch)[2]}")
    print(("  LVS: **一致**" if ok else "  LVS: **不一致**"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

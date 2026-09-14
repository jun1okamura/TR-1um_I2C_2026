#!/usr/bin/env python3
"""lef/simulation/REG8x16.spice を ngspice 用に直す（M カード -> XM 呼び出し）。

  usage: python3 scripts/char/mkmemsrc.py lef/simulation/REG8x16.spice \
                 -o scripts/char/cells_mem/REG8x16_src.spi

PDK の PMOS/NMOS は `.model` ではなく**サブサーキット**なので、
設計ネットリストの素の `M` カードのままでは ngspice が落ちる。
"""
import argparse, os, re
ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("-o", "--out", required=True)
a = ap.parse_args()
os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
out = [re.sub(r"^M(\w+)(\s)", r"XM\1\2", ln.rstrip("\n")) for ln in open(a.src)]
open(a.out, "w").write("\n".join(out) + "\n")
print(f"wrote {a.out}  ({sum(1 for s in out if s.startswith('XM'))} device lines)")

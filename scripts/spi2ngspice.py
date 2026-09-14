#!/usr/bin/env python3
"""LVS ソースネットリスト -> ngspice で読めるネットリストに変換

  usage: python3 scripts/spi2ngspice.py spice/REG4x16_src.spi > spice/REG4x16_ngspice.spi

LVS 用の `spice/REG4x16_src.spi` は KLayout の LVS ランセットに合わせて
`M<name> D G S B PMOS W=..u L=..u` と書いてある。一方 TR-1um の PDK は
PMOS / NMOS を **サブサーキット**として定義していて（AS/AD/PS/PD を
sdwidth から自動で付けてくれる）、ngspice で使うには `XM` 呼び出しに
しなければならない。ランセット側の `04_Custom.lvs` も
`PREFIX_MAP = {'NMOS'=>'XM','PMOS'=>'XM'}` と、同じ対応を前提にしている。

変換内容はこの 2 つだけ:
  1. `M...` -> `XM...`（サブサーキット呼び出しに）、W=/L= を小文字の w=/l= に
  2. ノード名の角括弧を潰す（`ADD[0]` -> `ADD0`）

回路そのものは一切変えない。
"""
from __future__ import annotations
import re, sys


def sanitize(tok: str) -> str:
    return tok.replace("[", "").replace("]", "")


def convert(path):
    out = []
    for ln in open(path, encoding="utf-8"):
        raw = ln.rstrip("\n")
        s = raw.strip()
        if not s or s.startswith("*"):
            out.append(raw)
            continue
        t = raw.split()
        head = t[0]
        if re.match(r"^M", head, re.I):
            # M<name> D G S B <model> W=..u L=..u  ->  XM<name> ... w= l=
            d, g, sN, b, model = (sanitize(x) for x in t[1:6])
            params = []
            for x in t[6:]:
                if "=" in x:
                    k, v = x.split("=", 1)
                    params.append(f"{k.lower()}={v}")
                else:
                    params.append(x)
            out.append(f"X{head} {d} {g} {sN} {b} {model} " + " ".join(params))
        elif head.lower() in (".subckt",):
            out.append(" ".join([t[0], t[1]] + [sanitize(x) for x in t[2:]]))
        elif re.match(r"^X", head, re.I):
            out.append(" ".join([head] + [sanitize(x) for x in t[1:]]))
        else:
            out.append(raw)
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    print(f"* converted from {src} by scripts/spi2ngspice.py")
    print("* 回路は LVS ソースと同一。XM 呼び出し化とノード名の角括弧除去のみ。")
    for l in convert(src):
        print(l)

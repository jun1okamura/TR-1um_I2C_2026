#!/usr/bin/env python3
"""合成後ネットリストをシミュレーションするための**セルの Verilog モデル**を書き出す。

  usage: python3 mkcellverilog.py -o ../../hdl/rtl/tr1um_cells.v

なぜ要るか:
  `.lib` でマッピングした後のネットリストは `NAND2 U1 (.A(..), .B(..), .Y(..))` の
  ような実セルの羅列になる。これを iverilog で回すには各セルの振る舞いが要る。

出どころ:
  **`cellspec.py` 1 箇所だけ**。ここは `check_comb.py` / `check_seq.py` が
  ngspice で実物と突き合わせている表そのものなので、
  「RTL ≡ マップ後ネットリスト」が iverilog で示せれば、
  ngspice 側の「セル ≡ レイアウト」と繋がって
  **RTL ≡ レイアウト**まで一本の鎖になる。

  遅延は入れない（ゼロ遅延モデル）。タイミングは `.lib` + STA の仕事。
"""
from __future__ import annotations
import argparse, os, sys
import cellspec

HERE = os.path.dirname(os.path.abspath(__file__))


def expr_to_verilog(s):
    """Liberty の式 (`*` AND / `+` OR / `!` NOT / `^` XOR) を Verilog に直す"""
    return s.replace("*", " & ").replace("+", " | ").replace("!", "~").replace("^", " ^ ")


def comb_module(cell, funcs, ports):
    ins = [p for p in ports if p not in funcs]
    L = [f"module {cell} ("]
    L.append("    input  " + ", ".join(ins) + ",")
    L.append("    output " + ", ".join(funcs) + ");")
    for o, f in funcs.items():
        L.append(f"  assign {o} = {expr_to_verilog(f)};")
    L.append("endmodule")
    return "\n".join(L)


def ff_module(cell, spec):
    d = cellspec.SEQ_PINS[cell]
    ins = ["CK"] + d["data"] + d["async"]
    L = [f"module {cell} ("]
    L.append("    input  " + ", ".join(ins) + ",")
    L.append("    output Q, QB);")
    L.append("  reg q;")
    ns = expr_to_verilog(spec["next_state"])
    # 非同期端子。clear は "!RSTB" のような式で来る
    clr = spec.get("clear")
    pre = spec.get("preset")
    sens = ["posedge CK"]
    if clr:
        p = clr.lstrip("!")
        sens.append(("negedge " if clr.startswith("!") else "posedge ") + p)
    if pre:
        p = pre.lstrip("!")
        sens.append(("negedge " if pre.startswith("!") else "posedge ") + p)
    L.append(f"  always @({' or '.join(sens)})")
    body = []
    if clr:
        body.append(f"    if ({expr_to_verilog(clr)}) q <= 1'b0;")
    if pre:
        body.append(f"    {'else ' if clr else ''}if ({expr_to_verilog(pre)}) q <= 1'b1;")
    body.append(f"    {'else ' if (clr or pre) else ''}q <= {ns};")
    L += body
    L.append("  assign Q  = q;")
    L.append("  assign QB = ~q;")
    # `initial` は入れない。RTL 側の FF も初期値を持たないので、
    # 入れると形式等価検証で初期状態が食い違う。実物も電源投入時は不定で、
    # 値は RSTB が決める。
    L.append("endmodule")
    return "\n".join(L)


def latch_module(cell, spec):
    """RSLATCH: S でセット / R でリセットの SR ラッチ"""
    L = [f"module {cell} (input S, R, output Q, QB);"]
    L.append("  reg q;")
    L.append("  always @* begin")
    L.append(f"    if ({expr_to_verilog(spec['clear'])}) q = 1'b0;")
    L.append(f"    else if ({expr_to_verilog(spec['preset'])}) q = 1'b1;")
    L.append("  end")
    L.append("  assign Q  = q;")
    L.append("  assign QB = ~q;")
    L.append("endmodule")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=f"{HERE}/tr1um_cells.v")
    a = ap.parse_args()

    o = ["// TR-1um 標準セルのゼロ遅延 Verilog モデル",
         "//",
         "// scripts/char/mkcellverilog.py が cellspec.py から自動生成。手で編集しないこと。",
         "// cellspec.py の表は check_comb.py / check_seq.py が ngspice で",
         "// 実レイアウトの抽出ネットリストと突き合わせて検証している。",
         "//",
         "// 用途: .lib でマッピングした合成後ネットリストを iverilog で回す。",
         "// 遅延は入っていない（タイミングは .lib + STA の仕事）。",
         "",
         "`timescale 1ns/1ps", ""]

    n = 0
    for cell in sorted(cellspec.COMB):
        if cell in cellspec.BLOCK_ONLY:
            continue          # アレイ内部専用。合成では出てこない
        funcs = cellspec.LIBFUNC.get(cell)
        if not funcs:
            continue
        ports = list(dict.fromkeys(
            [p for _, (ips, _) in cellspec.COMB[cell].items() for p in ips]
            + list(funcs)))
        o.append(comb_module(cell, funcs, ports)); o.append("")
        n += 1
    for cell, spec in sorted(cellspec.FF.items()):
        o.append(ff_module(cell, spec)); o.append("")
        n += 1
    for cell, spec in sorted(cellspec.LATCH.items()):
        o.append(latch_module(cell, spec)); o.append("")
        n += 1

    open(a.out, "w").write("\n".join(o) + "\n")
    print(f"wrote {a.out}  ({n} cells)")


if __name__ == "__main__":
    main()

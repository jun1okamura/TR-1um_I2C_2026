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
  **ただし `--delay` を付けたときだけ単位遅延を入れる。** Async I2C の RTL は
  NOR2 のクロス結合で SR ラッチを組んでいて、ゼロ遅延だと iverilog の
  デルタサイクルでループが収束しない（値が x のまま、あるいは発振する）。
  `TR-1um_Async_I2C/src/stdcell_behavioral_stubs.v` が `assign #1` にしていたのと
  同じ理由。合成後ネットリストにも RSLATCH 以外のクロス結合が残りうるので、
  I2C 側は常に `--delay 1` で生成する。

  `--power` を付けると全モジュールに `input VDD, GND;`（未使用）が付く。
  Async I2C の RTL は `NOR2 u_x (.A(..), .B(..), .Y(..), .VDD(VDD), .GND(GND))` と
  電源ピンまで繋いで書いてあるので、これが無いと iverilog が
  「port VDD not found」で落ちる。yosys が `read_liberty` から起こすインスタンスは
  電源ピンを繋がないが、入力ポートが未接続でも構わないので同じモデルで両方通る。
"""
from __future__ import annotations
import argparse, os, sys
import cellspec

HERE = os.path.dirname(os.path.abspath(__file__))


def expr_to_verilog(s):
    """Liberty の式 (`*` AND / `+` OR / `!` NOT / `^` XOR) を Verilog に直す"""
    return s.replace("*", " & ").replace("+", " | ").replace("!", "~").replace("^", " ^ ")


def comb_module(cell, funcs, ports, power=False, delay=0):
    ins = [p for p in ports if p not in funcs]
    d = f"#{delay} " if delay else ""
    L = [f"module {cell} ("]
    L.append("    input  " + ", ".join(ins) + ",")
    L.append("    output " + ", ".join(funcs) + (");" if not power else ","))
    if power:
        L.append("    input  VDD, GND);")
    for o, f in funcs.items():
        L.append(f"  assign {d}{o} = {expr_to_verilog(f)};")
    L.append("endmodule")
    return "\n".join(L)


def ff_module(cell, spec, power=False, delay=0):
    d = cellspec.SEQ_PINS[cell]
    ins = ["CK"] + d["data"] + d["async"]
    L = [f"module {cell} ("]
    L.append("    input  " + ", ".join(ins) + ",")
    L.append("    output Q, QB" + ("," if power else ");"))
    if power:
        L.append("    input  VDD, GND);")
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


def latch_module(cell, spec, power=False, delay=0):
    """RSLATCH: S でセット / R でリセットの SR ラッチ。

    `--delay` があるときは**レイアウトどおりのクロス結合 NOR** で書く:

        Q  = ~(R | QB)
        QB = ~(S | Q)

    if/else の reg 版より忠実。違いが出るのは S=R=1 のときで、実物（NOR 型）は
    **Q=QB=0** になるのに対し、reg 版は Q と QB が必ず反転した値になる。
    このセルを使う 3 箇所は設計上 S と R が同時に立たないので実害は無いが、
    **モデルが実物と食い違っていると、その前提が崩れたときに気付けない。**
    クロス結合はゼロ遅延だと iverilog のデルタサイクルで収束しないので、
    `--delay` が無いときだけ従来の reg 版に落とす。
    """
    pw = ", input VDD, GND);" if power else ");"
    L = [f"module {cell} (input S, R, output Q, QB{pw}"]
    if delay:
        d = f"#{delay} "
        L.append("  // レイアウトどおりのクロス結合 NOR（S=R=1 で Q=QB=0 になる）")
        L.append(f"  assign {d}Q  = ~({expr_to_verilog(spec['clear'])} | QB);")
        L.append(f"  assign {d}QB = ~({expr_to_verilog(spec['preset'])} | Q);")
    else:
        L.append("  // ゼロ遅延ではクロス結合が収束しないので reg で書く。")
        L.append("  // **S=R=1 の挙動が実物と違う**（実物は Q=QB=0）。")
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
    ap.add_argument("--power", action="store_true",
                    help="全モジュールに未使用の VDD / GND 入力を足す")
    ap.add_argument("--delay", type=int, default=0,
                    help="組合せ出力に入れる単位遅延（クロス結合の収束用。I2C は 1）")
    a = ap.parse_args()

    o = ["// TR-1um 標準セルのゼロ遅延 Verilog モデル",
         "//",
         "// scripts/char/mkcellverilog.py が cellspec.py から自動生成。手で編集しないこと。",
         "// cellspec.py の表は check_comb.py / check_seq.py が ngspice で",
         "// 実レイアウトの抽出ネットリストと突き合わせて検証している。",
         "//",
         "// 用途: .lib でマッピングした合成後ネットリストを iverilog で回す。",
         "// 遅延は .lib + STA の仕事。ここに入っているのは、クロス結合ループを",
         "// iverilog で収束させるためだけの単位遅延（--delay）。",
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
        o.append(comb_module(cell, funcs, ports, a.power, a.delay)); o.append("")
        n += 1
    for cell, spec in sorted(cellspec.FF.items()):
        o.append(ff_module(cell, spec, a.power, a.delay)); o.append("")
        n += 1
    for cell, spec in sorted(cellspec.LATCH.items()):
        o.append(latch_module(cell, spec, a.power, a.delay)); o.append("")
        n += 1

    open(a.out, "w").write("\n".join(o) + "\n")
    print(f"wrote {a.out}  ({n} cells)")


if __name__ == "__main__":
    main()

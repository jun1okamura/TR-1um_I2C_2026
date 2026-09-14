#!/usr/bin/env python3
"""RTL と **マッピング後のネットリスト**が同じ回路かを形式的に確かめる。

  usage: python3 scripts/syn_equiv.py <top> [-r "RTL ファイル..."] [-n out/<top>.v]

なぜ要るか:
  `abc -g simple` の頃は「抽象ゲートに落として面積を概算する」だけだったので、
  合成結果そのものは成果物ではなかった。`.lib` でマッピングすると
  **実セルのネットリストが成果物**になり、これが P&R の入力になる。
  だから「RTL と本当に同じか」を見ておく必要がある。

二段構え:
  1. **帰納法（無制限）** — `equiv_induct`。通れば全サイクルで等価。
  2. 通らなければ **有界 SAT** — `sat -seq N`。リセットから N サイクルの範囲で
     反例が無いことを示す。帰納法が弱いだけなのか、本当に違うのかが分かれる。

セルの振る舞いは `hdl/rtl/tr1um_cells.v`（`scripts/char/mkcellverilog.py` が
`cellspec.py` から生成）を使う。cellspec.py は ngspice で実レイアウトの抽出と
突き合わせてあるので、ここが通れば **RTL ≡ マップ後 ≡ レイアウト**が繋がる。

下準備のパスに意味がある:
  memory_map   RTL 側の `case` 文が `$mem_v2`（ROM セル）になっていると、
               論理に展開済みのゲート側と対応が取れない。両側で論理に落とす。
  async2sync   非同期リセット付き FF（`$adff`）は SAT に渡せない。
  opt_clean -purge
               内部の public wire を消す。残っていると equiv_make が名前で
               勝手に対応付けてしまい、最適化で消えた信号が「未証明」に化ける。
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys

PREP = """prep -top {top} -flatten
memory_map
opt -full
async2sync
{purge}"""

EQUIV = """read_verilog {rtl}
""" + PREP + """rename {top} gold
design -stash gold
read_verilog {net} hdl/rtl/tr1um_cells.v
""" + PREP + """rename {top} gate
design -stash gate
design -copy-from gold -as gold gold
design -copy-from gate -as gate gate
equiv_make gold gate equiv
hierarchy -top equiv
equiv_simple -seq {seq}
equiv_induct -seq {seq}
equiv_status -assert
"""

MITER = """read_verilog {rtl}
""" + PREP + """rename {top} gold
design -stash gold
read_verilog {net} hdl/rtl/tr1um_cells.v
""" + PREP + """rename {top} gate
design -stash gate
design -copy-from gold -as gold gold
design -copy-from gate -as gate gate
miter -equiv -flatten -make_assert gold gate miter
hierarchy -top miter
sat -seq {cycles} -prove-asserts -set-init-zero -verify
"""


def run(script, ys):
    p = subprocess.run([ys, "-s", "/dev/stdin"], input=script,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("top")
    ap.add_argument("-r", "--rtl", default="hdl/rtl/td4_core.v hdl/rtl/td4_mem.v "
                    "hdl/rtl/td4_soc_rom.v hdl/rtl/td4_soc_ff.v hdl/rtl/td4_soc_arr.v")
    ap.add_argument("-n", "--net", default=None)
    ap.add_argument("--seq", type=int, default=5, help="帰納法の深さ")
    ap.add_argument("--cycles", type=int, default=30, help="有界 SAT のサイクル数")
    ap.add_argument("--ys", default=os.environ.get("YOSYS", "yosys"))
    a = ap.parse_args()
    net = a.net or f"out/{a.top}.v"
    if not os.path.exists(net):
        sys.exit(f"ネットリストが無い: {net}")

    # 内部 public wire を消すかどうかで帰納法の通り方が変わる。
    #   残す  : equiv_make が内部信号も対応付けるので、そこを足場に証明が進む
    #   消す  : 最適化で消えた信号が「未証明」に化けるのを防げる
    # どちらが効くかは回路による（td4_core は残す方、td4_soc_rom は消す方）ので両方試す。
    best = (None, None)
    for purge in ("", "opt_clean -purge\n"):
        rc, log = run(EQUIV.format(top=a.top, rtl=a.rtl, net=net,
                                   seq=a.seq, purge=purge), a.ys)
        if rc == 0 and "Equivalence successfully proven!" in log:
            print(f"  {a.top:<14} 形式等価: **証明**（帰納法・全サイクル"
                  f"{'' if not purge else ' / 内部信号を消して'}）")
            return 0
        m = re.search(r"Found (\d+) unproven \$equiv cells in 'equiv_status", log)
        n = int(m.group(1)) if m else 10**9
        if best[0] is None or n < best[0]:
            best = (n, len(re.findall(r"Trying to prove .*: success!", log)))
    nun, ok = best

    rc2, log2 = run(MITER.format(top=a.top, rtl=a.rtl, net=net,
                                 cycles=a.cycles, purge=""), a.ys)
    if rc2 == 0 and "SAT proof finished - no model found: SUCCESS!" in log2:
        print(f"  {a.top:<14} 形式等価: 有界で一致（リセットから {a.cycles} サイクル）"
              f"  — 帰納法では {nun} 点が未証明（{ok} 点は証明済み）")
        return 0
    print(f"  {a.top:<14} 形式等価: **不一致の疑い**  帰納法 未証明 {nun} 点 / "
          f"有界 SAT rc={rc2}")
    for ln in log2.splitlines():
        if "ERROR" in ln or "FAIL" in ln:
            print("    " + ln)
    return 1


if __name__ == "__main__":
    sys.exit(main())

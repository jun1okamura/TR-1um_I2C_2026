#!/usr/bin/env python3
"""gen_chip_tb_ringosc.py -- RING_OSC が本当に発振するかを見る短い TB。

    layout/chip/simulation/<top>_sim.spice   （RING_OSC 入りの抽出）
  -> layout/chip/simulation/tb_ringosc.spice

14 項目の回帰（`gen_chip_tb_batch14.py`）は RING_OSC を外して流す。544 µs の
あいだ 190 段が発振し続けると刻みが潰れて終わらないため。こちらは逆に
**RING_OSC だけを見る短い TB**。

## つなぎ方

`ENB` はパッド P15（`rst_n` と共用）。リセットを解いた瞬間に発振が始まる。
出力は `OUT` -> P10、`OUTD` -> P9 で、どちらもフレームのドライバ経由。

    P15  0 -> 5 V （0.5 µs で）    ENB。ここから発振
    P7   5 V                        DIS。データパッドを全部 Hi-Z に
    P1   5 V / P2  10k プルアップ   I2C はアイドルのまま
    P9 / P10  10 pF                 ボンドワイヤ + プローブを想定
                                    （`<APRtools>/char/char_pad.py` と同じ条件）

## 何を測るか

`OUT` と `OUTD` の**立ち上がりの間隔**。5 周目から 15 周目までの 10 周で
割って 1 周期を出す（最初の数周は起動の過渡が乗る）。

速い方（`OUT`、INV_X1 95 段）と遅い方（`OUTD`、INV3D 95 段）の比が見どころ。
**トランジスタの W/L は同じ**で、違うのはレイアウトだけ（INV3D は縦長に
描いてあって拡散が大きい）。つまりこの比は**抽出した AS/AD/PS/PD の差**
そのもので、回路図からのネットリストでは出てこない。

  usage: python3 scripts/pnr/gen_chip_tb_ringosc.py [--until 10u] [--tmax 200p]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

SIM = os.path.join(cfg.CHIP, "simulation")
FLOAT_PADS = ("P3", "P4", "P5", "P6", "P11", "P12", "P13", "P14")
OSC = {"P10": "OUT", "P9": "OUTD"}
N_SKIP, N_SPAN = 5, 10         # 5 周目から 10 周ぶんで平均する


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # ★ 既定は **コミットしてある tb_ringosc.spice を作ったときの値**（U26）。
    #   以前の既定（10u / 200p / 2u-4u）はどこにも使われておらず、
    #   引数無しで回すと**コミット済みの TB と別物**が出ていた。
    ap.add_argument("--until", default="12u")
    ap.add_argument("--tmax", default="500p")
    ap.add_argument("--cload", default="10p", help="出力パッドに付ける容量")
    ap.add_argument("--vwin", nargs=2, default=("4u", "10u"),
                    help="振幅を見る窓（起動の過渡を避ける）")
    ap.add_argument("--netlist", default=None)
    ap.add_argument("--models", default=None,
                    help="PDK のモデル（既定: TB の隣の models.spice 経由）")
    ap.add_argument("-o", "--out", default=os.path.join(SIM, "tb_ringosc.spice"))
    a = ap.parse_args()

    # ★ **TB に機械依存の絶対パスを書かない**（U24）。PDK の場所は TB の隣に
    #   置く `models.spice` 1 行に閉じ込め、TB からは相対名で読む。
    #   `--models` で明示されたときだけ、そのパスをそのまま書く。
    models_inc = a.models or cfg.write_models_shim(SIM)
    net = a.netlist or os.path.join(SIM, cfg.CHIP_TOP_CELL + "_sim.spice")
    if not os.path.exists(net):
        raise SystemExit(f"{net} が無い。先に\n"
                         f"  python3 scripts/pnr/gen_chip_sim_ready.py")
    txt = open(net, encoding="utf-8").read()
    if not re.search(rf"^X\S+[^\n]*\s{re.escape(cfg.RING_OSC_CELL)}\s*$", txt, re.M):
        raise SystemExit(f"{net} に {cfg.RING_OSC_CELL} のインスタンスが無い"
                         f"（--no-ringosc で作ったものを渡していないか）")
    hdr = re.search(rf"^\.SUBCKT\s+{re.escape(cfg.CHIP_TOP_CELL)}"
                    r"([^\n]*(?:\n\+[^\n]*)*)", txt, re.M).group(1)
    ports = hdr.replace("+", " ").split()

    L = [
        "* tb_ringosc.spice -- scripts/pnr/gen_chip_tb_ringosc.py が生成。",
        "* 手で編集しないこと。",
        "*",
        "* RING_OSC の発振を見る。ENB = P15 = rst_n、OUT -> P10、OUTD -> P9。",
        "* ネットリストは**レイアウト抽出**なので、AS/AD/PS/PD は実測。",
        "",
        f".include '{models_inc}'",
        f".include '{os.path.basename(net)}'",
        "",
        ".param vdd=5.0",
        "vvdd VDD 0 DC 5.0",
        "vvss VSS 0 DC 0",
        "",
        "* リセット解除 = 発振開始",
        "vrstn P15 0 PWL(0 0 5e-07 0 6e-07 5.0)",
        "* DIS=H でデータパッドは全部 Hi-Z、I2C はアイドル",
        "vdis P7 0 DC 5.0",
        "vscl P1 0 DC 5.0",
        "rpu  P2 VDD 10k",
    ]
    for p in FLOAT_PADS:
        L.append(f"r{p.lower()} {p} VSS 1G")
    L.append("")
    L.append("* ボンドワイヤ + プローブ相当の負荷")
    for p in OSC:
        L.append(f"c{p.lower()} {p} 0 {a.cload}")
    L += [
        "",
        "xdut " + " ".join(ports) + f" {cfg.CHIP_TOP_CELL}",
        "",
        # **uic が要る**。リング発振器を抱えたチップは動作点が求まらない
        # （`Transient op failed, timestep too small`）。全節点 0 V から
        # 始めて、ENB を上げるまでの 0.5 µs で落ち着かせる。
        f".options gmin=1e-11 reltol=1e-3 method=gear",
        f".tran 100p {a.until} 0 {a.tmax} uic",
        "",
        "* ---- 発振周期 ----",
    ]
    for p, nm in OSC.items():
        L.append(f".measure tran t_{nm}_a WHEN v({p})='vdd/2' RISE={N_SKIP}"
                 f"  $ {nm}: {N_SKIP} 周目の立ち上がり")
        L.append(f".measure tran t_{nm}_b WHEN v({p})='vdd/2' RISE={N_SKIP + N_SPAN}"
                 f"  $ {nm}: {N_SKIP + N_SPAN} 周目の立ち上がり")
        L.append(f".measure tran period_{nm} PARAM='(t_{nm}_b-t_{nm}_a)/{N_SPAN}'"
                 f"  $ {nm} の 1 周期")
        L.append(f".measure tran freq_{nm} PARAM='{N_SPAN}/(t_{nm}_b-t_{nm}_a)'"
                 f"  $ {nm} の周波数 [Hz]")
        # FROM/TO に**別の measure の結果は書けない**（パース時に解決できず
        # "Undefined parameter" で落ちる）。定数の窓で振幅を見る。
        L.append(f".measure tran vmax_{nm} MAX v({p}) FROM={a.vwin[0]} TO={a.vwin[1]}")
        L.append(f".measure tran vmin_{nm} MIN v({p}) FROM={a.vwin[0]} TO={a.vwin[1]}")
    L += ["", ".end", ""]

    os.makedirs(SIM, exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    print(f"  ネットリスト {os.path.relpath(net, cfg.ROOT)}（RING_OSC 入り）")
    print(f"  .tran 100p {a.until} 0 {a.tmax}、出力負荷 {a.cload}")
    print(f"  流し方: cd {os.path.relpath(SIM, cfg.ROOT)} && "
          f"ngspice -b {os.path.basename(a.out)} > ringosc.log 2>&1")
    return 0


if __name__ == "__main__":
    sys.exit(main())

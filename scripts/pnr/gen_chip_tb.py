#!/usr/bin/env python3
"""gen_chip_tb.py -- 抽出したチップを ngspice で動かすテストベンチ。

    layout/chip/simulation/<top>_sim.spice  （抽出 -> ngspice 用に変換）
  -> layout/chip/simulation/tb_<top>.spi

`hdl/tb/tb_td4_soc_arr.v` と**同じ手順**をボンドパッドに対して流す:

    リセット -> Load モードで 5 命令書込 -> Exec モードで走らせる

    0: 1011_0011  OUT 3
    1: 1011_0110  OUT 6
    2: 1011_1100  OUT 12
    3: 1011_1000  OUT 8
    4: 1111_0000  JMP 0        -> OUT は 3, 6, 12, 8 の繰り返し

1 命令 = 下位ニブル（即値）-> 上位ニブル（オペコード）の 2 回書込。値は
**negedge で置いて posedge で取り込まれる**（Verilog の `load` タスクと同じ）。

## パッドの割り当て（`layout/chip/gio_connections.json`）

    P1 clk / P2 wr / P3 nibsel / P4..P7 d[3..0] / P9 rst_n / P14 exec
    P10..P13 out_port[0..3] / P15 cflag_o / VDD / VSS（P16 / P8）

入力パッドは `HIZ=1` で Hi-Z、コア側は `BUFTH`（シュミット）で受けるので、
外から電圧源で叩いてよい。出力パッドには実装を想定して 10 pF を付ける
（`scripts/char/char_pad.py` の測定条件と同じ）。

  usage: python3 scripts/pnr/gen_chip_tb.py [--period 100] [--cycles 12]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

SIM = os.path.join(cfg.CHIP, "simulation")
NETLIST = os.path.join(SIM, cfg.CHIP_TOP_CELL + "_sim.spice")
MODELS = os.path.join(cfg.ROOT, "scripts", "char", "models", "ip62_models")
OUT = os.path.join(SIM, "tb_" + cfg.CHIP_TOP_CELL + ".spi")

VDD = 5.0
TR = 1.0                        # 入力の遷移時間 ns
CL = "10p"                      # 出力パッドの負荷

PROGRAM = [0b1011_0011, 0b1011_0110, 0b1011_1100, 0b1011_1000, 0b1111_0000]
EXPECT = [3, 6, 12, 8]

# パッド -> 役割（gio_connections.json の PAD_MAP と同じ。ここは読むだけ）
IN_PADS = {"P1": "clk", "P2": "wr", "P3": "nibsel", "P4": "d3", "P5": "d2",
           "P6": "d1", "P7": "d0", "P9": "rst_n", "P14": "exec"}
OUT_PADS = {"P10": "out0", "P11": "out1", "P12": "out2", "P13": "out3",
            "P15": "cf"}


def subckt_ports(path, name):
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"^\.subckt\s+{re.escape(name)}\s", line, re.I):
            toks = line.split()[2:]
            j = i + 1
            while j < len(lines) and lines[j].startswith("+"):
                toks += lines[j][1:].split()
                j += 1
            return toks
    raise SystemExit(f".subckt {name} が {path} に無い")


def pwl(events, tr=TR):
    """[(t_ns, 0/1)] -> PWL 文字列。t で遷移を**始める**。"""
    out, prev = [], None
    for t, v in events:
        lv = VDD if v else 0.0
        if prev is None:
            out.append(f"0 {lv:g}")
        else:
            out.append(f"{t:g}n {prev:g}")
            out.append(f"{t + tr:g}n {lv:g}")
        prev = lv
    return "PWL(" + " ".join(out) + ")"


def build(period, cycles):
    """1 本ずつの波形と、期待する OUT のサンプル時刻。"""
    T = float(period)
    neg = lambda j: (j + 1) * T              # noqa: E731  負エッジ j の時刻
    pos = lambda j: (j + 0.5) * T            # noqa: E731  正エッジ j の時刻

    ev = {k: [(0.0, 0)] for k in IN_PADS.values() if k != "clk"}

    def put(t, sig, val):
        if ev[sig][-1][1] != val:
            ev[sig].append((t, val))

    put(neg(0), "rst_n", 1)                  # n0 でリセット解除
    j = 2                                    # n1 は空ける（Verilog と同じ）
    for instr in PROGRAM:
        lo, hi = instr & 0xF, (instr >> 4) & 0xF
        for k, nib in ((0, lo), (1, hi)):
            t = neg(j + k)
            put(t, "nibsel", k)
            for b in range(4):
                put(t, f"d{b}", (nib >> b) & 1)
            put(t, "wr", 1)
        put(neg(j + 2), "wr", 0)
        j += 3
    t_exec = neg(j)
    put(t_exec, "exec", 1)                   # ここから Exec モード
    j += 1

    # クロックは最後まで振り続ける
    n_last = j + cycles + 2
    clk = []
    for k in range(n_last + 2):
        clk.append((pos(k), 1))
        clk.append((neg(k), 0))
    clk = [(0.0, 0)] + [e for e in clk if e[0] > 0]
    ev["clk"] = clk

    # OUT を見る時刻（Verilog と同じく posedge の直後）
    samples = [(i, pos(j + i) + 0.6 * T) for i in range(cycles)]
    t_stop = pos(j + cycles) + T
    return ev, samples, t_stop, t_exec


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", type=float, default=100.0, help="クロック周期 ns")
    ap.add_argument("--cycles", type=int, default=12, help="Exec で見るサイクル数")
    ap.add_argument("--step", type=float, default=0.5, help="tran の刻み ns")
    ap.add_argument("-o", "--out", default=OUT)
    ap.add_argument("--netlist", default=NETLIST)
    a = ap.parse_args()

    ports = subckt_ports(a.netlist, cfg.CHIP_TOP_CELL)
    ev, samples, t_stop, t_exec = build(a.period, a.cycles)

    L = [f"* {os.path.basename(a.out)} -- 抽出したチップの動作確認（ngspice）",
         "* scripts/pnr/gen_chip_tb.py が生成。手で編集しないこと。",
         f"* プログラム: " + " ".join(f"{i:02X}" for i in PROGRAM)
         + f"  期待する OUT: {EXPECT} の繰り返し",
         f"* クロック {a.period:g} ns（{1000/a.period:.1f} MHz）"
         f"  Exec 開始 {t_exec:g} ns  終了 {t_stop:g} ns",
         "",
         f'.include "{MODELS}"',
         f'.include "{os.path.abspath(a.netlist)}"',
         "",
         f"Vvdd VDD 0 DC {VDD}",
         "Vvss VSS 0 DC 0",
         ""]

    inst = []
    for p in ports:
        inst.append(p if p in ("VDD", "VSS") else p)
    L.append("X1 " + " ".join(inst) + f" {cfg.CHIP_TOP_CELL}")
    L.append("")

    for pad, sig in sorted(IN_PADS.items(), key=lambda kv: kv[1]):
        L.append(f"V{sig} {pad} 0 {pwl(ev[sig])}")
    L.append("")
    for pad, sig in sorted(OUT_PADS.items()):
        L.append(f"C{sig} {pad} 0 {CL}")
    L.append("")

    L += [".option reltol=1e-3 abstol=1e-10 vntol=1e-5 chgtol=1e-14",
          ".option gmin=1e-12 itl1=500 itl2=200 itl4=100 method=gear",
          f".tran {a.step:g}n {t_stop:g}n",
          "",
          ".control",
          "run",
          'echo "=== OUT (out3 out2 out1 out0) / CF"']
    for i, t in samples:
        L.append(f'meas tran o0_{i} FIND v(P10) AT={t:g}n')
        L.append(f'meas tran o1_{i} FIND v(P11) AT={t:g}n')
        L.append(f'meas tran o2_{i} FIND v(P12) AT={t:g}n')
        L.append(f'meas tran o3_{i} FIND v(P13) AT={t:g}n')
        L.append(f'meas tran cf_{i} FIND v(P15) AT={t:g}n')
    L += [f'wrdata {os.path.join(SIM, "chip_tb.raw.csv")} '
          'v(P10) v(P11) v(P12) v(P13) v(P15) v(P1) v(P2) v(P14)',
          ".endc",
          ".end", ""]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(L))
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    print(f"  クロック {a.period:g} ns / Exec 開始 {t_exec:g} ns / "
          f"終了 {t_stop:g} ns / サンプル {len(samples)} 点")
    return 0


if __name__ == "__main__":
    sys.exit(main())

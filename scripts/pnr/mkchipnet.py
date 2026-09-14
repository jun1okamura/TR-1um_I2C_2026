#!/usr/bin/env python3
"""mkchipnet.py -- チップレベルの LVS ソースネットリスト。

    layout/portrait/simulation/td4_soc_arr_nrow_fm.spice  （コア、単体で LVS 済み）
  + lef/simulation/OSS_FRAME_GIO_nocombine.spice          （パッドリング、素子レベル）
  + layout/chip/gio_connections.json                      （何と何を繋ぐか）
  -> layout/chip/simulation/tr_1um_TD4.spice

チップは結局「サブサーキット 2 個とポート表」でしかない:

    .subckt tr_1um_TD4 P1 P2 P3 P4 P5 P6 P7 VSS P9 P10 P11 P12 P13 P14 P15 VDD
    x1 … OSS_FRAME_GIO
    x2 … td4_soc_arr_nrow_fm
    .ends

**ポートは 16 本**（ボンドパッド全部）。`add_top_pins.py` がレイアウト側に
同じ 16 本を打つ。KLayout の照合はまずこの**本数**が合っていないとグラフ
マッチに入らない（移植元は 2 本落として、他の全ピンが将棋倒しに不一致に
なるのを見ている。下のサブサーキット 27 個は全部合っていたのに）。

## どの網がどこから来るか

両方のインスタンスのポート順は、**それぞれの `.subckt` 行から読む**。
決め打ちしない。網は接続表から引く:

    P<n>      ボンドパッドの網。そのままトップのポート
    HIZ<n>    レール直結（TD4 は 14 本とも固定方向。入力は VDD / 出力は GND）
    OUT<n>    出力パッドならコアが駆動する網。入力パッドは浮くので GND
              （`route_chip.py` が実際に落としているのと同じ）
    コアのポート  そのパッドの網

どちらの側にも表に出てこないポートがあったら、**それぞれ固有の `NC_*`**
にする。まとめて 1 本にすると、浮いている端子どうしが短絡した網として
LVS に見えてしまう。

  usage: python3 scripts/pnr/mkchipnet.py [-o OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

# **チップ組み立ては縦置き専用。**（理由は assemble_top.py の同じ注記）
os.environ.setdefault("TD4_MACRO_MODE", "portrait")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402

GIO_CELL = "OSS_FRAME_GIO"          # .spice の中での名前
CHIP_GIO_CELL = cfg.FRAME_CELL_CHIP  # チップ GDS / LVS での名前（OSS_FRAME）
# **`combine_devices()` を掛けていない方**を使う。`lvs_pnr.py` は DFFRB で
# KLayout が内部エラーを出すので両側とも combine しない方針で、ここで
# combine 済みのフレームを混ぜると素子数が 316 個ずれる（2026-09-14 に実測:
# レイアウト 4225 vs ソース 3909）。`lef/simulation/OSS_FRAME_GIO.spice` は
# ngspice 用の combine 済みで、そちらは触らない。
GIO_SPICE = os.path.join(cfg.ROOT, "lef", "simulation",
                         GIO_CELL + "_nocombine.spice")
CORE_SPICE = os.path.join(cfg.LAYOUT, "portrait", "simulation",
                          cfg.TOP_CELL_NAME + ".spice")
CONN = os.path.join(cfg.CHIP, "gio_connections.json")
SIM_DIR = os.path.join(cfg.CHIP, "simulation")
OUT_PATH = os.path.join(SIM_DIR, cfg.CHIP_TOP_CELL + ".spice")

# フレームのグランドは VSS、コアは GND。**同じ 1 本**で、チップでの名前は
# フレーム側に合わせる（ボンドパッドのラベルが VSS なので）。
RAIL = {"VDD": "VDD", "GND": "VSS", "VSS": "VSS"}

# リングを回る物理的な並び。P8 = VSS / P16 = VDD はフレーム固定。
TOP_PIN_ORDER = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "VSS",
                 "P9", "P10", "P11", "P12", "P13", "P14", "P15", "VDD"]


def subckt_ports(path, name):
    """`.subckt <name> …` のポート列（`+` の継続行も拾う）。"""
    lines = open(path, encoding="utf-8").read().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f".subckt {name} "):
            toks = line.split()[2:]
            j = i + 1
            while j < len(lines) and lines[j].startswith("+"):
                toks += lines[j][1:].split()
                j += 1
            return toks
    raise SystemExit(f".subckt {name} が {path} に無い")


def build():
    conn = json.load(open(CONN, encoding="utf-8"))
    sig = {s["pad"]: s for s in conn["signals"]}
    hiz = {t["pad"]: t["tie"] for t in conn["hiz_ties"]}
    floats = {t["pad"] for t in conn["float_ties"]}

    gio_ports = subckt_ports(GIO_SPICE, GIO_CELL)
    core_ports = subckt_ports(CORE_SPICE, cfg.TOP_CELL_NAME)

    nc = []

    def floating(label):
        nc.append(f"NC_{label}")
        return nc[-1]

    problems = []

    # ---- フレーム側 -------------------------------------------------------
    gio_net = {}
    for p in gio_ports:
        if p in RAIL:
            gio_net[p] = RAIL[p]
            continue
        m = re.match(r"^(P|HIZ|OUT)(\d+)$", p)
        if not m:
            problems.append(f"{GIO_CELL} の知らないポート {p!r}")
            continue
        kind, n = m.group(1), int(m.group(2))
        if n not in sig:
            problems.append(f"{GIO_CELL} の {p!r} に対応するパッド {n} が表に無い")
            continue
        if kind == "P":
            gio_net[p] = f"P{n}"
        elif kind == "HIZ":
            gio_net[p] = RAIL[hiz[n]]
        elif sig[n]["dir"] == "out":
            gio_net[p] = sig[n]["net"]        # コアが駆動する網そのもの
        elif n in floats:
            gio_net[p] = RAIL["GND"]          # 入力パッドの浮いた OUT を落とす
        else:
            gio_net[p] = floating(p)

    # ---- コア側 -----------------------------------------------------------
    claim = {}
    for n, s in sig.items():
        claim[s["net"]] = f"P{n}" if s["dir"] == "in" else s["net"]
    core_net, unconnected = {}, []
    for p in core_ports:
        if p in RAIL:
            core_net[p] = RAIL[p]
        elif p in claim:
            core_net[p] = claim[p]
        else:
            core_net[p] = floating(f"CORE_{p}")
            unconnected.append(p)
    if unconnected:
        problems.append(f"どのパッドにも行かないコアのポート: {unconnected}")

    # ---- 突き合わせ -------------------------------------------------------
    for pad in TOP_PIN_ORDER:
        if pad not in RAIL and gio_net.get(pad) != pad:
            problems.append(f"トップピン {pad} が {gio_net.get(pad)!r} を運んでいる")
    if len(TOP_PIN_ORDER) != len(sig) + 2:
        problems.append(f"トップピン {len(TOP_PIN_ORDER)} 本 vs "
                        f"パッド {len(sig)} + レール 2")
    for n, s in sorted(sig.items()):
        side = "OUT" if s["dir"] == "out" else "P"
        a, b = core_net.get(s["net"]), gio_net.get(f"{side}{n}")
        if a != b:
            problems.append(f"パッド {n}: コア {s['net']}={a!r} だが "
                            f"{side}{n}={b!r}")

    # レイアウト側は `assemble_top.py` が `OSS_FRAME` に改名しているので、
    # ソース側の `.subckt` 名も揃える（LVS はセル名で対応を取る）。
    gio_body = re.sub(rf"\b{re.escape(GIO_CELL)}\b", CHIP_GIO_CELL,
                      open(GIO_SPICE, encoding="utf-8").read().rstrip("\n"))
    core_body = open(CORE_SPICE, encoding="utf-8").read().rstrip("\n")
    names = lambda t: set(re.findall(r"^\.subckt\s+(\S+)", t, re.M))  # noqa: E731
    clash = names(gio_body) & names(core_body)
    if clash:
        problems.append(f"2 つの本体で .subckt 名が衝突: {sorted(clash)}")

    return (gio_ports, core_ports, gio_net, core_net,
            gio_body, core_body, nc, problems)


def wrap(inst, nets, cell, per=8):
    out = [f"{inst} " + " ".join(nets[:per])]
    rest = nets[per:]
    while rest:
        out.append("+ " + " ".join(rest[:per]))
        rest = rest[per:]
    out[-1] += f" {cell}"
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=OUT_PATH)
    a = ap.parse_args()

    (gio_ports, core_ports, gio_net, core_net,
     gio_body, core_body, nc, problems) = build()

    header = [
        f"** {os.path.basename(a.out)} -- チップレベルの LVS ソースネットリスト。",
        "** scripts/pnr/mkchipnet.py が生成。手で編集しないこと。",
        f"**   コア    : {os.path.relpath(CORE_SPICE, cfg.ROOT)}",
        f"**   フレーム: {os.path.relpath(GIO_SPICE, cfg.ROOT)}",
        f"**   接続表  : {os.path.relpath(CONN, cfg.ROOT)}",
        "**",
        f"** x1 = {CHIP_GIO_CELL}（元 {GIO_CELL}）/ x2 = {cfg.TOP_CELL_NAME}。",
        "** `NC_*` は両側とも本当にどこにも繋がっていない端子で、1 本ずつ",
        "** 固有の名前を付けてある",
        "** （まとめると浮いた端子どうしが短絡して見える）。",
        "** トップは 16 本のボンドパッドを宣言する（P1-P7, VSS, P9-P15, VDD。",
        "** P8 は VSS、P16 は VDD でフレーム固定）。レイアウト側は",
        "** scripts/pnr/add_top_pins.py が同じ 16 本を打つ。**本数が合って",
        "** いないと KLayout はグラフマッチに入らない。**",
    ]
    lines = header + ["", gio_body, "", core_body, "",
                      f".subckt {cfg.CHIP_TOP_CELL} " + " ".join(TOP_PIN_ORDER),
                      wrap("x1", [gio_net[p] for p in gio_ports], CHIP_GIO_CELL),
                      wrap("x2", [core_net[p] for p in core_ports],
                           cfg.TOP_CELL_NAME),
                      ".ends", ""]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")

    print(f"\n{GIO_CELL}: {len(gio_ports)} ポート")
    print(f"{cfg.TOP_CELL_NAME}: {len(core_ports)} ポート")
    print(f"トップ: {len(TOP_PIN_ORDER)} 本のボンドパッド")
    print("\nコアのポート -> チップの網")
    for p in core_ports:
        print(f"  {p:<14} {core_net[p]}")
    print("\nフレームのピン -> チップの網（パッド以外）")
    for p in gio_ports:
        if not re.match(r"^P\d+$", p) and p not in RAIL:
            print(f"  {p:<8} {gio_net[p]}")
    if nc:
        print(f"\n浮いた網 {len(nc)} 本: {nc}")
    if problems:
        print()
        for p in problems:
            print("  PROBLEM: " + p)
        raise SystemExit(f"{len(problems)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())

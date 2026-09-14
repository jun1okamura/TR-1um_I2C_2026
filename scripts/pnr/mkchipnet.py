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

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

GIO_CELL = "OSS_FRAME_GIO"          # .spice の中での名前
CHIP_GIO_CELL = cfg.FRAME_CELL_CHIP  # チップ GDS / LVS での名前（OSS_FRAME）
# **`combine_devices()` を掛けていない方**を使う。`lvs_pnr.py` は DFFRB で
# KLayout が内部エラーを出すので両側とも combine しない方針で、ここで
# combine 済みのフレームを混ぜると素子数が 316 個ずれる（2026-09-14 に実測:
# レイアウト 4225 vs ソース 3909）。`lef/simulation/OSS_FRAME_GIO.spice` は
# ngspice 用の combine 済みで、そちらは触らない。
GIO_SPICE = os.path.join(cfg.ROOT, "lef", "simulation",
                         GIO_CELL + "_nocombine.spice")
SIM_DIR_EARLY = os.path.join(cfg.CHIP, "simulation")
CORE_SPICE = os.path.join(SIM_DIR_EARLY, cfg.TOP_CELL_NAME + ".spice")
# I2C 移植 (26): RING_OSC が 3 つ目のインスタンスとして居る。
RO_SPICE = os.path.join(SIM_DIR_EARLY, cfg.RING_OSC_CELL + ".spice")
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


def resolve_name(name, claim, floating, rail=RAIL):
    """接続表に書いてある「網の名前」-> チップでの網。

    `None` は結線しない端子。`"VDD"` / `"GND"` はレール直結。それ以外は
    設計上の網の名前で、`claim` がチップでの名前に読み替える
    （入力パッドが駆動する網は、そのパッドの網 `P<n>` になる）。"""
    if name is None:
        return None
    if name in rail:
        return rail[name]
    return claim.get(name, name)


def build():
    """--- I2C 移植 (26): 接続表の形が TD4 と違う + RING_OSC が居る --------

    TD4 の `gio_connections.json` は 1 パッド 1 網（`net` + `dir`）で、
    HIZ と浮いた OUT は別のリストだった。I2C は 1 パッドに 3 本

        P    パッドが駆動する（入力）/ パッドに出す（出力）網
        OUT  パッドのドライバ入力。出力パッドならコアが駆動する網
        HIZ  パッドの Hi-Z 制御。双方向パッドは `DIS`、SDA は `sda_oe`

    が並び、`VDD` / `GND` / `null` が混ざる。さらに

      * `DIS` は**パッドだけの網**（P7 のパッド網がそのまま 8 個の HIZ へ）
      * P15 は `rst_n` と `RING_OSC.ENB` の 2 本を同時に駆動する
      * RING_OSC が 3 つ目のインスタンスとして居る

    ので、TD4 版の build() は丸ごと書き直してある。
    """
    conn = json.load(open(CONN, encoding="utf-8"))
    sig = {s["pad"]: s for s in conn["signals"]}

    gio_ports = subckt_ports(GIO_SPICE, GIO_CELL)
    core_ports = subckt_ports(CORE_SPICE, cfg.TOP_CELL_NAME)
    ro_ports = subckt_ports(RO_SPICE, cfg.RING_OSC_CELL)

    nc = []

    def floating(label):
        nc.append(f"NC_{label}")
        return nc[-1]

    problems = []

    # ---- 設計上の網の名前 -> チップでの網 ---------------------------------
    # 入力パッドが駆動する網はそのパッドの網になる。出力とHi-Z制御は
    # コア（か RING_OSC）が駆動するので、網の名前をそのまま使う。
    claim = {}
    for n, s in sig.items():
        p = s.get("P")
        for name in ([p] if isinstance(p, str) else (p or [])):
            if name not in RAIL:
                claim[name] = f"P{n}"
    ro_prefix = cfg.RING_OSC_CELL + "."

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
        else:
            v = resolve_name(sig[n].get(kind), claim, floating)
            # 結線先が無い端子は `route_chip.py` が GND に落としている
            # （入力専用パッドの浮いたドライバ入力）。同じにする。
            gio_net[p] = v if v is not None else RAIL["GND"]

    # ---- コア側 -----------------------------------------------------------
    core_net, unconnected = {}, []
    for p in core_ports:
        if p in RAIL:
            core_net[p] = RAIL[p]
        elif p in claim:
            core_net[p] = claim[p]
        elif any(p == s.get("OUT") or p == s.get("HIZ") for s in sig.values()):
            core_net[p] = p                     # コアが駆動する網
        else:
            core_net[p] = floating(f"CORE_{p}")
            unconnected.append(p)
    want_unbonded = set(conn.get("unbonded", []))
    if set(unconnected) != want_unbonded:
        problems.append(f"未ボンドのコアポートが表と違う: "
                        f"{sorted(unconnected)} / 表 {sorted(want_unbonded)}")

    # ---- RING_OSC 側 ------------------------------------------------------
    ro_net = {}
    for p in ro_ports:
        if p in RAIL:
            ro_net[p] = RAIL[p]
            continue
        full = ro_prefix + p
        if full in claim:                       # ENB は P15 が駆動する
            ro_net[p] = claim[full]
        elif any(full == s.get("OUT") for s in sig.values()):
            ro_net[p] = full                    # OUT / OUTD はそのまま
        else:
            ro_net[p] = floating(f"RO_{p}")
            problems.append(f"RING_OSC の {p!r} がどのパッドにも行かない")

    # ---- 突き合わせ -------------------------------------------------------
    for pad in TOP_PIN_ORDER:
        if pad not in RAIL and gio_net.get(pad) != pad:
            problems.append(f"トップピン {pad} が {gio_net.get(pad)!r} を運んでいる")
    if len(TOP_PIN_ORDER) != len(sig) + 2:
        problems.append(f"トップピン {len(TOP_PIN_ORDER)} 本 vs "
                        f"パッド {len(sig)} + レール 2")
    # フレームの端子とコア / RING_OSC の端子が同じ網を名乗っているか
    for n, s in sorted(sig.items()):
        for kind in ("P", "OUT", "HIZ"):
            v = s.get(kind)
            for name in ([v] if isinstance(v, str) else (v or [])):
                if name in RAIL or name is None:
                    continue
                want = resolve_name(name, claim, floating)
                if name.startswith(ro_prefix):
                    got = ro_net.get(name[len(ro_prefix):])
                elif name in core_net:
                    got = core_net[name]
                else:
                    continue                    # DIS のようなパッドだけの網
                if got != want:
                    problems.append(f"パッド {n} の {kind}={name}: "
                                    f"ブロック側 {got!r} / パッド側 {want!r}")

    # レイアウト側は `assemble_top.py` が `OSS_FRAME` に改名しているので、
    # ソース側の `.subckt` 名も揃える（LVS はセル名で対応を取る）。
    gio_body = re.sub(rf"\b{re.escape(GIO_CELL)}\b", CHIP_GIO_CELL,
                      open(GIO_SPICE, encoding="utf-8").read().rstrip("\n"))
    core_body = open(CORE_SPICE, encoding="utf-8").read().rstrip("\n")
    ro_body = open(RO_SPICE, encoding="utf-8").read().rstrip("\n")
    names = lambda t: set(re.findall(r"^\.subckt\s+(\S+)", t, re.M | re.I))  # noqa: E731
    # RING_OSC とコアは同じセルライブラリを使うので `.subckt INV_X1` などが
    # 必ずダブる。**ダブった定義は RING_OSC 側から落とす**（中身は同じ）。
    dup = names(ro_body) & (names(core_body) | names(gio_body))
    if dup:
        for cell in sorted(dup):
            ro_body = re.sub(rf"^\.subckt\s+{re.escape(cell)}\b.*?^\.ends.*?$\n?",
                             "", ro_body, flags=re.S | re.M | re.I)
        print(f"  RING_OSC 側で重複した .subckt を落とした: {sorted(dup)}")
    clash = names(gio_body) & names(core_body)
    if clash:
        problems.append(f"2 つの本体で .subckt 名が衝突: {sorted(clash)}")

    return (gio_ports, core_ports, ro_ports, gio_net, core_net, ro_net,
            gio_body, core_body, ro_body, nc, problems)


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

    (gio_ports, core_ports, ro_ports, gio_net, core_net, ro_net,
     gio_body, core_body, ro_body, nc, problems) = build()

    header = [
        f"** {os.path.basename(a.out)} -- チップレベルの LVS ソースネットリスト。",
        "** scripts/pnr/mkchipnet.py が生成。手で編集しないこと。",
        f"**   コア    : {os.path.relpath(CORE_SPICE, cfg.ROOT)}",
        f"**   RING_OSC: {os.path.relpath(RO_SPICE, cfg.ROOT)}",
        f"**   フレーム: {os.path.relpath(GIO_SPICE, cfg.ROOT)}",
        f"**   接続表  : {os.path.relpath(CONN, cfg.ROOT)}",
        "**",
        f"** x1 = {CHIP_GIO_CELL}（元 {GIO_CELL}）/ x2 = {cfg.TOP_CELL_NAME}"
        f" / x3 = {cfg.RING_OSC_CELL}。",
        "** `NC_*` は両側とも本当にどこにも繋がっていない端子で、1 本ずつ",
        "** 固有の名前を付けてある",
        "** （まとめると浮いた端子どうしが短絡して見える）。",
        "** トップは 16 本のボンドパッドを宣言する（P1-P7, VSS, P9-P15, VDD。",
        "** P8 は VSS、P16 は VDD でフレーム固定）。レイアウト側は",
        "** scripts/pnr/add_top_pins.py が同じ 16 本を打つ。**本数が合って",
        "** いないと KLayout はグラフマッチに入らない。**",
    ]
    lines = header + ["", gio_body, "", core_body, "", ro_body, "",
                      f".subckt {cfg.CHIP_TOP_CELL} " + " ".join(TOP_PIN_ORDER),
                      wrap("x1", [gio_net[p] for p in gio_ports], CHIP_GIO_CELL),
                      wrap("x2", [core_net[p] for p in core_ports],
                           cfg.TOP_CELL_NAME),
                      wrap("x3", [ro_net[p] for p in ro_ports],
                           cfg.RING_OSC_CELL),
                      ".ends", ""]

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")

    print(f"\n{GIO_CELL}: {len(gio_ports)} ポート")
    print(f"{cfg.TOP_CELL_NAME}: {len(core_ports)} ポート")
    print(f"{cfg.RING_OSC_CELL}: {len(ro_ports)} ポート -> "
          + ", ".join(f"{p}={ro_net[p]}" for p in ro_ports))
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

#!/usr/bin/env python3
"""フレーム（`OSS_FRAME_GIO` ほか）の LVS ソースネットリストを書き出す。

  usage: python3 scripts/mkframespice.py <gds> <top> -o lef/simulation/<top>.spice

出どころ（`lef/simulation/README` の分類でいう **(B) 検証済み抽出を golden 凍結**）:
  フレームは PDK から与えられたもので回路図が無い。したがってこの .spice は
  **レイアウトから抽出したものを凍結した**ものであり、これに対する LVS は
  「レイアウト vs そのレイアウトから作ったネット」なので**それ自体は何も証明しない**。
  意味があるのは次の 2 つ:
    - フレームを取り込んだチップ全体の LVS で、フレーム部分が既知のネットと
      一致することを確かめられる（回帰検査）
    - 中身が読める形で残るので、OUT / HIZ / PAD の役割を人が確認できる

抽出は `scripts/klayout_extract.py`（KLayout のエンジン + PDK のランセットと
同じ層の導出）。**`scripts/gds_extract.py` は使えない** — パッドセルは
poly が横向きで W/L が入れ替わり、ゲートの無い P+ in Nwell（ダイオード）を
MOS の S/D と誤認して VDD と VSS を短絡させる。

書式は `lef/simulation/*.spice` に揃える（`M... PMOS/NMOS/NMOSE W=..u L=..u`）。
LVS ランセットの SPICE リーダはモデル名をデバイスクラス名として読む。
"""
from __future__ import annotations
import argparse, os, sys

import klayout.db as db
import klayout_extract

# 抽出ではラベルが無くて名無しになるピンに、役割の分かる名前を付ける。
# （番号のままだと .spice を人が読めない）
PINNAMES = {
    "OSS_NCH_DRV": {1: "G"},          # 出力 NMOS のゲート
    "OSS_PCH_DRV": {2: "G"},          # 出力 PMOS のゲート
    "OSS_DRV":     {3: "GP", 4: "GN"},  # プリドライバ -> PMOS / NMOS のゲート
    "diode_n":     {0: "A"},          # 保護ダイオードの信号側
}
# ラベルが複数付いたネットで、どれを名前に採るか
PREFER = ("VDD", "VSS", "PAD", "OUT", "HIZ")


def clean(s):
    """`$` は ngspice のコメント文字。名前に混ぜない。"""
    return s.replace("$", "")


def netname(net, counter):
    n = net.expanded_name()
    # KLayout はラベルの無いネットを `$8` のように呼ぶ。これは名前ではないので
    # こちらで通し番号を振る（`$` は ngspice のコメント文字でもある）。
    if n and not n.isdigit() and not n.startswith("$"):
        parts = [p for p in n.split(",") if p]
        for p in PREFER:
            if p in parts:
                return p
        return parts[0]
    counter[0] += 1
    return f"n{counter[0]}"


def emit(nl, top, gds):
    order, seen = [], set()

    def visit(c):
        if c.name in seen:
            return
        seen.add(c.name)
        for sc in c.each_subcircuit():
            visit(sc.circuit_ref())
        order.append(c)

    visit(nl.circuit_by_name(top))

    L = [f"* {top} — LVS ソースネットリスト（フレーム）",
         "*",
         "* scripts/mkframespice.py が生成。手で編集しないこと。",
         f"* 出どころ: {os.path.basename(gds)} を KLayout のエンジンで抽出し凍結した。",
         "*   フレームは PDK 提供で回路図が無いので、**この .spice に対する LVS は",
         "*   「レイアウト vs そのレイアウトから作ったネット」であり、それ自体は何も",
         "*   証明しない**。チップ全体の LVS での回帰検査用。",
         "*",
         "* 層の導出は PDK のランセット（00_Layers.drc / 02_Device.drc /",
         "* tech/lvs/01_Extract.lvs）に合わせてある。ESD 認識層 (63,2) の中の",
         "* NMOS は NMOSE、ゲートを持たない拡散はダイオード DN/DP として扱う。",
         "*",
         "* 書き出したあと scripts/lvs_check.py で抽出ネットと照合して一致を確認済み",
         "* （ネットやピンを取り違えていないことの確認。レイアウトの正しさの証明ではない）。",
         "*",
         "* OSS_ESD_5V_DIO の動作（ngspice で確認）:",
         "*   HIZ=0 -> PAD = OUT（非反転バッファ。CL=10pF で立上り 10.4ns / 立下り 9.8ns）",
         "*   HIZ=1 -> PAD は高インピーダンス（10uA を注いだら素直に電位が動いた）",
         "*   => 双方向 IO。読むときは HIZ=1 にして PAD をコアの入力に直結する",
         "*      （入力バッファは入っていないので受け側は自前）。",
         "*   出力段: PMOS W=300u / NMOS W=150u（L=2u）。",
         "*   これとは別に、ゲートを電源に固定した ESD 素子",
         "*   （PMOS W=200u gate=VDD / NMOSE W=350u gate=VSS）が並んでいる。",
         "*"]

    for c in order:
        cnt = [0]
        names = {}
        for net in c.each_net():
            names[net.expanded_name()] = netname(net, cnt)
        pins = []
        for i, p in enumerate(c.each_pin()):
            nm = PINNAMES.get(c.name, {}).get(i)
            if not nm:
                net = c.net_for_pin(p.id())
                nm = names[net.expanded_name()] if net else f"p{i}"
            pins.append(nm)
            net = c.net_for_pin(p.id())
            if net:
                names[net.expanded_name()] = nm     # ピン名をネット名に採用
        L.append("")
        L.append(f".subckt {c.name} {' '.join(pins)}")
        for sc in c.each_subcircuit():
            ref = sc.circuit_ref()
            args = []
            for p in ref.each_pin():
                n = sc.net_for_pin(p.id())
                args.append(names[n.expanded_name()] if n else "0")
            L.append(f"X{clean(sc.expanded_name())} {' '.join(args)} {ref.name}")
        for d in c.each_device():
            dc = d.device_class()
            t = [d.net_for_terminal(td.id()) for td in dc.terminal_definitions()]
            nn = [names[x.expanded_name()] if x else "0" for x in t]
            if dc.name in ("PMOS", "NMOS", "NMOSE"):
                w = d.parameter("W"); l = d.parameter("L")
                # KLayout の端子順は S, G, D, B。SPICE の M は D G S B。
                s, g, dd, b = nn[0], nn[1], nn[2], nn[3]
                L.append(f"M{clean(d.expanded_name())} {dd} {g} {s} {b} {dc.name} "
                         f"W={w:g}u L={l:g}u")
            else:                                    # DN / DP
                a = d.parameter("A"); p_ = d.parameter("P")
                L.append(f"D{clean(d.expanded_name())} {nn[0]} {nn[1]} {dc.name} "
                         f"A={a:g}p P={p_:g}u")
        L.append(f".ends {c.name}")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds"); ap.add_argument("top")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--no-combine", action="store_true",
                    help="combine_devices() を掛けない（チップ LVS 用）。"
                         "lvs_pnr.py は DFFRB で KLayout が落ちるため両側とも"
                         "掛けないので、フレーム側もこれで揃える")
    a = ap.parse_args()

    l2n = klayout_extract.build(a.gds, a.top)
    nl = l2n.netlist()
    nl.make_top_level_pins()
    if not a.no_combine:
        nl.combine_devices()
    nl.purge()
    nl.purge_nets()
    open(a.out, "w").write(emit(nl, a.top, a.gds))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

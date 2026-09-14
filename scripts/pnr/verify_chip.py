#!/usr/bin/env python3
"""verify_chip.py -- チップ配線の接続性と短絡（チップ step2 の検算）。

  usage: python3 scripts/pnr/verify_chip.py [GDS]

`route_chip.py` が引いたあと、**図形だけ**を見て確かめる:

  1. 信号 14 本が「コアのピン <-> パッドの端子」で同じ島に入っているか
  2. その 14 本が互いに別の島か（短絡していないか）
  3. HIZ / 浮いた OUT が VDD / GND の島に入っているか
  4. コアの電源タップ（上下 4 本ずつ）が VDD / GND の島に入っているか
  5. VDD と GND が別の島か
  6. VDD の島がフレームの M1 VDD ピンに、GND の島がフレームの VSS 壁ピンに
     届いているか

島の作り方は step10 の短絡検出と同じ: M1 と M2 をマージして、V1 と両方に
重なるところで union する。**LEF の宣言ではなく GDS の図形**しか見ない。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402

M1, M2, V1 = (13, 0), (20, 0), (19, 0)
# フレームがコアに向けて出している電源のランドマーク（GDS 実測）
FRAME_VDD_PIN = (200.0, 927.0)       # M1 (50,920)-(350,934)
FRAME_VSS_PIN = (-200.0, -926.0)     # M2 (-450,-934)-(50,-920)


def extractor(layout, top):
    """KLayout の接続抽出。M1/M2 を V1 で繋いだネットを持つ `LayoutToNetlist`。

    自前の union-find（step10 の短絡検出と同じ理屈）でも書けるが、チップは
    コアを丸ごと抱えていて図形が数万あるので、KLayout の抽出器に任せる。"""
    it = db.RecursiveShapeIterator(layout, top, [])
    l2n = db.LayoutToNetlist(it)
    rm1 = l2n.make_polygon_layer(layout.layer(*M1), "M1")
    rm2 = l2n.make_polygon_layer(layout.layer(*M2), "M2")
    rv1 = l2n.make_polygon_layer(layout.layer(*V1), "V1")
    l2n.connect(rm1)
    l2n.connect(rm2)
    l2n.connect(rm1, rv1)
    l2n.connect(rv1, rm2)
    l2n.extract_netlist()
    return l2n, {"M1": rm1, "M2": rm2}


def probe(l2n, layers, x, y, layer=None):
    """点 (x,y) に**その層で**乗っているネット。層を省くと M2 -> M1 の順。

    層を必ず指定すること。コアの左辺のピン（M1）は、いちばん左の GND TAP 柱
    （M2、x=-793.35 を中心に 3.4 幅）とちょうど重なる位置にあるので、
    層を省いて探ると 5 本とも GND に見える（2026-09-14 に実際に踏んだ）。"""
    for name in ([layer] if layer else ["M2", "M1"]):
        n = l2n.probe_net(layers[name], db.DPoint(x, y))
        if n is not None:
            return id(n.circuit()), n.name or n.expanded_name()
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds", nargs="?",
                    default=os.path.join(cfg.CHIP, "step2_routed.gds"))
    ap.add_argument("--plan", default=os.path.join(cfg.CHIP,
                                                   "signal_routing_plan.json"))
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    layout = db.Layout()
    layout.read(a.gds)
    top = layout.cell(cfg.CHIP_TOP_CELL)
    l2n, layers = extractor(layout, top)
    look = lambda x, y, L=None: probe(l2n, layers, x, y, L)   # noqa: E731

    bad = []
    net_island = {}
    print(f"=== 信号 {len(plan['signals'])} 本")
    for s in plan["signals"]:
        f, t = s["from"], s["to"]
        ia = look(f["x"], f["y"], f["layer"])
        ib = look(t["x"], t["y"], t["layer"])
        ok = ia is not None and ia == ib
        if not ok:
            bad.append(f"{s['net']}: コア側 {ia} / パッド側 {ib} が別の島")
        net_island[s["net"]] = ia
        print(f"  {s['net']:<14} {'OK' if ok else 'NG'}  島 {ia}")

    # --- I2C 移植 (19): 同じパッド端子に着く別ネットは同じ島でよい ----------
    # P15 は `rst_n` と `RING_OSC.ENB` の両方を駆動する（1 本のリセットで
    # コアと RING_OSC を同時に解く）。同じ端子に着く以上、同じ島になるのが
    # 正しい。端子を共有しないネットどうしだけを短絡として見る。
    by_terminal = defaultdict(set)
    for s in plan["signals"]:
        for k in ("from", "to"):
            if s[k].get("terminal"):
                by_terminal[s[k]["terminal"]].add(s["net"])
    allowed = set()
    for nets in by_terminal.values():
        for x in nets:
            for y in nets:
                allowed.add((x, y))
    for nets in by_terminal.values():
        if len(nets) > 1:
            print(f"  （同じ端子を共有: {', '.join(sorted(nets))}）")

    seen = {}
    for n, i in net_island.items():
        if i is not None and i in seen and (seen[i], n) not in allowed:
            bad.append(f"短絡: {seen[i]} と {n} が同じ島 {i}")
        seen[i] = n

    print("\n=== 電源")
    vdd = look(*FRAME_VDD_PIN, "M1")
    gnd = look(*FRAME_VSS_PIN, "M2")
    print(f"  フレーム M1 VDD ピン {FRAME_VDD_PIN} -> 島 {vdd}")
    print(f"  フレーム VSS 壁ピン  {FRAME_VSS_PIN} -> 島 {gnd}")
    if vdd is None or gnd is None:
        bad.append("フレームの電源ピンが島に乗っていない")
    elif vdd == gnd:
        bad.append(f"VDD と GND が同じ島 {vdd}")
    for n, i in net_island.items():
        if i is not None and i in (vdd, gnd):
            bad.append(f"{n} が電源の島 {i} に入っている")

    rails = {"VDD": vdd, "GND": gnd}
    ties = plan.get("ties")
    if ties is None:
        ties = plan["hiz_ties"] + plan["float_ties"]
    for t in ties:
        i = look(t["x"], t["y"], "M2")
        if i != rails[t["tie"]]:
            bad.append(f"{t['terminal']} が {t['tie']} の島に入っていない（{i}）")
    print(f"  HIZ / 浮いた OUT {len(ties)} 本のレール直結を確認")

    # コアの電源タップ
    dx, dy = plan["core_offset"]
    ly2 = db.Layout()
    ly2.read(cfg.CHIP_CORE_GDS)
    core = ly2.cell(cfg.TOP_CELL_NAME)
    # --- I2C 移植 (20): 下辺のタップは開放でよい --------------------------
    # 下のチャネルは RING_OSC とロゴで埋まっていて、下辺のタップから
    # 外へ出る道が無い（route_chip の移植 (17)）。TAP 柱で上辺と繋がって
    # いるので電気的には届く -- **繋がっていることは確かめる**が、
    # 「フレームまで自力で届いているか」は上辺のタップだけに問う。
    ct_core = core.bbox().top * ly2.dbu
    taps = open_taps = 0
    for s in core.shapes(ly2.layer(49, 0)).each():
        if not s.is_text() or s.text.string not in rails:
            continue
        x, y = s.text.x * ly2.dbu + dx, s.text.y * ly2.dbu + dy
        i = look(x, y, "M2")
        top_side = s.text.y * ly2.dbu > ct_core / 2.0
        taps += 1
        if not top_side:
            open_taps += 1
        if i != rails[s.text.string]:
            bad.append(f"コアの {s.text.string} タップ ({x:.1f}, {y:.1f}) "
                       f"が島 {i}（期待 {rails[s.text.string]}）"
                       + ("" if top_side else "  ※下辺"))
    print(f"  コアの電源タップ {taps} 本を確認"
          f"（うち下辺 {open_taps} 本は TAP 柱経由）")

    # --- I2C 移植 (24): RING_OSC の電源とバスバー --------------------------
    # RING_OSC は最初の版ではチップ電源にまったく繋がっていなかった。
    # 移植 (23) で両脇の M2 ストラップを M1 に落として上下のバスバーへ
    # 繋いだので、5 本のレール全部が正しい島に乗っていることを確かめる。
    # レールの y は RING_OSC の GDS 実測（セル y に RING_OSC_ORIGIN[1] を足す）。
    ro_y = cfg.RING_OSC_ORIGIN[1]
    # セル y は RING_OSC 自身のラベル位置（GDS 実測）をそのまま使う。
    ro_checks = [("VSS 下端レール", -106.9, "GND"), ("VDD 下レール", -52.3, "VDD"),
                 ("VSS 中レール", 2.3, "GND"), ("VDD 上レール", 56.9, "VDD"),
                 ("VSS 上端レール", 111.5, "GND")]
    for nm, cy, rail in ro_checks:
        i = look(cfg.RING_OSC_ORIGIN[0] + 400.0, ro_y + cy, "M1")
        if i != rails[rail]:
            bad.append(f"RING_OSC の {nm} が島 {i}（期待 {rails[rail]} = {rail}）")
    print(f"  RING_OSC のレール {len(ro_checks)} 本を確認")
    for nm, x, y, rail in (("RING_OSC 上の VDD バー", 0.0, -522.5, "VDD"),
                           ("RING_OSC 下の VSS バー", 0.0, -780.0, "GND")):
        i = look(x, y, "M1")
        if i != rails[rail]:
            bad.append(f"{nm} が島 {i}（期待 {rails[rail]} = {rail}）")
    print("  RING_OSC 上下の M1 バスバー 2 本を確認")

    # REG8x16 のポート（チップ側でバーまで延ばした 4 本 + step11 の右下 1 組）
    # I2C にマクロは無い（i2c_config.MACRO_MODE = "none"）。
    if getattr(cfg, "MACRO_MODE", "none") == "none":
        print()
        if bad:
            for b in bad:
                print(f"PROBLEM: {b}")
            return 1
        print(f"すべて OK（{len(net_island)} ネットが独立、"
              f"電源はフレームまで届いている）")
        return 0
    import connect_macro_power as _cmp
    origin = None
    for inst in core.each_inst():
        if ly2.cell(inst.cell_index).name == cfg.MACRO_CELL:
            origin = (inst.dtrans.disp.x, inst.dtrans.disp.y)
            break
    if origin is None:
        bad.append(f"{cfg.MACRO_CELL} がコアに無い")
    else:
        mports = _cmp.macro_power_ports(cfg.LEF_PATH, cfg.MACRO_CELL)
        nm = 0
        for net, rail in (("vdd", "VDD"), ("vss", "GND")):
            for r in mports[net]:
                x = origin[0] + (r[0] + r[2]) / 2.0 + dx
                y = origin[1] + (r[1] + r[3]) / 2.0 + dy
                i = look(x, y, "M2")
                nm += 1
                side = "上" if r[1] > 400 else "下"
                if i != rails[rail]:
                    bad.append(f"{cfg.MACRO_CELL}.{net} の{side}辺ポート "
                               f"({x:.1f}, {y:.1f}) が島 {i}（期待 {rails[rail]}）")
        print(f"  {cfg.MACRO_CELL} の電源ポート {nm} 本を確認")

    print()
    if bad:
        for b in bad:
            print(f"PROBLEM: {b}")
        return 1
    print("すべて OK（14 本の信号が独立、電源はフレームまで届いている）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

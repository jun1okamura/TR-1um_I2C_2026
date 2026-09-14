#!/usr/bin/env python3
"""電源ラベルが正しいネットに乗っているかを、素子の側から検査する。

  usage: python3 scripts/label_check.py lef/TR-1um_STDCELL.gds [CELL ...]

**ラベルは人が置くので間違える。** DRC も LVS も見逃す:
  * DRC はラベルを見ない
  * LVS は設計ネットリストと突き合わせるので、**両方で同じ間違い**を
    していれば通ってしまう

そこで名前ではなく**素子の繋がり**から判定する。

  VDD レール = PMOS のソース／ドレインが付き、NMOS が 1 つも付かないネット
  VSS レール = NMOS のソース／ドレインが付き、PMOS が 1 つも付かないネット

この判定と食い違うラベル（VDD レールに載った `vss` など）を報告する。
実際に DEC0 / DEC2 / DEC16 の VDD レールに `vss` ラベルが 1 枚ずつ乗っていて、
REG8x16 を抽出すると `vdd|vss` という SPICE に流せないネット名が出ていた。
"""
from __future__ import annotations
import argparse, sys, os, collections
import klayout.db as db

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import klayout_extract as ke

GND = {"vss", "gnd", "VSS", "GND"}
PWR = {"vdd", "VDD"}
# ラベルレイヤ -> 金属レイヤ。**これを守らないと誤検出する。**
# ADDBUF では M1 の vdd レールの真上を gnd の M2 ストラップが通っていて、
# 層を無視して座標だけで当てると「VDD ラベルが VSS レールに乗っている」と誤報した。
LBL = {(48, 0): "M1", (48, 1): "M1", (49, 0): "M2", (49, 1): "M2"}
TERM = {0: "S", 1: "G", 2: "D", 3: "B"}


def labels_of(ly, cell):
    """[(name, layer, x_dbu, y_dbu)] — セル配下の全テキスト"""
    out = []
    c = ly.cell(cell)
    for ld in LBL:
        li = ly.layer(*ld)
        for it in c.begin_shapes_rec(li):
            s = it.shape()
            if s.is_text():
                t = s.text.transformed(it.trans())
                out.append((s.text.string, ld, t.x, t.y))
    return out


def classify(net):
    """ネットに付いた素子から 'VDD' / 'VSS' / None を返す。"""
    p = n = 0
    for t in net.each_terminal():
        if TERM[t.terminal_id()] not in ("S", "D"):
            continue
        if t.device().device_class().name.startswith("P"):
            p += 1
        else:
            n += 1
    if p >= 2 and n == 0:
        return "VDD"
    if n >= 2 and p == 0:
        return "VSS"
    return None


def check(gds, cell):
    l2n = ke.build(gds, cell, False)
    nl = l2n.netlist()
    nl.make_top_level_pins(); nl.combine_devices(); nl.purge(); nl.purge_nets()
    c = nl.circuit_by_name(cell)
    if c is None:
        return []
    ly = db.Layout(); ly.read(gds)
    li_m1, li_m2 = l2n.layer_by_name("M1"), l2n.layer_by_name("M2")

    # 電源っぽいネットの形状を集める
    rails = []
    for net in c.each_net():
        kind = classify(net)
        if kind is None:
            continue
        shp = {}
        for lname, li in (("M1", li_m1), ("M2", li_m2)):
            r = l2n.shapes_of_net(net, li, True); r.merge()
            shp[lname] = r
        rails.append((kind, net.expanded_name(), shp))

    bad = []
    for name, ld, x, y in labels_of(ly, cell):
        want = "VDD" if name in PWR else "VSS" if name in GND else None
        if want is None:
            continue
        metal = LBL[ld]                    # ラベルの層に対応する金属だけを見る
        t = db.Region(db.Box(x - 1, y - 1, x + 1, y + 1))
        for kind, nname, shp in rails:
            if (shp[metal] & t).count() and kind != want:
                bad.append((name, ld, x, y, kind, nname))
    return bad


def ground_spelling(ly, cell):
    """そのセルが使っているグランドの綴り（gnd / vss）に合わせる"""
    c = ly.cell(cell)
    seen = collections.Counter()
    for ld in LBL:
        for it in c.begin_shapes_rec(ly.layer(*ld)):
            sh = it.shape()
            if sh.is_text() and sh.text.string in GND:
                seen[sh.text.string] += 1
    return seen.most_common(1)[0][0] if seen else "gnd"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("cells", nargs="*")
    ap.add_argument("--fix", action="store_true",
                    help="食い違ったラベルを正しい名前に書き換えて GDS を上書きする")
    ap.add_argument("-o", "--out", default=None, help="--fix の出力先（既定は上書き）")
    a = ap.parse_args()
    ly = db.Layout(); ly.read(a.gds)
    cells = a.cells or [c.name for c in ly.each_cell()
                        if not c.name.startswith(("$$$", "via"))]
    u = ly.dbu
    nbad = 0
    fixes = []
    for cell in sorted(cells):
        try:
            bad = check(a.gds, cell)
        except Exception as e:                      # noqa: BLE001
            print(f"  ! {cell}: 検査できず ({e})")
            continue
        for name, ld, x, y, kind, nname in bad:
            print(f"  ! {cell:<10} ラベル '{name}' ({ld[0]},{ld[1]}) @ "
                  f"{x*u:.1f},{y*u:.1f} が {kind} レール（抽出名 '{nname}'）に乗っている")
            nbad += 1
            fixes.append((cell, name, ld, x, y, kind))

    if a.fix and fixes:
        print()
        done = 0
        for cell, name, ld, x, y, kind in fixes:
            c = ly.cell(cell)
            li = ly.layer(*ld)
            # 書き換えは**そのセルが自分で持っているテキストだけ**。
            # 子セル由来のものは親では直せない（DEC2 の 2 件は DEC0 を直せば消える）。
            tgt = None
            for sh in c.shapes(li).each():
                if sh.is_text() and sh.text.string == name and \
                   abs(sh.text.x - x) <= 1 and abs(sh.text.y - y) <= 1:
                    tgt = sh
                    break
            if tgt is None:
                print(f"  - {cell}: '{name}' は子セル由来。親では直せない")
                continue
            new = "vdd" if kind == "VDD" else ground_spelling(ly, cell)
            t = tgt.text
            t.string = new
            tgt.text = t
            print(f"  fix {cell}: '{name}' -> '{new}' @ {x*u:.1f},{y*u:.1f}")
            done += 1
        if done:
            out = a.out or a.gds
            ly.write(out)
            print(f"wrote {out}  ({done} 件)")
            return 0
    print(f"\n{len(cells)} セルを検査、食い違い {nbad} 件")
    return 1 if nbad else 0


if __name__ == "__main__":
    sys.exit(main())

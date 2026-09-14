#!/usr/bin/env python3
"""add_top_pins.py -- ボンドパッドに LVS 用のピンを打つ（チップ step3）。

    layout/chip/step2_routed.gds  ->  layout/chip/step3_top_pins.gds

LVS はどちらの側も、**誰も宣言していないトップのポート**を名乗れない。
ソース側（`mkchipnet.py`）は 16 本のボンドパッドを `.subckt` のポートに
並べるので、レイアウト側にも同じ宣言を置く。コアで使っている流儀と同じ:

    M2PIN (49,1) に 3.0 x 3.0 µm の箱、TXM2 (49,0) に**箱の中心**でテキスト
    （KLayout の抽出はラベルが箱の中にあることを要求する）

パッドの位置と名前は `lef/TR-1um_frame_25x25.gds` から読む。`OSS_ESD_5V_DIO`
/ `OSS_ESD_5V_VDD` / `OSS_ESD_5V_VSS` のインスタンス原点がパッドの中心で、
そこに乗っている `P<n>` / `VDD` / `VSS` のラベルが名前（実測 16 個）。
番号を位置から決め打ちしない -- フレームが振り直されたら黙って壊れる。

書く前に、**中心に本当に M2 があるか**を必ず見る。何も無いところにピンを
置くと、そこだけ孤立した網として抽出されて LVS が幻を追うことになる。

## ラベルだけでは足りない -- M2 の実体も置く

パッドの金属は `OSS_FRAME_GIO` の**中**にある。トップにラベルしか置かないと、
抽出器の設定によっては「トップから物理的に触っていない」と見なされて、
サブサーキットにピンが生えない。2026-09-14 に PDK の LVS ランセットで:

    No equivalent pin P10 from reference netlist found in netlist.
    This is an indication that a physical connection is not made to the
    subcircuit.

P10/P11/P12/P13/P15 -- ちょうど**出力パッド 5 本**。入力パッドは `P<n>` 端子
までコアから配線が来ているので触れているが、出力パッドはコアが `OUT<n>` を
駆動するだけで、ボンドパッドの網にはトップから何も触れていなかった
（`scripts/klayout_extract.py` はラベル層を M2 に繋ぐので 44 ピン全部見えて
いて、気づけなかった）。

なので**同じ箱を M2 (20,0) にも置く**。パッドの M2 に重なるだけで DRC は
変わらず（マージされる）、抽出器の設定によらずピンが生える。

  usage: python3 scripts/pnr/add_top_pins.py [-o OUT]
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

import klayout.db as db                                     # noqa: E402

IN_GDS = os.path.join(cfg.CHIP, "step2_routed.gds")
OUT_GDS = os.path.join(cfg.CHIP, "step3_top_pins.gds")

M2PIN_LAYER = (49, 1)
TXM2_LAYER = (49, 0)
M2_LAYER = (20, 0)
PAD_CELLS = ("OSS_ESD_5V_DIO", "OSS_ESD_5V_VDD", "OSS_ESD_5V_VSS")
PIN_SIZE_UM = 3.0
TEXT_SIZE_UM = 20.0
NAME_RE = re.compile(r"^(P\d+|VDD|VSS)$")


def bond_pads(gds=None, cell=None):
    """{name: (x, y, edge)} -- ボンドパッド 16 個（チップ座標）。"""
    gds = gds or cfg.FRAME_GDS
    cell = cell or cfg.FRAME_CELL
    ly = db.Layout()
    ly.read(gds)
    u = ly.dbu
    top = ly.cell(cell)
    centres = {(round(i.dtrans.disp.x, 1), round(i.dtrans.disp.y, 1))
               for i in top.each_inst()
               if ly.cell(i.cell_index).name in PAD_CELLS}
    out = {}
    for lay in (TXM2_LAYER, (48, 0)):
        it = top.begin_shapes_rec(ly.layer(*lay))
        while not it.at_end():
            s = it.shape()
            if s.is_text():
                t = s.text.transformed(it.trans())
                p = (round(t.x * u, 1), round(t.y * u, 1))
                if p in centres and NAME_RE.match(t.string):
                    edge = (("RIGHT" if p[0] > 0 else "LEFT")
                            if abs(p[0]) > abs(p[1]) else
                            ("TOP" if p[1] > 0 else "BOTTOM"))
                    out.setdefault(t.string, (p[0], p[1], edge))
            it.next()
    if len(out) != len(centres):
        raise SystemExit(f"パッド {len(centres)} 個に対して名前が {len(out)} 個: "
                         f"{sorted(out)}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--in-gds", default=IN_GDS)
    ap.add_argument("-o", "--out", default=OUT_GDS)
    ap.add_argument("--text-size", type=float, default=TEXT_SIZE_UM)
    a = ap.parse_args()

    pads = bond_pads()
    ly = db.Layout()
    ly.read(a.in_gds)
    u = ly.dbu
    top = ly.cell(cfg.CHIP_TOP_CELL)
    if top is None:
        raise SystemExit(f"{cfg.CHIP_TOP_CELL} が {a.in_gds} に無い")

    m2 = db.Region(top.begin_shapes_rec(ly.layer(*M2_LAYER))).merged()
    existing = {s.text.string for s in top.shapes(ly.layer(*TXM2_LAYER)).each()
                if s.is_text()}
    half = PIN_SIZE_UM / 2.0
    pin_li, txt_li = ly.layer(*M2PIN_LAYER), ly.layer(*TXM2_LAYER)
    m2_li = ly.layer(*M2_LAYER)

    problems, added = [], []
    for name in sorted(pads, key=lambda n: (n[0] != "P", n)):
        x, y, edge = pads[name]
        box = db.DBox(x - half, y - half, x + half, y + half).to_itype(u)
        if (m2 & db.Region(box)).is_empty():
            problems.append(f"{name} ({x}, {y}): ピンの下に M2 が無い")
            continue
        if name in existing:
            problems.append(f"{name}: トップに同じ名前のラベルがもうある")
            continue
        top.shapes(pin_li).insert(box)
        top.shapes(m2_li).insert(box)      # ラベルだけでなく金属の実体も
        t = db.DText(name, x, y).to_itype(u)
        t.size = int(round(a.text_size / u))
        top.shapes(txt_li).insert(t)
        added.append((name, x, y, edge))

    for name, x, y, edge in added:
        print(f"  {name:5s} ({x:8.1f}, {y:8.1f})  {edge}")
    print(f"{len(added)} 本: M2PIN {M2PIN_LAYER} と M2 {M2_LAYER} に "
          f"{PIN_SIZE_UM} 角 + TXM2 {TXM2_LAYER} のテキスト"
          f"（セル {cfg.CHIP_TOP_CELL}）")
    if problems:
        for p in problems:
            print("  PROBLEM: " + p)
        raise SystemExit(f"{len(problems)} 件 -- 何も書いていない")

    ly.write(a.out)
    print(f"\nwrote {os.path.relpath(a.out, cfg.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

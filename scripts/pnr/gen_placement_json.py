#!/usr/bin/env python3
"""gen_placement_json.py -- ルータが読む配置 JSON へ変換する。

  usage: python3 scripts/pnr/gen_placement_json.py [-o layout/placement_nrow_fm.json]

`place.py` が配置そのものを持ち、ここではそれを移植元のルータ
（`route_channels_nrow_fm.py` 以下）が期待するスキーマに直すだけ:

  {"row_height", "row_width", "ch_heights",
   "rows": [[{"type", "name", "x", "width",
              "pins": {PIN: {"net", "use", "direction",
                             "rects": [[layer, x0, y0, x1, y1], ...]}}}]]}

ピン矩形は LEF から取り、x は**絶対座標**に直す（ルータは行の y だけ足す）。
ネットはゲートレベルネットリストから。Yosys の `assign` 別名は
`netlist_parser` の union-find が解決済み。

TAP / FILL には合成した名前を付ける。TAP 直後に予約した FILL2 は
`FILLPRI_*` という名前にする（ルータが優先 M2 コリドーとして自動検出する）。

SCLK_SPI 版との違いは 2 つ:

  1. **レイヤ名を M1 / M2 に正規化する。** TD4 の LEF は `METAL1` / `METAL2`
     と書く（`$APRTOOLS/apr/mklef.py` が LEF の慣習どおり技術ファイルのレイヤ名を
     使うため）が、ルータは `"M2"` と文字列比較している。ここで直さないと
     **ピンが 1 本も見つからないまま静かに通る**。

  2. **マクロ `MEMPORT` を row0 の末尾に入れる。** 帯はルータ座標の下
     （y -399.6…0）にあり、パッド 21 本はその上辺 (y -4.5…-1.1)。
     ルータはピンの y に `row_y0[0]` を足すので、ここで
     **row0 からの相対 y**（= 負の値）に直して渡す。ルータからは
     「row0 のセルのピンが下に飛び出している」ように見える。
     ストラブは min/max で描かれるので向きは問題にならない。
     行の右端の照合だけはマクロを除いて行う
     （`route_channels_nrow_fm.py` の「TD4 移植 (2)」）。
"""
from __future__ import annotations
import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import lef_parser                                           # noqa: E402
import netlist_parser                                       # noqa: E402
import netlist_util as nu                                   # noqa: E402
import place                                                # noqa: E402

PLACE = os.path.join(cfg.LAYOUT, "step4", "place_step4_fill.json")

# LEF のレイヤ名 -> ルータが使う名前
LAYER = {"METAL1": "M1", "METAL2": "M2", "M1": "M1", "M2": "M2"}


def conv_rects(rects, dx):
    out = []
    for lay, x0, y0, x1, y1 in rects:
        if lay not in LAYER:
            raise SystemExit(f"知らないレイヤ名 {lay!r}（LAYER に足すこと）")
        out.append([LAYER[lay], round(dx + x0, 4), y0, round(dx + x1, 4), y1])
    return out


NO_MACRO = getattr(cfg, "MACRO_MODE", "landscape") == "none"


def main(place_json=PLACE, out_json=None, net_path=None, lef_path=None):
    out_json = out_json or cfg.PLACEMENT_JSON
    net_path = net_path or cfg.NET_PATH
    lef_path = lef_path or cfg.LEF_PATH

    pl = json.load(open(place_json))
    macros = lef_parser.parse_lef(lef_path)
    net = netlist_parser.parse_netlist(net_path)
    pins_of = {name: pins for _t, name, pins in net["instances"]}
    type_of = {name: t for t, name, _p in net["instances"]}

    rows, npri, nsig = [], 0, 0
    for r, row in enumerate(pl["rows"]):
        out = []
        for k, e in enumerate(row):
            cell, inst = e["cell"], e["inst"]
            if inst:
                name = inst
                if type_of[inst] != cell:
                    raise SystemExit(f"{inst}: ネットリストは {type_of[inst]}、"
                                     f"配置は {cell}")
            elif e.get("pri"):
                name = f"FILLPRI_r{r}_{npri}"
                npri += 1
            elif cell.startswith("TAP"):
                name = f"TAP_r{r}_{k}"
            else:
                name = f"FILL_r{r}_{k}"

            pins = {}
            for pname, pinfo in macros[cell]["pins"].items():
                netname = None
                if pinfo["use"] not in ("POWER", "GROUND") and inst:
                    netname = pins_of.get(inst, {}).get(pname)
                    if netname:
                        nsig += 1
                pins[pname] = {"net": netname, "use": pinfo["use"],
                               "direction": pinfo["direction"],
                               "rects": conv_rects(pinfo["rects"], e["x"])}
            out.append({"type": cell, "name": name, "row": r, "x": e["x"],
                        "width": e["w"], "pins": pins})
        w = round(out[-1]["x"] + out[-1]["width"], 3)
        if abs(w - pl["row_width"]) > 1e-6:
            raise SystemExit(f"row {r} の右端が {w}（行幅 {pl['row_width']} のはず）")
        rows.append(out)

    # ---- マクロを row0 の末尾に（I2C はマクロ無しなので丸ごと飛ばす）----
    mcell = minst = None
    mpins, mconn, nmac, mx0, my0, row0_y0 = {}, {}, 0, 0.0, 0.0, cfg.row_y()[0][0]
    if not NO_MACRO:
        # ---- マクロを row0 の末尾に ------------------------------------------
        mx0, my0, _, my1 = cfg.macro_box()
        if cfg.MACRO_MODE == "landscape" and my1 > 1e-6:
            raise SystemExit(f"マクロ帯の上端 {my1} が 0 を超える。帯はルータ座標の"
                             f"下に置くこと")
        mrow = getattr(cfg, "MACRO_ALIGN_ROW", 0) if cfg.MACRO_MODE == "portrait" else 0
        row0_y0 = cfg.row_y()[0][mrow]
        mcell, minst = pl["macro"]["cell"], pl["macro"].get("net_cell", cfg.MACRO_NET_CELL)
        mcell, minst = pl["macro"]["cell"], pl["macro"]["inst"]
        # **バス接続を開く。** `netlist_parser` はピンごとに 1 ネットしか持たず、
        # `.ADD({ _004_, _003_, _002_, _001_ })` を丸ごと 1 本として返す。
        # そのままだと LEF 側の `ADD[0]` … `ADD[3]` に 1 本も当たらず、
        # **マクロのピンが 1 本しか繋がらないまま静かに通る**。
        resolve = netlist_parser._build_alias_resolver(open(net_path).read())
        mconn = {}
        for i in nu.parse(open(net_path).read()):
            if i.name != minst:
                continue
            for pin, expr in i.conns.items():
                for pn, n in place.expand(pin, expr):
                    mconn[pn] = resolve(n.strip())
        mpins, nmac = {}, 0
        for pname, pinfo in macros[mcell]["pins"].items():
            netname = None
            if pinfo["use"] not in ("POWER", "GROUND"):
                netname = mconn.get(pname)
                if netname:
                    nmac += 1
            # ピンの y は**帯ローカル**。ルータは row_y0[0] を足すので、
            # (帯の y0 + ローカル y) - row_y0[0] に直しておく。
            mpins[pname] = {"net": netname, "use": pinfo["use"],
                            "direction": pinfo["direction"],
                            "rects": [[l, x0, round(my0 + y0 - row0_y0, 4),
                                       x1, round(my0 + y1 - row0_y0, 4)]
                                      for l, x0, y0, x1, y1
                                      in conv_rects(pinfo["rects"], mx0)]}
        # マクロは**ピン列が向くチャネルの上の行**に足す。ルータは行ごとに
        # `row_y0[r]` を足してピンの絶対 y を作るので、ここで入れる行と
        # 上の `row0_y0` は同じ行でなければならない。
        rows[mrow].append({"type": mcell, "name": minst, "row": mrow, "x": mx0,
                           "width": cfg.MACRO_W, "pins": mpins})

    data = {"row_height": pl["row_h"], "row_width": pl["row_width"],
            "core_w": pl["core_w"], "core_h": pl["core_h"],
            "ch_heights": pl["ch_heights"],
            "macro": (None if NO_MACRO
                      else {"cell": mcell, "inst": minst, "box": pl["macro"]["box"]}),
            "top_cell": cfg.TOP_CELL_NAME, "rows": rows}
    os.makedirs(os.path.dirname(out_json), exist_ok=True)
    json.dump(data, open(out_json, "w"), indent=1)
    print(f"wrote {os.path.relpath(out_json, cfg.ROOT)}")
    print(f"  行 {[len(r) for r in rows]}   行幅 {data['row_width']}   "
          f"コア {data['core_w']} x {data['core_h']}")
    print(f"  ch_heights {data['ch_heights']}")
    print(f"  優先コリドー {npri} 本 / ネットの付いた信号ピン {nsig} 本")
    if not NO_MACRO:
        pad_y = [r[2] for p in mpins.values() for r in p["rects"]]
        print(f"  マクロ {mcell} {minst} @ ({mx0}, {my0})、信号パッド {nmac} 本 "
              f"（row0 相対 y {min(pad_y):.1f}…{max(pad_y):.1f}、絶対 y "
              f"{min(pad_y)+row0_y0:.1f}）")
        want = sum(1 for pn, pi in macros[mcell]["pins"].items()
                   if pi["use"] not in ("POWER", "GROUND"))
        if nmac != want:
            raise SystemExit(f"マクロの信号ピン {want} 本のうち {nmac} 本しか"
                             f"ネットが付いていない: "
                             f"{sorted(set(macros[mcell]['pins']) - set(mconn))}")

    return out_json


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--placement", default=PLACE)
    ap.add_argument("-o", "--output", default=None)
    ap.add_argument("--netlist", default=None)
    ap.add_argument("--lef", default=None)
    a = ap.parse_args()
    main(a.placement, a.output, a.netlist, a.lef)

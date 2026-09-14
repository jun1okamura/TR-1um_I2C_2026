#!/usr/bin/env python3
"""gen_top_routing_plan.py -- チップレベルの接続表と配線プラン。

  -> layout/chip/gio_connections.json      何と何を繋ぐか（論理）
  -> layout/chip/signal_routing_plan.json  その端点がどこにあるか（幾何）

移植元（SCLK_SPI / I2C）と同じ二段構え。**手で書くのは `PAD_MAP` だけ**で、
それは設計判断（`reference/05_pin_io_plan.md` §5 案A の確定表）。ほかは全部
実ファイルから読む:

  * パッド端子の座標   `lef/TR-1um_frame_25x25.gds`（`frame_pins.py`）
  * コアピンの座標     配置配線済みコアのラベル + `chip_geometry()` のオフセット
  * ポート一覧         合成後ネットリスト

## `OSS_ESD_5V_DIO` の挙動（`reference/05_pin_io_plan.md` §2）

    HIZ = 1  -> ドライバを放す。パッドは Hi-Z（入力専用）
    HIZ = 0  -> ドライバ ON。パッドは OUT の値を出す（非反転）

TD4 は 14 本すべて**方向が固定**なので、`HIZ` はレールに直結する
（入力は VDD、出力は GND）。`TIEHI`/`TIELO` はライブラリに無い。

入力パッドはコアのピンを **`P<n>`（パッド内側のスタブ）** に繋ぐ。
出力パッドはコアが **`OUT<n>`** を駆動する（`P<n>` には繋がない）。

  usage: python3 scripts/pnr/gen_top_routing_plan.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# **チップ組み立ては縦置き専用。** `TD4_MACRO_MODE` の既定は landscape で、
# 付け忘れると `FINAL_GDS` が step10 を指し、`MACRO_CELL` も MEMPORT になる
# （2026-09-14: マクロ電源の入っていないコアを載せたチップを作ってしまった）。
# ここで固定する。コア側を landscape で作り直したいときはコア側のスクリプトで。
os.environ.setdefault("TD4_MACRO_MODE", "portrait")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import frame_pins                                           # noqa: E402

import klayout.db as db                                     # noqa: E402

OUT_CONN = os.path.join(cfg.CHIP, "gio_connections.json")
OUT_PLAN = os.path.join(cfg.CHIP, "signal_routing_plan.json")

# `reference/05_pin_io_plan.md` §5 案A の確定表。P8=VSS / P16=VDD はフレーム固定。
# パッケージは上から下が MSB->LSB（P4=D[3] / P13=OUT[3]）。
PAD_MAP = {
    1:  {"role": "CLK",    "dir": "in",  "P": "clk",         "HIZ": "VDD"},
    2:  {"role": "WR",     "dir": "in",  "P": "wr",          "HIZ": "VDD"},
    3:  {"role": "NIBSEL", "dir": "in",  "P": "nibsel",      "HIZ": "VDD"},
    4:  {"role": "D[3]",   "dir": "in",  "P": "d[3]",        "HIZ": "VDD"},
    5:  {"role": "D[2]",   "dir": "in",  "P": "d[2]",        "HIZ": "VDD"},
    6:  {"role": "D[1]",   "dir": "in",  "P": "d[1]",        "HIZ": "VDD"},
    7:  {"role": "D[0]",   "dir": "in",  "P": "d[0]",        "HIZ": "VDD"},
    9:  {"role": "RSTN",   "dir": "in",  "P": "rst_n",       "HIZ": "VDD"},
    10: {"role": "OUT[0]", "dir": "out", "OUT": "out_port[0]", "HIZ": "GND"},
    11: {"role": "OUT[1]", "dir": "out", "OUT": "out_port[1]", "HIZ": "GND"},
    12: {"role": "OUT[2]", "dir": "out", "OUT": "out_port[2]", "HIZ": "GND"},
    13: {"role": "OUT[3]", "dir": "out", "OUT": "out_port[3]", "HIZ": "GND"},
    14: {"role": "EXEC",   "dir": "in",  "P": "exec",        "HIZ": "VDD"},
    15: {"role": "CF",     "dir": "out", "OUT": "cflag_o",   "HIZ": "GND"},
}

POWER_NETS = {"VDD", "GND"}
SITE = 5.4                      # リングのトラック間隔（コア内と同じ）
PIN_LAYERS = (((49, 0), (49, 1), "M2"), ((48, 0), (48, 1), "M1"))


def core_pins(gds, cell):
    """{port: {x,y,edge,layer,box}}（**チップ座標**ではなくコア座標）。

    移植元は上下の辺しか見ていなかった（あちらのコアは低くて横長で、
    中間行のポートも左右 10 µm 出るだけだった）。TD4 の縦置きは左辺に
    5 本出るので、**4 辺すべて**と **M1PIN / M2PIN の両方**を見る。"""
    ly = db.Layout()
    ly.read(gds)
    u = ly.dbu
    c = ly.cell(cell)
    if c is None:
        raise SystemExit(f"{cell} が {gds} に無い")
    bb = c.bbox()
    out = {}
    for txt_lay, shp_lay, lname in PIN_LAYERS:
        # **再帰で読んではいけない。** 標準セルは自分のピンラベル（A/Y/CK…）を
        # 同じ層に持っているので、`begin_shapes_rec` で拾うと 50 個以上出てくる。
        # トップレベルのポートマーカは `route_top_pins` / `add_power_pins` が
        # **コアセル直下**に打つので、そこだけ見る。
        shapes = db.Region()
        for sh in c.shapes(ly.layer(*shp_lay)).each():
            shapes.insert(sh.box if sh.is_box() else sh.polygon)
        shapes.merge()
        for s in c.shapes(ly.layer(*txt_lay)).each():
            if s.is_text() and s.text.string not in POWER_NETS:
                t = s.text
                hit = shapes.interacting(
                    db.Region(db.Box(t.x - 1, t.y - 1, t.x + 1, t.y + 1)))
                if not hit.is_empty():
                    b = hit.bbox()
                    cx = (b.left + b.right) / 2 * u
                    cy = (b.bottom + b.top) / 2 * u
                    d = {"L": cx - bb.left * u, "R": bb.right * u - cx,
                         "B": cy - bb.bottom * u, "T": bb.top * u - cy}
                    edge = {"L": "LEFT", "R": "RIGHT",
                            "B": "BOTTOM", "T": "TOP"}[min(d, key=d.get)]
                    out[s.text.string] = {
                        "x": round(cx, 2), "y": round(cy, 2), "edge": edge,
                        "layer": lname,
                        "box": [round(b.left * u, 2), round(b.bottom * u, 2),
                                round(b.right * u, 2), round(b.top * u, 2)],
                    }
    return out


def ring_s(x, y, r):
    """半径 r の正方形リング上の周長座標（右下角から反時計回り、0…8r）。

    パッド端子もコアピンも、いったんこの 1 本の物差しに載せると
    「どちら回りが近いか」「何 µm 回り込むか」が素直に出る。"""
    if abs(x) >= abs(y):                       # 左右の辺
        return (y + r) if x > 0 else (4 * r + (r - y))
    return (2 * r + (r - x)) if y > 0 else (6 * r + (x + r))


def ring_gap(a, b, r):
    d = abs(a - b) % (8 * r)
    return min(d, 8 * r - d)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--core-gds", default=None)
    ap.add_argument("--conn", default=OUT_CONN)
    ap.add_argument("--plan", default=OUT_PLAN)
    a = ap.parse_args()

    core_gds = a.core_gds or cfg.CHIP_CORE_GDS
    geom = cfg.chip_geometry(core_gds)
    dx, dy = geom["core_offset"]
    pads = frame_pins.load()
    pins = core_pins(core_gds, cfg.TOP_CELL_NAME)
    r = cfg.GIO_PIN_RADIUS

    # --- 突き合わせ -------------------------------------------------------
    want = set()
    for p in PAD_MAP.values():
        for k in ("P", "OUT"):
            if p.get(k) and p[k] not in POWER_NETS:
                want.add(p[k])
    missing = sorted(want - set(pins))
    extra = sorted(set(pins) - want)
    if missing:
        raise SystemExit(f"PAD_MAP が要求するコアピンがレイアウトに無い: {missing}")
    if extra:
        raise SystemExit(f"コアに PAD_MAP が使っていないピンがある: {extra}")

    conns, plan, rows = [], [], []
    for pad in sorted(PAD_MAP):
        e = PAD_MAP[pad]
        term = "P" if e["dir"] == "in" else "OUT"
        net = e[term]
        t = pads[f"{term}{pad}"]
        c = pins[net]
        cx, cy = round(c["x"] + dx, 2), round(c["y"] + dy, 2)
        s_pad, s_pin = ring_s(t["x"], t["y"], r), ring_s(cx, cy, r)
        gap = round(ring_gap(s_pad, s_pin, r), 1)
        same = t["edge"] == c["edge"]
        conns.append({
            "pad": pad, "role": e["role"], "dir": e["dir"], "net": net,
            "terminal": f"{term}{pad}", "hiz": e["HIZ"],
            "note": ("パッドはコアの入力を受ける（HIZ=1 で Hi-Z）" if e["dir"] == "in"
                     else "コアが OUT を駆動（HIZ=0 でドライバ ON）"),
        })
        plan.append({
            "net": net, "role": e["role"], "pad": pad,
            "from": {"what": "core", "x": cx, "y": cy,
                     "edge": c["edge"], "layer": c["layer"], "port": net},
            "to": {"what": "pad", "x": t["x"], "y": t["y"],
                   "edge": t["edge"], "layer": t["layer"], "terminal": f"{term}{pad}"},
            "ring_run_um": gap, "same_edge": same,
        })
        rows.append((pad, e["role"], net, c["edge"], cx, cy,
                     t["edge"], t["x"], t["y"], gap, same))

    # HIZ はレール直結（ネットではなく電源）
    hiz = [{"pad": pad, "terminal": f"HIZ{pad}", "tie": PAD_MAP[pad]["HIZ"],
            "x": pads[f"HIZ{pad}"]["x"], "y": pads[f"HIZ{pad}"]["y"],
            "edge": pads[f"HIZ{pad}"]["edge"]} for pad in sorted(PAD_MAP)]

    # 入力パッドの `OUT` は**浮いたゲート入力**。HIZ=1 でドライバは放している
    # ので論理には効かないが、ゲートが浮いたままなのは実チップとして良くない
    # （LVS も「どこにも繋がらない端子」を数える）。GND に落とす。
    # 出力パッドの `P` はボンドパッドそのものなので何もしない。
    floats = [{"pad": pad, "terminal": f"OUT{pad}", "tie": "GND",
               "x": pads[f"OUT{pad}"]["x"], "y": pads[f"OUT{pad}"]["y"],
               "edge": pads[f"OUT{pad}"]["edge"]}
              for pad in sorted(PAD_MAP) if PAD_MAP[pad]["dir"] == "in"]

    os.makedirs(cfg.CHIP, exist_ok=True)
    json.dump({"pad_cell": "OSS_ESD_5V_DIO",
               "pad_cell_behavior": {"HIZ=1": "Hi-Z（入力専用）",
                                     "HIZ=0": "PAD = OUT（非反転）"},
               "power_pads": {"P8": "VSS", "P16": "VDD"},
               "signals": conns, "hiz_ties": hiz, "float_ties": floats},
              open(a.conn, "w"), ensure_ascii=False, indent=1)
    json.dump({"core_offset": geom["core_offset"],
               "core_chip_bbox": geom["core_chip_bbox"],
               "pin_radius": r, "signals": plan, "hiz_ties": hiz,
               "float_ties": floats},
              open(a.plan, "w"), ensure_ascii=False, indent=1)

    print(f"=== パッド <-> コアピン（コアのオフセット {geom['core_offset']}）")
    print(f"{'pad':>4} {'role':8s} {'net':13s} "
          f"{'コアピン':16s}   {'パッド端子':16s}  リング周 同辺")
    for (pad, role, net, ce, cx, cy, te, tx, ty, gap, same) in rows:
        print(f"P{pad:<3d} {role:8s} {net:13s} "
              f"{ce:6s}({cx:8.1f},{cy:7.1f})   {te:6s}({tx:7.1f},{ty:7.1f})"
              f" {gap:8.1f}  {'✓' if same else ''}")
    # --- リングのどこで何本が重なるか（= その位置で要るトラック数）---------
    # 距離より**こちら**が効く。回り込みが長くても、同じ場所で重なる本数が
    # チャネルのトラック数に収まっていれば引ける。
    P = 8 * r
    segs = []
    for (pad, role, net, ce, cx, cy, te, tx, ty, gap, same) in rows:
        sa, sb = ring_s(cx, cy, r), ring_s(tx, ty, r)
        d = (sb - sa) % P
        segs.append((role, sa, d) if d <= P / 2 else (role, sb, P - d))
    sides = {"RIGHT": (0, 2 * r), "TOP": (2 * r, 4 * r),
             "LEFT": (4 * r, 6 * r), "BOTTOM": (6 * r, 8 * r)}
    print("\n  リングの混み具合（最大何本が同じ場所で重なるか / チャネルのトラック数）:")
    for nm, (lo, hi) in sides.items():
        mx, x = 0, lo
        while x < hi:
            n = sum(1 for _n, st, ln in segs if ((x - st) % P) <= ln)
            mx = max(mx, n)
            x += 2.0
        ch = geom["channel_" + nm.lower()][0]
        print(f"    {nm:6s} {mx:2d} 本 / {int(ch // SITE):2d} トラック"
              f"（チャネル {ch:.1f} µm）")

    n_same = sum(1 for r_ in rows if r_[10])
    print(f"\n  同じ辺に出ているもの {n_same} / {len(rows)}、"
          f"リング周の回り込み 最大 {max(r_[9] for r_ in rows):.1f} µm / "
          f"合計 {sum(r_[9] for r_ in rows):.1f} µm")
    import collections
    print("  コアピンの辺:", dict(collections.Counter(r_[3] for r_ in rows)))
    print("  パッドの辺  :", dict(collections.Counter(r_[6] for r_ in rows)))
    print(f"\nwrote {os.path.relpath(a.conn, cfg.ROOT)}")
    print(f"wrote {os.path.relpath(a.plan, cfg.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

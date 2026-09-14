#!/usr/bin/env python3
"""gen_top_routing_plan.py -- チップレベルの接続表と配線プラン。

  -> layout/chip/gio_connections.json      何と何を繋ぐか（論理）
  -> layout/chip/signal_routing_plan.json  その端点がどこにあるか（幾何）

移植元（SCLK_SPI / TD4）と同じ二段構え。**手で書くのは `PAD_MAP` だけ**で、
それは設計判断（V10 の確定ピン配置 = README のピン表）。ほかは全部実ファイルから読む:

  * パッド端子の座標   `lef/TR-1um_frame_25x25.gds`（`frame_pins.py`）
  * コアピンの座標     配置配線済みコアのラベル + `chip_geometry()` のオフセット
  * RING_OSC の座標    `lef/RING_OSC.lef` + `i2c_config.RING_OSC_ORIGIN`

## `OSS_ESD_5V_DIO` の挙動

    HIZ = 1  -> ドライバを放す。パッドは Hi-Z（入力専用）
    HIZ = 0  -> ドライバ ON。パッドは OUT の値を出す（非反転）

**TD4 と決定的に違うのはここ。** TD4 は 14 本すべて方向が固定なので `HIZ` を
レールに直結できた。I2C のチップは 2 種類の**動的な** HIZ を使う:

  * `SDA`（P2）は**オープンドレイン**。`OUT2` は GND に直結し、コアの
    `sda_oe` が `HIZ2` を叩く。`sda_oe=0` で Low を駆動、`1` で放す
    （外部プルアップが High を作る）。RTL の極性がそのままパッドに合う。
  * 8 本のデータパッド（P3…P6 / P11…P14）は `DIS`（P7）1 本で方向を一括制御。
    `DIS=0` で出力（`rx_data[i]` を出す）、`DIS=1` で Hi-Z（`tx_data[i]` を受ける）。
    **DIS の鎖はパッド端子どうしの配線**でコアを通らない。

`addr_match` / `busy` / `rw` / `rx_valid` は V7/V9/V10 と同じく**未ボンド**。
16 本のパッドに収まらないため。`UNBONDED` に挙げてある。

  usage: python3 scripts/pnr/gen_top_routing_plan.py
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import frame_pins                                           # noqa: E402

import klayout.db as db                                     # noqa: E402

OUT_CONN = os.path.join(cfg.CHIP, "gio_connections.json")
OUT_PLAN = os.path.join(cfg.CHIP, "signal_routing_plan.json")

# V10 の確定ピン表（README のピン配置表）。P8=VSS / P16=VDD はフレーム固定。
# 物理パッド番号の昇順と bit 番号が単調対応する（P3…P6 = bit0-3、P11…P14 = bit4-7）。
#
#   P     パッドの入力センス線 -> コアの入力ネット
#   OUT   コア（か RING_OSC）の出力ネット -> パッドのドライバ入力
#         "GND" と書いたらレール直結（SDA のオープンドレイン）
#   HIZ   "VDD" / "GND" はレール直結。それ以外は**ネット名**で、動的制御
PAD_MAP = {
    1:  {"role": "SCL",   "P": "scl",                                  "HIZ": "VDD"},
    2:  {"role": "SDA",   "P": "sda_in",    "OUT": "GND",              "HIZ": "sda_oe"},
    3:  {"role": "D0",    "P": "tx_data[0]", "OUT": "rx_data[0]",      "HIZ": "DIS"},
    4:  {"role": "D1",    "P": "tx_data[1]", "OUT": "rx_data[1]",      "HIZ": "DIS"},
    5:  {"role": "D2",    "P": "tx_data[2]", "OUT": "rx_data[2]",      "HIZ": "DIS"},
    6:  {"role": "D3",    "P": "tx_data[3]", "OUT": "rx_data[3]",      "HIZ": "DIS"},
    7:  {"role": "DIS",   "P": "DIS",                                  "HIZ": "VDD"},
    9:  {"role": "OSCD",  "OUT": "RING_OSC.OUTD",                      "HIZ": "GND"},
    10: {"role": "OSC",   "OUT": "RING_OSC.OUT",                       "HIZ": "GND"},
    11: {"role": "D4",    "P": "tx_data[4]", "OUT": "rx_data[4]",      "HIZ": "DIS"},
    12: {"role": "D5",    "P": "tx_data[5]", "OUT": "rx_data[5]",      "HIZ": "DIS"},
    13: {"role": "D6",    "P": "tx_data[6]", "OUT": "rx_data[6]",      "HIZ": "DIS"},
    14: {"role": "D7",    "P": "tx_data[7]", "OUT": "rx_data[7]",      "HIZ": "DIS"},
    15: {"role": "RSTN",  "P": ["rst_n", "RING_OSC.ENB"],              "HIZ": "VDD"},
}

# パッドに出さないコアの出力。16 パッドに収まらないので V7/V9/V10 と同じく落とす。
UNBONDED = {"addr_match", "busy", "rw", "rx_valid"}

# パッド端子どうしで閉じるネット（コアを通らない）。
#   DIS: P7 のセンス線 -> 8 本のデータパッドの HIZ
PAD_ONLY_NETS = {"DIS": "P7"}

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


def ringosc_pins():
    """{pin: {x,y,edge,layer}}（**チップ座標**）。LEF の RECT を実測して置き場所を足す。

    RING_OSC は帯状（1620 x 244.8）で、`OUT` / `OUTD` は右端の M1、`ENB` は
    左下の M2。辺は「ダイ中心から見てどちら側に近いか」ではなく、**帯そのものの
    どの辺に出ているか**で決める（リング配線は帯の端から出発するため）。
    """
    import re
    txt = open(cfg.RING_OSC_LEF).read()
    body = re.search(rf"MACRO {cfg.RING_OSC_CELL}(.*?)END {cfg.RING_OSC_CELL}",
                     txt, re.S).group(1)
    ox, oy = cfg.RING_OSC_ORIGIN
    out = {}
    for m in re.finditer(r"PIN (\w+)(.*?)END \1", body, re.S):
        name = m.group(1)
        if name in POWER_NETS or name in ("VSS",):
            continue
        lay = (re.search(r"LAYER (\w+)", m.group(2)) or [None, "M1"])[1] \
            if re.search(r"LAYER (\w+)", m.group(2)) else "M1"
        r = [tuple(float(v) for v in q) for q in re.findall(
            r"RECT\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)", m.group(2))]
        if not r:
            continue
        x0, y0, x1, y1 = r[0]
        cx, cy = ox + (x0 + x1) / 2, oy + (y0 + y1) / 2
        edge = "RIGHT" if x0 > 810 else ("LEFT" if x1 < 810 else "BOTTOM")
        out[f"{cfg.RING_OSC_CELL}.{name}"] = {
            "x": round(cx, 2), "y": round(cy, 2), "edge": edge, "layer": lay}
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

    # --- 端点をひとつの辞書に集める -------------------------------------
    #   コアのピン（コア座標 -> チップ座標）、RING_OSC のピン（すでにチップ座標）、
    #   パッド端子どうしで閉じるネット（DIS）。
    src = {}
    for n, c in pins.items():
        src[n] = {"what": "core", "x": round(c["x"] + dx, 2),
                  "y": round(c["y"] + dy, 2), "edge": c["edge"],
                  "layer": c["layer"], "port": n}
    for n, c in ringosc_pins().items():
        src[n] = {"what": "ringosc", "x": c["x"], "y": c["y"],
                  "edge": c["edge"], "layer": c["layer"], "port": n}
    for n, term in PAD_ONLY_NETS.items():
        t = pads[term]
        src[n] = {"what": "pad", "x": t["x"], "y": t["y"], "edge": t["edge"],
                  "layer": t["layer"], "terminal": term}

    # --- 突き合わせ -------------------------------------------------------
    want = set()
    for e in PAD_MAP.values():
        for k in ("P", "OUT", "HIZ"):
            v = e.get(k)
            for n in (v if isinstance(v, list) else [v]):
                if n and n not in POWER_NETS and n not in ("VSS",):
                    want.add(n)
    missing = sorted(n for n in want if n not in src)
    extra = sorted(set(pins) - want - UNBONDED)
    if missing:
        raise SystemExit(f"PAD_MAP が要求するネットが見つからない: {missing}")
    if extra:
        raise SystemExit(f"コアに PAD_MAP も UNBONDED も知らないピンがある: {extra}")

    conns, plan, rows, ties = [], [], [], []

    def add(net, pad, role, term, kind):
        """net -> 端子 term の 1 本を plan / rows に足す。"""
        a_ = src[net]
        t = pads[term]
        gap = round(ring_gap(ring_s(t["x"], t["y"], r),
                             ring_s(a_["x"], a_["y"], r), r), 1)
        plan.append({"net": net, "role": role, "pad": pad, "kind": kind,
                     "from": {k: v for k, v in a_.items()},
                     "to": {"what": "pad", "x": t["x"], "y": t["y"],
                            "edge": t["edge"], "layer": t["layer"],
                            "terminal": term},
                     "ring_run_um": gap,
                     "same_edge": t["edge"] == a_["edge"]})
        rows.append((pad, role, kind, net, a_["what"], a_["edge"], a_["x"], a_["y"],
                     t["edge"], t["x"], t["y"], gap))

    for pad in sorted(PAD_MAP):
        e = PAD_MAP[pad]
        role = e["role"]
        d_in = bool(e.get("P"))
        d_out = bool(e.get("OUT")) and e["OUT"] not in POWER_NETS
        e_dir = "bidir" if d_in and d_out else ("in" if d_in else "out")
        for n in (e["P"] if isinstance(e.get("P"), list) else [e.get("P")]):
            if n:
                add(n, pad, role, f"P{pad}", "P")
        if e.get("OUT"):
            if e["OUT"] in POWER_NETS or e["OUT"] == "VSS":
                ties.append({"pad": pad, "terminal": f"OUT{pad}", "tie": e["OUT"],
                             "why": "オープンドレイン（Low だけ駆動する）",
                             "x": pads[f"OUT{pad}"]["x"], "y": pads[f"OUT{pad}"]["y"],
                             "edge": pads[f"OUT{pad}"]["edge"]})
            else:
                add(e["OUT"], pad, role, f"OUT{pad}", "OUT")
        h = e["HIZ"]
        if h in POWER_NETS or h == "VSS":
            ties.append({"pad": pad, "terminal": f"HIZ{pad}", "tie": h,
                         "why": ("常時 Hi-Z（入力専用）" if h == "VDD"
                                 else "常時ドライブ（出力専用）"),
                         "x": pads[f"HIZ{pad}"]["x"], "y": pads[f"HIZ{pad}"]["y"],
                         "edge": pads[f"HIZ{pad}"]["edge"]})
        else:
            add(h, pad, role, f"HIZ{pad}", "HIZ")
        conns.append({"pad": pad, "role": role, "dir": e_dir,
                      "P": e.get("P"), "OUT": e.get("OUT"), "HIZ": h})

    # 入力専用パッドの `OUT` は浮いたゲート入力。GND に落とす（LVS 対策）。
    for pad in sorted(PAD_MAP):
        e = PAD_MAP[pad]
        if e.get("OUT") is None and f"OUT{pad}" in pads:
            ties.append({"pad": pad, "terminal": f"OUT{pad}", "tie": "GND",
                         "why": "入力専用パッドの浮いたドライバ入力",
                         "x": pads[f"OUT{pad}"]["x"], "y": pads[f"OUT{pad}"]["y"],
                         "edge": pads[f"OUT{pad}"]["edge"]})

    os.makedirs(cfg.CHIP, exist_ok=True)
    json.dump({"pad_cell": "OSS_ESD_5V_DIO",
               "pad_cell_behavior": {"HIZ=1": "Hi-Z（入力専用）",
                                     "HIZ=0": "PAD = OUT（非反転）"},
               "power_pads": {"P8": "VSS", "P16": "VDD"},
               "unbonded": sorted(UNBONDED),
               "signals": conns, "ties": ties},
              open(a.conn, "w"), ensure_ascii=False, indent=1)
    json.dump({"core_offset": geom["core_offset"],
               "core_chip_bbox": geom["core_chip_bbox"],
               "ring_osc_origin": list(cfg.RING_OSC_ORIGIN),
               "pin_radius": r, "signals": plan, "ties": ties},
              open(a.plan, "w"), ensure_ascii=False, indent=1)

    print(f"=== パッド <-> ネット（コアのオフセット {geom['core_offset']}）")
    print(f"{'pad':>4} {'role':5s} {'kind':4s} {'net':15s} {'出どころ':8s}"
          f"{'端点':22s}   {'パッド端子':20s} リング周 同辺")
    for (pad, role, kind, net, what, ce, cx, cy, te, tx, ty, gap) in rows:
        print(f"P{pad:<3d} {role:5s} {kind:4s} {net:15s} {what:8s}"
              f"{ce:6s}({cx:8.1f},{cy:7.1f})   {te:6s}({tx:7.1f},{ty:7.1f})"
              f" {gap:8.1f}  {'✓' if te == ce else ''}")
    for t in ties:
        print(f"P{t['pad']:<3d} {'':5s} tie  {t['terminal']:15s} -> {t['tie']:6s}"
              f"  {t['why']}")

    # --- リングのどこで何本が重なるか（= その位置で要るトラック数）---------
    P = 8 * r
    segs = []
    for (pad, role, kind, net, what, ce, cx, cy, te, tx, ty, gap) in rows:
        sa, sb = ring_s(cx, cy, r), ring_s(tx, ty, r)
        d = (sb - sa) % P
        segs.append((role, sa, d) if d <= P / 2 else (role, sb, P - d))
    sides = {"RIGHT": (0, 2 * r), "TOP": (2 * r, 4 * r),
             "LEFT": (4 * r, 6 * r), "BOTTOM": (6 * r, 8 * r)}
    print("\n  リングの混み具合（最大何本が同じ場所で重なるか / チャネルのトラック数）:")
    worst = []
    for nm, (lo, hi) in sides.items():
        mx, x = 0, lo
        while x < hi:
            n = sum(1 for _n, st, ln in segs if ((x - st) % P) <= ln)
            mx = max(mx, n)
            x += 2.0
        ch = geom["channel_" + nm.lower()][0]
        ntr = int(ch // SITE)
        worst.append((nm, mx, ntr))
        print(f"    {nm:6s} {mx:2d} 本 / {ntr:2d} トラック"
              f"（チャネル {ch:.1f} µm）{'   ** 足りない' if mx > ntr else ''}")

    n_same = sum(1 for r_ in rows if r_[8] == r_[5])
    print(f"\n  同じ辺に出ているもの {n_same} / {len(rows)}、"
          f"リング周の回り込み 最大 {max(r_[11] for r_ in rows):.1f} µm / "
          f"合計 {sum(r_[11] for r_ in rows):.1f} µm")
    import collections
    print("  端点の辺:", dict(collections.Counter(r_[5] for r_ in rows)))
    print("  パッドの辺:", dict(collections.Counter(r_[8] for r_ in rows)))
    print(f"  未ボンド: {', '.join(sorted(UNBONDED))}")
    print(f"\nwrote {os.path.relpath(a.conn, cfg.ROOT)}")
    print(f"wrote {os.path.relpath(a.plan, cfg.ROOT)}")
    return 1 if any(m > n for _s, m, n in worst) else 0


if __name__ == "__main__":
    sys.exit(main())

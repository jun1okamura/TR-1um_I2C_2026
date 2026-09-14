#!/usr/bin/env python3
"""connect_macro_power.py -- マクロの電源をコアの電源レールに繋ぐ（step11）。

  usage: python3 scripts/pnr/connect_macro_power.py <in.gds> -o <out.gds>

## なぜ要るか

縦置きでは `REG8x16` を行スタックの右に置くが、**マクロの電源ポートは上辺と
下辺にしか無い**（LEF: `PIN vdd` / `PIN vss`、どちらも METAL2）。行の電源
レールは x ≤ 行幅で終わり、その右の帯は縦 M2 バスが占めているので、
**マクロの vdd も vss も金属では何にも繋がらないまま**残る。

実測（`scripts/pnr/lvs_pnr.py`）:

    ** 電源の島が 1 個ある（トップピンに繋がっていない）:
         $3.vdd  端子 1476 本

`vss` が GND と同じ網に見えるのは**基板（bulk）経由**であって金属ではない
（抽出器は NMOS のバックゲートを 1 つのグローバルノードに繋ぐ）。電源として
使える配線ではないので、**両レールとも**繋ぐ。

## どこを通すか（実測に基づく）

縦置き・圧縮後の実座標で:

* マクロ下辺の電源ポート（M2, y 415.5–418.9）
    vss  x 1199.8–1203.2 / **1588.6–1592.0**
    vdd  x 1275.4–1278.8 / **1594.0–1597.4**
* 右端 TAP の M2 柱はコア全高を通る（GND x 1140.4–1143.8 / VDD x 1145.8–1149.2）
* マクロの下（x 1198.8–1598.4, y 0–414.4）にはマクロの信号エスケープの
  **横 M1 トランクが 21 本**あるが、**y 209 より下には M1 が 1 本も無い**
* x 1594 の列は y 0–415 が完全に空き

なので「TAP の柱 → 横ストラップ 2 本 → マクロ右下のポートへ縦に立ち上げ」で
繋がる。ストラップは M1（この設計の M1 は横向き）、ライザは M2。
M1 のストラップは信号エスケープの縦 M2 と交差するが**別層なので問題ない**
（via を打たない限り）。

## 落とし穴（必ず読むこと）

**マクロ下辺の長い M1（y 415.5–418.1, x 1198.8 から右）は `vdd`。**
一方、同じ高さにある右端 TAP の M1 レール（x 1139.4–1150.2, y 415.5–420.7）は
**`GND`**。つまり**同じ高さで別ネットが向かい合っている**ので、
「行のレールを右へ伸ばす」は VDD/GND 短絡になる。この高さは使わない。

## 置き場所

**step10（圧縮）の後**に掛ける。圧縮前に入れると y が動く/削られる。
座標はハードコードせず、配置 GDS のマクロ実体 + LEF のポート + `i2c_config`
の TAP 位置から導出し、ルータと同じく**実ジオメトリに対してライブ検査**する。
"""
from __future__ import annotations

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import spi_config as _cfg                                   # noqa: E402

import klayout.db as db                                     # noqa: E402
sys.path.insert(0, _cfg.pdk_tech_python())
import pya                                                  # noqa: E402
from cells import tr_1um                                    # noqa: E402

M1_LAYER = (13, 0)
M2_LAYER = (20, 0)
M1_MIN_GAP = 1.4
M2_MIN_GAP = 2.0
PAD = 3.4                     # via_1 の M1/M2 パッド（= M2 ポートの幅）
# TAP セル内での電源柱の x（route_channels_nrow_fm.py と同じ値）
TAP_GND_X_LOCAL = (1.0, 4.4)
TAP_VDD_X_LOCAL = (6.4, 9.8)


# ---- LEF からマクロの電源ポートを読む -------------------------------------
def macro_power_ports(lef_path, macro):
    """{'vdd': [(x0,y0,x1,y1)…], 'vss': […]}（マクロ座標、METAL2 のみ）。"""
    txt = open(lef_path).read()
    m = re.search(rf"MACRO\s+{re.escape(macro)}\b(.*?)END\s+{re.escape(macro)}\b",
                  txt, re.S)
    if not m:
        raise SystemExit(f"LEF に MACRO {macro} が無い: {lef_path}")
    body = m.group(1)
    out = {}
    for pm in re.finditer(r"PIN\s+(\w+)(.*?)END\s+\1\b", body, re.S):
        name, pbody = pm.group(1), pm.group(2)
        if name.lower() not in ("vdd", "vss"):
            continue
        rects, layer = [], None
        for ln in pbody.splitlines():
            t = ln.split()
            if len(t) >= 2 and t[0] == "LAYER":
                layer = t[1].rstrip(";")
            elif t and t[0] == "RECT" and layer == "METAL2":
                rects.append(tuple(float(v) for v in t[1:5]))
        out[name.lower()] = rects
    missing = {"vdd", "vss"} - set(out)
    if missing:
        raise SystemExit(f"{macro} の電源ポートが LEF に無い: {sorted(missing)}")
    return out


class Drawer:
    def __init__(self, gds):
        self.ly = db.Layout()
        self.ly.read(gds)
        self.top = self.ly.cell(cfg.TOP_CELL_NAME)
        if self.top is None:
            raise SystemExit(f"トップセル {cfg.TOP_CELL_NAME} が {gds} に無い")
        self.dbu = self.ly.dbu
        self.m1 = self.ly.layer(*M1_LAYER)
        self.m2 = self.ly.layer(*M2_LAYER)
        tr_1um("TR-1um")
        self.via_lib = pya.Library.library_by_name("TR-1um", "*")
        self.via_decl = self.via_lib.layout().pcell_declaration("via_1")

    def um(self, v):
        return int(round(v / self.dbu))

    def box(self, x0, y0, x1, y1):
        return db.Box(self.um(x0), self.um(y0), self.um(x1), self.um(y1))

    def clear(self, layer_idx, x0, y0, x1, y1, margin):
        """その層に（margin ぶん広げた）矩形と**重なる**図形が無いか。

        ルータの `channel_clear` と同じく「接しているだけ」は許す
        （`_overlapping` 流儀）。"""
        probe = self.box(x0 - margin, y0 - margin, x1 + margin, y1 + margin)
        r = db.Region(self.top.begin_shapes_rec_overlapping(layer_idx, probe))
        return (r & db.Region(probe)).is_empty()

    def m1_box(self, x0, y0, x1, y1):
        self.top.shapes(self.m1).insert(self.box(x0, y0, x1, y1))

    def m2_box(self, x0, y0, x1, y1):
        self.top.shapes(self.m2).insert(self.box(x0, y0, x1, y1))

    def via(self, cx, cy, w, h):
        """via_1 を 1 個。`x`/`y` を大きくすると PCell が**カットを配列に**する
        （実測: 3.4 -> 1 個 / 6.8 -> 4 個 / 10.0 -> 9 個）。
        ただし **x は 3.4 のまま**にすること。TAP の柱も M2 ポートも幅 3.4 で、
        隣の柱との間隔は 2.0 しかないので、横に太らせると隣のネットに当たる。"""
        idx = self.ly.add_pcell_variant(
            self.via_lib, self.via_decl.id(),
            {"x": w, "y": h, "x0": "c", "y0": "c"})
        self.top.insert(db.CellInstArray(idx, db.Trans(db.Vector(self.um(cx), self.um(cy)))))


def find_macro(d):
    for inst in d.top.each_inst():
        if d.ly.cell(inst.cell_index).name == cfg.MACRO_CELL:
            t = inst.dtrans
            return t.disp.x, t.disp.y
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--width", type=float, default=cfg.POWER_BAR_W,
                    help="ストラップの幅 µm（既定 = i2c_config.POWER_BAR_W）")
    ap.add_argument("--gap", type=float, default=cfg.POWER_BAR_GAP,
                    help="ストラップ間の隙間 µm")
    a = ap.parse_args()

    d = Drawer(a.gds)
    W, G = a.width, a.gap

    origin = find_macro(d)
    if origin is None:
        print(f"  マクロ {cfg.MACRO_CELL} がレイアウトに無い -- 何もしない")
        d.ly.write(a.out)
        print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
        return 0
    mx, my = origin
    print(f"=== マクロ {cfg.MACRO_CELL} @ ({mx:.1f}, {my:.1f})")

    ports = macro_power_ports(cfg.LEF_PATH, cfg.MACRO_CELL)
    # 下辺（マクロ座標で y が小さい方）のポートだけ使う。上辺はコア上辺と
    # 面一でコア内から届かない（チップ組み立てで上から受ける）。
    feed = {}
    for net, rects in ports.items():
        ymin = min(r[1] for r in rects)
        bottom = [r for r in rects if abs(r[1] - ymin) < 1e-6]
        r = max(bottom, key=lambda r: r[0])          # いちばん右
        feed[net] = (r[0] + mx, r[1] + my, r[2] + mx, r[3] + my)
        print(f"  {net} ポート（下辺・右端） x {feed[net][0]:.1f}..{feed[net][2]:.1f}"
              f"  y {feed[net][1]:.1f}..{feed[net][3]:.1f}")

    # --- TAP の電源柱（右端の TAP を使う）---
    tap_x = max(cfg.TAP_X)
    col = {"vss": (tap_x + TAP_GND_X_LOCAL[0], tap_x + TAP_GND_X_LOCAL[1]),
           "vdd": (tap_x + TAP_VDD_X_LOCAL[0], tap_x + TAP_VDD_X_LOCAL[1])}
    for net, (x0, x1) in col.items():
        print(f"  {net} の TAP 柱  x {x0:.1f}..{x1:.1f}（右端 TAP x={tap_x}）")

    # --- ストラップを通す y 帯を探す（マクロの下を下へ走査）---------------
    x_lo = min(col["vss"][0], col["vdd"][0]) - 1.0
    x_hi = max(feed["vss"][2], feed["vdd"][2])
    need = 2 * W + G
    band = None
    y = my - M1_MIN_GAP - need
    while y > 0:
        if d.clear(d.m1, x_lo, y, x_hi, y + need, M1_MIN_GAP):
            band = y
            break
        y -= 1.0
    if band is None:
        raise SystemExit("ストラップを通せる空き帯が見つからない")
    # 下を VDD、上を GND（どちらでもよいが決めておく）
    ys = {"vdd": (band, band + W), "vss": (band + W + G, band + W + G + W)}
    print(f"  ストラップ帯: y {band:.1f}..{band + need:.1f}"
          f"（幅 {W} x 2 本、隙間 {G}）  x {x_lo:.1f}..{x_hi:.1f}")

    # --- 検査してから描く -------------------------------------------------
    plan = []
    for net in ("vdd", "vss"):
        sy0, sy1 = ys[net]
        cx0, cx1 = col[net]
        px0, py0, px1, py1 = feed[net]
        # ストラップ本体（M1）
        if not d.clear(d.m1, cx0, sy0, px1, sy1, M1_MIN_GAP):
            raise SystemExit(f"{net} のストラップ（y {sy0:.1f}..{sy1:.1f}）が M1 で塞がっている")
        # ライザ（M2）: ストラップからポートまで。
        # **検査はマクロの下端で打ち切る。** ここを普通に margin つきで見ると、
        # 上に伸ばした分が**繋ぎ先のポートそのもの**を拾って「塞がっている」に
        # なる（実測でこれに引っかかった）。ポートから上はマクロ自身の金属で、
        # 同じネットなので検査の対象ではない。
        rx0, rx1 = px0, px1
        probe = d.box(rx0 - M2_MIN_GAP, sy0 - M2_MIN_GAP, rx1 + M2_MIN_GAP, my)
        r = db.Region(d.top.begin_shapes_rec_overlapping(d.m2, probe)) & db.Region(probe)
        if not r.is_empty():
            raise SystemExit(f"{net} のライザ（x {rx0:.1f}..{rx1:.1f}, y {sy0:.1f}..{my:.1f}）"
                             f"が M2 で塞がっている")
        plan.append((net, sy0, sy1, cx0, cx1, rx0, rx1, py0, py1))
        print(f"  [OK] {net}: ストラップ y {sy0:.1f}..{sy1:.1f} x {cx0:.1f}..{px1:.1f}"
              f" / ライザ x {rx0:.1f}..{rx1:.1f} y {sy0:.1f}..{py1:.1f}")

    for net, sy0, sy1, cx0, cx1, rx0, rx1, py0, py1 in plan:
        d.m1_box(cx0, sy0, rx1, sy1)                      # 横ストラップ
        d.via((cx0 + cx1) / 2.0, (sy0 + sy1) / 2.0, PAD, W)   # TAP 柱へ
        d.via((rx0 + rx1) / 2.0, (sy0 + sy1) / 2.0, PAD, W)   # ライザへ
        d.m2_box(rx0, sy0, rx1, py1)                      # 縦ライザ（ポートまで）

    d.ly.write(a.out)
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

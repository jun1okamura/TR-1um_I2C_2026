#!/usr/bin/env python3
"""route_chip.py -- コアを GIO パッドリングに配線する（チップ step2）。

    layout/chip/step1c_logo.gds            （コア + RING_OSC + ロゴ）
  + layout/chip/signal_routing_plan.json   （端点。gen_top_routing_plan の出力）
  -> layout/chip/step2_routed.gds

リングのエンジン（`perimeter_s` / `s_to_xy` / `ring_waypoints` /
`project_to_R` / `seg_layer` / `unroll` / `pack`）は SCLK_SPI -> I2C -> TD4 と
そのまま持ってきた。**水平は M1、垂直は M2**、層が変わるところに必ず via。

## 半径の割り当て（外側から）

    921.7   パッド端子（P / HIZ / OUT）と VSS の壁ピン
    920.0   フレームの金属の内縁（M1 / M2 とも実測でここまで）
    912.0   VDD リング（M1 水平 / M2 垂直、幅 10）      移植 (18)
    895.0   GND リング（同上）                          移植 (18)
    815.4   レーン 0、以降 5.4 ピッチで 14 本（最上 885.6）  移植 (15)
    810.0   RING_OSC の帯の縁（M1。M2 は 809.0）
    805.5   コアの bbox（x）。y は上 780.2 / 下 -183.0

## TD4 と違うところ（I2C 移植 (15)-(20)）

 (15) 下のチャネルに RING_OSC の帯が入っているので、レーン 0 を 810 から
      815.4 へ。左右の辺のレーン（M2）が帯の電源レールに乗らないように。
 (16) 1 ネットが何本にも分かれる。`DIS` は P7 から 8 個のデータパッドの
      HIZ 入力へ 9 本、`rst_n` と `RING_OSC.ENB` は同じパッド P15 から出る
      別ネット。ルートはネット名ではなく 1 本ずつの `_key` で持つ。
      同じ端子・同じネットの端点どうしは足の間隔の対象外。
 (17) 下のチャネルは RING_OSC（y -759.2…-536.0）と OpenSUSI ロゴ（M2、
      y -516…-203）で埋まっていて、コア下端 -183 から下辺の VSS 壁ピンへ
      M2 を降ろす道が無い。VDD も GND も**上のチャネル**から取る。
      コアの TAP 柱が上下を貫いているので、下辺のポートは開放でよい。
 (18) `DIS` の枝分かれぶん混むのでレーンが 14 本要る（2 µm 刻みで全周を
      探しても 14）。リングを 895 / 912 まで外へ寄せて帯を広げた。
 (19) (20) は verify_chip.py 側（同じ端子を共有するネット、開放の下辺タップ）。

## なぜリングを 2 本引くのか

フレームがコアに向けて出している電源端子は非対称:

  * **VDD は M1 の 1 枚だけ**。上辺中央の (50,920)-(350,934)。
  * **VSS は M2 の幅広**で四辺の壁に散っている（下辺中央の
    (-450,-934)-(50,-920) が VSS ボンドパッド P8 の真下）。

HIZ と浮いた OUT の結線はすべてレール直結で、四辺に散っている。素直に
リングを 2 本回して、端子からは**半径方向に一直線**で落とす。

交差はすべて M1 x M2 になる: 上下の辺ではリングは水平（M1）で端子からの
引き込みは垂直（M2）、左右の辺ではその逆。via を打つのは繋ぎたいところだけ。

## 電源の縦通し（移植 (17)）

  GND  上チャネルの M1 バス（y=790）で上辺の GND タップ 4 本を束ね、
       M2 ライザ 5 本（x -450/-350/-50/50/450）でレーン帯を跨いで GND
       リングへ。下辺中央の VSS 壁ピンへは**リングの下辺から** M2 の
       ストリップ 5 本で降ろす。残り三辺の壁ピンにも短いストラップ。
  VDD  上チャネルの M1 バス（y=804）で上辺の VDD タップ 4 本を束ね、
       M2 ライザ 5 本（x 80..320）で VDD リングへ。リングの M1 にそのまま
       乗り換えて y=927 のフレーム M1 VDD ピンへ入る。M2 のまま 920 まで
       行くとフレームの VSS（M2、上辺 920..934）に当たる。

  usage: python3 scripts/pnr/route_chip.py [-o OUT]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

import klayout.db as db

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import connect_macro_power                                  # noqa: E402

sys.path.insert(0, cfg.pdk_tech_python())
import pya                                                  # noqa: E402
from cells import tr_1um                                    # noqa: E402

IN_GDS = os.path.join(cfg.CHIP, "step1c_logo.gds")
OUT_GDS = os.path.join(cfg.CHIP, "step2_routed.gds")
PLAN = os.path.join(cfg.CHIP, "signal_routing_plan.json")

M1_LAYER = (13, 0)
M2_LAYER = (20, 0)
M1_WIRE_W = 1.8
M2_WIRE_W = 3.4
VIA_PAD = 3.4

# ---- リングの半径割り当て（ファイル先頭の表のとおり）---------------------
# --- I2C 移植 (15): レーン 0 を RING_OSC の外へ -----------------------------
# TD4 は開口の中にコアしか無いので 810 から始められた。I2C は下のチャネルに
# RING_OSC の帯（チップ x -810…810、M2 は -809…809）が入っているので、
# 左右の辺のレーン（垂直 = M2）が 810 では帯の電源レールに乗ってしまう。
# 1 トラック分（5.4）外に出して 815.4 から。M2 の縁 813.7 と帯の M2 809.0 で
# 4.7 µm 空く（要 2.0）。M1 レール 810.0 とは層が違うので当たらない。
LANE_R0 = 815.4
LANE_PITCH = 5.4         # M2 3.4 + 最小間隔 2.0。コア内のトラックと同じ
# --- I2C 移植 (18): リングを外へ寄せてレーン帯を 14 本ぶん確保 -------------
# TD4 は 12 レーンで足りたが、I2C は DIS が 9 本に枝分かれするぶん混み、
# どこで周を切っても 14 レーン要る（2 µm 刻みで全周を探した）。
# フレームの金属は四辺とも**きっかり 920.0** までしか来ていない（実測、
# M1 / M2 とも）。リング幅 10 の外縁 + M2 間隔 2.0 で R <= 913.0 まで置ける。
#   VDD 912.0 -> 907…917、壁 920 まで 3.0（M2 2.0 / M1 1.4 とも可）
#   GND 895.0 -> 890…900、VDD との間 7.0
#   レーン上限 895 - 5 - 2.0 - 1.7 = 886.3、最上レーン 885.6
GND_RING_R = 895.0
VDD_RING_R = 912.0
RING_W = 10.0
RING_VIA = 6.8           # 10 µm 同士の重なりに収まる 2x2 カット
WALL = 920.0             # 開口の内壁（実測。四隅まで同じ）

# ---- コアの電源をチャネルで束ねるバス -----------------------------------
# --- I2C 移植 (17): VDD も GND も**上のチャネル**から取る -------------------
# TD4 は上下のチャネルが両方空いていたので VDD を上、GND を下から取れた。
# I2C の下のチャネルは RING_OSC の帯（y -759.2…-536.0）と OpenSUSI ロゴの帯
# （M2、y -516…-203）で埋まっていて、コアの下端 -183 から下辺の VSS 壁ピン
# （y -926）まで M2 を降ろす道が無い。ロゴは M2 なので素通りできない。
#
# コアの VDD/GND は TAP 柱（M2）で全行を縦に貫いていて、柱は上辺と下辺の
# **両方**にポートを出している。つまり上辺だけから給電しても電気的には
# 全行に届く（IR ドロップが片側ぶん増えるだけ。5 V / 20 MHz なので許容）。
# 下辺のポートは開放のままにする。
#
# 上のチャネルはコア上端 780.2 からレーン 0 の 813.7 まで 33.5 µm。
# M1 バスを 2 本入れる: GND を内側（790.0）、VDD を外側（804.0）。
BUS_W = 10.0
TAP_STUB_W = 3.4         # コア側の M2 ポート幅そのまま。段差を作らない
VDD_BUS_Y = 804.0        # M1 799.0…809.0。レーン 0 の M1 縁 814.5 と 5.5 空く
GND_BUS_Y = 790.0        # M1 785.0…795.0。コア上端 780.2 と 4.8 空く
# フレームの M1 VDD ピン (50,920)-(350,934) へ。M2 は 916 で止めて M1 に
# 跳ねる（920 から上はフレームの VSS が M2 で寝ている）。
VDD_PIN_Y = 927.0
# リングが 912 まで来たので、リングの M1 にそのまま乗り換えてピンへ上がる
# （TD4 は 902 のリングと 916 の乗り換えが別だった）。
VDD_CROSS_Y = 912.0
VDD_RISER_W = 3.4
VDD_RISER_X = (80.0, 140.0, 200.0, 260.0, 320.0)
# GND バス -> GND リング（上辺 M1 y=884）の M2 ライザ。上辺に立っている
# ほかの M2（コアのピン / パッド端子 / HIZ タイ / VDD ライザ）から 30 µm 以上
# 離れた x を選んである（実測の空き: -450 / -350 / -50 / 50 / 450）。
GND_RISER_W = 3.4
GND_RISER_X = (-450.0, -350.0, -50.0, 50.0, 450.0)
# 下辺中央の VSS 壁ピン (-450,-934)-(50,-920) へ。10 µm 内側に着地する。
# I2C では**コアからではなく GND リングから**降ろす（上の (17) を参照）。
VSS_LAND_Y = -926.0
VSS_STRIP_W = 10.0
VSS_STRIP_X = (-400.0, -300.0, -200.0, -100.0, 0.0)
# 残り三辺の VSS 壁ピンへの短いストラップ（GND リング -> 壁）。
# x=400 の上辺は VDD ライザ（80..320）から 80 µm 離してある。
VSS_STRAP = (("LEFT", -400.0), ("LEFT", 0.0), ("LEFT", 400.0),
             ("RIGHT", -400.0), ("RIGHT", 0.0), ("RIGHT", 400.0),
             ("TOP", -400.0), ("TOP", 400.0), ("BOTTOM", 400.0))
STRAP_W = 6.0

# ---- REG8x16 の電源をチャネルの M1 バーまで引き上げる/下げる -------------
# マクロは vdd も vss も**上辺と下辺の両方**に M2 ポートを持ち、左右 2 列ある
# （LEF: vdd x 76.6-80.0 / 395.2-398.6、vss x 1.0-4.4 / 389.8-393.2、
#  y は 1.1-4.5 と 928.5-931.9）。マクロの上辺はコアの上辺と面一なので、
# **上辺のポートはコアの中からは届かない**（step11 の `connect_macro_power`
# が右下の 1 組だけ行の電源に繋いでいるのはそのため）。チップ側なら
# 上のチャネルに VDD の M1 バーが、下のチャネルに GND の M1 バーがあるので、
# そこまで M2 をまっすぐ延ばせる:
#
#   vdd 上辺 2 本 -> 上の VDD バー（コア上端 678.5 から 690 まで 12 µm）
#   vss 下辺 2 本 -> 下の GND バー（マクロ下端 -250.0 から -690 まで 440 µm）
#
# 下側の 440 µm は**行の右側の空き**（行幅 1150.2、マクロ左端 1198.8）を
# 通る。実測でこの 2 列は M2 も V1 も空で、横切るのは別ネットの M1 だけ
# （左列で 23 本）。M2 x M1 なので via を打たなければ何も起きない。
MACRO_RISER_W = 3.4      # マクロのポート幅ちょうど。段差を作らない

R_NOM = 866.0            # 区間計算用の名目半径（レーン帯のまん中あたり）
PERI = 8 * R_NOM

V1_CUT = 1.4
MIN_VIA_SPACE = 1.5


# --------------------------------------------------------------------------
# リングの素（I2C 版そのまま）
# --------------------------------------------------------------------------
def perimeter_s(x, y, edge, R):
    if edge == "TOP":    return max(-R, min(R, x)) + R
    if edge == "RIGHT":  return 2 * R + (R - max(-R, min(R, y)))
    if edge == "BOTTOM": return 4 * R + (R - max(-R, min(R, x)))
    if edge == "LEFT":   return 6 * R + (max(-R, min(R, y)) + R)
    raise ValueError(edge)


def s_to_xy(s, R):
    P = 8 * R
    s = s % P
    if s <= 2 * R: return (s - R, R)
    if s <= 4 * R: return (R, R - (s - 2 * R))
    if s <= 6 * R: return (R - (s - 4 * R), -R)
    return (-R, (s - 6 * R) - R)


def ring_waypoints(s1, s2, R, force_dir=None):
    P = 8 * R
    corners = [2 * R, 4 * R, 6 * R, 8 * R]
    if force_dir is None:
        direction = "CW" if (s2 - s1) % P <= (s1 - s2) % P else "CCW"
    else:
        direction = force_dir
    pts = []
    if direction == "CW":
        span = (s2 - s1) % P
        for k in corners:
            off = (k - s1) % P
            if 0 < off < span: pts.append((off, k % P))
    else:
        span = (s1 - s2) % P
        for k in corners:
            off = (s1 - k) % P
            if 0 < off < span: pts.append((off, k % P))
    pts.sort()
    return [s_to_xy(k, R) for _, k in pts]


def project_to_R(px, py, edge, R):
    if edge in ("TOP", "BOTTOM"):
        return (px, R if edge == "TOP" else -R)
    return (R if edge == "RIGHT" else -R, py)


def seg_layer(a, b):
    if abs(a[1] - b[1]) < 1e-6 and abs(a[0] - b[0]) >= 1e-6: return "M1"
    if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) >= 1e-6: return "M2"
    raise ValueError(f"non-manhattan or zero-length segment {a} {b}")


def ring_layer(edge):
    """リング（VDD/GND）がその辺で走っている層。"""
    return "M1" if edge in ("TOP", "BOTTOM") else "M2"


def edge_layer(edge):
    """その辺から**まっすぐ内側へ出るとき**の層。

    フレームの端子は 42 本すべて **M1 と M2 のスタック**（フレーム自身が
    V1 を打っている。例: P3 は M2 (-923.4,528.3)-(-920,531.7) の裏に
    M1 (-960,528.3)-(-920,531.7) と V1 (-922.4,529.3)-(-921,530.7)）。
    なので端子の上に**自分の via を打ってはいけない** -- フレームの V1 と
    間隔違反になるし、そもそも要らない。出ていく向きに合った層を選んで
    そのまま重ねればつながる。左右の辺なら M1、上下なら M2。"""
    return "M1" if edge in ("LEFT", "RIGHT") else "M2"


def pack(intervals, margin=5.0, min_lane=None):
    """貪欲な区間スケジューリング: {key: lane}。I2C 版に下限を足したもの。

    `min_lane[key]` はそのルートが使える最小のレーン（= 最小半径）。
    `stub_order()` が出す「パッド側の足はコア側の足より外を通れ」という
    制約をこれで効かせる。"""
    min_lane = min_lane or {}
    lane_last, lane_of = [], {}
    for key, (lo, hi) in sorted(intervals.items(), key=lambda kv: kv[1][0]):
        want = min_lane.get(key, 0)
        while len(lane_last) < want:
            lane_last.append(float("-inf"))
        for i in range(want, len(lane_last)):
            if lane_last[i] < lo - margin:
                lane_of[key] = i
                lane_last[i] = hi
                break
        else:
            lane_of[key] = len(lane_last)
            lane_last.append(hi)
    return lane_of, len(lane_last)


# 辺に沿ってこれより近い 2 本の「足」は、半径方向に重なった瞬間に間隔違反。
# 足の層は向きで決まるので、要る間隔も辺で変わる:
#   上下 = 垂直 = M2  3.4 + 2.0 = 5.4
#   左右 = 水平 = M1  1.8 + 1.4 = 3.2
STUB_SEP = {"TOP": M2_WIRE_W + 2.0, "BOTTOM": M2_WIRE_W + 2.0,
            "LEFT": M1_WIRE_W + 1.4, "RIGHT": M1_WIRE_W + 1.4}
EPS = 1e-6


def skey(s):
    """--- I2C 移植 (16): 1 本ずつの識別子 ---------------------------------

    TD4 はネット名がそのままルート 1 本だった。I2C は **1 ネットが何本にも
    分かれる**: `DIS` は P7 から 8 個のデータパッドの HIZ 入力へ 10 本、
    `rst_n` と `RING_OSC.ENB` は同じパッド P15 から出る別ネット。
    `{s["net"]: ...}` で持つと `DIS` が 1 本に潰れて 9 本消える。"""
    return s.get("_key") or s["net"]


def same_node(a, ka, b, kb):
    """同じネット、または同じパッド端子に着く端点どうしか。

    同じ端子に着く 2 本（P15 の `rst_n` と `RING_OSC.ENB`）や同じネットの
    複数本（`DIS`）は、辺の上で重なって当たり前なので間隔の対象外。"""
    if a["net"] == b["net"]:
        return True
    ta, tb = a[ka].get("terminal"), b[kb].get("terminal")
    return ta is not None and ta == tb


def stub_order(signals):
    """[(内側にいるべきルート, 外側にいるべきルート)]。

    端子からもコアピンからも、配線は辺に対して**垂直な足**でレーンまで出る。
    足が占める半径は、コア側が「コアの縁 .. レーン半径」、パッド側が
    「レーン半径 .. 921.7」。同じ辺で 5.4 µm 以内に並んだこの 2 本は、
    **パッド側のレーンがコア側より外**でないと必ず重なる。

    2026-09-14 に実際に出た: `cflag_o` のコアピン（上辺 x=-534.1）と
    `wr` のパッド端子 P2（上辺 x=-530）が 4.1 µm 違いで、レーンが
    wr=815.4 < cflag_o=826.2 だったため M2 が 0.7 µm まで寄った。"""
    def tang(d):
        return d["x"] if d["edge"] in ("TOP", "BOTTOM") else d["y"]

    pairs, unfixable = [], []
    for a in signals:
        for b in signals:
            if same_node(a, "from", b, "to"):
                continue
            if a["from"]["edge"] != b["to"]["edge"]:
                continue
            if (abs(tang(a["from"]) - tang(b["to"]))
                    < STUB_SEP[a["from"]["edge"]] - EPS):
                pairs.append((skey(a), skey(b)))
    for i, a in enumerate(signals):
        for b in signals[i + 1:]:
            for ka, kb in (("from", "from"), ("to", "to")):
                if same_node(a, ka, b, kb):
                    continue
                if (a[ka]["edge"] == b[kb]["edge"]
                        and abs(tang(a[ka]) - tang(b[kb]))
                        < STUB_SEP[a[ka]["edge"]] - EPS):
                    unfixable.append((skey(a), skey(b), ka))
    return pairs, unfixable


# --------------------------------------------------------------------------
def build_plan(signals, cut):
    """{name: (a, b)} と区間・向き・レーン。`cut` は周を開く位置。

    パッカーは**巻き戻さない素の区間**で重なりを見るので、配線はその区間の
    内側に収まる向きでなければならない（短い方の弧を勝手に選ぶと、継ぎ目を
    跨いだ配線に対してパッカーが見当違いの区間を見ることになる。移植元で
    物理的に重なる 2 本が同じレーンに入った原因がこれ）。"""
    def ep(d):
        # 端子側もコア側も「辺から垂直に出る」ので、層は向きで決まる。
        # コアのピンもちょうどそうなっている（左辺は M1、上下は M2）ので、
        # 食い違っていたら黙って直さずに落とす。
        want = edge_layer(d["edge"])
        # I2C 移植 (14) の続き: RING_OSC のピンも層と向きが合っていること。
        # `gen_top_routing_plan.ringosc_pins()` が層で辺を決めているので
        # ここは必ず通る。通らなければ帯のレールに足を引いている。
        if d["what"] in ("core", "ringosc") and d["layer"] != want:
            raise SystemExit(f"{d.get('port')} のピン層 {d['layer']} が "
                             f"{d['edge']} 辺の向き（{want}）と合わない")
        return (d["x"], d["y"], d["edge"], want)

    routes = {skey(s): (ep(s["from"]), ep(s["to"])) for s in signals}
    interval, direction = {}, {}
    for name, (a, b) in routes.items():
        u1 = (perimeter_s(a[0], a[1], a[2], R_NOM) - cut) % PERI
        u2 = (perimeter_s(b[0], b[1], b[2], R_NOM) - cut) % PERI
        interval[name] = (min(u1, u2), max(u1, u2))
        direction[name] = "CW" if u1 < u2 else "CCW"
    pairs, _ = stub_order(signals)
    min_lane = {}
    for _ in range(len(signals) + 2):
        lane_of, n_lanes = pack(interval, min_lane=min_lane)
        bad = [(i, o) for i, o in pairs if lane_of[o] <= lane_of[i]]
        if not bad:
            break
        for i, o in bad:
            min_lane[o] = max(min_lane.get(o, 0), lane_of[i] + 1)
    else:
        raise SystemExit(f"足の重なりが解けない: {bad}")
    return routes, interval, direction, lane_of, n_lanes


def choose_cut(signals, step=20.0):
    """レーン数、次いで総配線長がいちばん小さくなる継ぎ目を選ぶ。"""
    best = None
    c = 0.0
    while c < PERI:
        _, interval, _, _, n = build_plan(signals, c)
        cost = (n, sum(hi - lo for lo, hi in interval.values()))
        if best is None or cost < best[0]:
            best = (cost, c)
        c += step
    return best[1], best[0]


# --------------------------------------------------------------------------
class Drawer:
    def __init__(self, layout, top):
        self.layout, self.top = layout, top
        self.dbu = layout.dbu
        self.idx = {"M1": layout.layer(*M1_LAYER), "M2": layout.layer(*M2_LAYER)}
        self.w = {"M1": M1_WIRE_W, "M2": M2_WIRE_W}
        tr_1um("TR-1um")
        self.via_lib = pya.Library.library_by_name("TR-1um", "*")
        self.via_decl = self.via_lib.layout().pcell_declaration("via_1")
        self.shapes = defaultdict(list)
        self.net = None
        self._via_done = set()

    def um(self, v): return int(round(v / self.dbu))

    def wire(self, layer, x0, y0, x1, y1, w=None):
        w = w if w is not None else self.w[layer]
        hw = w / 2.0
        if abs(x0 - x1) < 1e-6:
            box = db.Box(self.um(x0 - hw), self.um(min(y0, y1)),
                         self.um(x0 + hw), self.um(max(y0, y1)))
        elif abs(y0 - y1) < 1e-6:
            box = db.Box(self.um(min(x0, x1)), self.um(y0 - hw),
                         self.um(max(x0, x1)), self.um(y0 + hw))
        else:
            raise ValueError(f"non-manhattan segment {(x0, y0, x1, y1)}")
        self.top.shapes(self.idx[layer]).insert(box)
        if self.net:
            self.shapes[self.net].append(
                (layer, box.left * self.dbu, box.bottom * self.dbu,
                 box.right * self.dbu, box.top * self.dbu))

    def via(self, cx, cy, x=VIA_PAD, y=VIA_PAD):
        """`via_1` を 1 個。x/y を大きくすると PCell がカットを配列にする。"""
        key = (round(cx, 3), round(cy, 3))
        if key in self._via_done:
            return
        self._via_done.add(key)
        idx = self.layout.add_pcell_variant(
            self.via_lib, self.via_decl.id(),
            {"x": x, "y": y, "x0": "c", "y0": "c"})
        self.top.insert(db.CellInstArray(
            idx, db.Trans(db.Vector(self.um(cx), self.um(cy)))))
        if self.net:
            self.shapes[self.net].append(
                ("VIA", cx - x / 2, cy - y / 2, cx + x / 2, cy + y / 2))

    def path(self, pts, start_layer=None, end_layer=None, w=None):
        """マンハッタンの折れ線。層は向きで決まり、変わるところに via。"""
        layers = [seg_layer(pts[k], pts[k + 1]) for k in range(len(pts) - 1)]
        if start_layer and start_layer != layers[0]:
            self.via(*pts[0])
        for k, L in enumerate(layers):
            a, b = pts[k], pts[k + 1]
            self.wire(L, a[0], a[1], b[0], b[1], w)
            if k > 0 and layers[k - 1] != L:
                self.via(a[0], a[1])
        if end_layer and end_layer != layers[-1]:
            self.via(*pts[-1])
        return layers


# --------------------------------------------------------------------------
def draw_route(d, name, a, b, R, force_dir):
    """1 本の信号を、端点からリングを回って端点まで**ひと続きの折れ線**で。

    リングと端子への寄り道を別々の path で描くと、リングが垂直（M2）で
    到着して寄り道が水平（M1）で出ていく角の via をどちらも打たず、
    ネットが開いたままになる（移植元の最初の版がそれで全滅した）。"""
    pa = [(a[0], a[1]), project_to_R(a[0], a[1], a[2], R)]
    pb = [(b[0], b[1]), project_to_R(b[0], b[1], b[2], R)]
    s1 = perimeter_s(pa[-1][0], pa[-1][1], a[2], R)
    s2 = perimeter_s(pb[-1][0], pb[-1][1], b[2], R)
    pts = pa + ring_waypoints(s1, s2, R, force_dir) + list(reversed(pb))
    clean = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - clean[-1][0]) > 1e-6 or abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    d.net = name
    d.path(clean, start_layer=a[3], end_layer=b[3])
    d.net = None
    return len(clean)


def draw_ring(d, net, R):
    """半径 R の電源リング。水平は M1、垂直は M2、四隅に via。"""
    d.net = net
    d.wire("M1", -R, R, R, R, RING_W)
    d.wire("M1", -R, -R, R, -R, RING_W)
    d.wire("M2", -R, -R, -R, R, RING_W)
    d.wire("M2", R, -R, R, R, RING_W)
    for cx in (-R, R):
        for cy in (-R, R):
            d.via(cx, cy, RING_VIA, RING_VIA)
    d.net = None


def macro_risers(gds, dx, dy):
    """{"VDD": [(x, y_start)], "GND": [(x, y_start)]}（チップ座標）。

    マクロの電源ポートのうち、上辺の `vdd` と下辺の `vss` を取る。x は
    ポートの中心、y はポートの**外側の端**（そこからバーへ向かって延ばす）。
    座標は LEF の宣言ではなく、GDS のインスタンス位置 + LEF のポート矩形。"""
    # I2C にマクロは無い（i2c_config.MACRO_MODE = "none"）。
    if getattr(cfg, "MACRO_MODE", "none") == "none":
        return {"VDD": [], "GND": []}, None
    ly = db.Layout()
    ly.read(gds)
    core = ly.cell(cfg.TOP_CELL_NAME)
    origin = None
    for inst in core.each_inst():
        if ly.cell(inst.cell_index).name == cfg.MACRO_CELL:
            origin = (inst.dtrans.disp.x, inst.dtrans.disp.y)
            break
    if origin is None:
        return {"VDD": [], "GND": []}, None
    mx, my = origin
    ports = connect_macro_power.macro_power_ports(cfg.LEF_PATH, cfg.MACRO_CELL)
    out = {"VDD": [], "GND": []}
    for net, rail, top_side in (("vdd", "VDD", True), ("vss", "GND", False)):
        rects = ports[net]
        ymark = (max if top_side else min)(r[1] for r in rects)
        for r in rects:
            if abs(r[1] - ymark) > 1e-6:
                continue
            x = mx + (r[0] + r[2]) / 2.0 + dx
            y = my + (r[1] if top_side else r[3]) + dy
            out[rail].append((round(x, 3), round(y, 3)))
    for k in out:
        out[k].sort()
    return out, (mx + dx, my + dy)


def core_power_pins(gds, dx, dy):
    """コアの VDD/GND の M2 ポートを辺ごとに。{net: {'TOP': [x], 'BOTTOM': [x]}}"""
    ly = db.Layout()
    ly.read(gds)
    c = ly.cell(cfg.TOP_CELL_NAME)
    u = ly.dbu
    bb = c.bbox()
    out = {"VDD": defaultdict(list), "GND": defaultdict(list)}
    for s in c.shapes(ly.layer(49, 0)).each():
        if not s.is_text() or s.text.string not in out:
            continue
        x, y = s.text.x * u, s.text.y * u
        edge = "TOP" if abs(y - bb.top * u) < abs(y - bb.bottom * u) else "BOTTOM"
        out[s.text.string][edge].append(round(x + dx, 2))
    for net in out:
        for e in out[net]:
            out[net][e] = sorted(out[net][e])
    return {k: dict(v) for k, v in out.items()}


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=OUT_GDS)
    ap.add_argument("--in-gds", default=IN_GDS)
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--core-gds", default=None)
    a = ap.parse_args()

    plan = json.load(open(a.plan, encoding="utf-8"))
    core_gds = a.core_gds or cfg.CHIP_CORE_GDS
    cl, cb, cr, ct = plan["core_chip_bbox"]
    dx, dy = plan["core_offset"]

    layout = db.Layout()
    layout.read(a.in_gds)
    top = layout.cell(cfg.CHIP_TOP_CELL)
    if top is None:
        raise SystemExit(f"{cfg.CHIP_TOP_CELL} が {a.in_gds} に無い")
    d = Drawer(layout, top)

    # ---- 信号 -------------------------------------------------------------
    # I2C 移植 (16): 1 ネットが何本にも分かれるので、まず 1 本ずつに名前を振る。
    seen = defaultdict(int)
    for s in plan["signals"]:
        seen[s["net"]] += 1
        s["_key"] = s["net"] if seen[s["net"]] == 1 else f'{s["net"]}#{seen[s["net"]]}'
    dup = {n: c for n, c in seen.items() if c > 1}
    if dup:
        print("枝分かれするネット: "
              + ", ".join(f"{n} x{c}" for n, c in sorted(dup.items())))

    pairs, unfixable = stub_order(plan["signals"])
    if unfixable:
        raise SystemExit("同じ辺で 5.4 µm 以内に同種の足が並んでいる"
                         f"（レーンでは解けない）: {unfixable}")
    if pairs:
        print("足の順番の制約（内側 -> 外側）: "
              + ", ".join(f"{i}<{o}" for i, o in pairs))
    cut, cost = choose_cut(plan["signals"])
    routes, interval, direction, lane_of, n_lanes = build_plan(plan["signals"], cut)
    top_lane_r = LANE_R0 + (n_lanes - 1) * LANE_PITCH
    room = GND_RING_R - RING_W / 2 - 2.0 - (M2_WIRE_W / 2)
    print(f"継ぎ目 s={cut:.0f}（総長 {cost[1]:.0f} µm）、"
          f"{len(routes)} 本を {n_lanes} レーン "
          f"R {LANE_R0:.1f}..{top_lane_r:.1f}（上限 {room:.1f}）")
    if top_lane_r > room:
        raise SystemExit(f"レーン帯が GND リング（R={GND_RING_R}）に当たる: "
                         f"最上レーン {top_lane_r}")
    if LANE_R0 - M2_WIRE_W / 2 < max(abs(cl), abs(cr)) + 2.0:
        raise SystemExit(f"レーン 0（R={LANE_R0}）がコアに近すぎる")

    for name in sorted(routes):
        ep_a, ep_b = routes[name]
        R = LANE_R0 + lane_of[name] * LANE_PITCH
        n = draw_route(d, name.split("#")[0], ep_a, ep_b, R, direction[name])
        print(f"  {name:<16} lane={lane_of[name]:<3} R={R:6.1f} "
              f"{direction[name]} {n} 点")

    # ---- 電源リング -------------------------------------------------------
    draw_ring(d, "GND", GND_RING_R)
    draw_ring(d, "VDD", VDD_RING_R)
    print(f"VDD リング R={VDD_RING_R}、GND リング R={GND_RING_R}（幅 {RING_W}）")

    # ---- HIZ / 浮いた OUT をレールに落とす --------------------------------
    # I2C 版の gen_top_routing_plan は HIZ タイも浮いた OUT も 1 つの
    # `ties` に入れて `why` で区別している。
    ties = plan.get("ties")
    if ties is None:
        ties = plan["hiz_ties"] + plan["float_ties"]
    for t in sorted(ties, key=lambda t: t["terminal"]):
        rail = t["tie"]
        R = VDD_RING_R if rail == "VDD" else GND_RING_R
        d.net = rail
        d.path([(t["x"], t["y"]), project_to_R(t["x"], t["y"], t["edge"], R)],
               start_layer=edge_layer(t["edge"]), end_layer=ring_layer(t["edge"]))
        d.net = None
    print(f"{len(ties)} 本の HIZ / 浮いた OUT をリングへ")

    # ---- コアの電源 -------------------------------------------------------
    taps = core_power_pins(core_gds, dx, dy)
    risers, macro_at = macro_risers(core_gds, dx, dy)
    # I2C 移植 (17): VDD も GND も**上辺のタップ**から、上のチャネルの M1 バスへ。
    # 下辺のタップは開放（TAP 柱で上辺と繋がっているので電気的には届く）。
    for net, bus_y, risers_x in (("GND", GND_BUS_Y, GND_RISER_X),
                                 ("VDD", VDD_BUS_Y, VDD_RISER_X)):
        xs = taps[net]["TOP"]
        if len(xs) != 4:
            raise SystemExit(f"{net} の TOP タップが 4 本でない: {xs}")
        d.net = net
        lo = min(min(xs), min(risers_x)) - 8.0
        hi = max(max(xs), max(risers_x)) + 8.0
        # マクロのライザもこのバーで受けるので、バーを伸ばす（I2C では空）
        for rx, _ in risers[net]:
            lo, hi = min(lo, rx - 8.0), max(hi, rx + 8.0)
        d.wire("M1", lo, bus_y, hi, bus_y, BUS_W)
        for tx in xs:
            d.wire("M2", tx, ct - 1.5, tx, bus_y + 3.5, TAP_STUB_W)
            d.via(tx, bus_y, TAP_STUB_W, 6.8)
        d.net = None
        print(f"{net} バス M1 y={bus_y} x [{lo:.1f}, {hi:.1f}]、"
              f"上辺タップ {len(xs)} 本 {xs}")
        if taps[net].get("BOTTOM"):
            print(f"    下辺タップ {len(taps[net]['BOTTOM'])} 本は開放"
                  f"（下は RING_OSC とロゴで塞がっている）")

    # ---- REG8x16 の電源をバーまで延伸 ------------------------------------
    for net, bus_y in (("VDD", VDD_BUS_Y), ("GND", GND_BUS_Y)):
        d.net = net
        for rx, ry in risers[net]:
            d.wire("M2", rx, ry, rx, bus_y, MACRO_RISER_W)
            d.via(rx, bus_y, MACRO_RISER_W, 6.8)
        d.net = None
    if macro_at:
        print(f"{cfg.MACRO_CELL} @ {macro_at} のポートからバーへ: "
              + "  ".join(f"{k} " + ", ".join(f"x={x} y={y}" for x, y in v)
                          for k, v in risers.items() if v))

    # VDD: バス -> リング -> M1 でフレームのピンへ
    d.net = "VDD"
    for rx in VDD_RISER_X:
        d.via(rx, VDD_BUS_Y, VDD_RISER_W, 6.8)
        d.wire("M2", rx, VDD_BUS_Y, rx, VDD_CROSS_Y, VDD_RISER_W)
        d.via(rx, VDD_RING_R, VDD_RISER_W, 6.8)          # リングへ
        d.via(rx, VDD_CROSS_Y, VDD_RISER_W, VDD_RISER_W)  # M1 へ跳ねる
        d.wire("M1", rx, VDD_CROSS_Y, rx, VDD_PIN_Y, VDD_RISER_W)
    d.net = None
    print(f"VDD ライザ {len(VDD_RISER_X)} 本 x={list(VDD_RISER_X)} -> "
          f"M1 ピン y={VDD_PIN_Y}（M2 は y={VDD_CROSS_Y} で止める）")

    # GND: バス -> リング（上辺のライザ）。下辺の VSS 壁ピンへはリングから降ろす
    d.net = "GND"
    for gx in GND_RISER_X:
        d.via(gx, GND_BUS_Y, GND_RISER_W, 6.8)
        d.wire("M2", gx, GND_BUS_Y, gx, GND_RING_R, GND_RISER_W)
        d.via(gx, GND_RING_R, GND_RISER_W, 6.8)
    for sx in VSS_STRIP_X:
        d.wire("M2", sx, -GND_RING_R, sx, VSS_LAND_Y, VSS_STRIP_W)
        d.via(sx, -GND_RING_R, VSS_STRIP_W, 6.8)
    # 残り三辺の VSS 壁ピンへ
    for edge, v in VSS_STRAP:
        p = (v, 0.0) if edge in ("TOP", "BOTTOM") else (0.0, v)
        inner = project_to_R(p[0], p[1], edge, GND_RING_R)
        outer = project_to_R(p[0], p[1], edge, abs(VSS_LAND_Y))
        d.path([inner, outer], start_layer=ring_layer(edge),
               end_layer="M2", w=STRAP_W)
    d.net = None
    print(f"GND ライザ {len(GND_RISER_X)} 本 x={list(GND_RISER_X)} -> リング、"
          f"ストリップ {len(VSS_STRIP_X)} 本 -> 下辺の VSS 壁ピン y={VSS_LAND_Y}、"
          f"ほか {len(VSS_STRAP)} 本のストラップ")

    with open(a.out.replace(".gds", "_net_shapes.json"), "w") as f:
        json.dump(dict(d.shapes), f, indent=1)
    layout.write(a.out)
    print(f"\nwrote {os.path.relpath(a.out, cfg.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

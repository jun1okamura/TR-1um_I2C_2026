#!/usr/bin/env python3
"""フレームとパッドセルの LEF を生成する。

  usage: python3 scripts/mkleffrm.py lef/TR-1um_frame_25x25.gds -o lef/TR-1um_frame.lef

`scripts/mklef.py`（標準セル用）と分けてある理由:

  - **ラベルの層が違う。** 標準セルはピン名を (49,1) に置いているが、
    フレームは PDK 提供で **(49,0)**（LVS の `M2_LBL` と同じ層）に置いてある。
  - **CLASS が違う。** パッドセルは `CLASS PAD`、フレームは `CLASS BLOCK`。
    行に置くものではないので SITE も付けない。
  - **ピンが階層の下にある。** `P1`..`P15` はフレーム自身ではなく、
    各 `OSS_ESD_5V_DIO` インスタンスの中のボンディングパッド。
    インスタンスの変換を掛けて拾う必要がある。

出力する MACRO:

  OSS_ESD_5V_DIO / _ANA / _VDD / _VSS   400 x 240 um、CLASS PAD
  OSS_FRAME_GIO                          2500 x 2500 um、CLASS BLOCK
        44 ピン（P1-P15 / OUT1-15 / HIZ1-15 / VDD / VSS）+ コア開口以外を OBS

`OSS_ESD_5V_DIO` のピンの意味（ngspice で確認済み）:
  OUT  コアからの出力データ。HIZ=0 のとき PAD = OUT（非反転）
  HIZ  1 でドライバを放す。読むときはこれを 1 にする
  PAD  ボンディングパッド。**上辺にコア側へのスタブも出ている**ので、
       入力として読むときはそこをコアの入力に繋ぐ（入力バッファは無い）
"""
from __future__ import annotations
import argparse, math, os, sys

try:
    import gdstk
except ImportError:
    sys.exit("pip install gdstk")

M1, M2, PINSH, LBL, M1LBL, BOUND, PO = ((13, 0), (20, 0), (49, 1), (49, 0),
                                        (48, 0), (235, 0), (14, 0))
EPS = 1e-3
PAD_CELLS = ["OSS_ESD_5V_DIO", "OSS_ESD_5V_ANA", "OSS_ESD_5V_VDD", "OSS_ESD_5V_VSS"]
PWR, GND = {"VDD", "vdd"}, {"VSS", "vss", "gnd", "GND"}
# ピンの向き。.lib と揃える（OUT/HIZ はコアからパッドセルへの入力）。
DIRECTION = {"OUT": "INPUT", "HIZ": "INPUT", "PAD": "INOUT", "P": "INOUT"}


def dir_of(n):
    import re as _re
    return DIRECTION.get(_re.sub(r"\d+$", "", n), "INOUT")


def use_of(n):
    return "POWER" if n in PWR else "GROUND" if n in GND else "SIGNAL"


def sel(cell, ld):
    return [p for p in cell.polygons if (p.layer, p.datatype) == ld]


def bb(p):
    b = p.bounding_box()
    return (b[0][0], b[0][1], b[1][0], b[1][1])


def rect_of(p, dx, dy, ind):
    x0, y0, x1, y1 = bb(p)
    return f"{ind}RECT {x0-dx:.3f} {y0-dy:.3f} {x1-dx:.3f} {y1-dy:.3f} ;"


def xform(poly, ref):
    """参照の変換（回転・鏡映・移動）をポリゴンに掛けた複製を返す"""
    q = poly.copy()
    if ref.x_reflection:
        q.scale(1, -1)
    if ref.rotation:
        q.rotate(ref.rotation)
    q.translate(*ref.origin)
    return q


def pin_shapes(cell, lib_cells, extra=(), labels=None, netof=None):
    """ラベル -> ピン図形。戻り値は {name: [(LAYER, polygon), ...]}。

    **ラベルの層と配線層を対応させる**（DRC/LVS デッキと同じ）:
      (48,0) = M1 ラベル -> METAL1 の図形
      (49,0) = M2 ラベル -> METAL2 の図形

    信号ピンは (49,1) のピン図形（コア側へのスタブ）を優先して使う。
    **電源ピンは (49,1) を使わない。** フレームの内側リングでは 1 枚の (49,1) が
    VDD と VSS の両方のラベルに掛かっていて、どちらの網か判別できない。

    フレームは **VDD をコア側の内縁に M1 で引き出している**（(150-190, 920-990)
    など 3 本）。ここを拾わないと、LEF 上で VDD に繋げる場所が
    パッドの外側リングだけになってしまう。
    """
    cand = sel(cell, PINSH) + list(extra)
    def flat(ld):
        return (cell.get_polygons(layer=ld[0], datatype=ld[1])
                if cell.references else sel(cell, ld))
    m1, m2, po = flat(M1), flat(M2), flat(PO)
    out = {}
    for lab in (labels if labels is not None else cell.labels):
        if lab.layer not in (LBL[0], M1LBL[0]):
            continue
        lay, arr = (("METAL1", m1) if lab.layer == M1LBL[0] else ("METAL2", m2))
        pt = gdstk.rectangle((lab.origin[0] - .2, lab.origin[1] - .2),
                             (lab.origin[0] + .2, lab.origin[1] + .2))
        power = use_of(lab.text) != "SIGNAL"
        got = []
        if not power and lay == "METAL2":
            got = [("METAL2", s) for s in cand
                   if gdstk.boolean([pt], [s], "and", precision=EPS)]
        if not got:
            hit = [s for s in arr if gdstk.boolean([pt], [s], "and", precision=EPS)]
            if hit and po and lay == "METAL2":
                # ボンディングパッドは開口 (14,0) に合わせて切る
                clip = gdstk.boolean(hit, po, "and", precision=EPS)
                hit = clip or hit
            got = [(lay, s) for s in hit]
            if power and netof is not None and hit:
                n = netof(lab.origin, lay)
                if n and n != lab.text:
                    print(f"    ** 迷子ラベル: {lab.text!r} @"
                          f"({lab.origin[0]:.1f},{lab.origin[1]:.1f}) {lay} は "
                          f"実際には {n!r} の網。LEF からは外す")
                    got = []
        for lay2, s in got:
            out.setdefault(lab.text, [])
            key = (lay2,) + tuple(round(float(v), 3) for v in bb(s))
            if key not in {(l3,) + tuple(round(float(v), 3) for v in bb(q))
                           for l3, q in out[lab.text]}:
                out[lab.text].append((lay2, s))
    return out


def macro(name, cell, lib_cells, cls, extra=(), obs=None, note=None, labels=None,
          netof=None):
    b = sel(cell, BOUND)
    x0, y0, x1, y1 = bb(b[0]) if b else cell.bounding_box()[0] + cell.bounding_box()[1]
    if not b:
        (x0, y0), (x1, y1) = cell.bounding_box()
    w, h = x1 - x0, y1 - y0
    dx, dy = x0, y0
    L = [f"MACRO {name}", f"  CLASS {cls} ;",
         f"  FOREIGN {name} {-dx:.3f} {-dy:.3f} ;",
         "  ORIGIN 0.000 0.000 ;",
         f"  SIZE {w:.3f} BY {h:.3f} ;",
         "  SYMMETRY X Y ;"]
    if note:
        L.insert(1, f"  # {note}")
    pins = pin_shapes(cell, lib_cells, extra, labels, netof)
    for pn in sorted(pins):
        use = use_of(pn)
        L += [f"  PIN {pn}", f"    DIRECTION {dir_of(pn)} ;", f"    USE {use} ;"]
        if use != "SIGNAL":
            L.append("    SHAPE ABUTMENT ;")
        L.append("    PORT")
        cur = None
        for lay, s in sorted(pins[pn], key=lambda t: t[0]):
            if lay != cur:
                L.append(f"      LAYER {lay} ;")
                cur = lay
            L.append(rect_of(s, dx, dy, "        "))
        L += ["    END", f"  END {pn}"]
    if obs:
        L.append("  OBS")
        L.append("    LAYER METAL1 ;")
        for r in obs:
            L.append(f"      RECT {r[0]-dx:.3f} {r[1]-dy:.3f} {r[2]-dx:.3f} {r[3]-dy:.3f} ;")
        L.append("    LAYER METAL2 ;")
        for r in obs:
            L.append(f"      RECT {r[0]-dx:.3f} {r[1]-dy:.3f} {r[2]-dx:.3f} {r[3]-dy:.3f} ;")
        L.append("  END")
    L.append(f"END {name}")
    return "\n".join(L), pins


def obstructions(cell):
    """フレームが塞いでいる領域を矩形の列で返す。

    **中央の正方形 1 個で表すと狭くなりすぎる。** パッドの内側は ±920 µm だが
    四隅の `OSS_FRAME_CNR` が 800〜1160 µm を占めるので、最大の正方形は
    1600 x 1600（2.56 mm²）にしかならない。実際に空いているのは
    「±920 の正方形から四隅の 120 x 120 を欠いた形」で 3.33 mm² ある。
    ルータには実形状を渡したいので、各インスタンスの外形をそのまま OBS にする。

    `OSS_EDGE_SEAL` のように**自分では図形を持たず参照だけ**のセルは、
    外形が版全体になってしまうので 1 段展開する。
    """
    out = []

    def walk(c, ox=0.0, oy=0.0, rot=0.0, mir=False):
        for r in c.references:
            if r.cell.name.startswith("via"):
                continue
            rr = (r.rotation or 0.0) + rot
            mm = bool(r.x_reflection) ^ mir
            px, py = r.origin
            if mir:
                py = -py
            if rot:
                cc, ss = math.cos(rot), math.sin(rot)
                px, py = px * cc - py * ss, px * ss + py * cc
            px += ox; py += oy
            if r.cell.references and not r.cell.polygons:
                walk(r.cell, px, py, rr, mm)       # 参照だけのセルは展開する
                continue
            (bx0, by0), (bx1, by1) = r.cell.bounding_box()
            xs, ys = [], []
            for qx, qy in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)):
                if mm:
                    qy = -qy
                if rr:
                    cc, ss = math.cos(rr), math.sin(rr)
                    qx, qy = qx * cc - qy * ss, qx * ss + qy * cc
                xs.append(qx + px); ys.append(qy + py)
            out.append((min(xs), min(ys), max(xs), max(ys)))

    walk(cell)
    return out


def core_opening(cell, verbose=False):
    """中央に取れる最大の正方形（= セルを置けるコア領域）の半辺を返す。

    各インスタンスの外形（変換後）に対して「一辺 2L の中央正方形がそれに
    触れない」条件は
        L <= ax0 (左端が右側)  /  L <= -ax1 (右端が左側)
        L <= ay0 (下端が上側)  /  L <= -ay1 (上端が下側)
    のどれか。**角の座標のチェビシェフ距離で近似してはいけない** —
    斜めに離れたセルを過小評価して、実際より狭いコアになる（1840 が 1600 に化けた）。
    """
    lim, who = 1e9, None
    for r in cell.references:
        if r.cell.name.startswith(("via", "OSS_EDGE_SEAL", "OSS_LOGO")):
            continue
        (bx0, by0), (bx1, by1) = r.cell.bounding_box()
        xs, ys = [], []
        for px, py in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)):
            if r.x_reflection:
                py = -py
            if r.rotation:
                c, s = math.cos(r.rotation), math.sin(r.rotation)
                px, py = px * c - py * s, px * s + py * c
            xs.append(px + r.origin[0]); ys.append(py + r.origin[1])
        ax0, ax1, ay0, ay1 = min(xs), max(xs), min(ys), max(ys)
        cand = [v for v in (ax0 if ax0 > 0 else None, -ax1 if ax1 < 0 else None,
                            ay0 if ay0 > 0 else None, -ay1 if ay1 < 0 else None)
                if v is not None]
        if not cand:
            continue                     # 中央にかかっている（ありえないはず）
        if max(cand) < lim:
            lim, who = max(cand), r.cell.name
    if verbose:
        print(f"    コアを決めているのは {who}")
    return lim


def make_netof(gds, top):
    """点 -> その点の M2 が属する網の名前。KLayout の抽出に問い合わせる。

    電源ラベルが本当にその網に乗っているかの確認に使う。KLayout が入って
    いなければ None を返す（確認を飛ばすだけで LEF は生成できる）。
    """
    try:
        import klayout.db as kdb
        import klayout_extract
    except ImportError:
        print("    （klayout が無いので電源ラベルの網チェックは飛ばす）")
        return None
    l2n = klayout_extract.build(gds, top)
    nl = l2n.netlist()
    circuit = nl.circuit_by_name(top)
    cache = {}
    for lay in ("M1", "M2"):
        lr = l2n.layer_by_name(lay)
        for net in circuit.each_net():
            nm = net.expanded_name()
            if nm in ("VDD", "VSS"):
                r = l2n.shapes_of_net(net, lr, True)
                r.merge()
                cache[(lay, nm)] = r

    def netof(pt, lay="METAL2"):
        k = "M1" if lay == "METAL1" else "M2"
        x, y = pt
        box = kdb.Region(kdb.Box(int((x - .2) * 1000), int((y - .2) * 1000),
                                 int((x + .2) * 1000), int((y + .2) * 1000)))
        for (kk, nm), r in cache.items():
            if kk == k and not (r & box).is_empty():
                return nm
        return None
    return netof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("-o", "--out", default="lef/TR-1um_frame.lef")
    ap.add_argument("--top", default="OSS_FRAME_GIO")
    a = ap.parse_args()
    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}

    out = ["# TR-1um フレーム / パッドセルの LEF",
           "# scripts/mkleffrm.py が生成。手で編集しないこと。",
           f"# source: {os.path.basename(a.gds)}", ""]

    for nm in PAD_CELLS:
        if nm not in cells:
            continue
        note = ("3 ステート双方向 IO。HIZ=0 で PAD=OUT（非反転）、HIZ=1 で高Z。"
                if nm.endswith("DIO") else "ESD のみ")
        txt, pins = macro(nm, cells[nm], cells, "PAD", note=note)
        out += [txt, ""]
        print(f"  {nm:<18} pin {sorted(pins)}")

    # --- フレーム本体 ---
    top = cells[a.top]
    # パッドセルのピン図形をインスタンスの変換を掛けて持ち上げる
    extra, labels = [], list(top.labels)
    for r in top.references:
        if not r.cell.name.startswith("OSS_ESD_5V"):
            continue
        for s in sel(r.cell, PINSH):
            extra.append(xform(s, r))
        # パッドセルの中の電源ラベルも持ち上げる。そうしないと VDD のポートが
        # ボンディングパッド 1 枚だけになり、コアから繋ぐ場所が無くなる。
        for lab in r.cell.labels:
            if lab.layer in (LBL[0], M1LBL[0]) and use_of(lab.text) != "SIGNAL":
                q = gdstk.Label(lab.text, lab.origin, layer=lab.layer,
                                texttype=lab.texttype)
                x, y = lab.origin
                if r.x_reflection:
                    y = -y
                if r.rotation:
                    c_, s_ = math.cos(r.rotation), math.sin(r.rotation)
                    x, y = x * c_ - y * s_, x * s_ + y * c_
                q.origin = (x + r.origin[0], y + r.origin[1])
                labels.append(q)
    lim = core_opening(top, verbose=True)
    obs = obstructions(top)
    (X0, Y0), (X1, Y1) = top.bounding_box()
    # 使えるコア面積を数える。
    # **パッドリングの内側だけを数えること。** 版全体で数えると、パッドと
    # シールリングの間の 16um の隙間まで「空き」に入って 3.47 mm2 と出るが、
    # そんな幅ではセルは置けない。
    import numpy as np
    inner = 1e9
    for r in top.references:
        if not r.cell.name.startswith("OSS_ESD_5V"):
            continue
        (bx0, by0), (bx1, by1) = r.cell.bounding_box()
        xs, ys = [], []
        for qx, qy in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)):
            if r.x_reflection:
                qy = -qy
            if r.rotation:
                cc, ss = math.cos(r.rotation), math.sin(r.rotation)
                qx, qy = qx * cc - qy * ss, qx * ss + qy * cc
            xs.append(qx + r.origin[0]); ys.append(qy + r.origin[1])
        cand = [v for v in (min(xs) if min(xs) > 0 else None,
                            -max(xs) if max(xs) < 0 else None,
                            min(ys) if min(ys) > 0 else None,
                            -max(ys) if max(ys) < 0 else None) if v is not None]
        inner = min(inner, max(cand))
    step = 2.0
    gx = np.arange(-inner + step / 2, inner, step)
    free = np.ones((len(gx), len(gx)), dtype=bool)
    for r in obs:
        free[np.ix_((gx >= r[0]) & (gx <= r[2]), (gx >= r[1]) & (gx <= r[3]))] = False
    area = free.sum() * step * step
    note = (f"コア: パッド内側 {2*inner:.0f} x {2*inner:.0f} um から四隅を欠いて "
            f"空き {area/1e6:.2f} mm2 / 内接する最大の正方形 "
            f"{2*lim:.0f} x {2*lim:.0f} um = {(2*lim)**2/1e6:.2f} mm2")
    txt, pins = macro(a.top, top, cells, "BLOCK", extra=extra, obs=obs, note=note,
                      labels=labels, netof=make_netof(a.gds, a.top))
    out += [txt, ""]
    miss = [p for p in pins if not pins[p]]
    print(f"  {a.top:<18} pin {len(pins)} / OBS {len(obs)} 個 / {note}"
          + (f"  ** 図形の無いピン {miss}" if miss else ""))

    open(a.out, "w").write("\n".join(out))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()

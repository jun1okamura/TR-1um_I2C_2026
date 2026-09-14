#!/usr/bin/env python3
"""TR-1um_STDCELL.gds から LEF（tech + セル + マクロ）を生成する。

  usage: python3 scripts/mklef.py lef/TR-1um_STDCELL.gds -o lef/

出力:
  lef/TR-1um_tech.lef      LAYER / VIA / SITE 定義
  lef/TR-1um_cells.lef     全 MACRO（標準セル + アレイセル + REG4x16）

レイヤ規約（GDS 実測）:
  (13,0)=M1  (19,0)=V1  (20,0)=M2  (49,1)=信号ピン形状  (48,1)=電源レール/貫通WL
  (235,0)=セル境界（= LEF の SIZE）  (140,0)=N-well

ピンの層は、(49,1) の形状が M2 と重なれば METAL2、そうでなければ METAL1 と判定する。
TLAT の WR/WRB/RD/RDB のように (48,1) にラベルがあり、かつセル左右端に届く M1 は
「貫通ワードライン」として信号ピン扱いにする（abut で繋がる想定）。
"""
from __future__ import annotations
import argparse, collections, os, sys

try:
    import gdstk
except ImportError:
    sys.exit("pip install gdstk --break-system-packages")

M1, V1, M2 = (13, 0), (19, 0), (20, 0)
PINL, LBL, BOUND, NWELL = (49, 1), (48, 1), (235, 0), (140, 0)
EPS = 1e-3

ROW_H, SITE_W = 59.4, 5.4          # 標準セル行高 / 配置グリッド（ポリピッチ）
M2_PITCH, M2_OFFSET, M2_W = 5.4, 2.7, 3.4   # M2 配線トラック（GDS 実測）
DBU = 1000                          # LEF DATABASE MICRONS

# 標準セル行（59.4）に乗せずマクロ／アレイとして扱うもの
BLOCKS = {"TLAT", "TAP2S", "REGBUF", "DEC0", "DEC2", "DEC16", "ADDBUF",
          "TLAT4", "TLAT4B", "TLAT8", "TLAT8B", "TLAT64", "TLAT128",
          "REGBUF4", "REGBUF8", "REG4x16", "REG8x16"}
SPACER = {"FILL1", "FILL2", "FILL3"}
WELLTAP = {"TAP2", "TAP3", "TAP2S"}

TECH = f"""VERSION 5.8 ;
BUSBITCHARS "[]" ;
DIVIDERCHAR "/" ;
UNITS
  DATABASE MICRONS {DBU} ;
END UNITS

MANUFACTURINGGRID 0.1 ;

LAYER METAL1
  TYPE ROUTING ;
  DIRECTION HORIZONTAL ;
  PITCH 3.2 ;
  WIDTH 1.8 ;
  SPACING 1.4 ;
END METAL1

LAYER VIA1
  TYPE CUT ;
  SPACING 1.4 ;
END VIA1

LAYER METAL2
  TYPE ROUTING ;
  DIRECTION VERTICAL ;
  PITCH {M2_PITCH} ;
  OFFSET {M2_OFFSET} ;
  WIDTH {M2_W} ;
  SPACING 2.0 ;
END METAL2

VIA V1_1x1 DEFAULT
  LAYER METAL1 ;
    RECT -1.7 -1.7 1.7 1.7 ;
  LAYER VIA1 ;
    RECT -0.7 -0.7 0.7 0.7 ;
  LAYER METAL2 ;
    RECT -1.7 -1.7 1.7 1.7 ;
END V1_1x1

SITE TR1UM
  CLASS CORE ;
  SYMMETRY Y ;
  SIZE {SITE_W} BY {ROW_H} ;
END TR1UM
"""


PWR = {"vdd", "vdda", "vccd", "vcc"}
GND = {"gnd", "vss", "vssd", "vssa"}


def use_of(name):
    return "POWER" if name in PWR else "GROUND" if name in GND else "SIGNAL"


def sel(cell, ld):
    return [p for p in cell.polygons if (p.layer, p.datatype) == ld]


def bbox(poly):
    p = poly.points
    return p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()


def is_rect(poly):
    p = poly.points
    if len(p) != 4:
        return False
    xs, ys = sorted(set(round(v, 4) for v in p[:, 0])), sorted(set(round(v, 4) for v in p[:, 1]))
    return len(xs) == 2 and len(ys) == 2


def emit_shape(poly, dx, dy, indent):
    if is_rect(poly):
        x0, y0, x1, y1 = bbox(poly)
        return f"{indent}RECT {x0-dx:.3f} {y0-dy:.3f} {x1-dx:.3f} {y1-dy:.3f} ;"
    pts = " ".join(f"{x-dx:.3f} {y-dy:.3f}" for x, y in poly.points)
    return f"{indent}POLYGON {pts} ;"


_FLAT = {}


def flat(cell, ld):
    """階層セルでも配下まで含めた指定レイヤのポリゴンを返す"""
    key = (id(cell), ld)
    if key not in _FLAT:
        if cell.references:
            _FLAT[key] = cell.get_polygons(layer=ld[0], datatype=ld[1])
        else:
            _FLAT[key] = sel(cell, ld)
    return _FLAT[key]


def pin_layer(cell, shape):
    """(49,1) の形状が M2 と重なれば METAL2、でなければ METAL1"""
    bb = shape.bounding_box()
    near = [p for p in flat(cell, M2)
            if not (p.bounding_box()[1][0] < bb[0][0] or p.bounding_box()[0][0] > bb[1][0] or
                    p.bounding_box()[1][1] < bb[0][1] or p.bounding_box()[0][1] > bb[1][1])]
    if near and gdstk.boolean([shape], near, "and", precision=EPS):
        return "METAL2"
    return "METAL1"


def collect_pins(cell):
    """{name: [(layer, polygon), ...]} と、電源ピン名の集合を返す"""
    pins = collections.defaultdict(list)
    power = set()
    pin_shapes = sel(cell, PINL)
    m1 = gdstk.boolean(sel(cell, M1), [], "or", precision=EPS)
    b = sel(cell, BOUND)
    x0, x1 = (bbox(b[0])[0], bbox(b[0])[2]) if b else (None, None)

    # (49,1) のピン形状 <- レイヤ49のラベルで命名
    for lab in cell.labels:
        if lab.layer != PINL[0]:
            continue
        probe = gdstk.rectangle((lab.origin[0] - 0.2, lab.origin[1] - 0.2),
                                (lab.origin[0] + 0.2, lab.origin[1] + 0.2))
        for s in pin_shapes:
            if gdstk.boolean([probe], [s], "and", precision=EPS):
                pins[lab.text].append((pin_layer(cell, s), s))
                break

    # (48,1) のラベル: 電源レール と 貫通ワードライン
    for lab in cell.labels:
        if lab.layer != LBL[0]:
            continue
        probe = gdstk.rectangle((lab.origin[0] - 0.3, lab.origin[1] - 0.3),
                                (lab.origin[0] + 0.3, lab.origin[1] + 0.3))
        for s in m1:
            if not gdstk.boolean([probe], [s], "and", precision=EPS):
                continue
            if use_of(lab.text) != "SIGNAL":
                power.add(lab.text)
            if not any(s is q for _, q in pins[lab.text]):
                pins[lab.text].append(("METAL1", s))
            break
    return pins, power


def hier_bound(cells, cell, M=None):
    """自前の (235,0) が無い階層セル: 配下の境界の和で外形を求める"""
    import numpy as np
    M = np.eye(3) if M is None else M
    xs, ys = [], []
    for r in cell.references:
        if r.cell.name.startswith("via"):
            continue
        rep = r.repetition
        offs = list(rep.get_offsets()) if rep is not None else []
        if not offs:
            offs = [(0.0, 0.0)]
        for ox, oy in offs:
            a = r.rotation or 0.0
            c, s = np.cos(a), np.sin(a)
            R = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
            F = np.diag([1.0, -1.0, 1.0]) if r.x_reflection else np.eye(3)
            T = np.array([[1, 0, r.origin[0] + ox], [0, 1, r.origin[1] + oy], [0, 0, 1]])
            M2 = M @ T @ R @ F
            b = sel(r.cell, BOUND)
            if b:
                bx = bbox(b[0])
                pts = np.array([[bx[0], bx[1], 1], [bx[2], bx[1], 1],
                                [bx[2], bx[3], 1], [bx[0], bx[3], 1]]).T
                q = (M2 @ pts)[:2]
                xs += [q[0].min(), q[0].max()]; ys += [q[1].min(), q[1].max()]
            if r.cell.references:
                sub = hier_bound(cells, r.cell, M2)
                if sub:
                    xs += [sub[0], sub[2]]; ys += [sub[1], sub[3]]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def macro(cell, name, cells=None):
    b = sel(cell, BOUND)
    if not b:
        if cells is None or not cell.references:
            return None
        hb = hier_bound(cells, cell)
        if hb is None:
            return None
        return hier_macro(cell, name, hb)
    x0, y0, x1, y1 = bbox(b[0])
    w, h = x1 - x0, y1 - y0
    dx, dy = x0, y0                      # LEF 原点をセル境界の左下に合わせる
    cls = ("BLOCK" if name in BLOCKS else
           "CORE SPACER" if name in SPACER else
           "CORE WELLTAP" if name in WELLTAP else "CORE")
    L = [f"MACRO {name}",
         f"  CLASS {cls} ;",
         f"  FOREIGN {name} {-dx:.3f} {-dy:.3f} ;",
         f"  ORIGIN 0.000 0.000 ;",
         f"  SIZE {w:.3f} BY {h:.3f} ;"]
    if cls.startswith("CORE") and abs(h - ROW_H) < 1e-6:
        L.append("  SITE TR1UM ;")
        L.append("  SYMMETRY X Y ;")
    else:
        L.append("  SYMMETRY X Y ;")

    pins, power = collect_pins(cell)
    for pname in sorted(pins):
        use = use_of(pname)
        direction = "INOUT" if use != "SIGNAL" else "INOUT"
        L.append(f"  PIN {pname}")
        L.append(f"    DIRECTION {direction} ;")
        L.append(f"    USE {use} ;")
        if use != "SIGNAL":
            L.append(f"    SHAPE ABUTMENT ;")
        L.append(f"    PORT")
        cur = None
        for lay, shp in pins[pname]:
            if lay != cur:
                L.append(f"      LAYER {lay} ;")
                cur = lay
            L.append(emit_shape(shp, dx, dy, "        "))
        L.append(f"    END")
        L.append(f"  END {pname}")

    # OBS
    if cell.references and not sel(cell, M1) and not sel(cell, M2):
        # 金属を一切自前で持たない純粋なコンテナ（REG8x16 / REG4x16）は全面を塞ぐ。
        # sel(cell, M1) が空なので下の差分計算では OBS が丸ごと消えてしまう
        # （トップに (235,0) を入れて hier_macro() を通らなくなったときに実際に消えた）。
        # TLAT / REGBUF / TAP2S のように自前の金属を持つ BLOCK はここを通さない
        # ——全面を塞ぐと行に置けなくなる。
        L += ["  OBS", "    LAYER METAL1 ;",
              f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
              "    LAYER METAL2 ;",
              f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
              "  END", f"END {name}"]
        return "\n".join(L)

    # 標準セル: ピン以外の M1 / M2
    used = [s for v in pins.values() for _, s in v]
    obs = []
    for lay, ld in (("METAL1", M1), ("METAL2", M2)):
        rest = gdstk.boolean(sel(cell, ld), used, "not", precision=EPS)
        if rest:
            obs.append((lay, rest))
    if obs:
        L.append("  OBS")
        for lay, shapes in obs:
            L.append(f"    LAYER {lay} ;")
            for s in shapes:
                L.append(emit_shape(s, dx, dy, "      "))
        L.append("  END")
    L.append(f"END {name}")
    return "\n".join(L)


def hier_macro(cell, name, hb):
    """階層マクロ（REG4x16 等）: 外形は配下の境界の和、OBS は全面をふさぐ"""
    x0, y0, x1, y1 = hb
    w, h = x1 - x0, y1 - y0
    dx, dy = x0, y0
    L = [f"MACRO {name}",
         "  CLASS BLOCK ;",
         f"  FOREIGN {name} {-dx:.3f} {-dy:.3f} ;",
         "  ORIGIN 0.000 0.000 ;",
         f"  SIZE {w:.3f} BY {h:.3f} ;",
         "  SYMMETRY X Y ;"]
    pins, _ = collect_pins(cell)
    for pname in sorted(pins):
        use = use_of(pname)
        L += [f"  PIN {pname}", "    DIRECTION INOUT ;", f"    USE {use} ;"]
        if use != "SIGNAL":
            L.append("    SHAPE ABUTMENT ;")
        L.append("    PORT")
        cur = None
        for lay, shp in pins[pname]:
            if lay != cur:
                L.append(f"      LAYER {lay} ;"); cur = lay
            L.append(emit_shape(shp, dx, dy, "        "))
        L += ["    END", f"  END {pname}"]
    if not pins:
        L.append("  # ★ ピン未定義: GDS のトップにラベル/(49,1) 形状を入れて再生成すること")
    # ハードマクロなので上は通さない
    L += ["  OBS", "    LAYER METAL1 ;",
          f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
          "    LAYER METAL2 ;",
          f"      RECT 0.000 0.000 {w:.3f} {h:.3f} ;",
          "  END", f"END {name}"]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("-o", "--outdir", default="lef")
    a = ap.parse_args()

    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}
    os.makedirs(a.outdir, exist_ok=True)

    tech = os.path.join(a.outdir, "TR-1um_tech.lef")
    open(tech, "w").write(TECH)
    print(f"wrote {tech}")

    out = ["# TR-1um cell library — generated by scripts/mklef.py",
           f"# source: {os.path.basename(a.gds)}", ""]
    made, skipped = [], []
    for n in sorted(cells):
        if n.startswith(("$$$", "via_")):
            continue
        m = macro(cells[n], n, cells)
        if m is None:
            # 階層マクロ: 自前の 235 が無ければ配下から合成
            skipped.append(n)
            continue
        out.append(m); out.append("")
        made.append(n)
    out.append("END LIBRARY")
    path = os.path.join(a.outdir, "TR-1um_cells.lef")
    open(path, "w").write("\n".join(out))
    print(f"wrote {path}  ({len(made)} MACRO)")

    print("\n--- ピンの入っていないセル ---")
    for n in made:
        p, _ = collect_pins(cells[n])
        sig = [k for k in p if use_of(k) == "SIGNAL"]
        if not sig:
            print(f"  ! {n:<10} 信号ピンなし")
    if skipped:
        print("\n--- (235,0) が無く MACRO 化できなかったセル ---")
        for n in skipped:
            print(f"  ! {n}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""TR-1um_STDCELL.gds から1セルを簡易抽出して SPICE サブサーキットを起こす。

  usage: python3 scripts/gds_extract.py lef/TR-1um_STDCELL.gds TLAT [-o tlat.spi]

正規の LVS 抽出器ではない（PDK の KLayout ランセットを置き換えるものではない）。
セルの回路構成を確認し、SPICE 検証の出発点を作るための道具。

レイヤ: (3,1)=P+ (3,2)=N+ (8,1)=poly (11,0)=contact (13,0)=M1 (19,0)=V1 (20,0)=M2
        (48,1)/(49,1)=ラベル (140,0)=Nwell (235,0)=セル境界
"""
from __future__ import annotations
import argparse, sys
from collections import defaultdict

try:
    import gdstk
except ImportError:
    sys.exit("pip install gdstk --break-system-packages")

EPS = 1e-3
L = dict(PIMP=(3, 1), NIMP=(3, 2), POLY=(8, 1), CONT=(11, 0), M1=(13, 0),
         V1=(19, 0), M2=(20, 0), NWELL=(140, 0), BOUND=(235, 0))


class UF:
    def __init__(self): self.p = {}
    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb: self.p[ra] = rb


def sel(cell, key):
    ld = L[key]
    return [p for p in cell.polygons if (p.layer, p.datatype) == ld]


GROW = 0.01        # µm。辺で接するだけの図形を確実に繋ぐための膨張量


def merge(polys):
    """重なり／接触するポリゴンを連結成分ごとにまとめる。

    **辺で接するだけの図形は boolean 'or' では繋がらないことがある。**
    XOR2 では電源スタブ 2 本が同じ形でレールに接しているのに、片方だけ
    別ネットに割れて PMOS プルアップの vdd が外れ、出力がフルレールに
    振れない「バグ」に見えていた（実際はレイアウトは正しく、こちらの
    抽出が割っていた）。KLayout の LVS は接触＝導通として扱うので、
    それに合わせて **{GROW} µm だけ膨らませてから結合する**。
    最小間隔は M1 で 1.4 µm あるので、この膨張で別ネットが繋がることはない。
    """
    if not polys:
        return []
    grown = gdstk.offset(polys, GROW, join="miter", precision=EPS, use_union=True)
    return grown if grown else gdstk.boolean(polys, [], "or", precision=EPS)


def hits(shape, targets):
    """shape と面積を持って重なる targets のインデックス"""
    out = []
    for i, t in enumerate(targets):
        if gdstk.boolean([shape], [t], "and", precision=EPS):
            out.append(i)
    return out


def extract(cell):
    nwell = sel(cell, "NWELL")
    poly = merge(sel(cell, "POLY"))
    m1 = merge(sel(cell, "M1"))
    m2 = merge(sel(cell, "M2"))

    pact = gdstk.boolean(sel(cell, "PIMP"), nwell, "and", precision=EPS)
    nact = gdstk.boolean(sel(cell, "NIMP"), nwell, "not", precision=EPS)

    # ゲート = poly ∩ active、拡散島 = active ∖ poly
    devs = []          # (type, gate_poly, W, L)
    diff = {}          # ('P'|'N', idx) -> polygon
    for tag, act in (("P", pact), ("N", nact)):
        for g in gdstk.boolean(sel(cell, "POLY"), act, "and", precision=EPS):
            devs.append((tag, g))
        for i, d in enumerate(merge(gdstk.boolean(act, sel(cell, "POLY"), "not", precision=EPS))):
            diff[(tag, i)] = d

    uf = UF()
    nodes = ([("poly", i) for i in range(len(poly))] + [("m1", i) for i in range(len(m1))] +
             [("m2", i) for i in range(len(m2))] + list(diff))
    for n in nodes: uf.find(n)

    # コンタクト: M1 <-> poly / 拡散
    for c in sel(cell, "CONT"):
        for i in hits(c, m1):
            for j in hits(c, poly): uf.union(("m1", i), ("poly", j))
            for k, d in diff.items():
                if gdstk.boolean([c], [d], "and", precision=EPS): uf.union(("m1", i), k)
    # ビア: M1 <-> M2
    for v in sel(cell, "V1"):
        for i in hits(v, m1):
            for j in hits(v, m2): uf.union(("m1", i), ("m2", j))

    # ラベル → ネット名
    names = {}
    stray = []
    for lab in cell.labels:
        pt = gdstk.rectangle((lab.origin[0] - .2, lab.origin[1] - .2),
                             (lab.origin[0] + .2, lab.origin[1] + .2))
        # **ラベルの層とその下の配線層を一致させる**。DRC/LVS デッキ（00_Layers.drc）も
        #   M1_LBL = labels(48,0) / M2_LBL = labels(49,0)
        # と層ごとに対応させている。層をまたいで拾うと、M2 のつもりで置いたラベルが
        # 真下の M1 電源レールに付いて電源ネットが信号名に化ける（REGBUF で実際に起きた）。
        order = (("m1", m1), ("poly", poly)) if lab.layer == 48 else (("m2", m2),)
        for kind, arr in order:
            for i in hits(pt, arr):
                names.setdefault(uf.find((kind, i)), lab.text)
                break
            else:
                continue
            break
        else:
            stray.append((lab.text, lab.layer, tuple(round(float(v), 2) for v in lab.origin)))
    if stray:
        print("* 迷子ラベル（その層の配線が真下に無い。LVS では何にも付かない）:")
        for t, ly, o in stray:
            want = "M1(13,0)" if ly == 48 else "M2(20,0)"
            print(f"*   {t!r} layer {ly} @ {o} … 直下に {want} が無い")

    # 無名ネットには決定的な番号を振る（実行ごとに変わらないように）
    anon = {}
    for node in sorted(nodes, key=lambda n: (str(n[0]), n[1])):
        r = uf.find(node)
        if r not in names and r not in anon:
            anon[r] = f"n{len(anon) + 1}"

    def netname(node):
        r = uf.find(node)
        return names.get(r, anon.get(r, "n?"))

    # --- 各ゲートの端子と寸法 -------------------------------------------------
    # **チャネルの向きを決め打ちにしないこと。** 標準セルは poly が縦に走るので
    # 「W = ゲートの高さ / L = 幅」で済んでいたが、フレームのパッドセルは
    # OSS_NCH_DRV / OSS_PCH_DRV が 90 度回して置いてあり poly が横向きになる。
    # 決め打ちだと W と L が入れ替わる（W=500µm の出力段が W=2µm に化けた）。
    #
    # 物理で決める: ゲートを x だけ／y だけ膨らませて、**拡散島が 2 つ当たる方が
    # 電流の流れる向き**。その向きの寸法が L、直交方向が W。
    def touch(tag, bb, dx, dy):
        grow = gdstk.rectangle((bb[0][0] - dx, bb[0][1] - dy),
                               (bb[1][0] + dx, bb[1][1] + dy))
        return {k for k, d in diff.items()
                if k[0] == tag and gdstk.boolean([grow], [d], "and", precision=EPS)}

    out = []
    for tag, g in devs:
        gate = next((netname(("poly", i)) for i in hits(g, poly)), "?")
        # ゲートと拡散は**辺で接している**（重なりゼロ）ので 'and' では拾えない。
        # ゲート図形そのものを少しだけ膨らませて交差を取る。
        # bbox を膨らませる方式だと L 字のゲート（FILL2/FILL3 のデキャップ）で
        # 片側の拡散を取りこぼす。
        gg = gdstk.offset([g], 0.1, join="miter", precision=EPS, use_union=True)
        sd = [netname(k) for k, d in diff.items()
              if k[0] == tag and gdstk.boolean(gg, [d], "and", precision=EPS)]
        bb = g.bounding_box()
        ex, ey = bb[1][0] - bb[0][0], bb[1][1] - bb[0][1]
        nx, ny = len(touch(tag, bb, 0.1, 0.0)), len(touch(tag, bb, 0.0, 0.1))
        if (nx >= 2) == (ny >= 2):
            horiz = ex <= ey            # 決まらなければ短い方を L とする
        else:
            horiz = nx >= 2             # 左右に拡散 = 電流は横向き
        l, w = (ex, ey) if horiz else (ey, ex)
        out.append((tag, gate, sorted(set(sd)), round(float(w), 2), round(float(l), 2)))
    return out, names, uf


def cell_pins(cell):
    """(49,1) のピンラベル + セル左右端に接する (48,1) ラベル（= 貫通するワードライン）。
    TLAT の WR/WRB/RD/RDB は現状 (48,1) にあるので後者で拾う。"""
    b = sel(cell, "BOUND")
    x0, x1 = (b[0].points[:, 0].min(), b[0].points[:, 0].max()) if b else (None, None)
    pins, seen = [], set()
    for lab in cell.labels:
        t = lab.text
        if t in ("vdd", "vss") or t in seen:
            continue
        edge = x0 is not None and (abs(lab.origin[0] - x0) < 2.0 or abs(lab.origin[0] - x1) < 2.0)
        if lab.layer == 49 or (lab.layer == 48 and edge):
            seen.add(t); pins.append(t)
    return pins


def spice(cell, devs, name):
    pins = cell_pins(cell)
    lines = [f".subckt {name} {' '.join(pins)} vdd vss",
             "* auto-extracted by scripts/gds_extract.py -- NOT an LVS-grade netlist"]
    for i, (tag, gate, sd, w, l) in enumerate(devs):
        # ソースとドレインが同じネットに落ちるのは異常ではない。
        # FILL2/FILL3 のデキャップは拡散の両側とも同じレールに繋ぐ MOS 容量なので、
        # 区別できるネットは 1 本しかない。'?' を出さずにそのネットを両端に使う。
        if len(sd) == 1:
            s = d = sd[0]
        else:
            s, d = (sd + ["?", "?"])[:2]
        mtype = "pmos" if tag == "P" else "nmos"
        bulk = "vdd" if tag == "P" else "vss"
        lines.append(f"M{i} {d} {gate} {s} {bulk} {mtype} W={w}u L={l}u")
    lines.append(".ends")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gds"); ap.add_argument("cell"); ap.add_argument("-o", "--out")
    a = ap.parse_args()
    lib = gdstk.read_gds(a.gds)
    cells = {c.name: c for c in lib.cells}
    if a.cell not in cells:
        sys.exit(f"cell {a.cell} not found. have: {', '.join(sorted(cells))}")
    c = cells[a.cell]
    devs, names, uf = extract(c)

    # --- セルフチェック: 電源が分離できていなければ結果は信用できない ---
    nets = set(names.values())
    has_lbl = {t for t in (l.text for l in c.labels) if t in ("vdd", "vss")}
    warn = []
    if not {"vdd", "vss"} <= has_lbl:
        print(f"* 注意: このセルには {'/'.join(sorted({'vdd','vss'} - has_lbl))} のラベルが無いため、"
              "電源ネットの分離を確認できません。")
        print("*       直列/並列の構造そのものは読めますが、ネット名は当てになりません。\n")
    elif not {"vdd", "vss"} <= nets:
        warn.append("vdd / vss のラベルはあるのに別ネットとして解決できていない（誤併合の疑い）")
    if {"vdd", "vss"} <= nets:
        for tag, rail in (("P", "vdd"), ("N", "vss")):
            if any(d[0] == tag and rail not in d[2] and len(d[2]) < 2 for d in devs):
                warn.append(f"{tag}MOS の一部で {rail} 側の端子が取れていない")
    if warn:
        print("!" * 68)
        print("! 抽出結果は信用できません:")
        for w in warn:
            print(f"!   - {w}")
        print("!   ネットが誤って併合されている可能性が高く、ゲート/ドレインの")
        print("!   割り当てが入れ替わって見えることがあります。")
        print("!   正式な確認は PDK の LVS ランセットで行ってください。")
        print("!" * 68)
        print()

    print(f"=== {a.cell}: {len(devs)} transistors ===")
    by = defaultdict(list)
    for tag, gate, sd, w, l in devs:
        by[gate].append((tag, sd, w, l))
    for tag, gate, sd, w, l in devs:
        mark = "  <- L が最小長でない" if abs(l - 1.0) > 1e-6 else ""
        print(f"  {tag}MOS W={w:5.1f} L={l:4.1f}  gate={gate:<6} s/d={','.join(sd)}{mark}")
    print("\nnamed nets:", sorted(set(names.values())))
    txt = spice(c, devs, a.cell)
    if a.out:
        open(a.out, "w").write(txt); print(f"\nwrote {a.out}")
    else:
        print("\n" + txt)

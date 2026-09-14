#!/usr/bin/env python3
"""TR-1um_STDCELL.gds を読んで、セルの実寸法 / Tr数 / ピンを表にし、
Yosys 用 genlib と area_estimate.py 用の面積テーブルを生成する。

  usage: python3 scripts/cellinfo.py lef/TR-1um_STDCELL.gds [--genlib out.genlib]
                                     [--areas scripts/cell_area.json] [--check]

`--areas` は全セルの実測面積を JSON に書き出す。`scripts/area_estimate.py` が
これを読むので、ライブラリを直したら genlib と一緒に必ず作り直すこと
（面積の表を手で持たないための仕組み。行高 64.8→59.4 で古い表が残った反省）。

レイヤ規約（GDS から読み取ったもの）:
  (3,1)=P+ implant  (3,2)=N+ implant  (8,1)=poly/GC  (11,0)=contact
  (13,0)=M1  (19,0)=V1  (20,0)=M2  (48,1)=電源レール/内部ネットラベル
  (49,1)=信号ピン(M2上のマーカ)  (140,0)=N-well  (235,0)=セル境界(abutment box)
セル面積 = (235,0) の外形。行高 59.4 µm、ポリピッチ 5.4 µm、セル幅 = 5.4 * n。
M2 配線トラックは prBoundary 左端から 2.7 + n*5.4（= 半ピッチオフセット）。
"""
from __future__ import annotations
import argparse, json, sys

try:
    import gdstk
except ImportError:
    sys.exit("pip install gdstk --break-system-packages")

ROW_H, POLY_PITCH, W_BASE = 59.4, 5.4, 5.4   # 2026-09-11 に行高を 64.8 -> 59.4 に変更
COX = 1.77                                   # fF/µm²（Tox 19.5nm, eps_ox 3.9 -> 1.77e-3 F/m²）
L_BOUND, L_NWELL, L_POLY, L_PIN, L_LBL = (235, 0), (140, 0), (8, 1), (49, 1), (48, 1)
L_PIMP, L_NIMP = (3, 1), (3, 2)


def sel(cell, ld):
    return [p for p in cell.polygons if (p.layer, p.datatype) == ld]


def devices(cell):
    """poly ∩ (implant ∩/∖ nwell) で実ゲートを取り出す。
    戻り値 {'P':[W..],'N':[W..], 'GA': ゲート総面積[µm²]}"""
    poly, nwell = sel(cell, L_POLY), sel(cell, L_NWELL)
    out, ga = {}, 0.0
    for tag, ld, op in (("P", L_PIMP, "and"), ("N", L_NIMP, "not")):
        act = gdstk.boolean(sel(cell, ld), nwell, op, precision=1e-3)
        gates = gdstk.boolean(poly, act, "and", precision=1e-3)
        out[tag] = [round(float(g.points[:, 1].max() - g.points[:, 1].min()), 2) for g in gates]
        ga += sum(abs(float(g.area())) for g in gates)
    out["GA"] = round(ga, 1)
    return out


SKIP = {"cont_n", "via_1", "via_1$1"}


def scan(path):
    """全セルの外形／Tr 数／ピンを拾う。

    REG8x16 のような**階層セルは自分では prBoundary を持たない**（配下の
    (235,0) が並んで外形になる）ので、その場合は展開して外形を求め、
    `array=True` を立てる。行高や幅ピッチの規約チェックは行に置く
    標準セルだけに適用し、アレイ／マクロは対象外にする。
    """
    lib = gdstk.read_gds(path)
    rows = []
    for cell in sorted(lib.cells, key=lambda c: c.name):
        if cell.name.startswith("$$$") or cell.name in SKIP:
            continue
        b = sel(cell, L_BOUND)
        array = False
        if b:
            pts = b[0].points
            x0, x1 = float(pts[:, 0].min()), float(pts[:, 0].max())
            y0, y1 = float(pts[:, 1].min()), float(pts[:, 1].max())
        else:
            flat = cell.copy("_f_" + cell.name)
            flat.flatten()
            fb = sel(flat, L_BOUND)
            if not fb:
                continue
            bb = [p.bounding_box() for p in fb]
            x0, x1 = min(b_[0][0] for b_ in bb), max(b_[1][0] for b_ in bb)
            y0, y1 = min(b_[0][1] for b_ in bb), max(b_[1][1] for b_ in bb)
            array = True
        w, h = round(x1 - x0, 3), round(y1 - y0, 3)
        # 階層セルは図形が配下にあるので、Tr 数は展開してから数える。
        # 自前の prBoundary を持っていても（= array=False でも）配下に
        # インスタンスがあれば展開が要る — REG8x16/REG4x16 にトップの
        # (235,0) を入れたときに Tr 数が 0 に化けたのがこれ。
        if not array and cell.references:
            flat = cell.copy("_f_" + cell.name)
            flat.flatten()
            array_flat = True
        else:
            array_flat = array
        d = devices(flat) if array_flat else devices(cell)
        rows.append(dict(
            name=cell.name, w=w, h=h, area=round(w * h, 1), array=array, gate_area=d["GA"],
            nP=len(d["P"]), nN=len(d["N"]), tr=len(d["P"]) + len(d["N"]),
            WP=sorted(set(d["P"])), WN=sorted(set(d["N"])),
            pins=[l.text for l in cell.labels if l.layer == L_PIN[0]],
            pinshapes=len(sel(cell, L_PIN)),
            netlabels=sorted({l.text for l in cell.labels if l.layer == L_LBL[0]}),
        ))
    return rows


# --- 意図的に規約から外れているセル（毎回出ると本当の逸脱が埋もれる）---
#     自前の prBoundary を持つので array 判定には乗らないが、行には置かないもの
MACRO_BY_COORD = {"DEC0",          # デコーダ 1 行ぶん。高さ 86.4 で座標指定して並べる
                  "REG4x16", "REG8x16"}  # 高さ 933.0 のマクロ。トップに (235,0) を
                                         # 入れたので array 判定には乗らない
# 信号ピンを持たないのが正しいセル（電源だけで完結する）
NO_SIGNAL_PIN = {"FILL1", "FILL2", "FILL3", "TAP2", "TAP2S", "TAP3"}
# ワードラインを横 abut で通すため、信号を (48,1) に置いているセル
ABUT_WORDLINE = {"TLAT", "DEC0"}


def check(rows):
    """設計規約からの逸脱を洗い出す（行に置く標準セルだけが対象）"""
    bad = []
    for r in rows:
        n = r["name"]
        if r["array"] or n in MACRO_BY_COORD:
            continue                       # アレイ／マクロは座標指定で置くので対象外
        k = (r["w"] - W_BASE) / POLY_PITCH
        if abs(k - round(k)) > 1e-6:
            bad.append(f"{n}: 幅 {r['w']} µm がポリピッチ格子外 "
                       f"(10.8 + {k:.3f}×5.4 / 最寄り {W_BASE + round(k)*POLY_PITCH:.1f})")
        if abs(r["h"] - ROW_H) > 1e-6:
            bad.append(f"{n}: 行高 {r['h']} µm (規定 {ROW_H})")
        if r["tr"] and r["pinshapes"] == 0 and n not in NO_SIGNAL_PIN:
            bad.append(f"{n}: (49,1) のピン形状が無い（ラベルのみ）")
        sig = [s for s in r["netlabels"] if s not in ("vdd", "vss")]
        outside = [s for s in sig if s.isupper() and s not in ("CKP", "CKB", "QM", "QS")]
        if outside and n not in ABUT_WORDLINE:
            bad.append(f"{n}: {','.join(outside)} が (48,1) にある"
                       f"（外部ピンなら他セル同様 (49,1) へ）")
    return bad


# --- genlib 用の論理式（面積は GDS 実測で埋める）---
FUNC = [
    ("INV_X1",  "Y=!A;",            "INV"),
    ("INV_X2",  "Y=!A;",            "INV"),
    ("BUF_X1",  "Y=A;",             "NONINV"),
    ("BUF_X2",  "Y=A;",             "NONINV"),
    ("NAND2",   "Y=!(A*B);",        "INV"),
    ("NAND3",   "Y=!(A*B*C);",      "INV"),
    ("NAND4",   "Y=!(A*B*C*D);",    "INV"),
    ("NOR2",    "Y=!(A+B);",        "INV"),
    ("NOR3",    "Y=!(A+B+C);",      "INV"),
    ("NOR4",    "Y=!(A+B+C+D);",    "INV"),
    ("AND2_X1", "Y=A*B;",           "NONINV"),
    ("AND3_X1", "Y=A*B*C;",         "NONINV"),
    ("AND4_X1", "Y=A*B*C*D;",       "NONINV"),
    ("OR2",     "Y=A+B;",           "NONINV"),
    ("OR3",     "Y=A+B+C;",         "NONINV"),
    ("OR4",     "Y=A+B+C+D;",       "NONINV"),
    ("XOR2",    "Y=(A*!B)+(!A*B);", "UNKNOWN"),
    ("XNOR2",   "Y=(A*B)+(!A*!B);", "UNKNOWN"),
    # **S=0 で A、S=1 で B**。ngspice の真理値表チェックで確認（回路は AOI で
    #   n2 = !((A & !S) | (B & S))、Y = !n2）。以前は A/B が逆に書いてあり、
    # genlib マッピングに切り替えた瞬間に MUX の入力が入れ替わるところだった。
    ("MUX2",    "Y=(A*!S)+(B*S);",  "UNKNOWN"),
]


def genlib(rows):
    a = {r["name"]: r["area"] for r in rows}
    out = [f"# TR-1um STDCELL - area from GDS (235,0) abutment box [um^2], row height {ROW_H}um",
           "# generated by scripts/cellinfo.py   (delays are placeholders)",
           "GATE ZERO   0.0    Y=CONST0;",
           "GATE ONE    0.0    Y=CONST1;"]
    for name, fn, ph in FUNC:
        if name not in a:
            continue
        # X2 は駆動 2 倍・入力容量 2 倍として、ABC が X1 と使い分けられるようにする
        #   PIN * <phase> <入力負荷> <max負荷> <立上り固定> <立上り/負荷> <立下り固定> <立下り/負荷>
        load, slope = (2, 0.1) if name.endswith("_X2") else (1, 0.2)
        out.append(f"GATE {name:<9}{a[name]:>8.1f} {fn:<20}"
                   f"PIN * {ph:<8}{load} 999 1 {slope} 1 {slope}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("--genlib")
    ap.add_argument("--areas", help="全セルの実測面積を JSON で書き出す（area_estimate.py 用）")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    rows = scan(args.gds)
    for tag, want in (("--- 標準セル（行に置く / 行高 %.1f）---" % ROW_H, False),
                      ("--- アレイ／マクロ（座標指定で置く）---", True)):
        grp = [r for r in rows if r["array"] is want]
        if not grp:
            continue
        print(tag)
        print(f"{'cell':<12}{'W':>8}{'H':>7}{'area':>10}{'Tr':>6}  {'W(P)':<14}{'W(N)':<7} pins")
        for r in grp:
            wp = "/".join(f"{v:g}" for v in r["WP"]) or "-"
            wn = "/".join(f"{v:g}" for v in r["WN"]) or "-"
            print(f"{r['name']:<12}{r['w']:>8.1f}{r['h']:>7.1f}{r['area']:>10.1f}{r['tr']:>6}  "
                  f"{wp:<14}{wn:<7} {','.join(dict.fromkeys(r['pins']))}")
        print()

    # --- デキャップ: 信号ピンを持たないのにゲートがあるセル ---
    caps = [r for r in rows if r["name"] in NO_SIGNAL_PIN and r["gate_area"] > 0]
    if caps:
        print(f"--- デキャップ（Cox = {COX:.2f} fF/µm², Tox 19.5nm）---")
        for r in caps:
            c = r["gate_area"] * COX          # fF
            print(f"{r['name']:<12}ゲート面積 {r['gate_area']:7.1f} µm²  = {c:6.1f} fF"
                  f"   （セル面積比 {r['gate_area']/r['area']:.0%}"
                  f" / {c/r['area']*1000:.0f} fF per 1000µm²）")
        print()

    if args.check:
        bad = check(rows)
        print("\n=== 規約チェック ===")
        print("\n".join("  ! " + b for b in bad) if bad else "  逸脱なし")

    if args.genlib:
        open(args.genlib, "w").write(genlib(rows))
        print(f"\nwrote {args.genlib}")

    if args.areas:
        doc = {
            "source": args.gds,
            "row_height": ROW_H,
            "poly_pitch": POLY_PITCH,
            "cells": {r["name"]: {"w": r["w"], "h": r["h"], "area": r["area"],
                                  "tr": r["tr"], "array": r["array"]}
                      for r in rows},
        }
        with open(args.areas, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
            f.write("\n")
        print(f"wrote {args.areas}  ({len(rows)} cells, row height {ROW_H} um)")

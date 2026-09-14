#!/usr/bin/env python3
"""td4_mem（16word x 8bit 命令メモリ）を FF 実装 / TLAT アレイで作った場合の面積比較。

FF 実装側は Yosys 合成の実測差分:
    td4_soc_arr（メモリも FF）      out/td4_soc_arr.stat
    td4_soc_arr（td4_mem をBB化）   out/td4_soc_arr_bb.stat
どちらも `sh scripts/syn.sh` が .lib で実セルにマッピングして作る。

アレイ側は **実在するセルの GDS 実測寸法**で積み上げる（推定値ではない）。
セル寸法は `scripts/cell_area.json`（scripts/cellinfo.py --areas が GDS から生成）
から読むので、ライブラリを直せば自動で追従する。

**2026-09-11**: REG8x16 が実際に出来て DRC/LVS クリーンになったので、
積み上げ見積りと並べて**実測値**も出す。見積りの検算になる。
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
AREAS = os.path.join(HERE, "cell_area.json")

if not os.path.exists(AREAS):
    sys.exit(f"{AREAS} が無い。先に\n"
             f"  python3 scripts/cellinfo.py lef/TR-1um_STDCELL.gds "
             f"--genlib scripts/tr1um.genlib --areas scripts/cell_area.json")
_doc = json.load(open(AREAS))
C = _doc["cells"]
ROW_H = _doc["row_height"]                     # 標準セル行高（2026-09-11: 59.4）

W = lambda n: C[n]["w"]
A = lambda n: C[n]["area"]

W_TLAT, W_INV, W_BUF = W("TLAT"), W("INV_X1"), W("BUF_X1")
W_AND2, W_AND4 = W("AND2_X1"), W("AND4_X1")
TLAT_H = C["TLAT"]["h"]
TLAT_PITCH = 54.6                              # TLAT64 での実効行ピッチ（縦に食い込ませる）
A_MUX2, A_DFFE = A("MUX2"), A("MUXDFFRB")
CORE = 1840.0 * 1840.0

WORDS, BITS = 16, 8
NBIT = WORDS * BITS
TILE = 4                                       # ビットセルタイルのビット幅

def _mapped_area(stat, fallback):
    """`.lib` でマッピングした結果の面積を Yosys の stat から読む。

    **数字を手書きしない**（行高変更のとき手書き表だけ取り残された反省）。
    `sh scripts/syn.sh` が out/*.stat を作る。無ければ従来の
    `abc -g simple` + area_estimate.py の概算値で代用し、その旨を出す。
    """
    import re
    p = os.path.join(HERE, os.pardir, "out", stat)
    if os.path.exists(p):
        m = re.search(r"Chip area for module.*?:\s*([\d.]+)", open(p).read())
        if m:
            return float(m.group(1)), True
    return fallback, False


SOC_FF, FF_MAPPED = _mapped_area("td4_soc_arr.stat", 1429429.0)
SOC_BB, BB_MAPPED = _mapped_area("td4_soc_arr_bb.stat", 277488.0)
MEM_FF = SOC_FF - SOC_BB

ARRAY_H = (WORDS - 1) * TLAT_PITCH + TLAT_H    # 878.4 (TLAT64 実測と一致)
W_ARRAY = BITS * W_TLAT                        # 302.4
# アドレスは R/W 共通・デコーダ1個。SEL[i] をそのまま RD[i] に使い、WR[i] = SEL[i] & WE。
#   AND4(SEL=RD) + INV(RDB) + AND2(WR) + INV(WRB) が1行ぶんの帯
W_DECDRV = W_AND4 + W_INV + W_AND2 + W_INV     # = 75.6
H_IO = ROW_H                                   # ライトドライバ + リード受け 1行

# 実際に出来た REG8x16 の外形（lef/TR-1um_STDCELL.gds の 235/0 実測）
REG8X16 = C.get("REG8x16")

if __name__ == "__main__":
    print(f"（セル寸法は {os.path.relpath(AREAS, os.path.join(HERE, os.pardir))} "
          f"= GDS 実測 / 行高 {ROW_H} um）")
    print()
    src = (".lib で実セルにマッピングした実測" if (FF_MAPPED and BB_MAPPED)
           else "abc -g simple + area_estimate.py の概算（syn.sh を流すと実測に変わる）")
    print(f"=== FF 実装（Yosys 合成の差分 / {src}） ===")
    print(f"  td4_soc_arr 全体   {SOC_FF/1e6:.3f} mm2 / うちメモリ以外 {SOC_BB/1e6:.3f} mm2")
    print(f"  命令メモリ {NBIT}bit  {MEM_FF/1e6:.3f} mm2  (全体の {MEM_FF/SOC_FF:.0%})")
    # 内訳。実マッピングでは合成が **DFF + イネーブル用 MUX2** に分けるので
    # MUXDFFRB は出てこない（面積は DFFRB + MUX2 = MUXDFFRB でちょうど同じ）。
    print(f"    内訳の目安: 記憶 {NBIT}bit {NBIT*(A('DFF')+A_MUX2):,.0f}"
          f"（DFF+イネーブルMUX2）+ 16:1 リード MUX x{BITS}bit "
          f"{BITS*(WORDS-1)*A_MUX2:,.0f} um2")
    if FF_MAPPED:
        import re, collections
        p_ = os.path.join(HERE, os.pardir, "out", "td4_soc_arr.stat")
        cs = dict(re.findall(r"^\s+([A-Z][A-Za-z0-9_]*)\s+(\d+)\s*$",
                             open(p_).read(), re.M))
        if cs:
            print("    実マッピング: " + ", ".join(f"{k} x{v}" for k, v in
                  sorted(cs.items(), key=lambda x: -A(x[0]) * int(x[1]))[:5]))
    print()

    print(f"=== TLAT アレイ 積み上げ見積り（{TILE}bit タイル x {BITS//TILE} = {BITS}bit ワード）===")
    blocks = [
        (f"ビットセル {WORDS}行 x {BITS}列 (TLAT {W_TLAT}x{TLAT_H})", W_ARRAY, ARRAY_H),
        ("デコーダ+WLドライバ帯 (AND4/INV/AND2/INV) x16行",          W_DECDRV, ARRAY_H),
        ("カラム I/O 帯 (ライトドライバ x8 + リード受け x16)",         W_ARRAY, H_IO),
    ]
    tot = 0.0
    for n, w, h in blocks:
        a = w * h; tot += a
        print(f"  {n:<44}{w:6.1f} x {h:6.1f} = {a:9,.0f} um2")
    print(f"  {'計':<44}{'':>15} {tot:9,.0f} um2 = {tot/1e6:.3f} mm2   ({MEM_FF/tot:.1f}x 圧縮)")
    mw, mh = W_ARRAY + W_DECDRV, ARRAY_H + H_IO
    print(f"  マクロ外形 {mw:.1f} x {mh:.1f} um = {mw*mh/1e6:.3f} mm2")
    print()

    if REG8X16:
        rw, rh, ra = REG8X16["w"], REG8X16["h"], REG8X16["area"]
        print("=== 実測: 出来上がった REG8x16（DRC/LVS クリーン）===")
        print(f"  外形 {rw:.1f} x {rh:.1f} um = {ra/1e6:.3f} mm2  "
              f"({REG8X16['tr']:,} Tr / {ra/NBIT:,.0f} um2 per bit)")
        print(f"  見積り {mw*mh/1e6:.3f} mm2 に対して {ra/(mw*mh):.2f}x "
              f"(差 {(ra-mw*mh)/1e6:+.3f} mm2)")
        print(f"  FF 実装比 {MEM_FF/ra:.1f}x 小さい")
        print()
        mem_area = ra
    else:
        print("  ※ REG8x16 がまだ GDS に無いので、以下は積み上げ見積りで計算する。")
        mem_area = mw * mh

    print("=== ワードライン RC（M1 が途切れ、セルごとに poly を 9.2 µm 渡る）===")
    COX = 1.77e-3          # F/m2  (Tox 19.5nm, eps_ox 3.9)
    cg = lambda w: w * 1.0 * COX * 1e3   # fF: W[um]*L[um]*1e-12 m2 * COX[F/m2] * 1e15
    per_cell = {"WR": cg(3.4) + cg(7.2), "RD": cg(3.4)}   # TG-W(N)+TG-F(P) / TG-R(N)
    for n, c in per_cell.items():
        print(f"  {n}: ゲート容量 {c:.1f} fF/bit -> {TILE}bit {c*TILE:5.1f} fF / {BITS}bit {c*BITS:5.1f} fF")
    print("  poly 区間 9.2 µm/bit が直列 -> R も C も bit 数に比例 -> **RC は bit 数の 2乗**")
    print(f"  {BITS}bit を1本で引くと {TILE}bit タイルの {(BITS/TILE)**2:.0f} 倍。")
    print("  ※ 実測: ngspice で REG8x16 の読出 23.1->27.7ns / 書込 23.5->26.8ns "
          "(CBL 0->200fF)。4bit 版 +2ns に収まった。")
    print()

    print("=== チップ全体（td4_soc_arr） ===")
    for tag, m, u in (("FF 実装", MEM_FF, 0.6), ("TLAT アレイ (REG8x16)", mem_area, 1.0)):
        total = SOC_BB / 0.6 + m / u
        print(f"  {tag:<22} ロジック {SOC_BB/1e6:.3f} + メモリ {m/1e6:.3f} "
              f"-> {total/1e6:.3f} mm2  (コアの {total/CORE:.0%})  {'OK' if total <= CORE else 'NG'}")

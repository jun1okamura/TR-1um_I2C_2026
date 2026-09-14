#!/usr/bin/env python3
"""TD4 / TR-1um: 素直な STDLIB 合成結果に C4004 設計方針のカスタムセルを適用した面積再見積り。

**【2026-09-11 役目を終えた】このスクリプトは当時の見込みを残すためだけに置いてある。**

  ・面積定数は**行高 62.6 µm 世代**のもの（NAND2=1821.7 / DFFR=6297.6 …）で、
    現ライブラリ（行高 59.4 µm, NAND2=962.3, MUXDFFRB=5773.7）とは別物。
  ・「命令メモリをカスタムアレイ化」「FF を TG 化」は**当時の仮定**だったが、
    実際に REG8x16（399.6 x 933.0 µm / 1,876 Tr）が出来て DRC/LVS/検証まで
    通ったので、仮定ではなく実測で語れるようになった。

  → 今の見積りは以下を使うこと。数字は `scripts/cell_area.json`（GDS 実測）から読むので
     ライブラリを直せば自動で追従する。

       python3 scripts/area_estimate.py     stat.txt --top TOP   # 合成結果の面積換算
       python3 scripts/mem_array_estimate.py                     # メモリ FF vs アレイ

入力は area_estimate.py と同じ Yosys stat（FF数・組合せセル面積）。
カスタムセル面積は reference/05_cell_circuits.md (C4004) の値を使用。
"""
import sys

print("** scripts/area_custom.py は行高 62.6µm 世代の見込み値。"
      "今の見積りは area_estimate.py / mem_array_estimate.py を使うこと。\n",
      file=sys.stderr)

NAND2 = 1821.7
DFFR, MUX2, AND4, INV = 6297.6, 3887.5, 2854.6, 1821.7
DFFE_STD = DFFR + MUX2      # 10,185.1  現状 STDLIB での enable 付き FF
DFFE_TG = 4900.0            # TG 型 22T カスタム
RFCELL = 1100.0             # ラッチ型 10T レジスタファイル 1bit
MINSIZE = 0.68              # W(P) 10.2->5.1um 化による全体スケール
CORE = 1840.0 * 1840.0

def rows(label, ff_std, comb_area, mem_bits=0, mem_extra=0.0, a_std=None):
    """ff_std: STDLIB DFFE で数えた FF 数, comb_area: 組合せセル面積[um2]
    a_std: 素直な STDLIB 合成の実測値（アレイ化で消える論理も含む）"""
    if a_std is None:
        a_std = ff_std * DFFE_STD + comb_area + mem_bits * DFFE_STD
    a_arr = ff_std * DFFE_STD + comb_area + mem_bits * RFCELL + mem_extra
    a_tg = ff_std * DFFE_TG + comb_area + mem_bits * RFCELL + mem_extra
    a_min = a_tg * MINSIZE
    return [(f"{label}: 既存 STDLIB のみ", a_std),
            (f"{label}: + 命令メモリをカスタムアレイ化", a_arr),
            (f"{label}: + FF を TG-DFFE(22T) 化", a_tg),
            (f"{label}: + 最小サイズセル化 (x0.68)", a_min)]

def show(items):
    print(f"{'ステップ':<44}{'素セル面積':>12}{'@util60%':>11}  判定")
    for name, a in items:
        need = a / 0.6
        print(f"{name:<44}{a/1e6:>10.3f} mm2{need/1e6:>9.3f} mm2  {'OK' if need <= CORE else 'NG'}")
    print()

if __name__ == "__main__":
    # --- td4_core (外部ROM): FF 17, 組合せ面積 = 0.328mm2 - 17*DFFE_STD
    core_comb = 327809 - 17 * DFFE_STD
    print("### A) td4_core — CPUコアのみ / 命令メモリは外付け")
    show(rows("core", 17, core_comb))

    # --- td4_soc_rom (マスクROM): FF 13, 0.261mm2
    rom_comb = 258723 - 13 * DFFE_STD
    print("### B) td4_soc_rom — コア + 16x8 マスクROM（固定プログラム）")
    show(rows("mask ROM", 13, rom_comb))

    # --- td4_soc_ff: FF 149 = core17 + ld_addr4 + mem128, 組合せ 536セル
    #     組合せ面積 = 2.691mm2 - 149*DFFE_STD
    soc_comb_all = 2690951 - 149 * DFFE_STD
    # カスタムアレイ化すると 16:1 リードマルチプレクサ x8bit と書込デコーダが
    # アレイ内蔵になるので、その分の組合せ論理を差し引く。
    #   読み出し 16:1 MUX x 8bit ~ 8*15 MUX2、書込デコーダ 4->16 ~ 16 AND4 + 4 INV
    mux_area = 8 * 15 * MUX2
    dec_area = 16 * AND4 + 4 * INV
    array_overhead = dec_area + 8 * 16 * 300.0   # 行デコーダ + カラム読出パス(概算)
    print("### C) td4_soc_ff — コア + 16x8 書き換え可能プログラムメモリ（TinyTapeout 方式）")
    print(f"    (STDLIB 合成: FF 149 / 組合せ 536 セル / 組合せ面積 {soc_comb_all/1e6:.3f} mm2)")
    show(rows("writable mem", 21, soc_comb_all - mux_area - dec_area,
              mem_bits=128, mem_extra=array_overhead, a_std=2690951.0))
    print(f"    参考: STDLIB そのままの合成値 = 2.691 mm2 (@util60% -> 4.485 mm2, NG)")
    print(f"    core available = {CORE/1e6:.3f} mm2")

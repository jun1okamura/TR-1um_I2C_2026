#!/usr/bin/env python3
"""REG<BITS>x16 の LVS 用ソースネットリスト（設計意図側）を生成する。

  usage: python3 scripts/mkspice.py --bits 4        -> spice/REG4x16_src.spi
         python3 scripts/mkspice.py --bits 8        -> spice/REG8x16_src.spi
         python3 scripts/mkspice.py --bits 8 -o ... -> 出力先を明示

ビット幅だけが違う同じ構成（デコーダは 4->16 なので幅に依らず 1 個）。
レイアウトも TLAT の列数と REGBUF の個数が変わるだけ。

**これはレイアウトから抽出したものではなく、設計意図を書き下したもの。**
LVS はこれとレイアウト抽出ネットリストを突き合わせるので、意図と違う配線が
あればここで捕まる。抽出結果をソースにしてしまうと LVS が同語反復になる。

回路構成（TLAT / DEC0 は GDS からの抽出で確認済み、REGBUF / ADDBUF は意図）:

  TLAT  (12T)  D --[TG-W:WR]-- n3 --INV1--> n1 --INV2--> n2 --[TG-F:WRB]-- n3
                                    n1 --INV3--> n4 --[TG-R:RD]-- Q
  DEC0  (16T)  RDB = NAND4(A0,A1,A2,A3)      ← アクティブロー選択がそのまま RDB
               RD  = INV(RDB)
               WR  = NOR2(RDB, WEB)
               WRB = INV(WR)
  REGBUF (8T)  D --INV--INV--> DD            書込（外部 → ビット線）
               Q  --INV--INV--> QQ           読出（ビット線 → 外部）
  ADDBUF (20T) ABk = INV(Ak_pin) / Ak = INV(ABk)  (k=0..3)   平衡型 true/complement
               t   = INV(WEB_pin) / WEB = INV(t)              バッファ2段
"""
from __future__ import annotations
import argparse

# --- REG4x16 のトップピン名（GDS のラベル実測に一致させてある）---
P_ADDR = "ADD[{k}]"      # アドレス
P_WEB  = "WEB"           # 書込イネーブル（アクティブロー）
# ADDBUF が作るバッファ後の内部 WE 線。SPICE は大文字小文字を区別しないので
# トップピン WEB と同じ綴り（web）にすると同一ネットに潰れてしまう。必ず別名にする。
W_INT  = "WEBI"
P_DIN  = "D[{j}]"        # 外部書込データ  -> REGBUF.D
P_DOUT = "Q[{j}]"        # 外部読出データ  <- REGBUF.QQ
VDD, VSS = "vdd", "vss"  # 電源。セル内のラベルも vss に統一済み

# デバイスクラス名は PDK の LVS ランセットに一致させる（libs.tech/klayout/tech/lvs/01_Extract.lvs）
#   extract_devices(mos4("PMOS")) / mos4("NMOS")  -> 4端子 (D G S B)
#   tolerance W = 1% / L = 0%  ... L はぴったり 1.0u でなければならない
MOD_P, MOD_N = "PMOS", "NMOS"

WP_TLAT, WN_TLAT = 7.2, 3.4
WP_DEC,  WN_DEC = 12.2, 4.6
WP_BUF,  WN_BUF = 10.2, 3.4
L = 1.0

WORDS, BITS = 16, 4          # --bits / --words で上書きされる
TOP = "REG4x16"              # = f"REG{BITS}x{WORDS}"
SIZE = "248.4 x 933.0 um"    # アバットメントボックス実測

# レイアウト実測のマクロ寸法（アバットメントボックス 235/0）
SIZES = {"REG4x16": "248.4 x 933.0 um", "REG8x16": "399.6 x 933.0 um"}


def inv(idx, a, y, wp, wn):
    return [f"MP{idx} {y} {a} {VDD} {VDD} {MOD_P} W={wp}u L={L}u",
            f"MN{idx} {y} {a} {VSS} {VSS} {MOD_N} W={wn}u L={L}u"]


def tg(idx, gp, gn, t1, t2, wp, wn):
    """CMOS トランスファゲート: gn=H で導通"""
    return [f"MP{idx} {t1} {gp} {t2} {VDD} {MOD_P} W={wp}u L={L}u",
            f"MN{idx} {t1} {gn} {t2} {VSS} {MOD_N} W={wn}u L={L}u"]


def sub_tlat():
    o = ["* TLAT — 12T ratioless ラッチ ビットセル (37.8 x 59.4 um)",
         ".subckt TLAT WR WRB RD RDB D Q " + VDD + " " + VSS]
    o += tg(0, "WRB", "WR", "D", "n3", WP_TLAT, WN_TLAT)       # 書込 TG
    o += inv(1, "n3", "n1", WP_TLAT, WN_TLAT)                  # INV1
    o += inv(2, "n1", "n2", WP_TLAT, WN_TLAT)                  # INV2
    o += tg(3, "WR", "WRB", "n2", "n3", WP_TLAT, WN_TLAT)      # 帰還 TG (WR=L で閉じる)
    o += inv(4, "n1", "n4", WP_TLAT, WN_TLAT)                  # INV3 = 読出バッファ
    o += tg(5, "RDB", "RD", "n4", "Q", WP_TLAT, WN_TLAT)       # 読出 TG
    o.append(".ends TLAT")
    return o


def dec_row(tag, a, web, wr, wrb, rd, rdb):
    """デコーダ1行ぶん 16Tr。DEC2 にウェル／基板タップが入ったので
    バルクはレール（vdd/vss）と同一ネットでよい（TLAT / REGBUF と同じ）。"""
    n = lambda x: f"{x}_{tag}"
    o = [f"* --- 行 {tag}: RDB=NAND4(A) / RD=INV / WR=NOR2(RDB,WEB) / WRB=INV ---"]
    for i, g in enumerate(a):
        o.append(f"MP{tag}{i} {rdb} {g} {VDD} {VDD} {MOD_P} W={WP_DEC}u L={L}u")
    # 直列スタックは VSS 側から a[3], a[2], a[1], a[0] の順（レイアウト実測）
    chain = [VSS, n("s1"), n("s2"), n("s3"), rdb]
    for i, g in enumerate(reversed(a)):
        o.append(f"MN{tag}{i} {chain[i+1]} {g} {chain[i]} {VSS} {MOD_N} W={WN_DEC}u L={L}u")
    o += [f"MP{tag}A {rd} {rdb} {VDD} {VDD} {MOD_P} W={WP_DEC}u L={L}u",
          f"MN{tag}A {rd} {rdb} {VSS} {VSS} {MOD_N} W={WN_DEC}u L={L}u",
          f"MP{tag}B {n('p1')} {web} {VDD} {VDD} {MOD_P} W={WP_DEC}u L={L}u",
          f"MP{tag}C {wr} {rdb} {n('p1')} {VDD} {MOD_P} W={WP_DEC}u L={L}u",
          f"MN{tag}B {wr} {rdb} {VSS} {VSS} {MOD_N} W={WN_DEC}u L={L}u",
          f"MN{tag}C {wr} {web} {VSS} {VSS} {MOD_N} W={WN_DEC}u L={L}u",
          f"MP{tag}D {wrb} {wr} {VDD} {VDD} {MOD_P} W={WP_DEC}u L={L}u",
          f"MN{tag}D {wrb} {wr} {VSS} {VSS} {MOD_N} W={WN_DEC}u L={L}u"]
    return o


def sub_dec2():
    """DEC2 = デコーダ2行ぶん 32Tr / 18ピン（抽出実測に一致）。

    * アドレスの bit0 だけが2行で異なり、bit1..3 は**同じネットを共有**する。
      → アドレスピンは 8 本ではなく **5 本**（A0, AB0, A1, A2, A3）。
    * DEC2 に N-well タップ (x -1.3..1.3, y 81.8..84.4 → vdd レール) と
      基板タップ (x ±53.3..55.9 → vss レール) が入ったので、
      **バルクはレールと同一ネット**。電源ピンは 2 本。
    * レイアウトでは DEC2 #k = 行 2k（ミラーした DEC0, bit0=0 → AB0）
                            + 行 2k+1（通常の DEC0, bit0=1 → A0）。
    """
    o = ["* DEC2 — デコーダ2行ぶん (114.0 x 86.4 um, 32Tr, 16pin)",
         "*   E = 偶数行 2k（bit0=0 → AB0）/ O = 奇数行 2k+1（bit0=1 → A0）",
         "*   A1..A3 は2行で共有 / タップ内蔵なのでバルク = レール",
         f".subckt DEC2 A0 AB0 A1 A2 A3 WEB"
         f" WRE WRBE RDE RDBE WRO WRBO RDO RDBO {VDD} {VSS}"]
    o += dec_row("E", ["AB0", "A1", "A2", "A3"], "WEB", "WRE", "WRBE", "RDE", "RDBE")
    o += dec_row("O", ["A0", "A1", "A2", "A3"], "WEB", "WRO", "WRBO", "RDO", "RDBO")
    o.append(".ends DEC2")
    return o


def sub_regbuf():
    o = ["* REGBUF — 1bit ぶんのデータバッファ (37.8 x 59.4 um)",
         "*   D -> DD : 書込（外部 → ビット線） / Q -> QQ : 読出（ビット線 → 外部）",
         "*   ピン名は GDS のラベルに合わせる。**D が外側、DD がビット線側。**",
         "*   以前は逆に書いていた（DD が外側）。LVS はネット名ではなく構造で",
         "*   照合するので通ってしまい、名前で読む側だけが食い違っていた。",
         f".subckt REGBUF D DD Q QQ {VDD} {VSS}"]
    o += inv(0, "D", "w1", WP_BUF, WN_BUF)
    o += inv(1, "w1", "DD", WP_BUF, WN_BUF)
    o += inv(2, "Q", "r1", WP_BUF, WN_BUF)
    o += inv(3, "r1", "QQ", WP_BUF, WN_BUF)
    o.append(".ends REGBUF")
    return o


def sub_addbuf():
    pins = " ".join(f"A{k}_PIN" for k in range(4))
    outs = " ".join(f"A{k} AB{k}" for k in range(4))
    o = ["* ADDBUF — アドレス相補生成 + WE バッファ (99.0 x 63.4 um)",
         "*   ABk = INV(Ak_PIN) / Ak = INV(ABk)  -> スキューを INV 1段に固定した平衡型",
         f".subckt ADDBUF {pins} WEB_PIN {outs} WEB {VDD} {VSS}"]
    n = 0
    for k in range(4):
        o += inv(n, f"A{k}_PIN", f"AB{k}", WP_BUF, WN_BUF); n += 1
        o += inv(n, f"AB{k}", f"A{k}", WP_BUF, WN_BUF); n += 1
    o += inv(n, "WEB_PIN", "wt", WP_BUF, WN_BUF); n += 1
    o += inv(n, "wt", "WEB", WP_BUF, WN_BUF)
    o.append(".ends ADDBUF")
    return o


def top():
    apins = " ".join(P_ADDR.format(k=k) for k in range(4))
    dpins = " ".join(P_DIN.format(j=j) for j in range(BITS))
    qpins = " ".join(P_DOUT.format(j=j) for j in range(BITS))
    o = [f"* {TOP} — {BITS}bit x {WORDS}word レジスタファイル ({SIZE})",
         "* ポート名は GDS のピンラベル実測に一致させてある",
         f".subckt {TOP} {apins} {P_WEB} {dpins} {qpins} {VDD} {VSS}", ""]
    ai = " ".join(f"a{k} ab{k}" for k in range(4))
    o.append(f"* アドレス相補生成 + WE バッファ")
    o.append(f"XADDBUF {apins} {P_WEB} {ai} {W_INT} {VDD} {VSS} ADDBUF")
    o.append("")
    o.append(f"* 行デコーダ: DEC2 x{WORDS//2}（1個で2行、bit0 以外のアドレスは2行で共有）")
    for k in range(WORDS // 2):
        e, ow = 2 * k, 2 * k + 1
        hi = " ".join((f"a{b+1}" if (k >> b) & 1 else f"ab{b+1}") for b in range(3))
        o.append(f"XDEC2_{k} a0 ab0 {hi} {W_INT} "
                 f"wr{e} wrb{e} rd{e} rdb{e} wr{ow} wrb{ow} rd{ow} rdb{ow} "
                 f"{VDD} {VSS} DEC2")
    o.append("")
    o.append(f"* ビットセル {WORDS} x {BITS}")
    for i in range(WORDS):
        for j in range(BITS):
            o.append(f"XT{i:02d}_{j} wr{i} wrb{i} rd{i} rdb{i} dl{j} ql{j} {VDD} {VSS} TLAT")
    o.append("")
    o.append(f"* データバッファ x{BITS}   （トップの D[j] -> REGBUF.D、REGBUF.QQ -> トップの Q[j]）")
    for j in range(BITS):
        o.append(f"XBUF{j} {P_DIN.format(j=j)} dl{j} ql{j} {P_DOUT.format(j=j)} {VDD} {VSS} REGBUF")
    o.append(f".ends {TOP}")
    return o


HEADER = """* {TOP} — LVS ソースネットリスト（設計意図）
* generated by scripts/mkspice.py   TR-1um (IP62), L = 1.0 um
*
* 注意:
*  - これはレイアウト抽出ではなく設計意図。LVS はこれと抽出結果を突き合わせる。
*  - トランジスタモデル名 pmos/nmos は PDK の LVS 設定に合わせて読み替えること
*    (TR-1um/libs.tech/klayout/tech/lvs/run.lvs)。
*  - ポート順・ポート名は GDS のピンラベルに合わせること。
"""


def main():
    global WORDS, BITS, TOP, SIZE
    ap = argparse.ArgumentParser()
    ap.add_argument("--bits", type=int, default=4, help="データ幅（既定 4）")
    ap.add_argument("--words", type=int, default=16, help="ワード数（既定 16）")
    ap.add_argument("-o", "--out", default=None)
    a = ap.parse_args()
    BITS, WORDS = a.bits, a.words
    TOP = f"REG{BITS}x{WORDS}"
    SIZE = SIZES.get(TOP, "サイズ未登録")
    if a.out is None:
        a.out = f"spice/{TOP}_src.spi"
    lines = [HEADER.format(TOP=TOP)]
    for f in (sub_tlat, sub_dec2, sub_regbuf, sub_addbuf, top):
        lines += f(); lines.append("")
    txt = "\n".join(lines) + "\n"
    import os
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    open(a.out, "w").write(txt)
    dev = sum(1 for l in txt.splitlines() if l[:1] in "Mm" and " " in l)
    print(f"wrote {a.out}")
    print(f"  サブサーキット: TLAT / DEC2 / REGBUF / ADDBUF / {TOP}")
    print(f"  インスタンス: TLAT x{WORDS*BITS}, DEC2 x{WORDS//2}, REGBUF x{BITS}, ADDBUF x1")
    print(f"  素子数: TLAT 12*{WORDS*BITS} + DEC2 32*{WORDS//2} + REGBUF 8*{BITS} + ADDBUF 20 = "
          f"{12*WORDS*BITS + 16*WORDS + 8*BITS + 20} Tr")


if __name__ == "__main__":
    main()

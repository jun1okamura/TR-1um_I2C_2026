#!/usr/bin/env python3
"""REG4x16 / REG8x16 タイミング確認用 ngspice デッキ生成

  usage: python3 scripts/gen_ngspice_tran.py <CBL_fF> <出力.spi> [モデル] [ネットリスト] [BITS]

IRSIM / Verilog で機能が確認できたので、最後に実デバイスモデル
（TR-1um IP62, BSIM3 level49）で遅延だけを確かめる。時間刻みは 0.1ns。

測るもの（最上位ビット Q[BITS-1] で代表。D は全 1 を書くので全ビット同じ動き）:

  t_write   WEB 立下げ    -> Q 立上り   書込レイテンシ
  t_rd_fall ADD 0 -> 15   -> Q 立下り   読出アクセス時間（1 -> 0）
  t_rd_rise ADD 15 -> 0   -> Q 立上り   読出アクセス時間（0 -> 1）

配線容量はネットリストに入っていないので、**外付けの集中容量として
掃引**する（CBL）。ビット線は M2 878um、アドレス線もデコーダ全高
（821um）を走るので同じ値。ワードラインはビット幅に比例する
（4bit=151um / 8bit=302um）ので CBL x (BITS*37.8/878.4) にしてある。
CBL=0 が IRSIM と同じ条件。

タイムライン（VDD=5V、入力の遷移時間 1ns）:

     0 -  100ns  ADD=0, D=1111, WEB=H     全セル .ic で 0 に初期化
   100 -  200ns  WEB=L                    ワード 0 に 全1 を書く
   200 -  300ns  WEB=H                    そのままワード 0 を読んでいる
   300 -  400ns  ADD=15                   ワード 15（=全0）を読む
   400 -  500ns  ADD=0                    ワード 0（=全1）を読む
"""
from __future__ import annotations
import os, re, sys

NW, NB = 16, 4          # NB は第5引数で上書き（4 or 8）
TOP = "REG4x16"
VDD = 5.0
TR = "1n"          # 入力の遷移時間
T_WEB_FALL = 100
T_WEB_RISE = 200
T_ADD_HI = 300
T_ADD_LO = 400
T_STOP = 500


def body_of(path, name):
    """指定サブサーキットの中身（ポート行と .ends を除く）を返す。"""
    out, inside = [], False
    for ln in open(path, encoding="utf-8"):
        s = ln.rstrip("\n")
        t = s.split()
        if not t:
            continue
        if t[0].lower() == ".subckt" and t[1].upper() == name.upper():
            inside = True
            continue
        if inside and t[0].lower().startswith(".ends"):
            break
        if inside:
            out.append(s)
    return out


def main():
    cbl_ff = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    out = sys.argv[2] if len(sys.argv) > 2 else "spice/REG4x16_tran.spi"
    models = sys.argv[3] if len(sys.argv) > 3 else \
        os.path.join(os.environ.get("TR1UM_PDK",
                     os.path.expanduser("~/TR-1um")),
                     "libs.tech/spice/models/ip62_models")
    netlist = sys.argv[4] if len(sys.argv) > 4 else "spice/REG4x16_ngspice.spi"
    global NB, TOP
    if len(sys.argv) > 5:
        NB = int(sys.argv[5])
    TOP = f"REG{NB}x{NW}"
    MSB = NB - 1

    L = []
    a = L.append
    a(f"* {TOP} タイミング確認 (ngspice, 0.1ns 刻み)  CBL = {cbl_ff:g} fF")
    a("* scripts/gen_ngspice_tran.py が生成。手で編集しないこと。")
    a(f"* 回路は LVS クリーンな spice/{TOP}_src.spi と同一（XM 呼び出し化のみ）。")
    a("*")
    a(f".include {models}")
    a(f".include {netlist}")
    a("")
    a(f".param VDD={VDD}")
    a(f".param CBL={cbl_ff}f")
    wl = NB * 37.8
    a(f".param CWL='CBL*{wl/878.4:.3f}'   $ ワードライン {wl:.1f}um / ビット線 878.4um "
      f"({NB}bit ぶん)")
    a("")
    a("Vvdd vdd 0 {VDD}")
    a("Vvss vss 0 0")
    a("")
    a("* --- 入力 -------------------------------------------------------------")
    a("* D は全ビット 1 固定（ワード 0 に書く値）")
    for j in range(NB):
        a(f"VD{j} D{j} 0 {{VDD}}")
    a("* WEB: アクティブロー。100ns で落として 200ns で戻す")
    a(f"VWEB WEB 0 PWL(0 {{VDD}} {T_WEB_FALL}n {{VDD}} "
      f"{T_WEB_FALL + 1}n 0 {T_WEB_RISE}n 0 {T_WEB_RISE + 1}n {{VDD}})")
    a("* ADD: 0 -> 15 (300ns) -> 0 (400ns)。4 ビット同時に動かす")
    for b in range(4):
        a(f"VADD{b} ADD{b} 0 PWL(0 0 {T_ADD_HI}n 0 {T_ADD_HI + 1}n {{VDD}} "
          f"{T_ADD_LO}n {{VDD}} {T_ADD_LO + 1}n 0)")
    a("")
    a("* --- 配線容量（ネットリストに無いので外付けで掃引する）----------------")
    a("* ビット線 dl/ql: M2 878um  /  アドレス線 a,ab,WEBI: デコーダ全高 821um")
    for j in range(NB):
        a(f"Cdl{j} dl{j} 0 {{CBL}}")
        a(f"Cql{j} ql{j} 0 {{CBL}}")
    for k in range(4):
        a(f"Ca{k} a{k} 0 {{CBL}}")
        a(f"Cab{k} ab{k} 0 {{CBL}}")
    a("Cwebi WEBI 0 {CBL}")
    a("* ワードライン wr/wrb/rd/rdb x16")
    for i in range(NW):
        for s in ("wr", "wrb", "rd", "rdb"):
            a(f"C{s}{i} {s}{i} 0 {{CWL}}")
    a("")
    a(f"* --- {TOP} 本体（サブサーキットの中身をトップに展開）----------------")
    a("* 内部のビット線・ワードラインに容量をぶら下げるため、トップに直に置く。")
    for ln in body_of(netlist, TOP):
        a(ln)
    a("")
    a(f"* --- 初期状態: 全 {NW*NB} ビットセルの保持ノードを 0 に ------------------")
    a("* uic は使わない。.ic で保持ノードだけ決めて DC 動作点を解かせるので、")
    a("* 残りのノードは整合の取れた値から始まる。")
    for i in range(NW):
        for j in range(NB):
            a(f".ic v(XT{i:02d}_{j}.n3)=0")
    a("")
    a("* --- 解析 -------------------------------------------------------------")
    a(f".tran 0.1n {T_STOP}n 0 0.1n     $ 刻み 0.1ns / 最大ステップも 0.1ns")
    a("")
    a("* 書込レイテンシ: WEB 立下げ -> Q 立上り")
    a(f".meas tran t_write TRIG v(WEB) VAL='VDD/2' FALL=1 TARG v(Q{MSB}) VAL='VDD/2' RISE=1")
    a("* 読出アクセス: ADD 0->15 でワード15(0000) を読む -> Q 立下り")
    a(f".meas tran t_rd_fall TRIG v(ADD0) VAL='VDD/2' RISE=1 TARG v(Q{MSB}) VAL='VDD/2' FALL=1")
    a("* 読出アクセス: ADD 15->0 でワード0(1111) を読む -> Q 立上り")
    a(f".meas tran t_rd_rise TRIG v(ADD0) VAL='VDD/2' FALL=1 TARG v(Q{MSB}) VAL='VDD/2' RISE=2")
    a(f"* {NB} ビットぶん（ビット線の位置による差を見る）")
    for j in range(NB):
        a(f".meas tran t_rd_rise_q{j} TRIG v(ADD0) VAL='VDD/2' FALL=1 "
          f"TARG v(Q{j}) VAL='VDD/2' RISE=2")
    a("* 論理値の確認（書けているか / 読めているか）")
    a(f".meas tran vq_w FIND v(Q{MSB}) AT={T_ADD_HI - 10}n      $ ワード0 = 全1 -> H")
    a(f".meas tran vq_0 FIND v(Q{MSB}) AT={T_ADD_LO - 10}n      $ ワード15 = 全0 -> L")
    a(f".meas tran vq_1 FIND v(Q{MSB}) AT={T_STOP - 10}n      $ ワード0 = 全1 -> H")
    a("")
    a(".end")

    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"{out}: {len(L)} 行  (CBL={cbl_ff:g} fF)", file=sys.stderr)


if __name__ == "__main__":
    main()

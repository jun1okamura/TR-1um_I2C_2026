#!/usr/bin/env python3
"""REG4x16 最小 WEB パルス幅測定用 ngspice デッキ生成

  usage: python3 scripts/gen_ngspice_pw.py <CBL_fF> <出力.spi> [モデル] [ネットリスト] [幅リスト] [BITS]

幅リストは "6,7,8,9,10,12" のようにカンマ区切り [ns]（既定 2,4,6,10,16,24）。

WEB=0 の幅をワードごとに変えて 1111 を書き込み、最後に全部読み出して
「どの幅から書けるようになるか」を 1 回の過渡解析で調べる。

  ワード 0..N にそれぞれ違う幅で 1111 を書く
  -> 最後に読み出して 1111 になっているか（0000 のままなら書けていない）

初期状態は .ic で全セル 0。書けていなければ 0000 のまま残る。
"""
from __future__ import annotations
import sys

NB = 4              # 第6引数で上書き（4 or 8）
NW = 16
TOP = "REG4x16"
VDD = 5.0
PWS = [2, 4, 6, 10, 16, 24]     # ns（コマンドラインで上書きできる）
T_SETUP = 40                    # アドレス確定から WEB 立下げまで
T_REC = 60                      # WEB 立上げから次のスロットまで
T_READ = 60                     # 読出 1 回ぶん
EDGE = 1                        # 入力の遷移時間 [ns]


def body_of(path, name):
    out, inside = [], False
    for ln in open(path, encoding="utf-8"):
        s = ln.rstrip("\n"); t = s.split()
        if not t:
            continue
        if t[0].lower() == ".subckt" and t[1].upper() == name.upper():
            inside = True; continue
        if inside and t[0].lower().startswith(".ends"):
            break
        if inside:
            out.append(s)
    return out


def pwl(points, vdd):
    """[(t_ns, 0/1)] -> PWL 文字列（EDGE ns の遷移をつける）"""
    s, prev = [], None
    for t, v in points:
        if prev is None:
            s.append(f"0 {v*vdd:g}")
        else:
            s.append(f"{t}n {prev*vdd:g}")
            s.append(f"{t+EDGE}n {v*vdd:g}")
        prev = v
    return "PWL(" + " ".join(s) + ")"


def main():
    cbl = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
    out = sys.argv[2] if len(sys.argv) > 2 else "spice/REG4x16_pw.spi"
    models = sys.argv[3] if len(sys.argv) > 3 else \
        "~/Dropbox/91_OpenPDK/TR-1um/libs.tech/spice/models/ip62_models"
    netlist = sys.argv[4] if len(sys.argv) > 4 else "spice/REG4x16_ngspice.spi"
    global PWS, NB, TOP
    if len(sys.argv) > 5 and sys.argv[5]:
        PWS = [int(x) for x in sys.argv[5].split(",")]
    if len(sys.argv) > 6:
        NB = int(sys.argv[6])
    TOP = f"REG{NB}x{NW}"
    MSB = NB - 1

    # ---- タイムライン ----------------------------------------------------
    add_pts = [[(0, 0)] for _ in range(4)]
    web_pts = [(0, 1)]
    t = 20
    slots = []
    for i, pw in enumerate(PWS):
        for b in range(4):
            add_pts[b].append((t, (i >> b) & 1))
        web_pts.append((t + T_SETUP, 0))
        web_pts.append((t + T_SETUP + pw, 1))
        slots.append((i, pw, t))
        t += T_SETUP + pw + T_REC
    read_t0 = t + 40
    reads = []
    for i, pw in enumerate(PWS):
        rt = read_t0 + i * T_READ
        for b in range(4):
            add_pts[b].append((rt, (i >> b) & 1))
        reads.append((i, pw, rt + T_READ - 5))
    t_stop = read_t0 + len(PWS) * T_READ + 10

    L = []; a = L.append
    a(f"* {TOP} 最小 WEB パルス幅 (ngspice, 0.1ns 刻み)  CBL = {cbl:g} fF")
    a("* scripts/gen_ngspice_pw.py が生成。手で編集しないこと。")
    a("* ワードごとに WEB=0 の幅を変えて全ビット 1 を書き、最後に読み出して判定する。")
    a("*   " + " / ".join(f"word{i}:{pw}ns" for i, pw in enumerate(PWS)))
    a("*")
    a(f".include {models}")
    a(f".include {netlist}")
    a("")
    a(f".param VDD={VDD}")
    a(f".param CBL={cbl}f")
    a(f".param CWL='CBL*{NB*37.8/878.4:.3f}'   $ ワードライン {NB*37.8:.1f}um / ビット線 878.4um")
    a("")
    a("Vvdd vdd 0 {VDD}")
    a("Vvss vss 0 0")
    for j in range(NB):
        a(f"VD{j} D{j} 0 {{VDD}}")
    a(f"VWEB WEB 0 {pwl(web_pts, VDD)}")
    for b in range(4):
        a(f"VADD{b} ADD{b} 0 {pwl(add_pts[b], VDD)}")
    a("")
    a("* --- 配線容量 ---------------------------------------------------------")
    for j in range(NB):
        a(f"Cdl{j} dl{j} 0 {{CBL}}")
        a(f"Cql{j} ql{j} 0 {{CBL}}")
    for k in range(4):
        a(f"Ca{k} a{k} 0 {{CBL}}")
        a(f"Cab{k} ab{k} 0 {{CBL}}")
    a("Cwebi WEBI 0 {CBL}")
    for i in range(NW):
        for s in ("wr", "wrb", "rd", "rdb"):
            a(f"C{s}{i} {s}{i} 0 {{CWL}}")
    a("")
    a(f"* --- {TOP} 本体 -----------------------------------------------------")
    for ln in body_of(netlist, TOP):
        a(ln)
    a("")
    a("* --- 初期状態: 全セル 0 ----------------------------------------------")
    for i in range(NW):
        for j in range(NB):
            a(f".ic v(XT{i:02d}_{j}.n3)=0")
    a("")
    a(f".tran 0.1n {t_stop}n 0 0.1n")
    a("")
    a("* 読出結果。5V 近ければ書けた、0V 近ければ書けなかった。")
    for i, pw, at in reads:
        a(f".meas tran vq_pw{pw:02d} FIND v(Q{MSB}) AT={at}n   $ word{i}, WEB幅 {pw}ns")
    a("")
    a(".end")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"{out}: {len(L)} 行  CBL={cbl:g}fF  tstop={t_stop}ns", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""IRSIM タイミング測定用コマンドファイル生成

  usage: python3 scripts/gen_irsim_timing.py irsim/reg4x16_timing.cmd

1ns 分解能（stepsize 1）で次を測る:

  M1  読出アクセス時間      ADD 変化 -> Q 確定（0000<->1111 の両方向）
  M2  書込レイテンシ        WEB 立下げ -> Q に反映
  M3  最小 WEB パルス幅     WEB=0 の幅を 1ns ずつ広げ、書けるようになる幅

判定は scripts/check_irsim_timing.py で行う。
"""
from __future__ import annotations
import sys

A_LO, A_HI = 0, 15
NSTEP = 40          # 1ns 刻みで観測する点数
PW_MAX = 24         # WEB パルス幅の掃引上限 [ns]


class G:
    def __init__(self):
        self.o = []
        self.add = self.din = self.web = None

    def c(self, s=""):
        self.o.append("| " + s if s else "|")

    def r(self, s):
        self.o.append(s)

    def set_add(self, a):
        for b in range(4):
            v = (a >> b) & 1
            if self.add is None or ((self.add >> b) & 1) != v:
                self.r(f"{'h' if v else 'l'} ADD{b}")
        self.add = a

    def set_din(self, d):
        for b in range(4):
            v = (d >> b) & 1
            if self.din is None or ((self.din >> b) & 1) != v:
                self.r(f"{'h' if v else 'l'} D{b}")
        self.din = d

    def set_web(self, v):
        if self.web != v:
            self.r(f"{'h' if v else 'l'} WEB")
        self.web = v

    def wr(self, a, d, pw=100):
        self.set_add(a); self.set_din(d)
        self.r("s 100")
        self.set_web(0); self.r(f"s {pw}")
        self.set_web(1); self.r("s 200")


def build():
    g = G()
    g.c("reg4x16_timing.cmd -- REG4x16 タイミング測定（IRSIM, 1ns 分解能）")
    g.c("scripts/gen_irsim_timing.py が生成。手で編集しないこと。")
    g.c("判定: python3 scripts/check_irsim_timing.py irsim/reg4x16_timing_run.log")
    g.r("stepsize 1")
    g.r("settle 10")
    g.r("h Vdd")
    g.r("l Gnd")
    g.set_web(1); g.set_add(0); g.set_din(0)
    g.r("s 200")
    g.r("vector QV Q3 Q2 Q1 Q0")

    g.c()
    g.c("全ワードを 0000 に初期化（電源投入直後の X を解く）")
    for a in range(16):
        g.wr(a, 0)

    #---- M1 読出アクセス時間 ------------------------------------------------
    g.o.append("")
    g.c("=" * 60)
    g.c("M1 読出アクセス時間: ADD 変化 -> Q 確定")
    g.c("=" * 60)
    g.wr(A_HI, 0b1111)
    g.set_add(A_LO); g.r("s 300")
    g.c("MARK M1_RISE  ADD %d(0000) -> %d(1111)" % (A_LO, A_HI))
    g.r("print MARK M1_RISE")
    g.set_add(A_HI)
    for _ in range(NSTEP):
        g.r("s 1"); g.r("d QV")
    g.r("s 300")
    g.c("MARK M1_FALL  ADD %d(1111) -> %d(0000)" % (A_HI, A_LO))
    g.r("print MARK M1_FALL")
    g.set_add(A_LO)
    for _ in range(NSTEP):
        g.r("s 1"); g.r("d QV")
    g.r("s 300")

    #---- M2 書込レイテンシ --------------------------------------------------
    g.o.append("")
    g.c("=" * 60)
    g.c("M2 書込レイテンシ: WEB 立下げ -> Q に反映（同じ番地を読んだまま）")
    g.c("=" * 60)
    g.wr(A_LO, 0b0000)
    g.set_add(A_LO); g.set_din(0b1111); g.r("s 300")
    g.c("MARK M2_WRITE")
    g.r("print MARK M2_WRITE")
    g.set_web(0)
    for _ in range(NSTEP):
        g.r("s 1"); g.r("d QV")
    g.set_web(1); g.r("s 300")

    #---- M3 最小 WEB パルス幅 ----------------------------------------------
    g.o.append("")
    g.c("=" * 60)
    g.c("M3 最小 WEB パルス幅: 幅を 1ns ずつ広げて、書けるようになる幅を探す")
    g.c("=" * 60)
    for pw in range(1, PW_MAX + 1):
        g.c(f"-- pulse width = {pw} ns --")
        g.wr(A_LO, 0b0000)               # 0000 に戻す（十分長いパルスで）
        g.set_din(0b1111)
        g.r("s 200")
        g.c(f"MARK M3_PW {pw}")
        g.r(f"print MARK M3_PW {pw}")
        g.set_web(0)
        g.r(f"s {pw}")
        g.set_web(1)
        g.r("s 300")
        g.r("d QV")

    g.o.append("")
    g.c("end of reg4x16_timing.cmd")
    return g


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "irsim/reg4x16_timing.cmd"
    g = build()
    open(out, "w", encoding="utf-8").write("\n".join(g.o) + "\n")
    print(f"{out}: {len(g.o)} 行", file=sys.stderr)

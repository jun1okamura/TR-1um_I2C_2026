#!/usr/bin/env python3
"""ngspice の .meas 結果をまとめて表にする

  usage: python3 scripts/check_ngspice.py tran <log> [<log> ...]
         python3 scripts/check_ngspice.py pw   <log> [<log> ...]

`tran` は spice/REG4x16_tran.spi、`pw` は spice/REG4x16_pw.spi のログを読む。
ログにはデッキのコメント（日本語）がそのまま出るので、
バイナリ扱いにならないよう errors="replace" で読む。
"""
from __future__ import annotations
import re, sys

RE_MEAS = re.compile(r"^\s*(\w+)\s*=\s*([-\d.eE+]+)")
RE_CBL = re.compile(r"CBL\s*=\s*([\d.]+)\s*fF")


def read(path):
    """ログから .meas の結果を読む。CBL はログに出ないことがあるので
    ファイル名（tran_100.log など）からも拾う。"""
    vals, cbl = {}, None
    m = re.search(r"_(\d+)\.log$", path)
    if m:
        cbl = float(m.group(1))
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = RE_CBL.search(ln)
        if m and cbl is None:
            cbl = float(m.group(1))
        m = RE_MEAS.match(ln)
        if m:
            try:
                vals[m.group(1)] = float(m.group(2))
            except ValueError:
                pass
    return cbl, vals


def bits_of(vals):
    """.meas の t_rd_rise_q<j> の個数からビット幅を割り出す。"""
    n = sum(1 for k in vals if k.startswith("t_rd_rise_q"))
    return n if n else 4


def do_tran(logs):
    nb = 4
    for p in logs:
        _, v = read(p)
        nb = max(nb, bits_of(v))
    print("=" * 70)
    print(f" REG{nb}x16  タイミング確認（ngspice, TR-1um IP62 BSIM3, 0.1ns 刻み）")
    print("=" * 70)
    print(f"  {'配線容量':>10}  {'書込レイテンシ':>14}  {'読出 1->0':>10}  {'読出 0->1':>10}   論理")
    print(f"  {'CBL [fF]':>10}  {'WEB↓→Q':>14}  {'ADD→Q':>10}  {'ADD→Q':>10}")
    print("-" * 70)
    rows = []
    for p in logs:
        cbl, v = read(p)
        cbl = 0.0 if cbl is None else cbl
        if "t_write" not in v:
            print(f"  {p}: .meas の結果が無い（収束していない可能性）")
            continue
        ok = (v.get("vq_w", 0) > 4.0 and v.get("vq_0", 5) < 1.0 and v.get("vq_1", 0) > 4.0)
        rows.append((cbl, v))
        print(f"  {cbl:10.0f}  {v['t_write']*1e9:11.2f} ns  "
              f"{v['t_rd_fall']*1e9:7.2f} ns  {v['t_rd_rise']*1e9:7.2f} ns   "
              f"{'OK' if ok else '**NG**'}")
    if len(rows) >= 2:
        (c0, v0), (c1, v1) = rows[0], rows[-1]
        if c1 != c0:
            print("-" * 70)
            for k, lbl in (("t_write", "書込レイテンシ"), ("t_rd_fall", "読出 1->0"),
                           ("t_rd_rise", "読出 0->1")):
                sl = (v1[k] - v0[k]) / (c1 - c0) * 1e12
                print(f"  {lbl:16} 配線容量に対する傾き {sl:5.1f} ps/fF")
    print("-" * 70)
    print("  論理 OK = 書いた値が読めている（全1 / 全0 / 全1）")
    print("  ※ 配線容量はネットリストに含まれないので、集中容量として外付けした値。")
    print("     ビット線 M2 878um・アドレス線 821um で 100〜200fF が現実的な範囲。")


def do_pw(logs):
    print("=" * 70)
    print(" 最小 WEB パルス幅（ngspice, 0.1ns 刻み）")
    print("=" * 70)
    for p in logs:
        cbl, v = read(p)
        cbl = 0.0 if cbl is None else cbl
        items = sorted((int(k[5:]), val) for k, val in v.items() if k.startswith("vq_pw"))
        if not items:
            print(f"  {p}: 結果が無い")
            continue
        print(f"  CBL = {cbl:g} fF")
        print("     WEB 幅 [ns] : " + "  ".join(f"{pw:5d}" for pw, _ in items))
        print("     読出 Q [V]  : " + "  ".join(f"{val:5.2f}" for _, val in items))
        print("     判定        : " + "  ".join(
            f"{'  書けた' if val > 4.0 else ('  書けず' if val < 1.0 else '   中間'):>5}"
            for _, val in items))
        okpw = [pw for pw, val in items if val > 4.0]
        print(f"     -> 確実に書ける最小幅: "
              f"{min(okpw) if okpw else '(掃引範囲では書けなかった)'} ns"
              "   （50% 点で測ったパルス幅）")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    (do_tran if sys.argv[1] == "tran" else do_pw)(sys.argv[2:])

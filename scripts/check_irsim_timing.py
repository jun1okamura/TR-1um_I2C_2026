#!/usr/bin/env python3
"""IRSIM タイミング測定ログの読み取り

  usage: python3 scripts/check_irsim_timing.py irsim/reg4x16_timing_run.log

`scripts/gen_irsim_timing.py` が生成した .cmd の出力から次を読み取る:

  M1  読出アクセス時間    ADD 変化から Q が確定するまで（立上り／立下り）
  M2  書込レイテンシ      WEB 立下げから Q に反映されるまで
  M3  最小 WEB パルス幅   書けるようになる WEB=0 の幅
"""
from __future__ import annotations
import re, sys

RE_MARK = re.compile(r"MARK\s+(\S+)(?:\s+(\d+))?")
RE_QV = re.compile(r"\bQV=([01xX]{4})")
RE_TIME = re.compile(r"time\s*=\s*([\d.]+)ns")


def scan(path):
    """[(種別, ラベル, 相対時刻[ns], 値)] を返す。"""
    events, mark, t0, t = [], None, None, 0.0
    for ln in open(path, encoding="utf-8", errors="replace"):
        for m in RE_TIME.finditer(ln):
            t = float(m.group(1))
        mm = RE_MARK.search(ln)
        if mm:
            mark = (mm.group(1), mm.group(2))
            t0 = t
            continue
        q = RE_QV.search(ln)
        if q and mark:
            events.append((mark[0], mark[1], t - t0, q.group(1)))
    return events


def first_reach(events, label, target):
    """label 区間で値が target になった最初の相対時刻。"""
    for lab, _arg, dt, v in events:
        if lab == label and v == target:
            return dt
    return None


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    ev = scan(sys.argv[1])
    if not ev:
        sys.exit("MARK が見つからない。.cmd かログを確認すること。")

    print("=" * 62)
    print(" REG4x16  タイミング測定（IRSIM, TR-1um.prm, 1ns 分解能）")
    print("=" * 62)

    tr = first_reach(ev, "M1_RISE", "1111")
    tf = first_reach(ev, "M1_FALL", "0000")
    print("  M1 読出アクセス時間  ADD 変化 -> Q 確定")
    print(f"       0000 -> 1111 : {tr if tr is not None else '(未確定)'} ns")
    print(f"       1111 -> 0000 : {tf if tf is not None else '(未確定)'} ns")
    if tr is not None and tf is not None:
        print(f"       ワースト      : {max(tr, tf)} ns")

    tw = first_reach(ev, "M2_WRITE", "1111")
    print()
    print("  M2 書込レイテンシ    WEB 立下げ -> Q に反映")
    print(f"       {tw if tw is not None else '(未確定)'} ns")

    print()
    print("  M3 最小 WEB パルス幅（WEB=0 の幅を 1ns ずつ広げる）")
    ok = []
    for lab, arg, _dt, v in ev:
        if lab == "M3_PW" and arg is not None:
            mark = "書けた" if v == "1111" else ("書けず" if v == "0000" else f"X ({v})")
            ok.append((int(arg), v))
    minw = None
    line = []
    for pw, v in ok:
        line.append(f"{pw}:{'O' if v=='1111' else ('-' if v=='0000' else 'x')}")
        if v == "1111" and minw is None:
            minw = pw
    print("       " + "  ".join(line))
    print(f"       -> 書き込めるようになる最小パルス幅: "
          f"{minw if minw else '(掃引範囲では書けなかった)'} ns")
    print("       （O = 書けた / - = 書けなかった / x = X になった）")


if __name__ == "__main__":
    main()

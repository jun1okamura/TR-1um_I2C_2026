#!/usr/bin/env python3
"""IRSIM の実行ログから合否を集計する

  usage: python3 scripts/check_irsim_log.py irsim/reg4x16_run.log [-v]

IRSIM の .cmd 言語には条件分岐も算術も無いので、テストベンチのように
自前で pass/fail を数えられない。`scripts/gen_irsim_cmd.py` が生成した .cmd は
読出のたびに

    print CHECK tag=<名前> add=<bbbb> exp=<bbbb>   ← 何を期待しているか
    assert QV <bbbb>                               ← IRSIM 自身の判定
    d AV QV                                        ← 実際の番地と値

の 3 行を出すので、ログだけで完結して集計できる（期待値ファイル不要）。

判定するもの:
  ・読み出した値が期待どおりか（`x` / `X` はその場で FAIL）
  ・そのとき表示されている番地が期待どおりか（ずれ = ログの対応崩れ）
  ・IRSIM 自身の assertion failed が出ていないか

I1* は「参考」なので合否には数えず、結果だけ報告する。
"""
from __future__ import annotations
import re, sys

RE_CHECK = re.compile(r"CHECK\s+tag=(\S+)\s+add=([01]+)\s+exp=([01]+)")
RE_VAL = re.compile(r"\b(AV|QV)=([01xX]+)")
RE_ASSERT = re.compile(r"assertion failed")


def parse(path):
    """[(tag, add, exp, av, qv)] を出現順に返す。"""
    out, cur, av = [], None, None
    nassert = 0
    for ln in open(path, encoding="utf-8", errors="replace"):
        if RE_ASSERT.search(ln):
            nassert += 1
        m = RE_CHECK.search(ln)
        if m:
            cur, av = (m.group(1), m.group(2), m.group(3)), None
            continue
        for name, val in RE_VAL.findall(ln):
            if name == "AV":
                av = val
            elif cur is not None:
                out.append((*cur, av, val))
                cur, av = None, None
    return out, nassert


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    verbose = "-v" in sys.argv[2:]

    rows, nassert = parse(path)
    nb = len(rows[0][2]) if rows else 4

    print("=" * 62)
    print(f" REG{nb}x16  IRSIM スイッチレベル検証   log = {path}")
    print("=" * 62)
    if not rows:
        print(" ** CHECK マーカーが 1 つも見つからない。")
        print("    .cmd が古い（print CHECK 行が無い）か、IRSIM が起動していない。")
        sys.exit(1)


    npass = nfail = 0
    per_tag, info = {}, {}
    shown = 0
    for i, (tag, add, exp, av, qv) in enumerate(rows):
        is_info = tag.startswith("I1")
        ok = (qv == exp) and (av is None or av == add)
        c = (info if is_info else per_tag).setdefault(tag, [0, 0])
        c[0 if ok else 1] += 1
        if not is_info:
            if ok:
                npass += 1
            else:
                nfail += 1
        if not ok and (shown < 20 or verbose):
            shown += 1
            extra = f"  (ログの番地 {av})" if av not in (None, add) else ""
            print(f"  ** {'DIFF' if is_info else 'FAIL'} #{i} {tag}: "
                  f"ADD={add} 期待 {exp} 実際 {qv}{extra}")
        elif verbose and ok:
            print(f"     ok #{i} {tag}: ADD={add} {qv}")

    print("-" * 62)
    for tag, (p, f) in per_tag.items():
        print(f"  {tag:14}  PASS {p:4d}   FAIL {f:4d}")
    print("-" * 62)
    print(f"  合計  PASS {npass} / FAIL {nfail}   （読出 {len(rows)} 回）")
    print(f"  IRSIM 自身の assertion failed: {nassert} 件")
    if nfail == 0 and nassert == 0:
        print(f"  結果: 全項目 PASS — 16 word x {nb} bit すべて正しくアクセスできる")
    else:
        print("  結果: 不一致あり")

    nx = sum(1 for r in rows if "x" in r[4].lower())
    if nx:
        print(f"  ** 読み出しに X が {nx} 回混じっている")

    if info:
        print()
        print("  [参考] アドレスと WEB のタイミング（合否には数えない）")
        note = {"I1a_timing": "アドレスと WEB を同時に動かす -> 1 ワードだけ書換",
                "I1b_timing": "WEB=0 のままアドレスを動かす -> 通過した 2 ワードが書換"}
        for tag, (p, f) in info.items():
            mark = "予想どおり" if f == 0 else "予想と違う"
            print(f"  {tag:14}  {mark}（一致 {p} / 相違 {f}）  {note.get(tag,'')}")

    sys.exit(1 if (nfail or nassert) else 0)


if __name__ == "__main__":
    main()

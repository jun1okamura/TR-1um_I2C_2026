#!/usr/bin/env python3
"""insert_bufth.py -- 外部入力を `BUFTH`（シュミットトリガ）で一度受ける。

  usage: python3 scripts/insert_bufth.py IN.v OUT.v            # 全入力ポート
         python3 scripts/insert_bufth.py IN.v OUT.v --nets clk,rst_n
         python3 scripts/insert_bufth.py IN.v OUT.v --list      # 対象を出すだけ

    clk ──▶ BUFTH u_bufth_clk ──▶ clk_buf ──▶ 内部の全シンク

なぜ要るか: `OSS_ESD_5V_DIO` には**入力バッファが入っていない**。`PAD` の
上辺スタブがそのままコアの標準セル入力につながる。ところが `PAD` の容量は
**4.8 pF**（パッド金属 + W=500 µm の ESD 素子）あるので、外部ドライバが弱いと
立上りが鈍る。鈍った波形を各段に配ると貫通電流が増えるし、`CLK` や `RSTN` に
チャタリングが乗ると誤動作する。

`BUFTH` は**シュミットトリガ**で、立上り 3.43 V / 立下り 1.44 V
（ヒステリシス 2.00 V、`lef/tr1um_typ_5v0_25c.lib` の `BUFTH_in`）。
`reference/05_pin_io_plan.md` §2 が「シュミット入力は無い。必要なら自作」と
書いていたのは誤りで、**ライブラリに最初から入っている**。

`TR-1um_SCLK_SPI/scripts/insert_bufth.py` の移植。あちらとの違いは
**バスポートに対応した**こと（TD4 の `d[3:0]`）。バスはビットごとに 1 個ずつ
`BUFTH` を入れ、`wire [3:0] d_buf;` を宣言する。

ポート宣言と `module` ヘッダは書き換えない。書き換えるのは**内部の使用箇所
だけ**なので、トップのポート名・順序・方向は変わらない。
"""
from __future__ import annotations
import argparse, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "pnr"))
import netlist_util as nu                                   # noqa: E402

CELL = "BUFTH"
SUFFIX = "_buf"
PREFIX = "u_bufth_"
IN_PIN, OUT_PIN = "A", "Y"

DECL = re.compile(r"^\s*(module|input|output|inout|wire|reg)\b")


def inputs(src):
    """[(名前, hi, lo)] を宣言から。スカラーは hi=lo=None。"""
    out = []
    for m in re.finditer(r"^\s*input\s+(?:wire\s+)?(?:\[(\d+):(\d+)\]\s+)?"
                         r"(\\?\S+?)\s*;", src, re.M):
        hi, lo, nm = m.group(1), m.group(2), m.group(3)
        out.append((nm, int(hi) if hi else None, int(lo) if lo else None))
    return out


ESC = re.compile(r"\\\S+")


def rename_internal(src, old, new):
    """宣言行と module ヘッダ以外で、単語としての `old` を `new` にする。
    バスは `d` → `d_buf` と書き換えるだけで `d[0]` が `d_buf[0]` になる。

    **エスケープ識別子は触らない。** Verilog の `\\u_core.rst_n ` は空白までが
    1 つの識別子で、中の `rst_n` は別物。単純な `\\brst_n\\b` は `.` と空白の
    両方を単語境界とみなすのでここに食いつき、`\\u_core.rst_n_buf` という
    **宣言されていない別ネット**を作ってしまう（元のネットは駆動されなくなる）。
    置換の前に伏せておく。
    """
    pat = re.compile(r"\b%s\b" % re.escape(old))
    out = []
    for ln in src.split("\n"):
        if DECL.match(ln):
            out.append(ln)
            continue
        hidden = []

        def mask(m):
            hidden.append(m.group(0))
            return f"\x00{len(hidden)-1}\x00"

        ln = ESC.sub(mask, ln)
        ln = pat.sub(new, ln)
        for i, h in enumerate(hidden):
            ln = ln.replace(f"\x00{i}\x00", h)
        out.append(ln)
    return "\n".join(out)


def insert(src, ports, cell=CELL, suffix=SUFFIX, prefix=PREFIX):
    wires, blocks, done = [], [], []
    for nm, hi, lo in ports:
        if not re.search(r"\b%s\b" % re.escape(nm), src):
            print(f"  !! '{nm}' がネットリストに無い — 飛ばす")
            continue
        buf = nm + suffix
        src = rename_internal(src, nm, buf)
        if hi is None:
            wires.append(f"  wire {buf};")
            blocks.append(f"  {cell} {prefix}{nm} "
                          f"(.{IN_PIN}({nm}), .{OUT_PIN}({buf}));")
            done.append(nm)
        else:
            wires.append(f"  wire [{hi}:{lo}] {buf};")
            for i in range(lo, hi + 1):
                blocks.append(f"  {cell} {prefix}{nm}_{i} "
                              f"(.{IN_PIN}({nm}[{i}]), .{OUT_PIN}({buf}[{i}]));")
                done.append(f"{nm}[{i}]")
        print(f"  {cell} on {nm}{'' if hi is None else f'[{hi}:{lo}]'} → {buf}")

    m = re.search(r"^module\s+[^;]*;\s*$", src, re.M)
    if not m:
        raise SystemExit("module ヘッダが見つからない")
    src = (src[:m.end() + 1]
           + f"  // --- 外部入力のシュミット受け（scripts/insert_bufth.py が生成）---\n"
           + "\n".join(wires) + "\n" + src[m.end() + 1:])
    src = nu.add_instances(
        src, [f"  // --- 外部入力 {len(done)} 本を {cell} で受ける ---"] + blocks)
    return src, done


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output", nargs="?")
    ap.add_argument("--nets", default=None,
                    help="対象の入力ポート（カンマ区切り）。既定は全入力")
    ap.add_argument("--skip", default="",
                    help="全入力のうち除くもの（カンマ区切り）")
    ap.add_argument("--cell", default=CELL)
    ap.add_argument("--suffix", default=SUFFIX)
    ap.add_argument("--list", action="store_true", help="対象を出して終わる")
    a = ap.parse_args()

    src = open(a.input).read()
    if f"{a.cell} " in src:
        raise SystemExit(f"{a.input} には既に {a.cell} が入っている。"
                         f"二重に挿さないよう合成からやり直すこと")
    allin = inputs(src)
    skip = {s.strip() for s in a.skip.split(",") if s.strip()}
    if a.nets:
        want = [n.strip() for n in a.nets.split(",") if n.strip()]
        by = {n: (n, h, l) for n, h, l in allin}
        miss = [n for n in want if n not in by]
        if miss:
            raise SystemExit(f"入力ポートに無い: {miss}（ある: {[n for n,_,_ in allin]}）")
        ports = [by[n] for n in want]
    else:
        ports = [p for p in allin if p[0] not in skip]

    print(f"入力ポート {len(allin)} 本、対象 {len(ports)} 本"
          + (f"（除外 {sorted(skip)}）" if skip else ""))
    if a.list:
        for n, h, l in ports:
            print(f"  {n}{'' if h is None else f'[{h}:{l}]'}")
        return 0
    if not a.output:
        raise SystemExit("出力ファイルを指定すること")

    dst, done = insert(src, ports, cell=a.cell, suffix=a.suffix)

    # --- 壊していないことの確認 ---
    bad = []
    # (1) エスケープ識別子は 1 つも増減・改名されていないこと
    e0, e1 = sorted(set(ESC.findall(src))), sorted(set(ESC.findall(dst)))
    if e0 != e1:
        bad.append(f"エスケープ識別子が変わった: "
                   f"消えた {sorted(set(e0)-set(e1))[:4]} / "
                   f"増えた {sorted(set(e1)-set(e0))[:4]}")
    # (2) ポート宣言（module ヘッダ + input/output/inout）が不変であること
    d = lambda s: [l for l in s.split("\n")
                   if re.match(r"^\s*(module|input|output|inout)\b", l)]
    if d(src) != d(dst):
        bad.append("ポート宣言が変わった")
    # (3) 元のトップ入力を、BUFTH 以外のセルが直接受けていないこと
    strip = re.sub(r"^\s*BUFTH\s.*$", "", dst, flags=re.M)
    for nm, hi, lo in ports:
        pat = (rf"\.\w+\(\s*{re.escape(nm)}\s*\)" if hi is None
               else rf"\.\w+\(\s*{re.escape(nm)}\[\d+\]\s*\)")
        hit = re.findall(pat, strip)
        if hit:
            bad.append(f"'{nm}' を {a.cell} 以外が直接受けている: {hit[:3]}")
    if bad:
        raise SystemExit("insert_bufth: 壊れている。書かない\n  - " + "\n  - ".join(bad))

    open(a.output, "w").write(dst)
    w = 32.4 if a.cell == CELL else 0.0
    print(f"wrote {a.output}")
    print(f"  {a.cell} {len(done)} 個を挿入"
          + (f"（{len(done)*w:.1f} um / {len(done)*w*59.4:,.0f} um2）" if w else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

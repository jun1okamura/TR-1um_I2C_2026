#!/usr/bin/env python3
"""KLayout の抽出ネットリスト `lef/extracted/<CELL>.extracted` を
ngspice でそのまま使える形に直す。

  usage: python3 loadext.py <extracted ディレクトリ> -o <出力ディレクトリ>

KLayout 版はこちらの簡易抽出器より**素性がよい**:

  ・DRC/LVS クリーンな状態の正規の抽出結果。
  ・**AS / AD / PS / PD（拡散の実面積と周長）が入っている。**
    PDK の PMOS/NMOS サブサーキットは既定で `AS='w*sdwidth'` と概算するが、
    実レイアウトの値で上書きできるので、接合容量が正確になる。
  ・すでに `XM...` 呼び出し形式（PDK のサブサーキットモデルに合う）。

直すのは 2 点だけ。回路は一切変えない。

  1. 無名ネットの `\\$6` → `n6`。`$` は ngspice で行末コメントの開始記号なので、
     そのまま食わせるとネット名が途中で切れる。
  2. インスタンス名の `XM$1` → `XM1`、サブサーキット呼び出しの `X$4` → `X4`。同じ理由。
     残った `$` は `_` に落とす（`vss$1` → `vss_1`）。
  3. `M$1 ...` → `XM1 ...`。PDK の PMOS/NMOS は `.model` ではなく
     **サブサーキット**なので、素の `M` カードでは ngspice が
     「model PMOS が無い」で落ちる。KLayout の SPICE ライタは MOS4 を
     `M` で書くことがある（`--flat` や素の NetlistSpiceWriter のとき）。
"""
from __future__ import annotations
import argparse, os, re, sys

RE_NET = re.compile(r"\\\$(\w+)")
RE_INST = re.compile(r"^(XM)\$(\w+)")
RE_XINST = re.compile(r"^X\$(\w+)")   # サブサーキット呼び出し X$4 -> X4
RE_MOS = re.compile(r"^M\$?(\w+)(\s)")


def convert(path):
    """[本文の行] を返す。コメントは落とさない（由来が追えるように）。"""
    out = []
    for ln in open(path, encoding="utf-8"):
        s = ln.rstrip("\n")
        s = RE_NET.sub(r"n\1", s)              # \$6 -> n6
        s = RE_INST.sub(r"\1\2", s)            # XM$1 -> XM1
        s = RE_XINST.sub(r"X\1", s)             # X$4 -> X4
        if not s.lstrip().startswith("*"):
            # 残った `$` を潰す。`vss$1`（1 つのセルに同名のネットが 2 本ある
            # ときに KLayout が付ける区別子）がそのままだと ngspice は `$` から
            # 先をコメントとして捨て、**2 本が 1 本に潰れて .subckt 行に
            # 同名ポートが 2 つ並ぶ**。DEC0 は電源レールをアバットで繋ぐ設計で
            # 単体抽出だと必ずこれが出る。
            s = s.replace("$", "_")
        s = RE_MOS.sub(r"XM\1\2", s)           # M$1 -> XM1（PDK の MOS は subckt）
        out.append(s)
    return out


def ports_of_lines(lines):
    for s in lines:
        t = s.split()
        if t and t[0].lower() == ".subckt":
            return t[2:]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    n = 0
    print(f"{'cell':<12}{'Tr':>4}  ports")
    for f in sorted(os.listdir(a.src)):
        if not f.endswith(".extracted"):
            continue
        cell = f[:-len(".extracted")]
        lines = convert(f"{a.src}/{f}")
        open(f"{a.out}/{cell}.spi", "w").write("\n".join(lines) + "\n")
        ntr = sum(1 for s in lines if re.match(r"^XM", s))
        print(f"{cell:<12}{ntr:>4}  {' '.join(ports_of_lines(lines))}")
        n += 1
    print(f"\n{n} セルを {a.out} に書いた")


if __name__ == "__main__":
    main()

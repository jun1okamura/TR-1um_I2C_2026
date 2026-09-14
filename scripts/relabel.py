#!/usr/bin/env python3
"""GDS のテキストラベルを一括で改名する。

  usage: python3 scripts/relabel.py <gds> gnd=vss [old=new ...] [-o out.gds] [-n]

電源の綴りが `gnd` と `vss` に割れていたのを揃えるために作った。
標準セル 43 個が `gnd`、`DEC0`/`DEC2`/`DEC16` の 3 個が `vss`、
`REG4x16`/`REG8x16` はトップが `vss` で子が `gnd` という状態だった。
**P&R のルータは 1 つの名前しか追えない**ので揃える必要がある。

やること:
  * 全セル・全ラベルレイヤ ((48,0) (48,1) (49,0) (49,1)) のテキストを見る
  * 完全一致したものだけ差し替える（部分一致はしない）
  * 改名後に**同じセルの同じレイヤで同名ラベルが増えていないか**を数えて出す
    （衝突すれば抽出でネットが潰れる）

改名しても回路は変わらないが、`lef/extracted/*.extracted` や
`lef/simulation/*.spice` は GDS から作った別ファイルなので、
そちらも同じ置換をかけること（`lef/README.md` に手順）。
"""
from __future__ import annotations
import argparse, collections, sys
import klayout.db as db

LBL = ((48, 0), (48, 1), (49, 0), (49, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("rules", nargs="+", help="old=new")
    ap.add_argument("-o", "--out", default=None, help="既定は上書き")
    ap.add_argument("-n", "--dry-run", action="store_true")
    a = ap.parse_args()

    rules = {}
    for r in a.rules:
        if "=" not in r:
            sys.exit(f"規則は old=new の形で: {r}")
        o, n = r.split("=", 1)
        rules[o] = n

    ly = db.Layout(); ly.read(a.gds)
    hit = collections.Counter()
    per_cell = collections.Counter()
    for c in ly.each_cell():
        for ld in LBL:
            li = ly.layer(*ld)
            for sh in c.shapes(li).each():
                if not sh.is_text():
                    continue
                s = sh.text.string
                if s in rules:
                    hit[(s, rules[s])] += 1
                    per_cell[c.name] += 1
                    if not a.dry_run:
                        t = sh.text
                        t.string = rules[s]
                        sh.text = t

    for (o, n), k in sorted(hit.items()):
        print(f"  '{o}' -> '{n}'  {k} 枚")
    print(f"  対象セル {len(per_cell)} 個")

    # 衝突検査: 同じセル・同じレイヤ・同じ座標に同名が 2 枚できていないか
    dup = 0
    for c in ly.each_cell():
        for ld in LBL:
            seen = collections.Counter()
            for sh in c.shapes(ly.layer(*ld)).each():
                if sh.is_text():
                    seen[(sh.text.string, sh.text.x, sh.text.y)] += 1
            for k, v in seen.items():
                if v > 1:
                    print(f"  ! {c.name} ({ld[0]},{ld[1]}) '{k[0]}' が同じ座標に {v} 枚")
                    dup += 1
    if dup:
        print(f"  ** 重複 {dup} 件。抽出でネットが潰れる恐れ")

    if a.dry_run:
        print("（--dry-run なので書いていない）")
        return 0
    out = a.out or a.gds
    ly.write(out)
    print(f"wrote {out}")
    return 1 if dup else 0


if __name__ == "__main__":
    sys.exit(main())

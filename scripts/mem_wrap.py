#!/usr/bin/env python3
"""マップ後ネットリストの `td4_mem` を `REG8x16` マクロ + グルーに置き換える。

  usage: python3 scripts/mem_wrap.py out/td4_soc_arr_bb.v -o out/td4_soc_arr_pnr.v

なぜ要るか: RTL の `td4_mem` と実物の `REG8x16` は**ピン互換ではない**。

  module td4_mem (input clk, input [3:0] raddr, output [7:0] rdata,
                  input [3:0] waddr, input [7:0] wdata, input we);
      同期ライト（posedge clk）、リード／ライトでアドレスが別

  .subckt REG8x16 ADD[3:0] WEB D[7:0] Q[7:0]
      アドレス 1 本、WEB=0 の間だけ素通し（レベルセンス）、
      **WEB の立上りでラッチ**

リード／ライトは同時に起きない（EXEC=1 のとき書かない）ので 1 ポート時分割で
よい —— `reference/07_memory_array.md` §3 の前提そのもの。入れるグルーは:

  ADD[i] = we ? waddr[i] : raddr[i]      MUX2 x4   Y = (A*!S)+(B*S)
  WEB    = clk | ~we                     INV_X1 + OR2
  D      = wdata / rdata = Q             直結

`WEB = clk | ~we` にすると**書込み窓が clk の低期間**になり、`WEB` の立上り =
`clk` の posedge でラッチされる。RTL の `always @(posedge clk)` と一致し、
データには半サイクルぶんのセットアップが取れる。
（`WEB = ~(clk & we)` だと clk の高期間に書いて **posedge 直後に変わる
  waddr/wdata を拾ってしまう**ので採らない。）

面積コスト 4 x 1924.6 + 641.5 + 1283.0 = 9,632 um2（マクロ 372,827 um2 の 2.6%）。
"""
from __future__ import annotations
import argparse, os, re, sys

MEM = "td4_mem"
MACRO = "REG8x16"
PFX = "_mw"


def widths(txt):
    """ネットリストの宣言から {信号名: (hi, lo)} を作る。スカラーは (0, 0)。"""
    w = {}
    for m in re.finditer(r"^\s*(?:input|output|inout|wire|reg)\s+"
                         r"(?:\[(\d+):(\d+)\]\s+)?(\\?\S+?)\s*;", txt, re.M):
        hi, lo, nm = m.group(1), m.group(2), m.group(3)
        w.setdefault(nm, (int(hi), int(lo)) if hi is not None else (0, 0))
    return w


def one(p, w):
    """1 つの項を LSB 先頭のビット列に展開する。"""
    m = re.match(r"^(\\?\S+?)\s*\[(\d+):(\d+)\]$", p)
    if m:                                   # name[hi:lo]
        hi, lo = int(m.group(2)), int(m.group(3))
        return [f"{m.group(1)}[{i}]" for i in range(lo, hi + 1)]
    if re.match(r"^\\?\S+\[\d+\]$", p):     # name[k]
        return [p]
    if p in w:                              # 裸の名前 -> 宣言幅
        hi, lo = w[p]
        return [p] if (hi, lo) == (0, 0) else [f"{p}[{i}]" for i in range(lo, hi + 1)]
    return [p]


def bits(expr, n, w):
    """`{ a, b }` / `name` / `name[3:0]` を LSB 側から n ビットの式に割る。"""
    e = expr.strip()
    if e.startswith("{"):
        out = []
        for p in reversed([x.strip() for x in e[1:-1].split(",")]):  # 連結は MSB 先頭
            out += one(p, w)
    else:
        out = one(e, w)
    if len(out) != n:
        sys.exit(f"ビット数が合わない: {expr} -> {len(out)} 本（{n} 本のはず）\n"
                 f"  展開結果: {out}")
    return out



# --- アドレス MUX が冗長かどうかの構造チェック ------------------------------
#
# `we=1` のときに `raddr == waddr` が常に成り立つなら、ADD は raddr 直結でよく
# MUX2 4 個が丸ごと要らない。td4_soc_arr は
#     raddr = exec ? pc : ld_addr / waddr = ld_addr / we = ~exec & wr & nibsel
# なので `we=1 -> exec=0 -> raddr = ld_addr = waddr` で成立する。
# **設計に依存する性質なので、決め打ちにせず毎回確かめる。**

CELLS = re.compile(r"^\s*([A-Z][A-Za-z0-9_]*)\s+(\S+)\s*\((.*?)\);\s*$", re.S | re.M)
BUFINV = {"BUF_X1": 0, "BUF_X2": 0, "INV_X1": 1, "INV_X2": 1}
ANDS = {"AND2_X1", "AND3_X1", "AND4_X1"}


def instances(txt):
    out = []
    for m in CELLS.finditer(txt):
        c = dict(re.findall(r"\.(\w+)\s*\(\s*(.*?)\s*\)\s*(?:,|$)", m.group(3), re.S))
        out.append((m.group(1), m.group(2), {k: v.strip() for k, v in c.items()}))
    return out


def driver(insts, net):
    for ty, nm, c in insts:
        if c.get("Y") == net:
            return ty, nm, c
    return None


def root(insts, net, depth=0):
    """BUF/INV の鎖を遡って (根のネット, 反転回数の偶奇) を返す。"""
    d = driver(insts, net)
    if d and d[0] in BUFINV and depth < 8:
        r, par = root(insts, d[2]["A"], depth + 1)
        return r, par ^ BUFINV[d[0]]
    return net, 0


def addr_mux_redundant(txt, ra, wa, we):
    """(冗長か, 理由) を返す。"""
    insts = instances(txt)
    sels = set()
    for i, (r, w) in enumerate(zip(ra, wa)):
        d = driver(insts, r)
        if d is None or d[0] != "MUX2":
            return False, f"raddr[{i}] ({r}) を駆動しているのが MUX2 ではない"
        if d[2].get("A") != w:
            return False, f"raddr[{i}] の MUX2 の A が waddr[{i}] ({w}) ではない"
        sels.add(d[2].get("S"))
    if len(sels) != 1:
        return False, f"4 本の MUX2 の選択信号が揃っていない: {sels}"
    sel_root, sel_par = root(insts, sels.pop())

    dw = driver(insts, we)
    if dw is None or dw[0] not in ANDS:
        return False, f"we ({we}) を駆動しているのが AND ではない"
    for k, v in dw[2].items():
        if k == "Y":
            continue
        r, par = root(insts, v)
        if r == sel_root and par != sel_par:
            return (True,
                    f"we は {r} の反転を含む AND、MUX2 の選択も {r}（極性は逆）。"
                    f"we=1 -> 選択は A 側 -> raddr == waddr")
    return False, f"we の AND に MUX2 の選択信号 {sel_root} の反転が見当たらない"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("net")
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--keep-addr-mux", action="store_true",
                    help="冗長と判定されてもアドレス MUX を残す")
    a = ap.parse_args()
    txt = open(a.net).read()

    m = re.search(rf"^\s*{MEM}\s+(\S+)\s*\((.*?)\);\s*$", txt, re.S | re.M)
    if not m:
        sys.exit(f"{a.net} に {MEM} のインスタンスが無い")
    inst, body = m.group(1), m.group(2)
    conn = dict(re.findall(r"\.(\w+)\s*\(\s*(.*?)\s*\)\s*(?:,|$)", body, re.S))
    need = {"clk", "raddr", "rdata", "waddr", "wdata", "we"}
    if set(conn) != need:
        sys.exit(f"{MEM} のポートが想定と違う: {sorted(conn)}")

    w = widths(txt)
    ra, wa = bits(conn["raddr"], 4, w), bits(conn["waddr"], 4, w)
    wd, rd = bits(conn["wdata"], 8, w), bits(conn["rdata"], 8, w)
    clk, we = conn["clk"].strip(), conn["we"].strip()

    red, why = addr_mux_redundant(txt, ra, wa, we)
    use_mux = a.keep_addr_mux or not red
    print(f"  アドレス MUX: {'残す' if use_mux else '省く'} — {why}")

    L = [f"  // --- {MEM} -> {MACRO} + グルー（scripts/mem_wrap.py が生成）---",
         f"  wire {PFX}_web, {PFX}_nwe;"]
    if use_mux:
        L.insert(1, f"  wire [3:0] {PFX}_add;")
        for i in range(4):
            L.append(f"  MUX2 {PFX}_a{i} (.A({ra[i]}), .B({wa[i]}), .S({we}), "
                     f".Y({PFX}_add[{i}]));")
        add = [f"{PFX}_add[{i}]" for i in range(4)]
    else:
        L.insert(1, f"  // ADD は raddr 直結。{why}")
        add = ra
    L.append(f"  INV_X1 {PFX}_inv (.A({we}), .Y({PFX}_nwe));")
    L.append(f"  OR2 {PFX}_or (.A({clk}), .B({PFX}_nwe), .Y({PFX}_web));")
    L.append(f"  {MACRO} {inst} (")
    L.append(f"    .ADD({{ {', '.join(reversed(add))} }}),")
    L.append(f"    .WEB({PFX}_web),")
    L.append(f"    .D({{ {', '.join(reversed(wd))} }}),")
    L.append(f"    .Q({{ {', '.join(reversed(rd))} }})")
    L.append("  );")

    out = txt[:m.start()] + "\n".join(L) + "\n" + txt[m.end():]
    p = a.out or os.path.splitext(a.net)[0] + "_pnr.v"
    open(p, "w").write(out)
    print(f"wrote {p}")
    print(f"  {MEM} {inst} を {MACRO} に置換")
    n = 6 if use_mux else 2
    area = 9632.1 if use_mux else 1924.5
    print(f"  WEB = {clk} | ~{we}   INV_X1 + OR2")
    print(f"  追加セル {n} 個 / {area:,.0f} um2")


if __name__ == "__main__":
    main()

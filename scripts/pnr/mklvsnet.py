#!/usr/bin/env python3
"""mklvsnet.py -- 配置配線したコアの **LVS ソースネットリスト**を書き出す。

  usage: python3 scripts/pnr/mklvsnet.py        # -> layout/portrait/simulation/<top>.spice

出どころ（`lef/simulation/README` の分類でいう **(A) 設計意図**）:
  合成後ネットリスト `out/td4_soc_arr_pnr.v`（= P&R が読んだのと同じ物）と、
  `lef/simulation/*.spice` のセル単体ソースネットリストから組み立てる。
  **レイアウトからの抽出は一切使っていない**ので、これと抽出網を突き合わせる
  LVS は同語反復にならない。

P&R したコア特有の注意が 3 つある:

  1. **フィラーとタップはネットリストに出てこない。** `FILL2` / `FILL3` は
     2T のデキャップ（ゲートを反対側のレールに繋いだ MOS 容量）で、実体として
     レイアウトに居る。配置 JSON から拾って**ソース側にも同じ数だけ**入れる。
     入れないと LVS はレイアウト側の余剰デバイスとして落ちる。
     `TAP2` はデバイスを持たない（基板/ウェルのタップだけ）ので何も出さない。
  2. **電源はネットリストに無い。** 各セルの subckt は `vdd vss` を最後に持つ
     ので、トップの `VDD` / `GND` をそのまま全インスタンスに配る。名前は
     **レイアウトのピンラベルに合わせて** `VDD` / `GND`（`add_power_pins` が打つ）。
  3. **バスは連結で繋がっている。** `.ADD({_004_, _003_, _002_, _001_})` の
     形。Verilog の連結は**左が MSB** なので `ADD[3]=_004_` … と展開する。
     マクロ `REG8x16` の subckt 側は `ADD[0] ADD[1] …` と添字付きのポート名。

セルのポート順は**名前で引く**。`.subckt NAND2 A Y B` のように論理順でない
セルがあるので、位置で合わせてはいけない。
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402
import netlist_parser                                       # noqa: E402

SIM_DIR = os.path.join(cfg.ROOT, "lef", "simulation")
PWR = ("VDD", "GND")
# デバイスを持たない物理セル（ソース側には何も出さない）
NO_DEVICE_CELLS = {"TAP2", "FILL1"}


# ---- lef/simulation/*.spice から subckt を読む ----------------------------
def _read_file(path):
    """1 ファイル分の {NAME: (ports, body_text)}。継続行は畳む。"""
    out = {}
    lines = []
    for ln in open(path).read().splitlines():
        if ln.startswith("+") and lines:
            lines[-1] += " " + ln[1:].strip()
        else:
            lines.append(ln)
    cur = None
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0].lower() == ".subckt":
            cur = (t[1], t[2:], [ln])
            continue
        if cur is None:
            continue
        cur[2].append(ln)
        if t[0].lower().startswith(".ends"):
            out[cur[0]] = (cur[1], "\n".join(cur[2]))
            cur = None
    return out


def load_subckts(sim_dir=SIM_DIR):
    """ファイルごとに分けて持つ。

    **全ファイルを 1 つの辞書に混ぜてはいけない。** `DEC0.spice` は
    「抽出を凍結した」版でピンが付いておらず `.subckt DEC0 vdd vss`、
    一方 `REG4x16_lvs_src.spice` / `REG8x16.spice` の中の `DEC0` は
    `A0 A1 A2 A3 WEB WR WRB RD RDB vdd vss` を持つ。どちらが正しいかは
    **どのセルの中身として使うか**で決まるので、まず「そのセル自身の
    ファイル」を見て、無ければ `<名前>.spice` を見る、という順で引く。"""
    per_file = {}
    for path in sorted(glob.glob(os.path.join(sim_dir, "*.spice"))):
        per_file[os.path.splitext(os.path.basename(path))[0]] = _read_file(path)
    return per_file


class SubcktDB:
    """`(セル名) -> (ports, body)` を、そのセルのファイルを優先して引く。"""

    def __init__(self, per_file):
        self.per_file = per_file

    def home(self, cell):
        """cell を定義しているファイル名（まず同名ファイル）。"""
        if cell in self.per_file and cell in self.per_file[cell]:
            return cell
        for stem, d in self.per_file.items():
            if cell in d:
                return stem
        return None

    def get(self, cell, prefer=None):
        if prefer and prefer in self.per_file and cell in self.per_file[prefer]:
            return self.per_file[prefer][cell]
        stem = self.home(cell)
        if stem is None:
            return None
        return self.per_file[stem][cell]

    def collect(self, cell):
        """cell とその子 subckt を、定義の重複なく集める。

        子は**親と同じファイルの定義**を優先する（上の DEC0 の話）。
        戻り値は [(name, body)]（依存が先）。"""
        stem = self.home(cell)
        if stem is None:
            raise SystemExit(f"{cell} の subckt が {SIM_DIR} に無い")
        out, seen = [], set()

        def walk(name):
            if name in seen:
                return
            seen.add(name)
            got = self.get(name, prefer=stem)
            if got is None:
                raise SystemExit(f"{name} の subckt が {SIM_DIR} に無い（{cell} の中で使用）")
            ports, txt = got
            for ln in txt.splitlines():
                t = ln.split()
                if t and t[0][0] in "xX" and len(t) >= 2:
                    child = t[-1]
                    if child != name and self.get(child, prefer=stem) is not None:
                        walk(child)
            out.append((name, txt))

        walk(cell)
        return out


# ---- Verilog（連結・バス・エスケープ識別子を展開する） --------------------
# 識別子。Yosys のエスケープ識別子 `\u_core.reg_out ` は**末尾の空白まで**が
# トークン（Verilog の規則）。
# エスケープ識別子は空白で終わるのが Verilog の規則だが、行末や `;` の直前では
# 空白が無いこともある（`assign out_port = \\u_core.reg_out ;` の右辺は
# 空白を挟むが、式の切り出し側で strip されて消える）。空白は**任意**にする。
NAME = r"(?:\\[^\s;,()\[\]{}]+\s?|[A-Za-z_][A-Za-z0-9_$]*)"
_DECL = re.compile(r"^\s*(input|output|inout|wire|reg)\s*(?:\[(\d+):(\d+)\])?\s*"
                   r"(" + NAME + r")\s*;", re.M)
_ASSIGN = re.compile(r"assign\s+(.+?)\s*=\s*(.+?)\s*;")
_SEL = re.compile(r"^(" + NAME + r")\s*(?:\[(\d+)(?::(\d+))?\])?\s*$")


def norm(tok):
    r"""`\u_core.reg_out ` -> `u_core.reg_out`。普通の名前はそのまま。"""
    tok = tok.strip()
    if tok.startswith("\\"):
        tok = tok[1:]
    # エスケープ識別子は**末尾の空白までが 1 トークン**なので
    # `\u_core.reg_a [0]` のように名前と添字の間に空白が残る。潰す。
    return tok.replace(" ", "").replace("\t", "")


def sanitize(net):
    """Verilog のネット名を SPICE で使える形に。

    `.` はそのままだと SPICE リーダに階層の区切りと見られかねないので `_` にする。
    添字 `[3]` は残す（レイアウト側のピンラベルが `out_port[3]` なので揃う）。"""
    return norm(net).replace(" ", "").replace(".", "_")


def split_concat(expr):
    """`{ a, b, c }` -> ['a','b','c']（左が MSB）。連結でなければ [expr]。"""
    expr = expr.strip()
    if not expr.startswith("{"):
        return [expr]
    inner = expr[1:expr.rindex("}")]
    return [x.strip() for x in inner.split(",") if x.strip()]


def parse_decls(text):
    """{名前: (hi, lo) または None}。宣言の順も返す（トップのポート順用）。"""
    widths, order, kinds = {}, [], {}
    for m in _DECL.finditer(text):
        kind, hi, lo, name = m.groups()
        name = norm(name)
        w = None if hi is None else (int(hi), int(lo))
        if name not in widths or widths[name] is None:
            widths[name] = w
        kinds.setdefault(name, kind)
        if kind in ("input", "output", "inout") and name not in order:
            order.append(name)
        if kind in ("input", "output", "inout"):
            kinds[name] = kind
    return widths, order, kinds


def bits_of(expr, widths):
    """`out_port` / `ld_addr[3:1]` / `_005_` -> ビット名のリスト（MSB 先頭）。

    連結やリテラルは扱わない（呼び側で弾く）。"""
    m = _SEL.match(expr.strip())
    if not m:
        return None
    name, a, b = m.group(1), m.group(2), m.group(3)
    name = norm(name)
    if a is None:
        w = widths.get(name)
        if w is None:
            return [name]
        hi, lo = w
        return [f"{name}[{i}]" for i in range(hi, lo - 1, -1)]
    if b is None:
        return [f"{name}[{int(a)}]"]
    hi, lo = int(a), int(b)
    step = -1 if hi >= lo else 1
    return [f"{name}[{i}]" for i in range(hi, lo + step, step)]


def build_resolver(text, widths, top_bits):
    r"""ビット単位の alias 解決。

    **`netlist_parser._build_alias_resolver` では足りない。** あちらは
    `^\w+(\[\d+\])?$` にしか当たらないので
      `assign out_port = \u_core.reg_out ;`
    のような「エスケープ識別子 + バス丸ごと」の別名を**丸ごと取りこぼす**。
    実測: これを落とすと `out_port[*]` と `cflag_o` がどこにも繋がらない網に
    なり、LVS のトップピンが 16 → 11 本に減って不一致になった。

    代表元は**トップポートのビット名を優先**する。レイアウト側のピンラベルは
    `out_port[3]` なので、そちらに寄せておくと LVS が名前でも一致する。"""
    parent = {}

    def find(k):
        parent.setdefault(k, k)
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for m in _ASSIGN.finditer(text):
        lhs, rhs = m.group(1), m.group(2)
        if "{" in lhs or "{" in rhs or "'" in rhs:
            continue                     # 連結・リテラルは別名ではない
        lb, rb = bits_of(lhs, widths), bits_of(rhs, widths)
        if lb is None or rb is None or len(lb) != len(rb):
            continue
        for x, y in zip(lb, rb):
            union(x, y)

    # 代表元を選び直す（トップポート優先）
    groups = {}
    for k in list(parent):
        groups.setdefault(find(k), []).append(k)
    canon = {}
    for root, members in groups.items():
        best = min(members, key=lambda n: (0 if n in top_bits else 1, len(n), n))
        for mem in members:
            canon[mem] = best

    def resolve(net):
        net = norm(net)
        return canon.get(net, net)

    return resolve


def parse_verilog(path):
    text = open(path).read()
    widths, order, kinds = parse_decls(text)

    top_m = re.search(r"module\s+(\S+)\s*\((.*?)\)\s*;", text, re.S)
    top_name = top_m.group(1)

    top_bits = set()
    for name in order:
        top_bits.update(bits_of(name, widths) or [])

    resolve = build_resolver(text, widths, top_bits)

    instances = []
    for m in re.finditer(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(.*?)\)\s*;\s*$",
            text, re.M | re.S):
        typ, name, portlist = m.groups()
        if typ in netlist_parser._SKIP_TYPES:
            continue
        pins = {}
        for pm in re.finditer(r"\.(\w+)\s*\(\s*(\{[^}]*\}|[^),]*)\s*\)", portlist):
            pins[pm.group(1)] = pm.group(2).strip()
        instances.append((typ, name, pins))

    return {"top_name": top_name, "port_order": order, "widths": widths,
            "instances": instances, "resolve": resolve, "kinds": kinds}


def expand_port(name, w):
    if w is None:
        return [name]
    hi, lo = w
    return [f"{name}[{i}]" for i in range(hi, lo - 1, -1)]


# ---- 1 インスタンスのピン -> subckt のポート順 ----------------------------
def instance_nets(typ, iname, pins, ports, resolve, dangling):
    """subckt のポート順に並べたネット名リスト（vdd/vss は呼び側で足す）。"""
    # ピン名ごとに、そのピンが供給するビット列を作る
    supplied = {}
    for pin, expr in pins.items():
        bits = split_concat(expr)
        supplied[pin] = [sanitize(resolve(b.strip())) if "{" not in b else sanitize(b)
                         for b in bits]

    out = []
    for p in ports:
        if p.lower() in ("vdd", "vss"):
            continue
        m = re.match(r"^(\w+)\[(\d+)\]$", p)
        if m and m.group(1) in supplied:          # バスの 1 ビット
            base, idx = m.group(1), int(m.group(2))
            bits = supplied[base]
            # Verilog の連結は左が MSB。ビット幅 n なら bits[0] が [n-1]
            pos = len(bits) - 1 - idx
            if not (0 <= pos < len(bits)):
                raise SystemExit(f"{iname} ({typ}) の {p}: 連結のビット幅が合わない "
                                 f"({len(bits)} 本)")
            out.append(bits[pos])
            continue
        if p in supplied:
            bits = supplied[p]
            if len(bits) != 1:
                raise SystemExit(f"{iname} ({typ}) の {p} がスカラなのに連結")
            if not bits[0]:
                dangling[0] += 1
                out.append(f"n_open_{dangling[0]}")
            else:
                out.append(bits[0])
            continue
        # ネットリストに現れないピン（出力の未使用など）
        dangling[0] += 1
        out.append(f"n_open_{dangling[0]}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--placement", default=cfg.PLACEMENT_JSON)
    ap.add_argument("-n", "--netlist", default=cfg.NET_PATH)
    # **ファイル名は `<トップセル名>.spice`。** KLayout の LVS は
    # 「セル名と同じ名前の .spice」を探す流儀（`lef/simulation/*.spice` も
    # `REG8x16.spice` のようにセル名そのもの）。`_src` を付けた名前で出したら
    # ユーザ側でリネームが要った（2026-09-13）。既定でその名前にする。
    ap.add_argument("-o", "--out", default=None,
                    help="出力先（既定: layout/<mode>/simulation/<トップセル名>.spice）")
    ap.add_argument("--top", default=cfg.TOP_CELL_NAME,
                    help="書き出す subckt 名（既定: レイアウトのトップセル名）")
    a = ap.parse_args()
    if a.out is None:
        _sub = "portrait" if getattr(cfg, "MACRO_MODE", "landscape") == "portrait" else "landscape"
        a.out = os.path.join(cfg.LAYOUT, _sub, "simulation", f"{a.top}.spice")

    db = SubcktDB(load_subckts())
    v = parse_verilog(a.netlist)
    resolve = v["resolve"]
    pl = json.load(open(a.placement))

    # --- 実体の突き合わせ（配置 JSON が正、Verilog に無いものは物理セル）---
    from collections import Counter
    placed = Counter(i["type"] for row in pl["rows"] for i in row)
    logical = Counter(t for t, _n, _p in v["instances"])
    phys = Counter()
    for typ, n in placed.items():
        if typ in logical:
            if n != logical[typ]:
                raise SystemExit(f"{typ} の数が合わない: 配置 {n} / ネットリスト {logical[typ]}")
        else:
            phys[typ] = n
    missing = [t for t in logical if t not in placed]
    if missing:
        raise SystemExit(f"配置に無いセルがネットリストにある: {missing}")

    # --- トップのポート ---
    top_ports = []
    for name in v["port_order"]:
        top_ports += expand_port(name, v["widths"][name])
    top_ports += list(PWR)

    dangling = [0]
    body = []
    used = set()

    for typ, iname, pins in v["instances"]:
        got = db.get(typ)
        if got is None:
            raise SystemExit(f"{typ} の subckt が {SIM_DIR} に無い")
        ports, _txt = got
        nets = instance_nets(typ, iname, pins, ports, resolve, dangling)
        used.add(typ)
        body.append(f"X{sanitize(iname)} {' '.join(nets)} {PWR[0]} {PWR[1]} {typ}")

    # --- フィラー/タップ（配置 JSON の実体をそのまま）---
    fill_lines = []
    for row in pl["rows"]:
        for inst in row:
            typ = inst["type"]
            if typ not in phys:
                continue
            if typ in NO_DEVICE_CELLS:
                continue
            if db.get(typ) is None:
                raise SystemExit(f"物理セル {typ} の subckt が {SIM_DIR} に無い")
            used.add(typ)
            fill_lines.append(f"X{sanitize(inst['name'])} {PWR[0]} {PWR[1]} {typ}")

    # --- 依存する subckt を再帰的に集める（定義は親のファイルを優先）---
    defs, seen_def = [], set()
    for t in sorted(used):
        for name, txt in db.collect(t):
            if name in seen_def:
                continue
            seen_def.add(name)
            defs.append((name, txt))
    need = seen_def

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        f.write(f"* {a.top} -- LVS ソースネットリスト（設計意図側）\n"
                f"* scripts/pnr/mklvsnet.py が生成。手で編集しないこと。\n*\n"
                f"*   論理セル : {os.path.relpath(a.netlist, cfg.ROOT)}\n"
                f"*   物理セル : {os.path.relpath(a.placement, cfg.ROOT)} "
                f"({', '.join(f'{t} x{n}' for t, n in sorted(phys.items()))})\n"
                f"*   セル定義 : {os.path.relpath(SIM_DIR, cfg.ROOT)}/*.spice\n"
                f"*\n"
                f"* デバイスを持たない物理セルは出していない: "
                f"{', '.join(sorted(t for t in phys if t in NO_DEVICE_CELLS)) or 'なし'}\n"
                f"* 電源はトップの {PWR[0]} / {PWR[1]} を全インスタンスへ配っている。\n\n")
        for name, txt in defs:
            f.write(txt + "\n\n")
        f.write(f".subckt {a.top} {' '.join(top_ports)}\n")
        f.write("\n".join(body) + "\n")
        if fill_lines:
            f.write("\n* --- フィラー（デキャップ）---\n")
            f.write("\n".join(fill_lines) + "\n")
        f.write(f".ends {a.top}\n")

    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    print(f"  top pin   : {len(top_ports)}  ({' '.join(top_ports)})")
    print(f"  論理セル  : {sum(logical.values())} 個 / {len(logical)} 種")
    print(f"  物理セル  : {sum(phys.values())} 個 / {len(phys)} 種 "
          f"({', '.join(f'{t} x{n}' for t, n in sorted(phys.items()))})")
    print(f"  subckt    : {len(need)} 個を同梱")
    if dangling[0]:
        print(f"  未接続ピン: {dangling[0]} 本を n_open_* にした")
    return 0


if __name__ == "__main__":
    sys.exit(main())

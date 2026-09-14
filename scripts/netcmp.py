#!/usr/bin/env python3
"""2つの SPICE サブサーキットをグラフ同型判定で突き合わせる（LVS の予行演習）。

  usage: python3 scripts/netcmp.py A.spi DEC2  B.extracted DEC2 [--map "$2=A0,$3=AB0,..."]

MOSFET を「ゲート端子」と「S/D 端子（交換可能）」を区別したノードにして
networkx の VF2 で同型を判定する。LVS を回す前に、意図した回路とレイアウトが
本当に一致しているかを手元で確認するためのもの。
"""
from __future__ import annotations
import argparse, re, sys

try:
    import networkx as nx
except ImportError:
    sys.exit("pip install networkx --break-system-packages")


def parse(path, sub):
    """指定サブサーキットの (ピン列, デバイス列) を返す。M / XM 両形式に対応。"""
    txt, out, pins, inside = open(path).read(), [], [], False
    # 継続行 '+' を連結
    lines = []
    for ln in txt.splitlines():
        ln = ln.rstrip()
        if ln.startswith("+") and lines:
            lines[-1] += " " + ln[1:].strip()
        else:
            lines.append(ln)
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0].lower() == ".subckt" and t[1].upper() == sub.upper():
            inside, pins = True, [x.strip("\\") for x in t[2:]]
            continue
        if inside and t[0].lower().startswith(".ends"):
            break
        if not inside or ln.startswith("*"):
            continue
        if re.match(r"^X?M", t[0], re.I):
            n = [x.strip("\\") for x in t[1:5]]
            model = t[5].upper()
            w = next((x.split("=")[1] for x in t[6:] if x.upper().startswith("W=")), "?")
            out.append((model, n[0], n[1], n[2], n[3], w))   # d g s b W
    return pins, out


def graph(pins, devs, rename=None):
    rn = (lambda x: rename.get(x, x)) if rename else (lambda x: x)
    g = nx.Graph()
    for i, (model, d, gt, s, b, w) in enumerate(devs):
        dev = f"DEV{i}"
        g.add_node(dev, kind=f"{model}:{w}")
        for net, role in ((gt, "G"), (d, "SD"), (s, "SD"), (b, "B")):
            n = rn(net)
            if n not in g:
                g.add_node(n, kind="net")
            g.add_edge(dev, n, role=role) if not g.has_edge(dev, n) else \
                g.edges[dev, n].update(role=g.edges[dev, n]["role"] + "+" + role)
    for p in pins:
        n = rn(p)
        if n in g:
            g.nodes[n]["kind"] = "pin"
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("a"); ap.add_argument("suba")
    ap.add_argument("b"); ap.add_argument("subb")
    ap.add_argument("--map", default="", help="B側のネット名を A 側に合わせる: '$2=A0,$3=AB0'")
    x = ap.parse_args()

    rename = dict(kv.split("=", 1) for kv in x.map.split(",") if "=" in kv)
    pa, da = parse(x.a, x.suba)
    pb, db = parse(x.b, x.subb)
    print(f"A: {x.suba:8} ピン {len(pa):3d}  素子 {len(da):3d}   ({x.a})")
    print(f"B: {x.subb:8} ピン {len(pb):3d}  素子 {len(db):3d}   ({x.b})")
    if len(da) != len(db):
        print("★ 素子数が違う")

    ga, gb = graph(pa, da), graph(pb, db, rename)
    nm = nx.algorithms.isomorphism.categorical_node_match("kind", "net")
    em = nx.algorithms.isomorphism.categorical_edge_match("role", "")
    gm = nx.algorithms.isomorphism.GraphMatcher(ga, gb, node_match=nm, edge_match=em)
    if gm.is_isomorphic():
        print("\n=== 同型: 一致 ===")
        named = {k: v for k, v in gm.mapping.items() if ga.nodes[k]["kind"] == "pin"}
        for k in sorted(named):
            if k != named[k]:
                print(f"   {k:8} <-> {named[k]}")
    else:
        print("\n=== 同型でない ===")
        for tag, g in (("A", ga), ("B", gb)):
            sig = {}
            for n, d in g.nodes(data=True):
                if d["kind"] == "net" or d["kind"] == "pin":
                    sig[n] = tuple(sorted(g.edges[n, m]["role"] + ":" + g.nodes[m]["kind"]
                                          for m in g.neighbors(n)))
            print(f"  {tag} のネット別シグネチャ数: {len(set(sig.values()))}")
        sa = sorted(tuple(sorted(ga.edges[n, m]["role"] for m in ga.neighbors(n)))
                    for n in ga if ga.nodes[n]["kind"] != "net" or True)
        print("  → 手動で突き合わせが必要")


# ---------------------------------------------------------------------------
# トップ回路（サブサーキット呼び出しだけ）の比較
# ---------------------------------------------------------------------------
def parse_top(path, top):
    """(ピン列, [(サブ名, [接続ネット...])]) を返す。継続行 '+' に対応。"""
    lines, insts, pins, inside = [], [], [], False
    for ln in open(path).read().splitlines():
        ln = ln.rstrip()
        if ln.startswith("+") and lines:
            lines[-1] += " " + ln[1:].strip()
        else:
            lines.append(ln)
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0].lower() == ".subckt" and t[1].upper() == top.upper():
            inside, pins = True, [x.strip("\\") for x in t[2:]]
            continue
        if inside and t[0].lower().startswith(".ends"):
            break
        if inside and re.match(r"^X", t[0], re.I) and not re.match(r"^XM", t[0], re.I):
            insts.append((t[-1].strip("\\"), [x.strip("\\") for x in t[1:-1]]))
    return pins, insts


def top_graph(pins, insts, order, rename=None):
    """order: {サブ名: [正規ピン名(位置順)]}"""
    rn = (lambda x: rename.get(x, x)) if rename else (lambda x: x)
    g = nx.Graph()
    for i, (sub, nets) in enumerate(insts):
        node = f"I{i}"
        g.add_node(node, kind=f"sub:{sub.upper()}")
        names = order[sub.upper()]
        for pin, net in zip(names, nets):
            n = rn(net)
            if n not in g:
                g.add_node(n, kind="net")
            if g.has_edge(node, n):
                g.edges[node, n]["role"] += "+" + pin
            else:
                g.add_edge(node, n, role=pin)
    for p in pins:
        n = rn(p)
        if n in g:
            g.nodes[n]["kind"] = "pin"
    return g

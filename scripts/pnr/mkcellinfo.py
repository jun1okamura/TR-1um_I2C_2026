#!/usr/bin/env python3
"""mkcellinfo.py -- 配置器が使うセル寸法表 `layout/cell_info.json` を作る。

  usage: python3 scripts/pnr/mkcellinfo.py

寸法は **LEF の SIZE と GDS の prBoundary の両方**から取って突き合わせる。
片方だけだと、prBoundary を持たない／原点がずれているセルを黙って取りこぼす
（`REG8x16` の prBoundary 原点は (-86.4, -54.6) で (0,0) ではない）。
食い違ったら止まる。
"""
from __future__ import annotations
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402

PRB = (235, 0)


def lef_sizes(path):
    txt = open(path).read()
    out = {}
    for m in re.finditer(r"^MACRO (\S+)\n(.*?)\n\s*END\s+\1\s*$", txt, re.M | re.S):
        s = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;", m.group(2))
        cls = re.search(r"CLASS\s+([^;]+);", m.group(2))
        if s:
            out[m.group(1)] = dict(width_um=float(s.group(1)),
                                   height_um=float(s.group(2)),
                                   cls=(cls.group(1).strip() if cls else ""))
    return out


def gds_boundaries(path):
    import gdstk
    lib = gdstk.read_gds(path)
    out = {}
    for c in lib.cells:
        pr = [p for p in c.polygons if (p.layer, p.datatype) == PRB]
        if not pr:
            continue
        xs = [v for p in pr for v in (p.bounding_box()[0][0], p.bounding_box()[1][0])]
        ys = [v for p in pr for v in (p.bounding_box()[0][1], p.bounding_box()[1][1])]
        out[c.name] = dict(origin=(round(min(xs), 3), round(min(ys), 3)),
                           width_um=round(max(xs) - min(xs), 3),
                           height_um=round(max(ys) - min(ys), 3))
    return out


def main():
    lef = lef_sizes(cfg.LEF_PATH)
    gds = gds_boundaries(cfg.CELL_GDS)
    info, bad, skip = {}, [], []
    for name, d in sorted(lef.items()):
        g = gds.get(name)
        if g is None:
            # REG8x16 の内部だけで使う中間階層（TLAT8 / DEC16 / REGBUF8 …）は
            # 自前の prBoundary を持たない。行に置かないので配置器には要らない。
            skip.append(name)
            continue
        if abs(g["width_um"] - d["width_um"]) > 1e-6 or \
           abs(g["height_um"] - d["height_um"]) > 1e-6:
            bad.append(f"{name}: LEF {d['width_um']}x{d['height_um']} と "
                       f"GDS prBoundary {g['width_um']}x{g['height_um']} が違う")
            continue
        info[name] = dict(width_um=d["width_um"], height_um=d["height_um"],
                          sites=round(d["width_um"] / cfg.SITE_UM, 3),
                          origin=list(g["origin"]), cls=d["cls"])
    if bad:
        raise SystemExit("cell_info: 食い違い\n  - " + "\n  - ".join(bad))

    # ネットリストに出てくるセルが全部載っているか。載っていなければ配置できない。
    used = set(re.findall(r"^\s*([A-Z][A-Za-z0-9_]*)\s+\S+\s*\(", open(cfg.NET_PATH).read(), re.M))
    miss = sorted(used - set(info))
    if miss:
        raise SystemExit(f"cell_info: ネットリストのセル {miss} が寸法表に無い")

    os.makedirs(cfg.LAYOUT, exist_ok=True)
    json.dump(info, open(cfg.CELL_INFO, "w"), indent=1, sort_keys=True)
    rows = sum(1 for d in info.values() if abs(d["height_um"] - cfg.ROW_HEIGHT_UM) < 1e-6)
    print(f"wrote {os.path.relpath(cfg.CELL_INFO, cfg.ROOT)}  ({len(info)} セル)")
    print(f"  行高 {cfg.ROW_HEIGHT_UM} のセル {rows} 個 / それ以外 {len(info)-rows} 個")
    if skip:
        print(f"  prBoundary を持たない中間階層 {len(skip)} 個は除外: "
              + ", ".join(skip))
    off = {n: d["origin"] for n, d in info.items() if d["origin"] != [0.0, 0.0]}
    if off:
        print("  prBoundary 原点が (0,0) でないセル（配置時に補正が要る）:")
        for n, o in sorted(off.items()):
            print(f"    {n:10s} {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

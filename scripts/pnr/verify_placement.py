#!/usr/bin/env python3
"""verify_placement.py -- 配置結果の検証。

  usage: python3 scripts/pnr/verify_placement.py [layout/step4/place_step4_fill.json]

見るもの:
  1. ネットリストのインスタンスが**過不足なく 1 回ずつ**置かれているか
  2. 行内でセルがアバットしているか（重なり・隙間なし）、行幅ちょうどで終わるか
  3. 全部がサイトグリッド (5.4 µm) に乗っているか
  4. TAP2 が全行同じ x にあるか（縦 M2 電源メッシュの前提）
  5. マクロが設定どおりの位置にあり、行と重なっていないか
  6. コア枠に収まっているか / フレーム開口に収まっているか
  7. **GDS の実体**（参照数・実寸）が JSON と合っているか
"""
from __future__ import annotations
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import netlist_util as nu                                   # noqa: E402

NO_MACRO = getattr(cfg, "MACRO_MODE", "landscape") == "none"
EPS = 1e-6


def main(path=None):
    path = path or os.path.join(cfg.LAYOUT, "step4", "place_step4_fill.json")
    d = json.load(open(path))
    bad, note = [], []

    # ---- 1. インスタンスの被覆
    insts = nu.parse(open(cfg.NET_PATH).read())
    want = {i.name for i in insts if i.cell != cfg.MACRO_NET_CELL}
    got = [c["inst"] for row in d["rows"] for c in row if c["inst"]]
    dup = {x for x in got if got.count(x) > 1}
    got_s = set(got)
    if want - got_s:
        bad.append(f"置かれていないインスタンス {len(want-got_s)} 個: "
                   f"{sorted(want-got_s)[:6]}")
    if got_s - want:
        bad.append(f"ネットリストに無いインスタンス: {sorted(got_s-want)[:6]}")
    if dup:
        bad.append(f"二重に置かれている: {sorted(dup)[:6]}")

    # ---- 2/3. 行内のアバットとグリッド
    for r, row in enumerate(d["rows"]):
        x = 0.0
        for c in sorted(row, key=lambda e: e["x"]):
            if abs(c["x"] - x) > EPS:
                bad.append(f"row{r}: {c['cell']} {c['inst']} が x={c['x']} "
                           f"（x={x} でアバットするはず）")
                x = c["x"]
            if abs(c["x"] / cfg.SITE_UM - round(c["x"] / cfg.SITE_UM)) > 1e-9:
                bad.append(f"row{r}: x={c['x']} がサイトグリッドに乗っていない")
            x = round(x + c["w"], 3)
        if abs(x - d["row_width"]) > EPS:
            bad.append(f"row{r}: 右端が {x}（行幅 {d['row_width']} のはず）")

    # ---- 4. TAP の x
    for r, row in enumerate(d["rows"]):
        tx = sorted(c["x"] for c in row if c["cell"] == cfg.TAP_CELL)
        if [round(v, 3) for v in tx] != [round(v, 3) for v in cfg.TAP_X]:
            bad.append(f"row{r}: TAP の x が {tx}（{cfg.TAP_X} のはず）")

    # ---- 5. マクロ（I2C はマクロ無し）
    mx0, my0, mx1, my1 = cfg.macro_box()
    ys, stack = cfg.row_y()
    if NO_MACRO:
        note.append("ハードマクロ無し（標準セルだけのコア）")
    elif [round(v, 3) for v in d["macro"]["box"]] != [round(v, 3) for v in (mx0, my0, mx1, my1)]:
        bad.append(f"マクロ枠 {d['macro']['box']} が設定 {(mx0,my0,mx1,my1)} と違う")
    if NO_MACRO:
        pass
    elif cfg.MACRO_MODE == "portrait":
        # 縦置き: 行の**右**。行スタックと x が重ならないこと、底面が row0 と
        # 面一であること（下辺のピン列が ch[0] を向くための拘束）。
        if mx0 < cfg.ROW_WIDTH_UM - EPS:
            bad.append(f"マクロ左端 {mx0} が行スタック (…{cfg.ROW_WIDTH_UM}) と重なる")
        k = getattr(cfg, "MACRO_ALIGN_ROW", 0)
        if abs(my0 - ys[k]) > EPS:
            bad.append(f"マクロ底面 {my0} が row{k} の底面 {ys[k]} と面一でない")
        note.append(f"マクロは x {mx0}…{mx1} / y {my0}…{my1}（行スタックの右）。"
                    f"行スタック高 {stack}、コア高 {cfg.core_size()[1]} µm"
                    + ("（マクロが決めている）" if my1 > stack else "（行スタックが決めている）"))
    else:
        if my1 > EPS:
            bad.append(f"マクロ帯の上端 {my1} が 0 を超える。帯はルータ座標の下に"
                       f"置くこと（そうしないと ch[0] のトラックが帯に食い込む）")
        for r, y in enumerate(ys):
            if y < my1 - EPS:
                bad.append(f"row{r} (y {y}) がマクロ帯 (…{my1}) と重なる")
        note.append(f"マクロ帯は y {my0}…{my1}（ルータ座標の下）。"
                    f"チップに落とすときのコア外形は {cfg.chip_core_box()}、"
                    f"高さ {cfg.chip_core_height()} µm")

    # ---- 6. コア枠 / 開口
    cw, ch = cfg.core_size()
    if d["core_w"] != cw or d["core_h"] != ch:
        bad.append(f"コア {d['core_w']}x{d['core_h']} が設定 {cw}x{ch} と違う")
    h, op, marg = cfg.check_opening()
    note.append(f"圧縮前のコア高 {h} / 開口 {op} → 余り {marg:+.1f} µm"
                + ("（圧縮前なので負で当たり前）" if marg < 0 else ""))

    # ---- 7. GDS の実体
    gds = path.replace(".json", ".gds")
    import gdstk
    lib = gdstk.read_gds(gds)
    top = {c.name: c for c in lib.cells}[cfg.TOP_CELL_NAME]
    nref = len(top.references)
    njson = sum(len(r) for r in d["rows"]) + (0 if NO_MACRO else 1)   # +1 = マクロ
    if nref != njson:
        bad.append(f"GDS の参照 {nref} 個 vs JSON {njson} 個")
    pr = [p for p in top.polygons if (p.layer, p.datatype) == (235, 0)]
    if len(pr) != 1:
        bad.append(f"トップの prBoundary が {len(pr)} 枚（1 枚のはず）")
    else:
        b = pr[0].bounding_box()
        if abs(b[1][0] - b[0][0] - cw) > EPS or abs(b[1][1] - b[0][1] - ch) > EPS:
            bad.append(f"トップ prBoundary {b} がコア {cw}x{ch} と違う")
    # マクロ参照の実位置
    mref = [] if NO_MACRO else [r for r in top.references
                                if r.cell.name == cfg.MACRO_CELL]
    if NO_MACRO:
        pass
    elif len(mref) != 1:
        bad.append(f"GDS のマクロ参照が {len(mref)} 個")
    else:
        mb = [p for p in mref[0].cell.polygons if (p.layer, p.datatype) == (235, 0)]
        o = mref[0].origin
        bb = mb[0].bounding_box()
        real = (o[0] + bb[0][0], o[1] + bb[0][1], o[0] + bb[1][0], o[1] + bb[1][1])
        if max(abs(a - b_) for a, b_ in zip(real, (mx0, my0, mx1, my1))) > EPS:
            bad.append(f"GDS のマクロ prBoundary 実位置 "
                       f"{tuple(round(v,3) for v in real)} が設定 "
                       f"{(mx0,my0,mx1,my1)} と違う")

    # ---- レポート
    import place as _p
    usable = d["row_width"] - sum(w for _x, w, _k in _p.fixed_blocks(d["row_width"]))
    used = [sum(c["w"] for c in row if c["inst"]) for row in d["rows"]]
    fills = [sum(c["w"] for c in row if not c["inst"] and c["cell"] != cfg.TAP_CELL)
             for row in d["rows"]]
    print(f"配置検証: {os.path.relpath(path, cfg.ROOT)}")
    print(f"  ルータ領域 {cw} x {ch} um   チップ側コア高 {cfg.chip_core_height()} um")
    print(f"  行 {d['row_width']} um x {len(d['rows'])}   "
          f"充填率 " + ", ".join(f"{u/usable*100:.0f}%" for u in used)
          + f"（実効 {usable:.1f} um/行）")
    print(f"  論理セル幅 {sum(used):.1f} um / FILL {sum(fills):.1f} um")
    if not NO_MACRO:
        print(f"  マクロ {cfg.MACRO_CELL} @ ({mx0}, {my0}) - ({mx1}, {my1})")
    for n in note:
        print(f"  - {n}")
    if bad:
        print(f"  ** {len(bad)} 件 NG")
        for b_ in bad:
            print(f"     - {b_}")
        return 1
    print("  判定: **全数 OK**")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))

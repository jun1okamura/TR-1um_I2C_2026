#!/usr/bin/env python3
"""mkmemport.py -- `REG8x16` を 90° 回し、垂直なピン列を**水平なパッド列**に
変換したハードマクロ `MEMPORT` を作る。

  usage: python3 scripts/pnr/mkmemport.py
         python3 scripts/pnr/mkmemport.py --plot layout/memport.png
         python3 scripts/pnr/mkmemport.py --order-from layout/placement_nrow_fm.json

## なぜ要るか

`REG8x16` は 399.6 × 933.0 で、信号ピン 21 本は `y 1.1…4.5` の**水平 1 列**。
縦置きのまま行の横に並べると、コア幅 1598.4 のうち 421.2 µm を食うので
行幅が 1177.2 にしかならず、配置率が 79% まで上がって**行またぎの空き x が
枯れる**（M2 の無い x が 216 トラック中 48 本）。これが短絡 31 件の原因。

横倒し（R90）にすれば 933.0 × 399.6 になり、行はコア幅いっぱい使えて
配置率が 71%（4 行）/ 57%（5 行）まで下がる。**ただし 90° 回すと水平な
ピン列は垂直なピン列になる**（右辺、x 928.5…931.9、y 6.4…377.0 に 21 本）。
水平チャネルのルータはこれを扱えない。

そこで**マクロの右の空き地**（x 933…1598.4、y 0…399.6）で M1/M2 に振り替え、
帯の上辺に水平なパッド列を作る。

    ピン(M2) ─V1─ M1 を右へ（各ピン自身の y。21 本とも別の y）
                 └─V1─ M2 を上へ（ライザ列。21 本とも別の x、5.4 ピッチ）
                        └─V1─ **M1 をマクロの上で左右へ**（21 本とも別の y）
                               └─V1─ M2 を上へ
                                      └─ 上辺の M2 パッド + ラベル

M1 は水平・M2 は垂直で、`lef/TR-1um_tech.lef` の方向規則どおり。

**マクロの上に M1 の段を作る理由**: 中継をマクロの右だけで済ませると、
パッドが x 945…1593（右 40%）にしか置けない。すると 21 本のネットが全部
コアの右側から出発することになり、ch[0] に長いトランクが 21 本並んで
行またぎが集中する（実測: 短絡 22 件のうち 12 件がマクロ絡みだった）。
マクロの**上**に 1 本ずつ M1 の段を持てば、パッドを**コア幅いっぱい**に
散らせる。帯は 21+4 段ぶん（約 150 µm）高くなるが、圧縮後のコア高に
まだ余裕がある。

## 出力

  `lef/TR-1um_PNR.gds`   標準セル + `MEMPORT`（1598.4 × 399.6）を 1 ファイルに
  `lef/TR-1um_PNR.lef`   同じく MACRO を 1 ファイルに

**配置配線はこの 2 つだけを読む**（`i2c_config.CELL_GDS` / `LEF_PATH`）。
ライブラリ本体（`TR-1um_STDCELL.gds` / `TR-1um_cells.lef`）は汚さない。

以降のフローから見ると「上辺 1 列にピンがあるハードマクロ 1 個」になるので、
配置・配線は縦置きのときと同じ扱いで通る。

## 電源

マクロの `vdd`/`vss` は元の上辺と下辺に 2 本ずつ出ている。R90 すると
**左辺と右辺**に移る。左辺 (x≈2.8) はマクロの真上を通らないと外へ出せない
（OBS 全面）ので、**右辺の 2 本ずつだけ**を上辺へ引き出す。マクロ内部で
左右の電源は繋がっているので電気的には足りるが、**電流経路は片側だけ**に
なる。チップの電源メッシュ側で太く受けること。
"""
from __future__ import annotations
import argparse, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import lef_parser                                           # noqa: E402

SRC_CELL = "REG8x16"
CELL = "MEMPORT"
M1, M2, V1 = (13, 0), (20, 0), (19, 0)
M1LBL, M1PIN = (48, 0), (48, 1)
M2LBL, M2PIN = (49, 0), (49, 1)
BOUND = (235, 0)

PAD = 3.4                  # via_1 の既定パッド（M1/M2 とも）
HALF = PAD / 2.0
GRID = 5.4                 # サイト／トラックピッチ
M2_GAP = 2.0

# --- 中継の配置 ------------------------------------------------------------
VIA_X = 938.3              # マクロ右のピン引き出し V1 列（全ピン共通の x）
RISER_X0 = 943.7           # ライザ列の左端（ピンごとに 5.4 ずつずらす）
RISER_DX = 5.4
# ライザを避けてパッドを置く x の帯（左右 2 つ）。ライザ列は 943.7…1078.1。
PAD_BANDS = [(27.0, 928.8), (1090.8, 1592.0)]
TRACK_DY = 5.4             # マクロの上の M1 段のピッチ
TRACK_Y0 = 405.0           # 最初の M1 段（マクロ上端 399.6 + 5.4）
PAD_H = 3.4


def r90(x, y, w_src, h_src):
    """R90 + 平行移動。(x, y) -> (h_src - y, x)。外形は h_src × w_src になる。"""
    return (h_src - y, x)


def load_order(place_json):
    """配置結果から「負荷の重心 x」の順に並べたピン名を返す。

    パッドの x は**中継の M1 段でどこへでも引ける**ので、ピンの並び順のまま
    等間隔に散らす必然性は無い。接続先セルの重心に合わせて並べ替えると、
    ch[0] のトランクが短くなり行またぎも減る。

    実測（並べ替え前）: パッド x と負荷の重心のずれが合計 7,138 µm、
    平均 340 µm/ネット。`rom_data[0]` はパッド 378.0 に対し負荷の重心が
    1240.2（862 µm 離れ）だった。
    """
    import json
    pl = json.load(open(place_json))
    mac = [i for i in pl["rows"][0] if i["type"] == CELL][0]
    net_of = {p["net"]: pn for pn, p in mac["pins"].items() if p["net"]}
    cen = {}
    for row in pl["rows"]:
        for i in row:
            if i["type"] == CELL:
                continue
            for p in i["pins"].values():
                n = p["net"]
                if p["use"] in ("POWER", "GROUND") or n not in net_of:
                    continue
                cen.setdefault(n, []).append(i["x"] + i["width"] / 2.0)
    g = {net_of[n]: sum(v) / len(v) for n, v in cen.items()}
    return g


def load_pad_order_from_lef(lef_path):
    """既存の `MEMPORT` LEF から「パッド x の順に並んだピン名」を取る。

    **配置をやり直さずに帯の高さだけ変えたいとき**に使う。パッドの x と
    ネットの対応をそのまま引き継げば、配置器が見るマクロのピン座標
    （x = パッド x、y = -MACRO_GAP_UM - 5.7）が 1 µm も動かないので、
    配置も配線もビット単位で同じものが出る。帯の**下**が縮むだけ。

    `--order-from`（負荷の重心順）は逆に**並べ替える**ので、配置がやり直しに
    なり配線もサイコロを振り直すことになる。
    """
    pins = lef_parser.parse_lef(lef_path)[CELL]["pins"]
    out = []
    for name, info in pins.items():
        for r in info["rects"]:
            out.append((name, round((r[1] + r[3]) / 2.0, 3)))
    out.sort(key=lambda t: t[1])
    return [n for n, _x in out]


def build(plot=None, order_from=None, pads_from_lef=None):
    import gdstk
    lib = gdstk.read_gds(cfg.LIB_GDS)
    cells = {c.name: c for c in lib.cells}
    if SRC_CELL not in cells:
        raise SystemExit(f"{SRC_CELL} が {cfg.LIB_GDS} に無い")
    src = cells[SRC_CELL]
    prb = [p for p in src.polygons if (p.layer, p.datatype) == BOUND]
    b = prb[0].bounding_box()
    w_src, h_src = round(b[1][0] - b[0][0], 3), round(b[1][1] - b[0][1], 3)
    if abs(b[0][0]) > 1e-6 or abs(b[0][1]) > 1e-6:
        raise SystemExit(f"{SRC_CELL} の prBoundary 原点が (0,0) でない。"
                         f"先に scripts/normalize_prboundary.py")

    W = cfg.CORE_WIDTH_UM                    # 帯の幅 = コア幅
    if h_src > W:
        raise SystemExit(f"回転後の幅 {h_src} がコア幅 {W} を超える")

    lefpins = lef_parser.parse_lef(cfg.LIB_LEF)[SRC_CELL]["pins"]
    sig, pwr = [], []
    for name, info in lefpins.items():
        for lay, x0, y0, x1, y1 in info["rects"]:
            nx0, ny0 = r90(x0, y1, w_src, h_src)
            nx1, ny1 = r90(x1, y0, w_src, h_src)
            rec = (name, info["use"], round(nx0, 3), round(ny0, 3),
                   round(nx1, 3), round(ny1, 3))
            (sig if info["use"] not in ("POWER", "GROUND") else pwr).append(rec)
    sig.sort(key=lambda r: r[3])
    # 右辺（x が大きい方）に来た電源ピンだけ引き出せる
    pwr_r = sorted([p for p in pwr if p[2] > h_src / 2], key=lambda r: r[3])
    if len(sig) != 21:
        raise SystemExit(f"信号ピンが {len(sig)} 本（21 本のはず）")

    out = gdstk.Library(name=CELL, unit=1e-6, precision=1e-9)
    seen = set()

    def add_deep(c):
        if c.name in seen:
            return
        seen.add(c.name)
        out.add(c)
        for r in c.references:
            add_deep(r.cell)

    add_deep(src)
    top = out.new_cell(CELL)
    top.add(gdstk.Reference(src, (h_src, 0.0), rotation=math.pi / 2))

    def box(ld, x0, y0, x1, y1):
        top.add(gdstk.rectangle((x0, y0), (x1, y1), layer=ld[0], datatype=ld[1]))

    def via(cx, cy):
        # ルータの via_1 PCell と同じ寸法の生ボックスで描く（このセルは
        # ライブラリセル扱いなので PCell 依存を持ち込まない）。
        box(V1, cx - 0.7, cy - 0.7, cx + 0.7, cy + 0.7)
        box(M1, cx - HALF, cy - HALF, cx + HALF, cy + HALF)
        box(M2, cx - HALF, cy - HALF, cx + HALF, cy + HALF)

    def fanout_direct(name, use, px0, py0, px1, py1, rx, pad_y0, pad_y1):
        """ライザ列より**右**のパッドへは、マクロの上の段を使わずに直行する。

          ピン(M2) → M1 を**ピン自身の y のまま**パッドの x まで → M2 上 → パッド

        マクロの右（x 933…1598.4、y 0…399.6）は空き地なので、ここは
        ピンの y のまま水平に走れる。マクロの**上**に段を取るのは
        「マクロの OBS を越えて x<933 のパッドへ行く」ためだけなので、
        右側のパッドには要らない。

        効果: 段が 25 本 → 16 本になり、帯が **48.6 µm 低く**なる。
        """
        cy = round((py0 + py1) / 2.0, 3)
        box(M2, px0, cy - HALF, VIA_X + HALF, cy + HALF)
        via(VIA_X, cy)
        box(M1, VIA_X - HALF, cy - HALF, rx + HALF, cy + HALF)
        via(rx, cy)
        box(M2, rx - HALF, cy - HALF, rx + HALF, pad_y1)
        box(M2PIN, rx - HALF, pad_y0, rx + HALF, pad_y1)
        top.add(gdstk.Label(name, (rx, (pad_y0 + pad_y1) / 2.0),
                            layer=M2LBL[0], texttype=M2LBL[1], magnification=2.0))
        return dict(name=name, use=use, x0=round(rx - HALF, 3), y0=pad_y0,
                    x1=round(rx + HALF, 3), y1=pad_y1)

    def fanout(name, use, px0, py0, px1, py1, k, rx, ty):
        """1 本ぶんの中継。

          ピン(M2) → M1 右 → M2 上（ライザ） → M1 左右（マクロの上の段）
                                              → M2 上 → 上辺パッド
        """
        cy = round((py0 + py1) / 2.0, 3)
        ax = round(RISER_X0 + k * RISER_DX, 3)
        # 1) ピンから V1 列まで M2 を伸ばす（マクロの外へ出すぶんだけ）
        box(M2, px0, cy - HALF, VIA_X + HALF, cy + HALF)
        via(VIA_X, cy)
        # 2) M1 を右へ、ライザ列まで
        box(M1, VIA_X - HALF, cy - HALF, ax + HALF, cy + HALF)
        via(ax, cy)
        # 3) M2 でマクロの上の段まで上げる
        box(M2, ax - HALF, cy - HALF, ax + HALF, ty + HALF)
        via(ax, ty)
        # 4) M1 でその段を左右に走り、パッドの x まで
        box(M1, min(ax, rx) - HALF, ty - HALF, max(ax, rx) + HALF, ty + HALF)
        via(rx, ty)
        # 5) M2 で上辺パッドまで
        box(M2, rx - HALF, ty - HALF, rx + HALF, pad_y1)
        box(M2PIN, rx - HALF, pad_y0, rx + HALF, pad_y1)
        top.add(gdstk.Label(name, (rx, (pad_y0 + pad_y1) / 2.0),
                            layer=M2LBL[0], texttype=M2LBL[1], magnification=2.0))
        return dict(name=name, use=use, x0=round(rx - HALF, 3), y0=pad_y0,
                    x1=round(rx + HALF, 3), y1=pad_y1)

    allpins = sig + pwr_r
    n = len(allpins)

    # パッドの x を**コア幅いっぱい**に散らす（ライザ列の帯は避ける）
    span = sum(b - a for a, b in PAD_BANDS)
    pad_xs, acc = [], 0.0
    for i in range(n):
        want = span * i / max(n - 1, 1)
        s = 0.0
        for a, b in PAD_BANDS:
            if want <= s + (b - a) + 1e-9:
                x = a + (want - s)
                break
            s += b - a
        pad_xs.append(round(round(x / GRID) * GRID, 3))
    if len(set(pad_xs)) != n:
        raise SystemExit(f"パッドの x が重複した: {pad_xs}")

    # **マクロの上の M1 段は「ライザ列より左のパッド」にしか要らない。**
    # 右のパッドへはマクロの右の空き地をピン自身の y のまま直行できる
    # （fanout_direct）。段の本数がそのまま帯の高さなので、ここで
    # 25 本 → 左側のパッドの本数だけに減る。
    riser_hi = RISER_X0 + (n - 1) * RISER_DX
    n_track = sum(1 for x in pad_xs if x <= riser_hi)
    ty_last = TRACK_Y0 + (max(n_track, 1) - 1) * TRACK_DY
    pad_y0 = round(ty_last + TRACK_DY + HALF, 3)
    pad_y1 = round(pad_y0 + PAD_H, 3)
    H = round(pad_y1 + 1.1, 3)
    H = round(math.ceil(H / GRID) * GRID, 3)     # サイトグリッドに丸める

    # パッドの割り当て。既定はピンの並び順だが、配置結果があれば
    # **負荷の重心 x の順**に並べ替える（中継の M1 段はどこへでも引ける）。
    if pads_from_lef:
        want = load_pad_order_from_lef(pads_from_lef)
        if sorted(want) != sorted(r[0] for r in allpins):
            raise SystemExit(f"既存 LEF のピン構成が違う: {sorted(set(want))}")
        pool = {}
        for r in allpins:
            pool.setdefault(r[0], []).append(r)
        allpins = [pool[n].pop(0) for n in want]
        print(f"  パッドの割り当てを既存 LEF から引き継いだ（配置は動かない）")
    elif order_from:
        g = load_order(order_from)
        miss = [r[0] for r in sig if r[0] not in g]
        if miss:
            print(f"  ! 重心が取れないピン（負荷なし）: {miss} — 元の順のまま")
        key = {r[0]: g.get(r[0], 1e9) for r in allpins}
        # 電源は最後（重心が無い）。信号だけ重心順に並べ替える
        allpins = sorted(allpins, key=lambda r: (key[r[0]], r[3]))
        print(f"  パッドを負荷の重心 x 順に並べ替えた")

    pins = []
    k_track = 0                       # マクロの上の段は左側のパッドだけが使う
    for k, ((name, use, x0, y0, x1, y1), rx) in enumerate(zip(allpins, pad_xs)):
        if rx > riser_hi:
            pins.append(fanout_direct(name, use, x0, y0, x1, y1, rx,
                                      pad_y0, pad_y1))
            continue
        ty = round(TRACK_Y0 + k_track * TRACK_DY, 3)
        k_track += 1
        pins.append(fanout(name, use, x0, y0, x1, y1, k, rx, ty))

    top.add(gdstk.rectangle((0, 0), (W, H), layer=BOUND[0], datatype=BOUND[1]))

    # 干渉チェック: 同一レイヤの M2 ライザ同士が 2.0 µm 以上離れているか
    xs = sorted(p["x0"] + HALF for p in pins)
    tight = [(a, b) for a, b in zip(xs, xs[1:]) if b - a < PAD + M2_GAP - 1e-6]
    if tight:
        raise SystemExit(f"M2 ライザの間隔が足りない: {tight[:3]}")
    ys = sorted(round((r[3] + r[5]) / 2.0, 3) for r in allpins)
    tighty = [(a, b) for a, b in zip(ys, ys[1:]) if b - a < PAD + 1.4 - 1e-6]
    if tighty:
        raise SystemExit(f"M1 引き出しの y 間隔が足りない: {tighty[:3]}")

    # 標準セルも同じライブラリに入れて、P&R が読むファイルを 1 つにする
    for c in lib.cells:
        if c.name not in seen:
            seen.add(c.name)
            out.add(c)
    gds = os.path.join(cfg.ROOT, "lef", "TR-1um_PNR.gds")
    out.write_gds(gds, timestamp=__import__("datetime").datetime(2026, 1, 1))

    # --- LEF ---------------------------------------------------------------
    L = [f"MACRO {CELL}", "  CLASS BLOCK ;", f"  FOREIGN {CELL} 0.000 0.000 ;",
         "  ORIGIN 0.000 0.000 ;", f"  SIZE {W:.3f} BY {H:.3f} ;",
         "  SYMMETRY X Y ;"]
    # 同名のピン（vdd/vss は 2 枚ずつ）は **1 つの PIN にまとめる**。
    # 別々に書くと LEF 読み手の dict で後勝ちになり、片方が見えなくなる。
    byname = {}
    for p in pins:
        byname.setdefault(p["name"], (p["use"], []))[1].append(p)
    for name, (use, ps) in byname.items():
        L += [f"  PIN {name}", "    DIRECTION INOUT ;",
              f"    USE {use} ;", "    PORT", "      LAYER METAL2 ;"]
        L += [f"        RECT {q['x0']:.3f} {q['y0']:.3f} {q['x1']:.3f} {q['y1']:.3f} ;"
              for q in ps]
        L += ["    END", f"  END {name}"]
    L += ["  OBS", "    LAYER METAL1 ;",
          f"      RECT 0.000 0.000 {W:.3f} {H:.3f} ;",
          "    LAYER METAL2 ;",
          f"      RECT 0.000 0.000 {W:.3f} {H:.3f} ;",
          "  END", f"END {CELL}", ""]
    leff = os.path.join(cfg.ROOT, "lef", "TR-1um_PNR.lef")
    open(leff, "w").write(open(cfg.LIB_LEF).read()
                          + "\n" + "\n".join(L))

    print(f"wrote {os.path.relpath(gds, cfg.ROOT)}")
    print(f"wrote {os.path.relpath(leff, cfg.ROOT)}")
    print(f"  {CELL} {W} x {H} um   （{SRC_CELL} を R90 して {h_src} x {w_src}、"
          f"右の空き地 {W - h_src:.1f} um に中継）")
    print(f"  上辺パッド {n} 本（信号 {len(sig)} + 電源 {len(pwr_r)}）"
          f" x {min(pad_xs)}…{max(pad_xs)}（コア幅いっぱいに分散）")
    print(f"  マクロの上に M1 の段 {n_track} 本（y {TRACK_Y0}…{ty_last}）"
          f"／右側 {n - n_track} 本はピンの y のまま直行（段を使わない）")
    print(f"  ** 電源はマクロ右辺の 2 本ずつだけを引き出している"
          f"（左辺はマクロの真上を通れない）。チップ側で太く受けること")
    if plot:
        draw(plot, W, H, h_src, allpins, pins)
    return gds, leff


def draw(path, W, H, mw, allpins, pins):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig, ax = plt.subplots(figsize=(15, 5))
    ax.add_patch(Rectangle((0, 0), W, H, fc="#fcfcfc", ec="#2c3e50", lw=1.4))
    ax.add_patch(Rectangle((0, 0), mw, H, fc="#f8c471", ec="#ca6f1e", lw=1.0))
    ax.text(mw / 2, H / 2, f"{SRC_CELL} (R90)  {mw} x {H}", ha="center",
            va="center", fontsize=9)
    for name, use, x0, y0, x1, y1 in allpins:
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc="#8e44ad", ec="none"))
    for k, (p, (name, use, x0, y0, x1, y1)) in enumerate(zip(pins, allpins)):
        cy = (y0 + y1) / 2
        ax_ = RISER_X0 + k * RISER_DX
        ty = TRACK_Y0 + k * TRACK_DY
        rx = p["x0"] + 1.7
        ax.plot([x0, ax_], [cy, cy], color="#2980b9", lw=0.7)
        ax.plot([ax_, ax_], [cy, ty], color="#e67e22", lw=0.7)
        ax.plot([ax_, rx], [ty, ty], color="#2980b9", lw=0.7)
        ax.plot([rx, rx], [ty, p["y1"]], color="#e67e22", lw=0.7)
        ax.add_patch(Rectangle((p["x0"], p["y0"]), 3.4, 3.4, fc="#8e44ad", ec="none"))
    ax.set_xlim(-20, W + 20)
    ax.set_ylim(-20, H + 20)
    ax.set_aspect("equal")
    ax.set_title(f"{CELL}  {W} x {H} um   blue = M1 (horizontal), "
                 f"orange = M2 (vertical), purple = pins/pads", fontsize=9)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"wrote {os.path.relpath(path, cfg.ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plot", default=None)
    ap.add_argument("--order-from", default=None,
                    help="配置 JSON。パッドを負荷の重心 x 順に並べ替える")
    ap.add_argument("--pads-from-lef", default=None,
                    help="既存の MEMPORT LEF からパッドの割り当てを引き継ぐ。"
                         "**配置器が見るピン座標が 1 µm も動かない**ので、"
                         "配置も配線も同じまま帯の高さだけ変えられる")
    a = ap.parse_args()
    build(a.plot, a.order_from, a.pads_from_lef)

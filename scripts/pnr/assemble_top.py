#!/usr/bin/env python3
"""assemble_top.py -- 配置配線したコアを GIO パッドリングに落とす（チップ step1）。

    layout/step11/route_step_7_macro_power.gds  （コア、DRC/LVS クリーン）
  + lef/TR-1um_frame_25x25.gds                  （`OSS_FRAME_GIO`、16 パッド）
  -> layout/chip/step1_assembled.gds            （セル `tr_1um_TD4`）

**配置だけ。配線はしない。** 移植元（SCLK_SPI / I2C）もここで一旦止める。
下流は全部このオフセットから measure するので、先に KLayout で見ておくこと。

## フレームは (0,0)

`OSS_FRAME_GIO` は**セル自身がダイ中心を原点**に持つ（bbox -1250…+1250）。
なので `db.Trans(0,0)` に置けばダイは -1250…+1250 に載る。動かさない。

## コアはどこに座るか

**開口は四隅まで含めて 1840 x 1840 の正方形。** 実測（`frame_opening()` が
frame GDS の図形を測る）で、原点中心 1840 角は全層で完全に空き、1844 で
当たる。四方の内壁はどこも ±920。

`lef/TR-1um_frame.lef` の **OBS を読んではいけない**。四隅を 360x360 の矩形
（x 800…1160, y 800…1160）で粗く塞いでいるが、`OSS_FRAME_CNR` の実際の図形は
**外側 2 辺に沿った L 字**で内側の角は空いている。OBS を鵜呑みにすると
「幅 1600 超なら |y| <= 800」という実在しない崖が出る（2026-09-14 ユーザ指摘）。

コアの実 bbox は **1604.7 x 1357.0**。x が 1598.4 でなく 1604.7 なのは
**いちばん左のセルの N ウェル (140,0) が x=-6.3 まで出ている**から
（`CORE_WIDTH_UM` は prBoundary の幅）。

`td4_config.chip_geometry()` が **native bbox を中心対称**に置く
（SCLK_SPI と同じ流儀）。結果:

    コア bbox  -802.35 … 802.35  x  -678.5 … 678.5
    チャネル   左右 117.65 / 上下 241.5 µm（壁まで）
               左右 119.35 / 上下 243.2 µm（端子リング 921.7 まで）

`CORE_WIDTH_UM` は開口いっぱいまで広げられるが、**余裕を持たせたまま
据え置く**（ユーザ判断 2026-09-14）。

## PTECT は置いていない

移植元はコアが開口に対して極端に低く（324.9 / 1840）、余った下半分を
PTECT (63,1) で塞いでいた。TD4 のコアは 1357.0 で開口をほぼ埋めるため、
残りはそのまま配線チャネルになる。必要になったら `--ptect` で足せるように
してある。

  usage: python3 scripts/pnr/assemble_top.py [-o OUT] [--core-gds GDS]
"""
from __future__ import annotations

import argparse
import os
import sys

# **チップ組み立ては縦置き専用。** `TD4_MACRO_MODE` の既定は landscape で、
# 付け忘れると `FINAL_GDS` が step10 を指し、`MACRO_CELL` も MEMPORT になる
# （2026-09-14: マクロ電源の入っていないコアを載せたチップを作ってしまった）。
# ここで固定する。コア側を landscape で作り直したいときはコア側のスクリプトで。
os.environ.setdefault("TD4_MACRO_MODE", "portrait")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import td4_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402

OUT_GDS = os.path.join(cfg.CHIP, "step1_assembled.gds")


def measured_inner_wall(layout, cell, x0, x1):
    """コアの x 帯を横切る**実ジオメトリ**のうち、いちばん内側の |y|。

    LEF の OBS は宣言であって図形ではない。実際の金属/拡散がどこまで来て
    いるかは GDS から測る（移植元 `assemble_top.py` と同じ検算）。"""
    r = db.Region()
    for L in ((13, 0), (20, 0), (11, 0), (19, 0), (8, 1), (3, 1), (3, 2), (48, 1), (49, 1)):
        r += db.Region(cell.begin_shapes_rec(layout.layer(*L)))
    r.merge()
    u = layout.dbu
    strip = db.Region(db.Box(int(x0 / u), int(-1250 / u), int(x1 / u), int(1250 / u)))
    boxes = [p.bbox() for p in (r & strip).each()]
    above = min((b.bottom * u for b in boxes if b.bottom * u > 0), default=None)
    below = max((b.top * u for b in boxes if b.top * u < 0), default=None)
    return above, below


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=OUT_GDS)
    ap.add_argument("--core-gds", default=None,
                    help="既定は td4_config.FINAL_GDS（縦置きなら step11）")
    ap.add_argument("--keep-unused", action="store_true",
                    help="参照されないトップセルを残す（既定は刈る）")
    ap.add_argument("--ptect", action="store_true",
                    help="コアの下の余りを PTECT (63,1) で塞ぐ")
    a = ap.parse_args()

    core_gds = a.core_gds or cfg.CHIP_CORE_GDS
    geom = cfg.chip_geometry(core_gds)
    bad = cfg.chip_fits(geom)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    layout = db.Layout()
    layout.dbu = 0.001
    um = lambda v: int(round(v / layout.dbu))                # noqa: E731
    top = layout.create_cell(cfg.CHIP_TOP_CELL)

    # ---- コア ----
    layout.read(core_gds)
    core = layout.cell(cfg.TOP_CELL_NAME)
    if core is None:
        raise SystemExit(f"{cfg.TOP_CELL_NAME} が {core_gds} に無い")
    ox, oy = geom["core_offset"]
    top.insert(db.CellInstArray(core.cell_index(), db.Trans(db.Vector(um(ox), um(oy)))))

    # ---- GIO リング（セル自身がダイ中心原点なので (0,0)）----
    # **同名セルは必ずリネームさせる。** コアにもフレームにも `via_1` /
    # `via_1$1` という名前の via PCell 変種が入っていて（パラメータは別物）、
    # KLayout の既定（AddToCell）で読むと**両方の図形が同じセルに重なる**。
    # 2026-09-14 のチップ DRC 30 件（V1.W1 15 / V1.S1 15、|座標| 1030 近辺の
    # ボンドパッド下）はこれが原因で、フレーム GDS 単体は clean だった。
    # カットが 0.75 µm ずれて重なり、幅 2.15 の V1 と 0.75 の隙間ができる。
    opt = db.LoadLayoutOptions()
    opt.cell_conflict_resolution = \
        db.LoadLayoutOptions.CellConflictResolution.RenameCell
    layout.read(cfg.FRAME_GDS, opt)
    gio = layout.cell(cfg.FRAME_CELL)
    if gio is None:
        raise SystemExit(f"{cfg.FRAME_CELL} が {cfg.FRAME_GDS} に無い")
    top.insert(db.CellInstArray(gio.cell_index(), db.Trans(db.Vector(0, 0))))

    # ---- 使っていないトップセルを落とす ----
    # コアの GDS も frame の GDS も**ライブラリ全体**を抱えているので、
    # そのまま読むと `MEMPORT` / `REG4x16` / `OSS_FRAME_TEG` / KLayout の
    # `$$$CONTEXT_INFO$$$` など、`tr_1um_TD4` から参照されないセルが
    # トップレベルに並ぶ（実測 17 個）。タップアウト用の GDS としては雑音で、
    # 「トップセルが複数ある」と文句を言うツールもあるので刈る。
    if not a.keep_unused:
        dropped = []
        while True:
            extra = [c for c in layout.top_cells() if c.name != cfg.CHIP_TOP_CELL]
            if not extra:
                break
            for c in extra:
                dropped.append(c.name)
                layout.prune_cell(c.cell_index(), -1)
        if dropped:
            print(f"  参照されないトップセルを {len(dropped)} 個削除: "
                  f"{', '.join(sorted(dropped)[:8])}"
                  + (" …" if len(dropped) > 8 else ""))

    # ---- MPW のチェッカに合わせてフレームを `OSS_FRAME` に改名 ----
    # `scripts/pre_check.py` の `FRAME_CELL_NAMES` は {OSS_FRAME, OSS_FRAME_TEG}
    # で GIO 版の名前が無い。**刈ったあとにやること** -- フレーム GDS には
    # アナログ 16 パッドの `OSS_FRAME` も入っていて、読み込み直後は名前が
    # ぶつかる（刈ると参照の無いそちらが消える）。
    if gio.name != cfg.FRAME_CELL_CHIP:
        if layout.cell(cfg.FRAME_CELL_CHIP) is not None:
            raise SystemExit(f"{cfg.FRAME_CELL_CHIP} が既にある -- 改名できない"
                             "（--keep-unused を外すこと）")
        gio.name = cfg.FRAME_CELL_CHIP

    x0, y0, x1, y1 = geom["core_chip_bbox"]
    if a.ptect:
        pad = geom["channel_bottom"][0]
        top.shapes(layout.layer(*cfg.PTECT_LAYER)).insert(
            db.Box(um(x0), um(geom["wall"]["bottom"] + pad), um(x1), um(y0 - pad)))

    # ---- 検算（LEF の宣言ではなく実ジオメトリに対して）----
    above, below = measured_inner_wall(layout, gio, x0, x1)
    if above is None or below is None:
        bad.append(("リングの内壁が測れない", None))
    else:
        if y1 > above or y0 < below:
            bad.append((f"コア ({y0} … {y1}) がリングの内壁 ({below} … {above}) に当たる", None))

    layout.write(a.out)

    die = geom["die"]
    print(f"=== {cfg.CHIP_TOP_CELL}  ダイ {die} x {die}  ({-die/2} … {die/2})")
    print(f"  フレーム {cfg.FRAME_CELL} -> {cfg.FRAME_CELL_CHIP}  @ (0, 0)"
          f"   ← セル原点がダイ中心")
    print(f"  コア     {cfg.TOP_CELL_NAME}  @ {geom['core_offset']}")
    print(f"    native bbox {geom['core_native_bbox']}")
    print(f"    チップ座標  ({x0}, {y0}) … ({x1}, {y1})"
          f"   [{x1-x0:.1f} x {y1-y0:.1f}]")
    w = geom["wall"]
    print(f"  開口の壁（実測） 左 {w['left']} / 右 {w['right']} / "
          f"下 {w['bottom']} / 上 {w['top']}"
          f"   ※ コアの x 帯での内壁は {below} … {above}")
    print("  チャネル（壁まで / 端子リング 921.7 まで）:")
    for side in ("top", "bottom", "left", "right"):
        w, t = geom["channel_" + side]
        print(f"    {side:6s} {w:7.2f} / {t:7.2f} µm")
    print(f"\nwrote {os.path.relpath(a.out, cfg.ROOT)}")
    if bad:
        for why, rect in bad:
            print(f"  PROBLEM: {why}" + (f"  {rect}" if rect else ""))
        raise SystemExit(1)
    print("配置だけ。配線はまだ。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

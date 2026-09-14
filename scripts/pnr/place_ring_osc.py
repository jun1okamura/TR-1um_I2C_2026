#!/usr/bin/env python3
"""place_ring_osc.py -- RING_OSC をチップに置く（チップ step1b）。

    layout/chip/step1_assembled.gds  （コア + パッドリング）
  + lef/RING_OSC.gds                 （97 段リング x 2）
  -> layout/chip/step1b_ringosc.gds

**配置だけ。OUT / OUTD / ENB / VDD / VSS の配線はしない。**
`TR-1um_Async_I2C/script/place_ring_osc.py` と同じ流儀（先に幾何を見てから
配線に進む）。位置は `i2c_config.RING_OSC_ORIGIN`（V10 と同じ (-810, -650)）。

置いたあと、次の 3 つを実測して報告する:

  * コアとの間隔      コアを上へずらさずに済むか
  * 開口の壁との間隔  フレームの実ジオメトリに当たっていないか
  * 左右チャネルの残り幅  縦レーンが通れるか（RING_OSC は x ±816.3 まで来るので
                          コア (±805.5) より 10.8 µm 外へ出る）

  usage: python3 scripts/pnr/place_ring_osc.py [-o OUT] [--in GDS]
"""
from __future__ import annotations
import argparse, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import klayout.db as db                                     # noqa: E402

IN_GDS = os.path.join(cfg.CHIP, "step1_assembled.gds")
OUT_GDS = os.path.join(cfg.CHIP, "step1b_ringosc.gds")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", default=IN_GDS)
    ap.add_argument("-o", "--out", default=OUT_GDS)
    a = ap.parse_args()

    ly = db.Layout()
    ly.read(a.inp)
    u = ly.dbu
    top = ly.cell(cfg.CHIP_TOP_CELL)
    if top is None:
        raise SystemExit(f"{cfg.CHIP_TOP_CELL} が {a.inp} に無い")

    # RING_OSC を階層ごと読み込む（セル名の衝突があれば KLayout が教える）
    before = {c.name for c in ly.each_cell()}
    ly.read(cfg.RING_OSC_GDS)
    ro = ly.cell(cfg.RING_OSC_CELL)
    if ro is None:
        raise SystemExit(f"{cfg.RING_OSC_CELL} が {cfg.RING_OSC_GDS} に無い")
    added = sorted({c.name for c in ly.each_cell()} - before)

    ox, oy = cfg.RING_OSC_ORIGIN
    top.insert(db.CellInstArray(ro.cell_index(),
                                db.Trans(db.Vector(int(round(ox / u)),
                                                   int(round(oy / u))))))
    b = ro.bbox()
    box = (ox + b.left * u, oy + b.bottom * u, ox + b.right * u, oy + b.top * u)
    print(f"=== {cfg.CHIP_TOP_CELL}  RING_OSC @ ({ox}, {oy})")
    print(f"  セル bbox（原点基準） ({b.left*u:.1f}, {b.bottom*u:.1f}) - "
          f"({b.right*u:.1f}, {b.top*u:.1f})")
    print(f"  チップ座標            ({box[0]:.1f}, {box[1]:.1f}) - ({box[2]:.1f}, {box[3]:.1f})"
          f"   [{box[2]-box[0]:.1f} x {box[3]-box[1]:.1f}]")
    print(f"  取り込んだセル {len(added)} 個: {', '.join(added[:8])}"
          + (" …" if len(added) > 8 else ""))

    # ---- 実測 1: コアとの間隔
    core = ly.cell(cfg.TOP_CELL_NAME)
    ci = [i for i in top.each_inst() if i.cell.name == cfg.TOP_CELL_NAME]
    if ci:
        cb = ci[0].bbox()
        gap = cb.bottom * u - box[3]
        print(f"  コア下端 {cb.bottom*u:.1f} との間隔 {gap:.1f} µm"
              + ("   ** 重なっている" if gap < 0 else ""))

    # ---- 実測 2: フレームの実ジオメトリとの当たり
    ok = cfg.frame_clear(*box)
    print(f"  フレームの実ジオメトリと: {'当たっていない' if ok else '** 当たっている'}")

    # ---- 実測 3: 左右チャネルの残り
    print(f"  左右チャネル: 壁 ±920.0 に対し RING_OSC は x ±{max(abs(box[0]),abs(box[2])):.1f}"
          f" まで来る → 残り {920.0 - max(abs(box[0]), abs(box[2])):.1f} µm")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    ly.write(a.out)
    print(f"\nwrote {os.path.relpath(a.out, cfg.ROOT)}")
    print("配置だけ。OUT / OUTD / ENB / 電源の配線はまだ。")


if __name__ == "__main__":
    main()

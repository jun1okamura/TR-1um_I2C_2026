#!/usr/bin/env python3
"""export_mpw.py -- MPW に出す 2 つのファイルを `src/` に置く。

    layout/chip/step4_final.gds                     -> src/<top>.gds
    layout/chip/simulation/<top>.spice              -> src/<top>.cir

`info.yaml` の `gds.top_cell` / `gds.extension` / `lvs.extension` から名前を
組み立てる（CI の `scripts/read_info.py` と同じ決め方）。**名前が
info.yaml と食い違うと CI が即落ちる**ので、ここで突き合わせる。

出す前に `scripts/pre_check.py` と同じことを見る:

    トップセルがちょうど 1 個 / 名前が info.yaml と一致
    dbu = 0.001
    bbox = (-1250,-1250)-(1250,1250)
    フレームのセル（OSS_FRAME か OSS_FRAME_TEG）がある

  usage: python3 scripts/pnr/export_mpw.py [--info info.yaml] [-n]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

# （TD4 版はここで TD4_MACRO_MODE=portrait を固定していた。I2C の
#   i2c_config はマクロを持たないので不要。）
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402

FINAL_CHIP_GDS = os.path.join(cfg.CHIP, "step4_final.gds")
SRC = os.path.join(cfg.ROOT, "src")
INFO = os.path.join(cfg.ROOT, "info.yaml")

FRAME_OK = {"OSS_FRAME", "OSS_FRAME_TEG"}
DIE = 2500.0
DBU = 0.001


def read_info(path):
    """`info.yaml` から必要な 3 つだけ（pyyaml が無くても読めるように素で）。"""
    txt = open(path, encoding="utf-8").read()

    def grab(section, key):
        m = re.search(rf"^{section}:\s*$(.*?)(?=^\S|\Z)", txt, re.M | re.S)
        if not m:
            raise SystemExit(f"{path}: セクション {section} が無い")
        m2 = re.search(rf'^\s+{key}:\s*"?([^"\n#]+)"?', m.group(1), re.M)
        if not m2:
            raise SystemExit(f"{path}: {section}.{key} が無い")
        return m2.group(1).strip()

    return (grab("gds", "top_cell"), grab("gds", "extension"),
            grab("lvs", "extension"), grab("lvs", "netlist_only"))


def precheck(gds, top_name):
    ly = db.Layout()
    ly.read(gds)
    tops = list(ly.top_cells())
    bad = []
    if len(tops) != 1:
        bad.append(f"トップセルが {len(tops)} 個: {[c.name for c in tops]}")
    elif tops[0].name != top_name:
        bad.append(f"トップセル名 {tops[0].name!r} != info.yaml の {top_name!r}")
    if abs(ly.dbu - DBU) > 1e-12:
        bad.append(f"dbu が {ly.dbu} （期待 {DBU}）")
    if tops:
        b = tops[0].dbbox()
        want = (-DIE / 2, -DIE / 2, DIE / 2, DIE / 2)
        got = (b.p1.x, b.p1.y, b.p2.x, b.p2.y)
        if max(abs(a - c) for a, c in zip(want, got)) > 1e-6:
            bad.append(f"bbox {got} != {want}")
    if not any(c.name in FRAME_OK for c in ly.each_cell()):
        bad.append(f"フレームのセルが無い（{sorted(FRAME_OK)} のどれか）")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--info", default=INFO)
    ap.add_argument("--gds", default=FINAL_CHIP_GDS)
    ap.add_argument("--cir", default=None)
    ap.add_argument("-n", "--dry-run", action="store_true")
    a = ap.parse_args()

    top, gds_ext, lvs_ext, netlist_only = read_info(a.info)
    if top != cfg.CHIP_TOP_CELL:
        raise SystemExit(f"info.yaml の top_cell {top!r} と "
                         f"i2c_config.CHIP_TOP_CELL {cfg.CHIP_TOP_CELL!r} が違う")
    if netlist_only.lower() == "true":
        print("  注意: info.yaml の lvs.netlist_only が true "
              "-- CI は抽出するだけで照合しない")

    cir = a.cir or os.path.join(cfg.CHIP, "simulation", top + ".spice")
    for p in (a.gds, cir):
        if not os.path.exists(p):
            raise SystemExit(f"入力が無い: {p}")

    bad = precheck(a.gds, top)
    print(f"=== pre-check（{os.path.relpath(a.gds, cfg.ROOT)}）")
    if bad:
        for b in bad:
            print(f"  PROBLEM: {b}")
        raise SystemExit(f"{len(bad)} 件 -- 何も出さない")
    print(f"  ok  トップ 1 個 = {top} / dbu {DBU} / "
          f"bbox {DIE:.0f} 角 / フレームあり")

    os.makedirs(SRC, exist_ok=True)
    pairs = [(a.gds, os.path.join(SRC, f"{top}.{gds_ext}")),
             (cir, os.path.join(SRC, f"{top}.{lvs_ext}"))]
    print()
    for s, d in pairs:
        print(f"  {os.path.relpath(s, cfg.ROOT)}  ->  {os.path.relpath(d, cfg.ROOT)}"
              f"  ({os.path.getsize(s)/1024:.0f} KB)")
        if not a.dry_run:
            shutil.copyfile(s, d)
    stale = [f for f in sorted(os.listdir(SRC))
             if not f.startswith(top + ".")]
    if stale:
        print(f"\n  src/ に他のファイルが残っている: {stale}")
        print("  （テンプレートの雛形なら消すこと。CI は info.yaml の名前しか見ない）")
    if a.dry_run:
        print("\n--dry-run なので何も書いていない")
    return 0


if __name__ == "__main__":
    sys.exit(main())

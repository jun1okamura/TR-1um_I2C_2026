#!/usr/bin/env python3
"""drc_pdk.py -- **PDK の本物の DRC デッキ**を当てて結果を要約する。

  usage: python3 scripts/pnr/drc_pdk.py <gds> [top_cell] [-r report.lyrdb]
         python3 scripts/pnr/drc_pdk.py layout/chip/step1c_logo.gds

`scripts/pnr/drc_check_nrow_fm.py` は **M1 / M2 / V1 の幅と間隔しか見ない**。
ルータが自分の引いた線を検算するためのもので、拡散もコンタクトもゲートも
見ていない。チップとして正しいかは PDK のデッキ
（`TR-1um/libs.tech/klayout/tech/drc/run.drc`、00_Layers + 01_Basics +
02_Device + 03_Electrical + 本体の 357 行）を当てないと分からない。

これを入れた経緯（2026-09-14）: RING_OSC を `ly.read()` でそのまま取り込んだら、
RING_OSC の中の**旧世代 STDCELL**（prBoundary 64.8、こちらは 59.4）が
同名でコア側のセルを上書きし、**チップの DRC が 8,449 件**になった。
`drc_check_nrow_fm.py` は M1/M2/V1 しか見ないので 0 件のまま素通りしていた。

  PDK の場所: 環境変数 `TR1UM_PDK`、無ければ i2c_config の探索と同じ順。
  KLayout:    `klayout` コマンド（`-b` バッチ）。**0.29 以上が要る**。
              0.28 には `size_inside` が無く 02_Device.drc で止まるので、
              その 3 行を外した写しを作って流す（`--allow-old-klayout`）。
              **外した分だけ検査が緩い**ので、最終判断は新しい KLayout で。
"""
from __future__ import annotations
import argparse, collections, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402


def pdk_drc_dir():
    env = os.environ.get("TR1UM_PDK")
    cands = []
    if env:
        cands += [os.path.join(env, "libs.tech", "klayout", "tech", "drc"),
                  os.path.join(env, "klayout", "tech", "drc")]
    cands += [os.path.expanduser("~/Dropbox/91_OpenPDK/TR-1um/libs.tech/klayout/tech/drc"),
              os.path.join(cfg.ROOT, "TR-1um", "libs.tech", "klayout", "tech", "drc"),
              os.path.expanduser("~/TR-1um/libs.tech/klayout/tech/drc")]
    for c in cands:
        if os.path.exists(os.path.join(c, "run.drc")):
            return c
    raise SystemExit("PDK の DRC デッキが見つからない。TR1UM_PDK を向けてください。\n"
                     f"  試した場所: {cands}")


def klayout_version(exe):
    try:
        out = subprocess.run([exe, "-v"], capture_output=True, text=True).stdout
        m = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
        return tuple(int(v) for v in m.groups()) if m else (0, 0, 0)
    except FileNotFoundError:
        raise SystemExit(f"{exe} が無い。KLayout を入れるか KLAYOUT=... で指定してください")


def patched_deck(src_dir):
    """0.28 用に `size_inside` を使う行を外した写しを作る。"""
    d = tempfile.mkdtemp(prefix="tr1um_drc_")
    shutil.copytree(src_dir, d, dirs_exist_ok=True)
    n = 0
    for f in ("02_Device.drc", "run.drc"):
        p = os.path.join(d, f)
        if not os.path.exists(p):
            continue
        out = []
        for ln in open(p):
            ln = ln.rstrip("\n")
            if "size_inside" in ln and not ln.lstrip().startswith("#"):
                out.append("# [旧 KLayout のため外した] " + ln); n += 1
            elif "BG_CO_coverage" in ln and not ln.lstrip().startswith("#"):
                out.append("# [同上] " + ln); n += 1
            else:
                out.append(ln)
        open(p, "w").write("\n".join(out) + "\n")
    print(f"  ** KLayout が古いので `size_inside` を使う {n} 行を外した写しで流す。"
          f"その分だけ検査は緩い。")
    return d


def summarize(path):
    if not os.path.exists(path):
        print("  レポートが出ていない"); return 1
    t = open(path, errors="replace").read()
    items = re.findall(r"<item>.*?</item>", t, re.S)
    cats = re.findall(r"<category>([^<]*)</category>", t)
    print(f"\n  違反 {len(items)} 件")
    for k, v in collections.Counter(cats).most_common():
        print(f"    {v:6d}  {k.strip(chr(39))}")
    for it in items[:5]:
        m = re.search(r"<value>([^<]*)</value>", it)
        if m:
            print(f"      {re.sub(chr(92)+'s+', ' ', m.group(1))[:120]}")
    return 1 if items else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds")
    ap.add_argument("top_cell", nargs="?", default=None)
    ap.add_argument("-r", "--report", default=None)
    ap.add_argument("--allow-old-klayout", action="store_true",
                    help="0.29 未満でも size_inside を外した写しで流す")
    a = ap.parse_args()

    top = a.top_cell or (cfg.CHIP_TOP_CELL if "/chip/" in a.gds else cfg.TOP_CELL_NAME)
    # **絶対パスにする。** klayout はレポートを自分のカレントから解決するので、
    # 相対パスだと「流れたのにレポートが無い」になる。
    rep = os.path.abspath(a.report or os.path.splitext(a.gds)[0] + "_drc.lyrdb")
    gds = os.path.abspath(a.gds)
    exe = os.environ.get("KLAYOUT", "klayout")
    ver = klayout_version(exe)
    deck = pdk_drc_dir()
    print(f"DRC: {os.path.relpath(a.gds, cfg.ROOT)}  top={top}")
    print(f"  KLayout {'.'.join(map(str, ver))} / デッキ {deck}")
    if ver < (0, 29, 0):
        if not a.allow_old_klayout:
            raise SystemExit("  ** KLayout 0.29 以上が要る（02_Device.drc の size_inside）。\n"
                             "     どうしても流すなら --allow-old-klayout（検査が緩くなる）")
        deck = patched_deck(deck)

    r = subprocess.run([exe, "-b", "-r", os.path.join(deck, "run.drc"),
                        "-rd", f"input={gds}", "-rd", f"top_cell={top}",
                        "-rd", f"report={rep}"], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit(f"  ** klayout が {r.returncode} で終了した")
    print(f"  レポート {os.path.relpath(rep, cfg.ROOT)}")
    return summarize(rep)


if __name__ == "__main__":
    sys.exit(main())

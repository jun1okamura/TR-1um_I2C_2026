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
    cands += [
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
    """0.28 で流せるように `size_inside` / `steps` を使う行を書き換えた写し。

    どちらも KLayout 0.29 で入った。**外し方を間違えると結果が変わる**ので
    3 通りに分ける。

      1. ルール行（`.output(...)` を含む）は**丸ごとコメントアウト**する。
         引数だけ外すと `size_inside` の制約が消えて別物の検査になる。
         実際、`M1P.PE`（パッドの引き出し）で引数だけ外したら、金属の
         外まで太ってしまって**偽の違反が 36 件**出た（2026-09-14）。
         -> その分だけ検査は緩い。最終判断は 0.29 以上で。
      2. `BG_CO_coverage` は代入だが使っているのも同じルール 1 行だけなので、
         両方コメントアウトする。
      3. `RPSD`（`run_mdp.drc`）は代入で、後ろの 195 行目で使われている。
         コメントアウトすると `NameError` になるので**中身を差し替える**:

             RPSD = RR - (CO & RR).sized(4.2-1.0, size_inside(SG.holes), …)
                 -> RPSD = RR

         これは抵抗まわりの P+ ブロック領域で、`RR` は抵抗の活性層
         `AR`(3,3) から作る。**この設計には抵抗が無い**（GDS に 3/3・3/4・
         8/2 が 1 個も入っていない）ので `RR` は空。空から何を引いても空
         なので、この置き換えで出来上がるマスクは変わらない。
    """
    d = tempfile.mkdtemp(prefix="tr1um_drc_")
    shutil.copytree(src_dir, d, dirs_exist_ok=True)
    n = 0
    for f in ("02_Device.drc", "run.drc", "run_mdp.drc", "run_IP62.drc"):
        p = os.path.join(d, f)
        if not os.path.exists(p):
            continue
        out = []
        for ln in open(p):
            ln = ln.rstrip("\n")
            bare = ln.lstrip()
            if bare.startswith("#") or ("size_inside" not in ln
                                        and "BG_CO_coverage" not in ln):
                out.append(ln)
                continue
            n += 1
            if "BG_CO_coverage" in ln or ".output(" in ln:
                out.append("# [旧 KLayout のため外した] " + ln)
            elif re.match(r"\s*RPSD\s*=", ln):
                out.append("RPSD = RR   # [旧 KLayout: この設計に抵抗は無いので"
                           " RR は空。元は RR - (CO & RR).sized(…size_inside…)]")
            else:
                raise SystemExit(
                    f"{f} に知らない `size_inside` の使い方がある。外し方を"
                    f"決めずに流すと結果が変わるので止める:\n    {ln}")
        open(p, "w").write("\n".join(out) + "\n")
    print(f"  ** KLayout が古いので `size_inside` / `steps` を使う {n} 行を"
          f"書き換えた写しで流す。ルール行はコメントアウトしているので"
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

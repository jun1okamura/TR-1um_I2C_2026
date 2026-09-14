#!/usr/bin/env python3
"""lvs_pdk.py -- **PDK の本物の LVS デッキ**を当てて結果を要約する。

  usage: python3 scripts/pnr/lvs_pdk.py <gds> [top_cell] [-r report.lvsdb]
         python3 scripts/pnr/lvs_pdk.py layout/chip/step3_top_pins.gds

`scripts/pnr/lvs_pnr.py` は klayout.db を Python から叩いて**素子とネットの
グラフ同型だけ**を見る。デバイス抽出のルール（どの拡散が MOS で、どの
コンタクトがどのネットか）は PDK のデッキが持っているので、テープアウト
前の最終判断は
`TR-1um/libs.tech/klayout/tech/lvs/run.lvs`（01_Extract + 02_Extract +
03_Combiner + 04_Custom + 05_Compare）を当てて出す。

デッキの流儀（`05_Compare.lvs` 21 行目）:

    Sch_file = "simulation/" + source.cell_name + ".spice"

**GDS を置いたディレクトリの `simulation/<トップセル名>.spice`** を探す。
だから LVS 用のネットリストは `layout/chip/simulation/` に置いてある。

  PDK の場所: 環境変数 `TR1UM_PDK`、無ければ drc_pdk.py と同じ探索順。
  KLayout:    `klayout` コマンド（`-b` バッチ）。**0.29 以上が要る**。
              LVS デッキも 02_Device.drc を取り込むので、0.28 では
              `size_inside` で止まる。`--allow-old-klayout` でその行を
              外した写しを作って流せるが、**外した分だけ緩い**。
"""
from __future__ import annotations
import argparse, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402
import drc_pdk                                              # noqa: E402


def pdk_lvs_dir():
    """DRC デッキの隣の `lvs/`。"""
    d = os.path.join(os.path.dirname(drc_pdk.pdk_drc_dir()), "lvs")
    if not os.path.exists(os.path.join(d, "run.lvs")):
        raise SystemExit(f"PDK の LVS デッキが見つからない: {d}")
    return d


def patched_tech(lvs_dir):
    """0.28 用に `size_inside` を外した写しを `tech/` ごと作る。

    `run.lvs` は `../drc/00_Layers.drc` と `../drc/02_Device.drc` を
    取り込むので、lvs/ だけ写しても足りない。tech/ を丸ごと写す。"""
    tech = os.path.dirname(lvs_dir)
    d = tempfile.mkdtemp(prefix="tr1um_lvs_")
    shutil.copytree(tech, d, dirs_exist_ok=True)
    n = 0
    for rel in ("drc/02_Device.drc", "drc/run.drc", "lvs/run.lvs"):
        p = os.path.join(d, rel)
        if not os.path.exists(p):
            continue
        out = []
        for ln in open(p):
            ln = ln.rstrip("\n")
            if (("size_inside" in ln or "BG_CO_coverage" in ln)
                    and not ln.lstrip().startswith("#")):
                out.append("# [旧 KLayout のため外した] " + ln); n += 1
            else:
                out.append(ln)
        open(p, "w").write("\n".join(out) + "\n")
    print(f"  ** KLayout が古いので `size_inside` を使う {n} 行を外した写しで流す。"
          f"その分だけ検査は緩い。")
    return os.path.join(d, "lvs")


def summarize(out, rep):
    """デッキの標準出力から合否を拾う。"""
    ok = re.search(r"LVS\s*:?\s*(match|OK|success)", out, re.I)
    ng = re.findall(r"^.*(?:mismatch|not match|MISMATCH|ERROR|not found).*$",
                    out, re.M)
    tail = [l for l in out.splitlines() if l.strip()][-25:]
    print()
    for l in tail:
        print("  " + l)
    if os.path.exists(rep):
        print(f"\n  レポート {os.path.relpath(rep, cfg.ROOT)}"
              f"（{os.path.getsize(rep) // 1024} KB）")
    if ng and not ok:
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds")
    ap.add_argument("top_cell", nargs="?", default=None)
    ap.add_argument("-r", "--report", default=None)
    ap.add_argument("--netlist-only", action="store_true",
                    help="抽出だけして比較しない")
    # デッキは `<GDS のディレクトリ>/simulation/<トップ>.spice` しか見ない。
    # コアや RING_OSC のソースも layout/chip/simulation/ にまとめてあるので、
    # 一時ディレクトリに GDS と simulation/ を並べてから流せるようにする。
    ap.add_argument("--sch", default=None,
                    help="ソースネットリストを明示する（既定: GDS の隣の "
                         "simulation/<トップ>.spice）")
    ap.add_argument("--allow-old-klayout", action="store_true")
    # `flag_missing_ports` は KLayout 0.29 以降の LVS の機能。0.28 だと
    # 05_Compare.lvs の strict port モードが NameError で落ちるので、
    # 古い KLayout ではこちらに倒す（トップピンの本数と名前は
    # `lvs_pnr.py` が別途見ている）。
    ap.add_argument("--ignore-top-ports", action="store_true",
                    help="デッキの strict port モードを切る（古い KLayout 用）")
    a = ap.parse_args()

    top = a.top_cell or (cfg.CHIP_TOP_CELL if "/chip/" in a.gds else cfg.TOP_CELL_NAME)
    gds = os.path.abspath(a.gds)
    rep = os.path.abspath(a.report or os.path.splitext(a.gds)[0] + ".lvsdb")
    sch = a.sch or os.path.join(os.path.dirname(gds), "simulation",
                                top + ".spice")
    if a.sch:
        stage = tempfile.mkdtemp(prefix="tr1um_lvsin_")
        os.makedirs(os.path.join(stage, "simulation"))
        shutil.copy(gds, os.path.join(stage, os.path.basename(gds)))
        shutil.copy(sch, os.path.join(stage, "simulation", top + ".spice"))
        gds = os.path.join(stage, os.path.basename(gds))
    sch = os.path.abspath(sch)
    if not a.netlist_only and not os.path.exists(sch):
        raise SystemExit(f"デッキが探すソースが無い: {sch}\n"
                         f"  先に scripts/pnr/mkchipnet.py を流してください")
    exe = os.environ.get("KLAYOUT", "klayout")
    ver = drc_pdk.klayout_version(exe)
    deck = pdk_lvs_dir()
    print(f"LVS: {os.path.relpath(a.gds, cfg.ROOT)}  top={top}")
    print(f"  KLayout {'.'.join(map(str, ver))} / デッキ {deck}")
    print(f"  ソース  {os.path.relpath(sch, cfg.ROOT)}")
    if ver < (0, 29, 0):
        if not a.allow_old_klayout:
            raise SystemExit("  ** KLayout 0.29 以上が要る（02_Device.drc の size_inside）。\n"
                             "     どうしても流すなら --allow-old-klayout（検査が緩くなる）")
        deck = patched_tech(deck)

    cmd = [exe, "-b", "-r", os.path.join(deck, "run.lvs"),
           "-rd", f"input={gds}", "-rd", f"top_cell={top}",
           "-rd", f"report={rep}"]
    if a.netlist_only:
        cmd += ["-rd", "netlist_only=true"]
    if a.ignore_top_ports or ver < (0, 29, 0):
        cmd += ["-rd", "ignore_top_ports_mismatch=true"]
        print("  ** strict port モードを切って流す（flag_missing_ports は "
              "0.29 以降）。トップピンは lvs_pnr.py が別途照合している。")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-4000:]); print(r.stderr[-2000:])
        raise SystemExit(f"  ** klayout が {r.returncode} で終了した")
    return summarize(r.stdout, rep)


if __name__ == "__main__":
    sys.exit(main())

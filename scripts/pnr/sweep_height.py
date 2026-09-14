#!/usr/bin/env python3
"""sweep_height.py -- コア高を詰めるための探索。

  usage: python3 scripts/pnr/sweep_height.py
         python3 scripts/pnr/sweep_height.py --cases 4:5:1 5:5:1 5:5:2
         （ケースは `行数:PRL_MIN_PINS:シード`）

`sweep_seed.py` が「短絡が最少の配置」を選ぶのに対し、こちらは
**フロアプランのパラメタを振って、短絡 0 のまま最も低くなる組合せ**を探す。
step10 まで通し、最後に GDS の実 BBOX を測る（設定値ではなく実測）。

見る値:
  高さ   step10 GDS の top cell の BBOX 高さ（帯込み。これがチップに載る）
  行     行スタックの圧縮後高さ
  track  各チャネルで残ったトラック数
  短絡   verify_connectivity の PROBLEM 件数
  DRC    M1/M2 の width/space + V1 の 4 項目の合計
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402


def run(cmd, env):
    return subprocess.run([sys.executable] + cmd, cwd=cfg.ROOT,
                          capture_output=True, text=True,
                          env={**os.environ, **env})


def measure_gds(path):
    """step10 の GDS を実測する。設定値を信用しない。"""
    import klayout.db as db
    ly = db.Layout()
    ly.read(path)
    top = ly.cell(cfg.TOP_CELL_NAME)
    b = top.dbbox()
    return round(b.height(), 1), round(b.width(), 1)


def one(n_rows, prl, seed, pitch=None, ppad=None):
    t0 = time.time()
    env = {"TD4_N_ROWS": str(n_rows), "TD4_PRL_MIN_PINS": str(prl)}
    if pitch:
        env["TD4_TRACK_PITCH"] = str(pitch)
    if ppad:
        env["TD4_PROTECT_PAD"] = str(ppad)
    r = run([os.path.join(HERE, "place.py"), "--seed", str(seed)], env)
    if r.returncode:
        return dict(ok=False, why=(r.stdout + r.stderr).strip().split("\n")[-1][:90])
    r2 = run([os.path.join(HERE, "route.py"), "--from", "5"], env)
    log = r2.stdout + r2.stderr
    if r2.returncode:
        return dict(ok=False, why=log.strip().split("\n")[-1][:90])
    if "NO SHORTS DETECTED" in log.split("=== step10 ===")[-1]:
        shorts = 0
    else:
        m = re.findall(r"(\d+) PROBLEM\(S\) FOUND", log)
        shorts = int(m[-1]) if m else -1
    drc = 0
    for m in re.finditer(r"width viol=(\d+) space viol=(\d+)", log):
        drc += int(m.group(1)) + int(m.group(2))
    for m in re.finditer(r"^(V1 space viol|V1 enclosed by M[12]<1\.0 viol|"
                         r"V1-GC space<1\.2 viol):\s*(\d+)", log, re.M):
        drc += int(m.group(2))
    # 最後のブロック（step10 の DRC）だけを数え直す
    tail = log.split("=== step10 ===")[-1]
    drc = 0
    for m in re.finditer(r"width viol=(\d+) space viol=(\d+)", tail):
        drc += int(m.group(1)) + int(m.group(2))
    for m in re.finditer(r"viol[^:]*:\s*(\d+)", tail):
        drc += int(m.group(1))
    keep = [int(x) for x in re.findall(r"keeping=(\d+)", tail)]
    stack = re.search(r"core height: [\d.]+ um -> ([\d.]+) um", tail)
    h, w = measure_gds(cfg.SQUEEZED_GDS)
    ports = "ALL 14 TOP-LEVEL PORTS CONNECTED" in log or \
            "TOP-LEVEL PORTS CONNECTED TO THEIR CELL PINS" in log
    return dict(ok=True, rows=n_rows, prl=prl, seed=seed, pitch=pitch, ppad=ppad,
                height=h, width=w,
                stack=float(stack.group(1)) if stack else None,
                keep=keep, tracks=sum(keep), shorts=shorts, drc=drc,
                ports=ports, secs=round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", nargs="+", default=["4:5:1"],
                    help="行数:PRL_MIN_PINS:シード[:トラックピッチ[:保護膨らませ]]")
    ap.add_argument("-o", "--out", default=os.path.join(cfg.LAYOUT, "height_sweep.json"))
    a = ap.parse_args()

    print(f"{'行':>3}{'PRL':>5}{'seed':>5}{'高さ':>9}{'行スタック':>11}"
          f"{'track':>7}{'短絡':>6}{'DRC':>5}{'秒':>6}   チャネル")
    res = []
    for c in a.cases:
        f = c.split(":")
        n_rows, prl, seed = int(f[0]), int(f[1]), int(f[2])
        pitch = float(f[3]) if len(f) > 3 and f[3] else None
        ppad = int(f[4]) if len(f) > 4 and f[4] else None
        d = one(n_rows, prl, seed, pitch, ppad)
        res.append(d)
        if not d["ok"]:
            print(f"{n_rows:>3}{prl:>5}{seed:>5}   --- {d['why']}")
            continue
        tag = f" pitch={d['pitch']}" if d.get('pitch') else ""
        tag += f" ppad={d['ppad']}" if d.get('ppad') else ""
        print(f"{d['rows']:>3}{d['prl']:>5}{d['seed']:>5}{d['height']:>9.1f}"
              f"{d['stack']:>11.1f}{d['tracks']:>7}{d['shorts']:>6}{d['drc']:>5}"
              f"{d['secs']:>6.0f}   {d['keep']}{tag}")
        json.dump(res, open(a.out, "w"), indent=1)
    ok = [d for d in res if d["ok"] and d["shorts"] == 0 and d["drc"] == 0]
    if ok:
        b = min(ok, key=lambda d: d["height"])
        print(f"\n短絡 0 / DRC 0 で最小: 行 {b['rows']} / PRL {b['prl']} / seed "
              f"{b['seed']} → **{b['height']} µm**")
    json.dump(res, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())

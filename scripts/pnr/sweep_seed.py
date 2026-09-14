#!/usr/bin/env python3
"""sweep_seed.py -- 配置のシードを振って、**配線して短絡が最少になる配置**を選ぶ。

  usage: python3 scripts/pnr/sweep_seed.py --seeds 1 2 3 4 5 6 --restarts 800
         python3 scripts/pnr/sweep_seed.py --seeds 7 8 --keep   （最良を残す）

なぜ要るか: 行割当（FM 風分割）も行内順序（バリセンタ）も乱択で、`--seed` を
変えるとカット数と HPWL が変わる。カットが少ない配置ほど行またぎが減り、
行またぎが減ると「M2 の無い x が見つからない」で逃げる回数が減る —— これが
いまの短絡の主因なので、**配置の良し悪しは配線してみないと分からない**。

各シードについて step1〜step6 まで回し、`verify_connectivity` が出す
「SHORT SUSPECTED」の件数で順位を付ける。最後に最良のシードでもう一度
step1〜step4 を作り直して置いていく（`--keep`、既定で有効）。

配線は毎回**別プロセス**で回す。`route_channels_nrow_fm` はモジュール変数に
状態を持つので、同じプロセスで繰り返すと前の回の残りが混ざる。
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402


def run(cmd, env=None):
    return subprocess.run([sys.executable] + cmd, cwd=cfg.ROOT,
                          capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def one(seed, restarts, passes, tol):
    t0 = time.time()
    r = run([os.path.join(HERE, "place.py"), "--seed", str(seed),
             "--restarts", str(restarts), "--order-passes", str(passes),
             "--balance-tol", str(tol)])
    if r.returncode:
        return dict(seed=seed, ok=False, why=r.stdout.strip().split("\n")[-1][:90])
    m = re.search(r"チャネル交差 \[([^\]]*)\]", r.stdout)
    cross = [int(x) for x in m.group(1).split(",")] if m else []
    hp = re.search(r"HPWL \d+ → (\d+)", r.stdout)
    fill = re.findall(r"行: ([\d., ]+) um", r.stdout)

    r2 = run([os.path.join(HERE, "route.py"), "--from", "5", "--to", "6"])
    log = r2.stdout + r2.stderr
    # **短絡 0 のときは "PROBLEM(S) FOUND" が出ない。** 以前はそれを
    # 「配線が落ちた」と誤判定して、一番良いシードを捨てていた
    # （実測: seed 1 と 9 が 0 件なのに `---` 表示、seed 8 の 1 件を最良と
    #  報告していた）。
    if "NO SHORTS DETECTED" in log:
        n = 0
    elif "PROBLEM(S) FOUND" in log:
        n = int(re.search(r"(\d+) PROBLEM\(S\) FOUND", log).group(1))
    else:
        return dict(seed=seed, ok=False, cross=cross,
                    why=(log.strip().split("\n")[-1][:90] or "配線が落ちた"))
    nomac = len([l for l in log.splitlines()
                 if "SHORT SUSPECTED" in l and "u_mem" not in l])
    warn = len(re.findall(r"no clear X found for row", log))
    return dict(seed=seed, ok=True, shorts=n, shorts_nomacro=nomac,
                row_fail=warn, cross=cross, sum_cross=sum(cross),
                hpwl=int(hp.group(1)) if hp else None,
                secs=round(time.time() - t0, 1))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5, 6])
    ap.add_argument("--restarts", type=int, default=800)
    ap.add_argument("--order-passes", type=int, default=50)
    ap.add_argument("--balance-tol", type=float, default=0.02)
    ap.add_argument("--no-keep", action="store_true",
                    help="最後に最良シードで配置を作り直さない")
    ap.add_argument("-o", "--out", default=os.path.join(cfg.LAYOUT, "seed_sweep.json"))
    a = ap.parse_args()

    print(f"シード掃引: {a.seeds}  restarts={a.restarts} passes={a.order_passes} "
          f"tol={a.balance_tol}")
    print(f"{'seed':>5}{'短絡':>6}{'うちマクロ外':>13}{'行またぎ失敗':>13}"
          f"{'交差合計':>10}{'HPWL':>9}{'秒':>7}")
    res = []
    for s in a.seeds:
        d = one(s, a.restarts, a.order_passes, a.balance_tol)
        res.append(d)
        if not d["ok"]:
            print(f"{s:>5}   ---  {d.get('why','')}")
            continue
        print(f"{s:>5}{d['shorts']:>6}{d['shorts_nomacro']:>13}"
              f"{d['row_fail']:>13}{d['sum_cross']:>10}{d['hpwl']:>9}"
              f"{d['secs']:>7.0f}")
    ok = [d for d in res if d["ok"]]
    json.dump(res, open(a.out, "w"), indent=1)
    if not ok:
        print("全滅")
        return 1
    best = min(ok, key=lambda d: (d["shorts"], d["sum_cross"], d["hpwl"]))
    print(f"\n最良: seed={best['seed']}  短絡 {best['shorts']} 件 "
          f"(交差合計 {best['sum_cross']}, HPWL {best['hpwl']})")
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    if not a.no_keep:
        print(f"seed={best['seed']} で配置を作り直す")
        r = run([os.path.join(HERE, "place.py"), "--seed", str(best["seed"]),
                 "--restarts", str(a.restarts),
                 "--order-passes", str(a.order_passes),
                 "--balance-tol", str(a.balance_tol)])
        print(r.stdout.strip().split("\n")[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())

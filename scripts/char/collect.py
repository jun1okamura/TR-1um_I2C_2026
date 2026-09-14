#!/usr/bin/env python3
"""runjobs.sh が集めた results.txt を char/*.json に落とす。

  usage: python3 collect.py [-p pack ディレクトリ]

results.txt の 1 行は `タグ 測定名 値`。タグから jobs.json を引いて、
どのセルのどの表のどの升目かを決める。測れなかった点は None のまま残す
（mklib.py が同じ行の直近値で埋め、verify_lib.py が欠損として報告する）。

setup/hold は二分探索ではなく**掃引**の結果から境界を出す。
dt を大きくすると必ず安全側になるので、失敗した最大の dt のすぐ上が境界。
掃引点は 0 付近が 0.25ns 刻みなので、8 回の二分探索より分解能が良い。
"""
from __future__ import annotations
import argparse, json, os, sys
from collections import defaultdict
import cellspec
import char_seq
from charlib import HERE, VDD, SLEWS, LOADS, SLEWS_C, arcs_of


def read_results(path):
    """タグ -> {測定名: 値} 。異常終了は __rc として残る。"""
    res = defaultdict(dict)
    n = 0
    for ln in open(path):
        p = ln.split()
        if len(p) != 3:
            continue
        try:
            res[p[0]][p[1]] = float(p[2])
        except ValueError:
            continue
        n += 1
    return res, n


# --- 組合せ -----------------------------------------------------------------
def build_comb(cell, res):
    outs = cellspec.COMB[cell]
    arclist = arcs_of(cell, outs)
    d = {"cell": cell, "arcs": [], "cap": {}}
    for opin, ipin, side, sense in arclist:
        n = len(SLEWS)
        arc = {"related_pin": ipin, "pin": opin, "sense": sense,
               "cell_rise": [None] * n, "cell_fall": [None] * n,
               "rise_transition": [None] * n, "fall_transition": [None] * n}
        for si in range(n):
            for out_rise in (True, False):
                v = res.get(f"{cell}_{ipin}_{opin}_s{si}_{'r' if out_rise else 'f'}", {})
                dk = "r" if out_rise else "f"
                dl = [v.get(f"d{dk}{k}") for k in range(len(LOADS))]
                tl = [v.get(f"t{dk}{k}") for k in range(len(LOADS))]
                if out_rise:
                    arc["cell_rise"][si] = dl; arc["rise_transition"][si] = tl
                else:
                    arc["cell_fall"][si] = dl; arc["fall_transition"][si] = tl
        d["arcs"].append(arc)
    for opin, ipin, side, sense in arclist:
        if ipin in d["cap"]:
            continue
        q = res.get(f"{cell}_{ipin}_cap", {}).get("q")
        d["cap"][ipin] = abs(q) / VDD * 1e15 if q is not None else None
    return d


# --- 順序 -------------------------------------------------------------------
def boundary(pts):
    """(dt, 取り込めたか) の列から境界を返す。

    dt が大きいほど安全側。失敗した最大の dt のすぐ上の点が境界。
    返り値は (値, 注記)。
      すべて成功 -> 掃引の下端。実際の境界はもっと下（余裕がある）
      すべて失敗 -> None
    """
    pts = sorted(pts)
    ok = [(dt, v) for dt, v in pts if v is not None]
    if not ok:
        return None, "測れず"
    if all(v for _, v in ok):
        return ok[0][0], "掃引の下端でも取り込めた（実際の境界はさらに下）"
    if not any(v for _, v in ok):
        return None, "掃引の上端でも取り込めない"
    # 上から見て、最初に失敗する点を探す
    last_fail = max(dt for dt, v in ok if not v)
    above = [dt for dt, v in ok if dt > last_fail]
    if not above:
        return None, "掃引の上端で失敗"
    note = ""
    # 境界より上に失敗点が混ざっていないか（混ざっていたら単調でない = 怪しい）
    below_ok = [dt for dt, v in ok if dt < last_fail and v]
    if below_ok:
        note = f"単調でない（{min(below_ok):g}ns では取り込めている）"
    return min(above), note


def build_seq(cell, res, dt_sweep, warn):
    spec = char_seq.SEQ[cell]
    d = {"cell": cell, "seq": True, "q": spec["q"], "d": spec["d"],
         "ckq": {"cell_rise": [], "cell_fall": [],
                 "rise_transition": [], "fall_transition": []},
         "setup": {"rise": [], "fall": []}, "hold": {"rise": [], "fall": []},
         "cap": {}}
    for si in range(len(SLEWS)):
        for d_rise in (True, False):
            v = res.get(f"{cell}_ckq_s{si}_{'r' if d_rise else 'f'}", {})
            dl = [v.get(f"d{k}") for k in range(len(LOADS))]
            tl = [v.get(f"t{k}") for k in range(len(LOADS))]
            if d_rise:
                d["ckq"]["cell_rise"].append(dl); d["ckq"]["rise_transition"].append(tl)
            else:
                d["ckq"]["cell_fall"].append(dl); d["ckq"]["fall_transition"].append(tl)
    for d_rise in (True, False):
        key = "rise" if d_rise else "fall"
        for mode in ("setup", "hold"):
            rows = []
            for di in range(len(SLEWS_C)):
                row = []
                for ci in range(len(SLEWS_C)):
                    pts = []
                    for k, dt in enumerate(dt_sweep):
                        tag = (f"{cell}_{mode}_{di}_{ci}_"
                               f"{'r' if d_rise else 'f'}_{k:03d}")
                        vq = res.get(tag, {}).get("vq")
                        pts.append((dt, None if vq is None
                                    else (vq > VDD / 2) == bool(d_rise)))
                    val, note = boundary(pts)
                    if note:
                        warn.append(f"{cell} {mode} {key} "
                                    f"データ遷移 {SLEWS_C[di]}ns / クロック遷移 "
                                    f"{SLEWS_C[ci]}ns: {note}")
                    row.append(val)
                rows.append(row)
            d[mode][key] = rows
    return d


# --- 入力容量の較正 ---------------------------------------------------------
def apply_calib(cells, res, out):
    import calib_cap
    inv = out.get("INV_X1")
    if not inv:
        print("** INV_X1 の結果が無いので入力容量の較正はしない")
        return
    row = inv["arcs"][0]["cell_fall"][SLEWS.index(calib_cap.SLEW_IN)]
    print(f"\n--- 入力容量の較正（基準ドライバ INV_X1 / 入力遷移 "
          f"{calib_cap.SLEW_IN}ns の cell_fall 行を逆引き）---")
    print(f"  {'cell':<10}{'pin':<8}{'電荷から':>10}{'較正後':>9}{'比':>7}   N=2/4 のばらつき")
    for cell in cells:
        d = out[cell]
        if d.get("seq"):
            pins = (["CK"] + cellspec.SEQ_PINS[cell]["data"]
                    + cellspec.SEQ_PINS[cell]["async"])
            raws = {p: None for p in pins}
        else:
            raws = d["cap"]
        cal = {}
        for pin, raw in raws.items():
            est = []
            for n in calib_cap.FANOUTS:
                t = res.get(f"cal_{cell}_{pin}_{n}", {}).get("d")
                if t is None:
                    continue
                c = calib_cap.invert_row(LOADS, row, t)
                if c:
                    est.append(c / n)
            if not est:
                cal[pin] = raw
                print(f"  {cell:<10}{pin:<8}{(raw or 0):9.1f}{'':>9}{'':>7}   ** 測れず")
                continue
            v = sum(est) / len(est)
            cal[pin] = v
            spread = (max(est) - min(est)) / v if len(est) > 1 else 0.0
            ratio = f"{v/raw:7.2f}" if raw else f"{'-':>7}"
            print(f"  {cell:<10}{pin:<8}{(raw or 0):9.1f}{v:9.1f}{ratio}   {spread:.1%}"
                  f"{'  ** ばらつきが大きい' if spread > 0.15 else ''}")
        d["cap_charge"] = d.get("cap", {})
        d["cap_cal"] = cal


# --- 検算用 -----------------------------------------------------------------
def build_verify(res, jobs):
    """verify_lib.py が ngspice を回さずに済むよう、格子外とファンアウトの
    実測値だけを別ファイルに抜き出しておく。"""
    import genjobs
    v = {"offgrid": {}, "fanout": {}}
    for j in jobs:
        if j["kind"] == "verify":
            tag = f"vfy_{j['cell']}_{'r' if j['rise'] else 'f'}"
            got = res.get(tag, {}).get("dr0" if j["rise"] else "df0")
            v["offgrid"].setdefault(j["cell"], {})["r" if j["rise"] else "f"] = got
        elif j["kind"] == "fanout":
            v["fanout"][str(j["n"])] = res.get(f"vfy_fo{j['n']}", {}).get("d")
    v["slew"] = genjobs.VFY_SLEW
    v["cl"] = genjobs.VFY_CL
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--pack", default=f"{HERE}/pack")
    ap.add_argument("-r", "--results", default=None)
    a = ap.parse_args()
    jf = json.load(open(f"{a.pack}/jobs.json"))
    rpath = a.results or f"{a.pack}/results.txt"
    if not os.path.exists(rpath):
        sys.exit(f"results.txt が無い: {rpath}")
    res, nval = read_results(rpath)

    njob = len(jf["jobs"])
    ngot = sum(1 for j in jf["jobs"] if j["tag"] in res)
    nrc = sum(1 for t, v in res.items() if "__rc" in v)
    print(f"デッキ {njob} 本 / 結果のあるもの {ngot} 本 / 測定値 {nval} 個")
    if ngot < njob:
        miss = [j["tag"] for j in jf["jobs"] if j["tag"] not in res][:8]
        print(f"** 結果の無いデッキ {njob-ngot} 本: {', '.join(miss)} ...")
    if nrc:
        print(f"** ngspice が異常終了したデッキ {nrc} 本")

    os.makedirs(f"{HERE}/char", exist_ok=True)
    out, warn = {}, []
    for cell in jf["comb"]:
        out[cell] = build_comb(cell, res)
    for cell in jf["seq"]:
        out[cell] = build_seq(cell, res, jf["dt_sweep"], warn)
    apply_calib(list(out), res, out)

    for cell, d in out.items():
        json.dump(d, open(f"{HERE}/char/{cell}.json", "w"), indent=1)
    json.dump(build_verify(res, jf["jobs"]),
              open(f"{HERE}/char/_verify.json", "w"), indent=1)

    # --- 概要 ---
    print(f"\n--- 代表値（入力遷移 0.6ns / 負荷 50fF）---")
    si, li = SLEWS.index(0.6), LOADS.index(50)
    for cell in jf["comb"]:
        a_ = out[cell]["arcs"][0]
        f = lambda t: (f"{t[si][li]*1e9:.2f}" if t[si] and t[si][li] is not None else "-")
        print(f"  {cell:<10}{a_['related_pin']}->{a_['pin']:<4} "
              f"rise {f(a_['cell_rise']):>6} / fall {f(a_['cell_fall']):>6} ns")
    ci = SLEWS_C.index(1.5)
    for cell in jf["seq"]:
        d = out[cell]
        g = lambda t, k=1e9: f"{t*k:.2f}" if t is not None else "-"
        print(f"  {cell:<10}CK->Q  rise {g(d['ckq']['cell_rise'][si][li]):>6} / "
              f"fall {g(d['ckq']['cell_fall'][si][li]):>6} ns   "
              f"setup r {g(d['setup']['rise'][ci][ci],1)} / f {g(d['setup']['fall'][ci][ci],1)}   "
              f"hold r {g(d['hold']['rise'][ci][ci],1)} / f {g(d['hold']['fall'][ci][ci],1)} ns")

    nmiss = 0
    for cell, d in out.items():
        tbls = ([t for a_ in d.get("arcs", []) for t in
                 (a_["cell_rise"], a_["cell_fall"], a_["rise_transition"], a_["fall_transition"])]
                + list(d.get("ckq", {}).values()))
        for t in tbls:
            nmiss += sum(1 for r in t for v in (r or []) if v is None)
    print(f"\n表の欠損 {nmiss} 点")
    if warn:
        print(f"\n--- setup/hold の注記 {len(warn)} 件 ---")
        for w in warn[:30]:
            print(f"  {w}")
        if len(warn) > 30:
            print(f"  ... 他 {len(warn)-30} 件")
    print(f"\nchar/*.json を {len(out)} セル分書いた。次は mklib.py / verify_lib.py。")


if __name__ == "__main__":
    main()

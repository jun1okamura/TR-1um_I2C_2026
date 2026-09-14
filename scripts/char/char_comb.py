#!/usr/bin/env python3
"""組合せセルの NLDM 特性化（cell_rise/fall、rise/fall_transition、入力容量）。

  usage: python3 char_comb.py [セル名 ...]     結果は char/<cell>.json

1 本のデッキに**同じセルを 7 個並べ、負荷だけ変える**。入力遷移時間は
デッキごとに変えるので、1 アークあたり ngspice は 7 回で済む（7x7=49 回ではない）。

測るもの（Liberty の既定に合わせる）:
  遅延      入力 50% -> 出力 50%
  出力遷移  20% -> 80%（`slew_lower/upper_threshold_pct` で申告する）
入力容量は、入力を 0->VDD に振ったときに流れ込む電荷 Q を VDD で割った値。
"""
from __future__ import annotations
import json, os, sys
from concurrent.futures import ProcessPoolExecutor
import cellspec
from charlib import (HERE, VDD, SLEWS, LOADS, TH_DELAY, TH_SLEW_LO, TH_SLEW_HI,
                     header, ports_of, all_ports_of, run_ngspice, arcs_of, pwl_ramp,
                     NPROC, full_ramp, slews_of)

T0 = 100.0            # 入力を振り始める時刻 [ns]
SETTLE = 150.0        # 遷移後に落ち着かせる時間 [ns]
# 最重負荷 CL=800fF でも INV_X1 の遅延は 8ns 程度。150ns あれば十分落ち着く。


def build_delay(cell, opin, ipin, side, slew, rise_in, opins):
    ports = ports_of(cell)
    L = [f"* {cell} {ipin}->{opin} 入力遷移 {slew}ns  -- char_comb.py 生成"]
    L += header(cell)
    # 理想電圧源を 0.1ns で振ると 7 インスタンスぶんのゲート容量で
    # ソルバが落ちる（timestep too small）。微小な直列抵抗で正則化する。
    L.append(f"Vin {ipin}_src 0 {pwl_ramp(T0, slew, rise_in)}")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    for p, v in side.items():
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    for p in ports:
        if p != ipin and p not in side and p not in opins:
            L.append(f"V_{p} {p} 0 0")
    L.append("")
    for k, cl in enumerate(LOADS):
        pl = {p: (f"o{k}_{p}" if p == opin else p) for p in ports}
        L.append("X{0} ".format(k) + " ".join(pl.get(p, p) for p in all_ports_of(cell))
                 + f" {cell}")
        L.append(f"C{k} o{k}_{opin} 0 {cl}f")
    L.append("")
    L.append(f".tran {max(min(slew, 0.5) / 20, 0.02):g}n {T0+full_ramp(slew)+SETTLE:g}n")
    vt = VDD * TH_DELAY / 100
    lo, hi = VDD * TH_SLEW_LO / 100, VDD * TH_SLEW_HI / 100
    trig = "RISE=1" if rise_in else "FALL=1"
    for k in range(len(LOADS)):
        o = f"o{k}_{opin}"
        for edge, tag in (("RISE=1", "r"), ("FALL=1", "f")):
            L.append(f".meas tran d{tag}{k} TRIG v({ipin}) VAL={vt:g} {trig} "
                     f"TARG v({o}) VAL={vt:g} {edge}")
        L.append(f".meas tran tr{k} TRIG v({o}) VAL={lo:g} RISE=1 TARG v({o}) VAL={hi:g} RISE=1")
        L.append(f".meas tran tf{k} TRIG v({o}) VAL={hi:g} FALL=1 TARG v({o}) VAL={lo:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_cap(cell, ipin, side, opins):
    """入力 ipin を 0->VDD に振り、流れ込む電荷から容量を出す"""
    ports = ports_of(cell)
    sl = 2.0
    L = [f"* {cell} {ipin} 入力容量 -- char_comb.py 生成"]
    L += header(cell)
    L.append(f"Vin {ipin}_src 0 {pwl_ramp(T0, sl, True)}")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    for p, v in side.items():
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    for p in ports:
        if p != ipin and p not in side and p not in opins:
            L.append(f"V_{p} {p} 0 0")     # 未使用の入力ピン
    L.append("XU " + " ".join(all_ports_of(cell)) + f" {cell}")
    # 出力を素のままにすると出力が速く振れて Miller 帰還が最大になり、
    # 入力容量が過大に出る。代表負荷（50fF）を付けて測る。
    for p_ in opins:
        L.append(f"CL_{p_} {p_} 0 50f")
    L.append(f".tran 0.02n {T0+full_ramp(sl)+50:g}n")
    L.append(f".meas tran q INTEG i(Vin) FROM={T0:g}n TO={T0+full_ramp(sl):g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def _one(job):
    """遅延デッキ 1 本。プロセスプールから呼ぶのでトップレベル関数にする。"""
    cell, opin, ipin, side, sense, si, slew, out_rise, opins = job
    # 出力を立ち上げるのに必要な入力の向き。negative_unate なら逆。
    rise_in = (not out_rise) if sense == "negative_unate" else out_rise
    vals, _ = run_ngspice(
        build_delay(cell, opin, ipin, side, slew, rise_in, opins),
        f"{cell}_{ipin}_{opin}_s{si}_{'r' if out_rise else 'f'}")
    dk = "r" if out_rise else "f"
    d = [vals.get(f"d{dk}{k}") for k in range(len(LOADS))]
    t = [vals.get(f"tr{k}" if out_rise else f"tf{k}") for k in range(len(LOADS))]
    return (opin, ipin, si, out_rise, d, t)


def _cap(job):
    cell, ipin, side, opins = job
    vals, _ = run_ngspice(build_cap(cell, ipin, side, opins), f"{cell}_{ipin}_cap")
    q = vals.get("q")
    return ipin, (abs(q) / VDD * 1e15 if q is not None else None)


def characterize(cell, pool=None):
    outs = cellspec.COMB[cell]
    opins = set(outs)
    arclist = arcs_of(cell, outs)
    slews = slews_of(cell)          # BUFTH だけ 1000ns まで（charlib.CELL_SLEWS）
    jobs, capjobs, seen = [], [], set()
    for opin, ipin, side, sense in arclist:
        for si, slew in enumerate(slews):
            for out_rise in (True, False):
                jobs.append((cell, opin, ipin, side, sense, si, slew, out_rise, opins))
        if ipin not in seen:
            seen.add(ipin)
            capjobs.append((cell, ipin, side, opins))

    mapper = pool.map if pool else map
    got = list(mapper(_one, jobs))
    res = {"cell": cell, "slews": slews, "arcs": [],
           "cap": dict(mapper(_cap, capjobs))}
    for opin, ipin, side, sense in arclist:
        n = len(slews)
        arc = {"related_pin": ipin, "pin": opin, "sense": sense,
               "cell_rise": [None]*n, "cell_fall": [None]*n,
               "rise_transition": [None]*n, "fall_transition": [None]*n}
        for o, i, si, out_rise, d, t in got:
            if o != opin or i != ipin:
                continue
            if out_rise:
                arc["cell_rise"][si] = d; arc["rise_transition"][si] = t
            else:
                arc["cell_fall"][si] = d; arc["fall_transition"][si] = t
        res["arcs"].append(arc)
    return res


def main():
    # .lib に載せるのは LEF で CLASS CORE のセル（P&R が行に置くもの）だけ。
    # ADDBUF / REGBUF はアレイ内部の CLASS BLOCK なので特性化しない（機能確認は済み）。
    want = sys.argv[1:] or [c for c in sorted(cellspec.COMB)
                            if c not in cellspec.BLOCK_ONLY]
    miss = [c for c in want if not os.path.exists(f"{HERE}/{os.environ.get('TR1UM_CELLDIR','cells').split('/')[-1]}/{c}{os.environ.get('TR1UM_CELLEXT','.spi')}")]
    from check_comb import CELLDIR, CELLEXT
    miss = [c for c in want if not os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")]
    if miss:
        print(f"** ネットリストが無いので特性化しない: {', '.join(miss)}", flush=True)
    want = [c for c in want if c not in miss]
    os.makedirs(f"{HERE}/char", exist_ok=True)
    print(f"{'cell':<10}{'アーク':>5}  {'Cin [fF]':<28} 代表遅延(slew0.6/CL50) [ns]", flush=True)
    pool = ProcessPoolExecutor(max_workers=NPROC)
    for cell in want:
        r = characterize(cell, pool)
        json.dump(r, open(f"{HERE}/char/{cell}.json", "w"), indent=1)
        caps = " ".join(f"{k}:{v:.1f}" for k, v in r["cap"].items() if v is not None)
        # **格子はセルごとに違う**（BUFTH）。既定の SLEWS で添字を引くと別の行を読む。
        si, li = r["slews"].index(0.6), LOADS.index(50)
        a = r["arcs"][0]
        dr, df = a["cell_rise"][si][li], a["cell_fall"][si][li]
        sdr = f"{dr*1e9:.2f}" if dr is not None else "-"
        sdf = f"{df*1e9:.2f}" if df is not None else "-"
        print(f"{cell:<10}{len(r['arcs']):>5}  {caps:<28} rise {sdr} / fall {sdf}", flush=True)
    pool.shutdown()


if __name__ == "__main__":
    main()

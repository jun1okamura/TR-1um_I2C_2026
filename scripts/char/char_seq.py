#!/usr/bin/env python3
"""順序セルの特性化: CK->Q の遅延/遷移（7x7）と setup/hold（3x3）。

  usage: python3 char_seq.py [セル名 ...]     結果は char/<cell>.json

setup / hold は 1 点ごとに**二分探索**が要る。データ端とクロック端の間隔を
詰めていき、「Q が正しい値を取り込める限界」を探す。判定は取り込み後の
Q の電圧（VDD/2 を跨いだか）で行う。格子は SLEWS_C（3 点）に落としてある。

非同期リセット（RSTB）の recovery/removal は今回は測らない。TD4 のリセットは
電源投入時に一度きりで、クロックとの競合が問題にならないため。
"""
from __future__ import annotations
import json, os, sys
import cellspec
from charlib import (HERE, VDD, SLEWS, LOADS, SLEWS_C, TH_DELAY, TH_SLEW_LO,
                     TH_SLEW_HI, header, ports_of, all_ports_of, run_ngspice, pwl_ramp,
                     full_ramp)

T_CK = 200.0        # クロック立上りの 50% 通過時刻 [ns]
SETTLE = 150.0

# セルごとの: データピン, 出力, 非同期ピン(非アクティブ値), 固定する入力
SEQ = {
    "DFF":      dict(d="D", q="Q", qb="QB", idle={}),
    "DFFRB":    dict(d="D", q="Q", qb="QB", idle={"RSTB": 1}),
    "DFFS":     dict(d="D", q="Q", qb="QB", idle={"SET": 0}),
    "MUXDFFRB": dict(d="A", q="Q", qb="QB", idle={"RSTB": 1, "S": 0, "B": 0}),
}


def ramp_at(t50, slew, rise):
    """50% 通過時刻が t50 になる PWL。slew は 20-80% の遷移時間。"""
    tf = full_ramp(slew)
    t0 = t50 - tf / 2
    a, b = (0, VDD) if rise else (VDD, 0)
    return f"PWL(0 {a:g} {t0:g}n {a:g} {t0+tf:g}n {b:g})"


T_PRE = 80.0        # 下地を作る 1 発目のクロック立上り [ns]
T_DSW = 140.0       # そのあとデータを目的の値に変える時刻 [ns]


def build_ckq(cell, spec, ck_slew, d_rise):
    """CK->Q の遅延と出力遷移。負荷 7 点を 1 デッキに並べる。

    **1 発目のクロックで Q を逆の値にしておく**こと。D を最初から目的の値に
    しておくと、DC 動作点でもう Q がその値になっていて、測るべき遷移が
    起きない（CK->Q の立下りが丸ごと測れなかった原因）。
    """
    ports = ports_of(cell)
    q, qb = spec["q"], spec["qb"]
    outs = {q, qb}
    L = [f"* {cell} CK->{q} clk遷移 {ck_slew}ns data={'1' if d_rise else '0'}"]
    L += header(cell)
    # D: 最初は逆の値 -> T_DSW で目的の値へ
    v0, v1 = (0, VDD) if d_rise else (VDD, 0)
    L.append(f"Vd {spec['d']} 0 PWL(0 {v0:g} {T_DSW:g}n {v0:g} {T_DSW+1:g}n {v1:g})")
    for p, v in spec["idle"].items():
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    # **KLayout の抽出は内部ネットもピンに昇格させる**（DFF の CKB/CKP/QM/QS）。
    # 0V で駆動するとフリップフロップが壊れるので、本当の入力ピンだけ固定する。
    real_in = (set(cellspec.SEQ_PINS[cell]["data"])
               | set(cellspec.SEQ_PINS[cell]["async"]) | {"CK"})
    for p in ports:
        if (p in real_in and p not in ("CK", spec["d"])
                and p not in spec["idle"] and p not in outs):
            L.append(f"V_{p} {p} 0 0")
    # 1 発目（T_PRE）で逆の値を取り込み、2 発目（T_CK）が測定対象
    tf = full_ramp(ck_slew)
    L.append(f"Vck CK_src 0 PWL(0 0 {T_PRE-1:g}n 0 {T_PRE:g}n {VDD:g} "
             f"{T_PRE+20:g}n {VDD:g} {T_PRE+21:g}n 0 "
             f"{T_CK-tf/2:g}n 0 {T_CK+tf/2:g}n {VDD:g})")
    # 理想源を急峻に振ると 7 インスタンスぶんのゲート容量でソルバが落ちる
    L.append("Rck CK_src CK 0.001")
    L.append("")
    for k, cl in enumerate(LOADS):
        pl = {p: (f"o{k}_{p}" if p in outs else p) for p in ports}
        L.append(f"X{k} " + " ".join(pl.get(p, p) for p in all_ports_of(cell)) + f" {cell}")
        L.append(f"C{k} o{k}_{q} 0 {cl}f")
        L.append(f"Cb{k} o{k}_{qb} 0 {cl}f")
    L.append("")
    L.append(f".tran {max(min(ck_slew,0.5)/20, 0.02):g}n {T_CK+full_ramp(ck_slew)+SETTLE:g}n")
    vt = VDD * TH_DELAY / 100
    lo, hi = VDD * TH_SLEW_LO / 100, VDD * TH_SLEW_HI / 100
    edge = "RISE=1" if d_rise else "FALL=1"
    for k in range(len(LOADS)):
        o = f"o{k}_{q}"
        # クロックは 2 発あるので RISE=2 が測定対象。Q の遷移も 2 回目。
        L.append(f".meas tran d{k} TRIG v(CK) VAL={vt:g} RISE=2 TARG v({o}) VAL={vt:g} "
                 f"{'RISE=1' if d_rise else 'FALL=1'}")
        if d_rise:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={lo:g} RISE=1 TARG v({o}) VAL={hi:g} RISE=1")
        else:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={hi:g} FALL=1 TARG v({o}) VAL={lo:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


HOLD_SETUP_MARGIN = 60.0   # hold 測定で setup 側に確保する余裕 [ns]


def build_constraint(cell, spec, ck_slew, d_slew, d_rise, dt, mode="setup"):
    """クロック端に対するデータ端の位置を変えて、正しく取り込めるかを見る。

    **setup と hold は別の刺激が要る**（同じ波形で dt を動かすと、hold 側も
    setup と同じ境界を見つけてしまう。最初それで hold = -setup になっていた）。

      setup: D を t_ck - dt で「旧値 -> 新値」に変える。そのまま保持。
             dt を詰めていき、取り込める限界が setup 時間。
      hold : D を十分前（t_ck - 60ns）に新値へ変えて setup は満たしておき、
             **t_ck + dt で旧値へ戻す**。dt を詰めていき、新値を保持できる
             限界が hold 時間。
    """
    ports = ports_of(cell)
    q, qb = spec["q"], spec["qb"]
    outs = {q, qb}
    L = [f"* {cell} {mode} 探索 dt={dt}ns"]
    L += header(cell)
    v_old, v_new = (0, VDD) if d_rise else (VDD, 0)
    if mode == "setup":
        t_d = T_CK - dt
        L.append(f"Vd {spec['d']} 0 {ramp_at(t_d, d_slew, d_rise)}")
    else:
        t_in = T_CK - HOLD_SETUP_MARGIN          # 余裕をもって新値にする
        t_out = T_CK + dt                        # ここで旧値へ戻す
        L.append(f"Vd {spec['d']} 0 PWL(0 {v_old:g} "
                 f"{t_in-d_slew/2:g}n {v_old:g} {t_in+d_slew/2:g}n {v_new:g} "
                 f"{t_out-d_slew/2:g}n {v_new:g} {t_out+d_slew/2:g}n {v_old:g})")
    for p, v in spec["idle"].items():
        L.append(f"V_{p} {p} 0 {v*VDD:g}")
    # **KLayout の抽出は内部ネットもピンに昇格させる**（DFF の CKB/CKP/QM/QS）。
    # 0V で駆動するとフリップフロップが壊れるので、本当の入力ピンだけ固定する。
    real_in = (set(cellspec.SEQ_PINS[cell]["data"])
               | set(cellspec.SEQ_PINS[cell]["async"]) | {"CK"})
    for p in ports:
        if (p in real_in and p not in ("CK", spec["d"])
                and p not in spec["idle"] and p not in outs):
            L.append(f"V_{p} {p} 0 0")
    # 取り込み前に Q を逆の値にしておく（1 発目のクロックで下地を作る）
    t_pre = T_CK - 120
    tf = full_ramp(ck_slew)
    L.append(f"Vck CK_src 0 PWL(0 0 {t_pre-20:g}n 0 {t_pre-19:g}n {VDD:g} "
             f"{t_pre:g}n {VDD:g} {t_pre+1:g}n 0 "
             f"{T_CK-tf/2:g}n 0 {T_CK+tf/2:g}n {VDD:g})")
    L.append("Rck CK_src CK 0.001")
    L.append("")
    L.append("XU " + " ".join(all_ports_of(cell)) + f" {cell}")
    L.append(f"C0 {q} 0 {LOADS[2]}f")
    L.append(f"C1 {qb} 0 {LOADS[2]}f")
    L.append(f".tran 0.05n {T_CK+120:g}n")
    L.append(f".meas tran vq FIND v({q}) AT={T_CK+100:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def captures(cell, spec, ck_slew, d_slew, d_rise, dt, tag, mode="setup"):
    vals, _ = run_ngspice(
        build_constraint(cell, spec, ck_slew, d_slew, d_rise, dt, mode), tag)
    v = vals.get("vq")
    if v is None:
        return None
    return (v > VDD / 2) == bool(d_rise)


def bisect_setup(cell, spec, ck_slew, d_slew, d_rise, lo=-20.0, hi=60.0, n=8):
    """取り込める最小の dt（= setup 時間）。dt が小さいほど厳しい。"""
    tag = f"{cell}_st_{ck_slew}_{d_slew}_{int(d_rise)}"
    if not captures(cell, spec, ck_slew, d_slew, d_rise, hi, tag + "_hi"):
        return None                      # 一番緩い条件でも取り込めない
    if captures(cell, spec, ck_slew, d_slew, d_rise, lo, tag + "_lo"):
        return lo                        # 一番厳しい条件でも取り込める
    for i in range(n):
        mid = (lo + hi) / 2
        if captures(cell, spec, ck_slew, d_slew, d_rise, mid, f"{tag}_{i}"):
            hi = mid
        else:
            lo = mid
    return hi


def bisect_hold(cell, spec, ck_slew, d_slew, d_rise, lo=-20.0, hi=40.0, n=8):
    """クロック端の後、データを戻してよい最短時間（= hold）。

    dt が大きい（データを戻すのが遅い）ほど安全。詰めていって壊れる境界を探す。
    hold が負になることもある（クロックより前に戻しても間に合う = 余裕がある）。
    """
    tag = f"{cell}_hd_{ck_slew}_{d_slew}_{int(d_rise)}"
    if not captures(cell, spec, ck_slew, d_slew, d_rise, hi, tag + "_hi", "hold"):
        return None                      # 一番緩くても保持できない
    if captures(cell, spec, ck_slew, d_slew, d_rise, lo, tag + "_lo", "hold"):
        return lo                        # 一番厳しくても保持できる
    for i in range(n):
        mid = (lo + hi) / 2
        if captures(cell, spec, ck_slew, d_slew, d_rise, mid, f"{tag}_{i}", "hold"):
            hi = mid
        else:
            lo = mid
    return hi


def characterize(cell):
    spec = SEQ[cell]
    res = {"cell": cell, "seq": True, "q": spec["q"], "d": spec["d"],
           "ckq": {"cell_rise": [], "cell_fall": [],
                   "rise_transition": [], "fall_transition": []},
           "setup": {"rise": [], "fall": []}, "hold": {"rise": [], "fall": []},
           "cap": {}}
    for si, sl in enumerate(SLEWS):
        for d_rise in (True, False):
            vals, _ = run_ngspice(build_ckq(cell, spec, sl, d_rise),
                                  f"{cell}_ckq_s{si}_{'r' if d_rise else 'f'}")
            d = [vals.get(f"d{k}") for k in range(len(LOADS))]
            t = [vals.get(f"t{k}") for k in range(len(LOADS))]
            if d_rise:
                res["ckq"]["cell_rise"].append(d); res["ckq"]["rise_transition"].append(t)
            else:
                res["ckq"]["cell_fall"].append(d); res["ckq"]["fall_transition"].append(t)
    for d_rise in (True, False):
        k = "rise" if d_rise else "fall"
        for ds in SLEWS_C:
            rs, rh = [], []
            for cs in SLEWS_C:
                rs.append(bisect_setup(cell, spec, cs, ds, d_rise))
                rh.append(bisect_hold(cell, spec, cs, ds, d_rise))
            res["setup"][k].append(rs)
            res["hold"][k].append(rh)
    return res


def main():
    want = sys.argv[1:] or list(SEQ)
    from check_comb import CELLDIR, CELLEXT
    miss = [c for c in want if not os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")]
    if miss:
        print(f"** ネットリストが無いので特性化しない: {', '.join(miss)}", flush=True)
    want = [c for c in want if c not in miss]
    os.makedirs(f"{HERE}/char", exist_ok=True)
    print(f"{'cell':<10}  CK->Q(slew0.6/CL50) [ns]      setup [ns]        hold [ns]", flush=True)
    for cell in want:
        r = characterize(cell)
        json.dump(r, open(f"{HERE}/char/{cell}.json", "w"), indent=1)
        si, li = SLEWS.index(0.6), LOADS.index(50)
        dr = r["ckq"]["cell_rise"][si][li]; df = r["ckq"]["cell_fall"][si][li]
        ci = SLEWS_C.index(1.5)
        su_r = r["setup"]["rise"][ci][ci]; su_f = r["setup"]["fall"][ci][ci]
        ho_r = r["hold"]["rise"][ci][ci];  ho_f = r["hold"]["fall"][ci][ci]
        s = lambda v, k=1e9: f"{v*k:.2f}" if v is not None else "-"
        print(f"{cell:<10}  rise {s(dr)} / fall {s(df)}      "
              f"r {s(su_r,1)} / f {s(su_f,1)}    r {s(ho_r,1)} / f {s(ho_f,1)}", flush=True)


if __name__ == "__main__":
    main()

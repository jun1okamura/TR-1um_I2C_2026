#!/usr/bin/env python3
"""RSLATCH（NOR 型 SR ラッチ）の特性化。

  usage:
    python3 char_latch.py gen     [-o pack_rslatch]     デッキを書き出す
    python3 char_latch.py collect [-p pack_rslatch]     results.txt -> char/RSLATCH.json

`char_comb.py` / `char_seq.py` と同じ 3 段（生成 → 並列実行 → 回収）に分けてある。
実行は `runjobs.sh -p pack_rslatch` がそのまま使える（`__MODELS__` の埋め込みも同じ）。

## なぜ組合せセル用の char_comb.py で測れないか

`arcs_of()` は真理値関数から「他の入力を固定して当該入力を反転させると出力が変わる
組合せ」を探す。SR ラッチは**状態を持つ**ので真理値関数が書けず、この列挙が成立しない。
さらに測定そのものも、

  * 測る前にラッチを**反対の状態に初期化**しておく必要がある
  * アクティブ端（S↑ / R↑）にしかアークが立たない。S↓ / R↓ では出力は動かない
  * 出力が 2 本あり互いにクロス結合しているので、片方の負荷がもう片方の遅延に効く

の 3 点で組合せセルと違う。ここではそれぞれ、

  * 反対側の入力を t=0 から {T_INIT} ns まで VDD に張って初期化し、{T_REL} ns で放す
  * 立上りアークだけを測り、Liberty には preset / clear のアークとして書く
  * **測る側に負荷を掃引し、反対側には固定 {CL_OTHER} fF を付ける**。この条件を
    .lib のコメントにも書いておく（値の意味が条件込みでしか決まらないため）

としている。

## Liberty のモデル

NOR 型なので S / R ともアクティブ High、両方 High なら Q = QB = L。

    latch (IQ, IQN) { preset : "S"; clear : "R";
                      clear_preset_var1 : L; clear_preset_var2 : L; }

アークは 4 本:

    S -> Q   preset  positive_unate   (cell_rise / rise_transition のみ)
    S -> QB  clear   negative_unate   (cell_fall / fall_transition のみ)
    R -> Q   clear   negative_unate   (cell_fall / fall_transition のみ)
    R -> QB  preset  positive_unate   (cell_rise / rise_transition のみ)

加えて S / R の最小 High パルス幅を掃引で測り、min_pulse_width に入れる。
**`dont_use` を付ける。** ABC に SR ラッチを勝手に組ませないため（このセルは
RTL で明示インスタンスする前提）。.lib に入れるのは P&R の負荷計算と STA のため。
"""
from __future__ import annotations
import argparse, json, os, sys

HERE_ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE_)
import cellspec                                                   # noqa: E402
from charlib import (HERE, VDD, SLEWS, LOADS, TH_DELAY, TH_SLEW_LO, TH_SLEW_HI,
                     header, all_ports_of, pwl_ramp, full_ramp)   # noqa: E402

MODELS_TOKEN = "__MODELS__"

T_INIT, T_REL = 20.0, 21.0     # 反対側の入力を張っておく区間 [ns]
T0 = 100.0                     # 測る端を振り始める時刻 [ns]
SETTLE = 150.0                 # 遷移後に落ち着かせる時間 [ns]
CL_OTHER = 25.0                # 測らない側の出力に付ける固定負荷 [fF]
CL_MPW = 50.0                  # 最小パルス幅を測るときの負荷 [fF]
MPW_SLEW = 0.1                 # 同上、入力遷移 [ns]（速い縁で素の下限を見る）
VFY_SLEW, VFY_LOAD = 1.0, 150.0   # 格子の外での検算点

# 掃引する High パルス幅 [ns]（50% -> 50%）。10% 刻みの等比。
MPW_W = [round(0.25 * 1.10 ** i, 4) for i in range(50)]     # 0.25 .. 25.8 ns

# セルの定義。`ins[入力][出力]` = その入力をアクティブ(High)にしたとき出力が向かう先。
LATCH = {
    "RSLATCH": dict(
        q="Q", qb="QB",
        ins={"S": {"Q": "rise", "QB": "fall"},
             "R": {"Q": "fall", "QB": "rise"}},
        other={"S": "R", "R": "S"},     # 初期化に使う反対側の入力
    ),
}
# 出力が rise するアークが preset、fall するアークが clear。
TTYPE = {"rise": ("preset", "positive_unate"), "fall": ("clear", "negative_unate")}


# --------------------------------------------------------------------------
def _head(cell, title):
    """models の絶対パスはプレースホルダにしておく（runjobs.sh が実機のパスを埋める）"""
    L = [f"* {title}  -- char_latch.py 生成"] + header(cell)
    return [ln.replace(f"{HERE}/models", MODELS_TOKEN) for ln in L]


def _inst(cell, tag, omap):
    """インスタンス 1 行。omap = {出力ピン: ノード名}。入力と電源はそのまま。"""
    return (f"X{tag} " + " ".join(omap.get(p, p) for p in all_ports_of(cell))
            + f" {cell}")


def _init_other(sp, ipin):
    """反対側の入力で状態を決めておく。T_REL で放す（NOR ラッチは保持する）。"""
    oth = sp["other"][ipin]
    return f"V_{oth} {oth} 0 PWL(0 {VDD:g} {T_INIT:g}n {VDD:g} {T_REL:g}n 0)"


def build_delay(cell, ipin, opin, slew, loads=None):
    """ipin をアクティブに振り、opin の遅延と遷移を負荷掃引で測る。"""
    sp = LATCH[cell]
    loads = LOADS if loads is None else loads
    out2 = sp["qb"] if opin == sp["q"] else sp["q"]
    rise = sp["ins"][ipin][opin] == "rise"
    L = _head(cell, f"{cell} {ipin}->{opin} 入力遷移 {slew}ns "
                    f"(反対側の出力は {CL_OTHER:g}fF 固定)")
    # 理想電圧源を速く振るとソルバが落ちるので微小抵抗で正則化する（char_comb と同じ）
    L.append(f"Vin {ipin}_src 0 {pwl_ramp(T0, slew, True)}")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    L.append(_init_other(sp, ipin))
    L.append("")
    for k, cl in enumerate(loads):
        L.append(_inst(cell, k, {opin: f"o{k}_{opin}", out2: f"o{k}_{out2}"}))
        L.append(f"C{k} o{k}_{opin} 0 {cl:g}f")
        L.append(f"Cx{k} o{k}_{out2} 0 {CL_OTHER:g}f")
    L.append("")
    L.append(f".tran {max(min(slew, 0.5) / 20, 0.02):g}n "
             f"{T0 + full_ramp(slew) + SETTLE:g}n")
    vt = VDD * TH_DELAY / 100
    lo, hi = VDD * TH_SLEW_LO / 100, VDD * TH_SLEW_HI / 100
    edge = "RISE=1" if rise else "FALL=1"
    for k in range(len(loads)):
        o = f"o{k}_{opin}"
        L.append(f".meas tran d{k} TRIG v({ipin}) VAL={vt:g} RISE=1 "
                 f"TARG v({o}) VAL={vt:g} {edge}")
        if rise:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={lo:g} RISE=1 "
                     f"TARG v({o}) VAL={hi:g} RISE=1")
        else:
            L.append(f".meas tran t{k} TRIG v({o}) VAL={hi:g} FALL=1 "
                     f"TARG v({o}) VAL={lo:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_cap(cell, ipin, mode):
    """入力容量。mode='switch' は状態が変わる縁、'hold' は変わらない縁。

    SR ラッチの入力は、**同じ状態のまま叩かれることの方が多い**（保持中の再アサート）。
    状態が変わる縁はクロス結合を通した帰還があるぶん容量が大きく見える。
    両方測って .lib には大きい方を入れる（駆動側から見て安全側）。
    """
    sp = LATCH[cell]
    oth = sp["other"][ipin]
    sl = 2.0
    tf = full_ramp(sl)
    L = _head(cell, f"{cell} {ipin} 入力容量 ({mode})")
    if mode == "switch":
        L.append(f"Vin {ipin}_src 0 {pwl_ramp(T0, sl, True)}")
        L.append(_init_other(sp, ipin))
    else:
        # 自分自身で先に状態を作っておき、放してから同じ向きに叩き直す
        L.append(f"Vin {ipin}_src 0 PWL(0 {VDD:g} {T_INIT:g}n {VDD:g} "
                 f"{T_REL:g}n 0 {T0:g}n 0 {T0 + tf:g}n {VDD:g})")
        L.append(f"V_{oth} {oth} 0 0")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    L.append(_inst(cell, "u", {sp["q"]: "oq", sp["qb"]: "oqb"}))
    # 出力を素のままにすると Miller 帰還が最大になって過大に出る。代表負荷を付ける。
    L.append("CLq oq 0 50f")
    L.append("CLqb oqb 0 50f")
    L.append(f".tran 0.02n {T0 + tf + 50:g}n")
    L.append(f".meas tran q INTEG i(Vin) FROM={T0:g}n TO={T0 + tf:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_mpw(cell, ipin, w):
    """幅 w [ns]（50%->50%）の High パルスを 1 発入れて、状態が変わって**残る**か。"""
    sp = LATCH[cell]
    tf = full_ramp(MPW_SLEW)
    tend = T0 + w + tf + 120.0
    L = _head(cell, f"{cell} {ipin} 最小 High パルス幅 w={w}ns")
    L.append(f"Vin {ipin}_src 0 PWL(0 0 {T0:g}n 0 {T0 + tf:g}n {VDD:g} "
             f"{T0 + w:g}n {VDD:g} {T0 + w + tf:g}n 0)")
    L.append(f"Rin {ipin}_src {ipin} 0.001")
    L.append(_init_other(sp, ipin))
    L.append(_inst(cell, "u", {sp["q"]: "oq", sp["qb"]: "oqb"}))
    L.append(f"CLq oq 0 {CL_MPW:g}f")
    L.append(f"CLqb oqb 0 {CL_MPW:g}f")
    L.append(f".tran 0.01n {tend:g}n")
    L.append(f".meas tran qfin FIND v(oq) AT={T0 + w + tf + 100:g}n")
    L.append(f".meas tran qbfin FIND v(oqb) AT={T0 + w + tf + 100:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


# --------------------------------------------------------------------------
def gen(outdir, cells):
    os.makedirs(f"{outdir}/decks", exist_ok=True)
    jobs = []

    def emit(tag, deck, meta):
        open(f"{outdir}/decks/{tag}.spi", "w").write(deck)
        jobs.append({"tag": tag, **meta})

    for cell in cells:
        sp = LATCH[cell]
        for ipin, outs in sp["ins"].items():
            for opin in outs:
                for si, slew in enumerate(SLEWS):
                    emit(f"{cell}_{ipin}_{opin}_s{si}",
                         build_delay(cell, ipin, opin, slew),
                         {"kind": "delay", "cell": cell, "ipin": ipin,
                          "opin": opin, "si": si})
                # 格子の外（入力遷移 1.0ns / 負荷 150fF）での検算
                emit(f"{cell}_{ipin}_{opin}_vfy",
                     build_delay(cell, ipin, opin, VFY_SLEW, [VFY_LOAD]),
                     {"kind": "verify", "cell": cell, "ipin": ipin, "opin": opin})
            for mode in ("hold", "switch"):
                emit(f"{cell}_{ipin}_cap_{mode}", build_cap(cell, ipin, mode),
                     {"kind": "cap", "cell": cell, "ipin": ipin, "mode": mode})
            for k, w in enumerate(MPW_W):
                emit(f"{cell}_{ipin}_mpw_{k:03d}", build_mpw(cell, ipin, w),
                     {"kind": "mpw", "cell": cell, "ipin": ipin, "k": k, "w": w})

    json.dump(jobs, open(f"{outdir}/jobs.json", "w"), indent=1)
    n = len(jobs)
    kinds = {}
    for j in jobs:
        kinds[j["kind"]] = kinds.get(j["kind"], 0) + 1
    print(f"デッキ {n} 本 -> {outdir}/decks/")
    for k in sorted(kinds):
        print(f"  {k:<7} {kinds[k]:>4}")
    return n


# --------------------------------------------------------------------------
def read_results(pack):
    """results.txt -> {タグ: {測定名: 値}}"""
    p = f"{pack}/results.txt"
    if not os.path.exists(p):
        raise SystemExit(f"{p} が無い。先に ./runjobs.sh -p {pack} を流してください")
    res = {}
    for ln in open(p):
        t = ln.split()
        if len(t) != 3:
            continue
        try:
            res.setdefault(t[0], {})[t[1]] = float(t[2])
        except ValueError:
            pass
    return res


def interp2(x_idx, y_idx, tbl, x, y):
    """SLEWS x LOADS の表を双線形補間する（格子の外は端の 2 点で外挿）。"""
    def pos(idx, v):
        for i in range(len(idx) - 1):
            if v <= idx[i + 1] or i == len(idx) - 2:
                lo, hi = idx[i], idx[i + 1]
                return i, (v - lo) / (hi - lo)
        return 0, 0.0
    i, fx = pos(x_idx, x)
    j, fy = pos(y_idx, y)
    a = tbl[i][j] + (tbl[i][j + 1] - tbl[i][j]) * fy
    b = tbl[i + 1][j] + (tbl[i + 1][j + 1] - tbl[i + 1][j]) * fy
    return a + (b - a) * fx


def collect(pack, cells):
    res = read_results(pack)
    ng = 0
    for cell in cells:
        sp = LATCH[cell]
        out = {"cell": cell, "latch": True, "slews": SLEWS, "loads": LOADS,
               "arcs": [], "cap": {}, "cap_hold": {}, "cap_switch": {},
               "mpw": {}, "cond": {"cl_other": CL_OTHER, "cl_mpw": CL_MPW,
                                   "mpw_slew": MPW_SLEW}}
        for ipin, outs in sp["ins"].items():
            # --- 入力容量 ---
            for mode in ("hold", "switch"):
                v = res.get(f"{cell}_{ipin}_cap_{mode}", {}).get("q")
                out[f"cap_{mode}"][ipin] = abs(v) / VDD * 1e15 if v is not None else None
            cands = [out["cap_hold"][ipin], out["cap_switch"][ipin]]
            cands = [c for c in cands if c is not None]
            out["cap"][ipin] = max(cands) if cands else None

            # --- 遅延アーク ---
            for opin in outs:
                rise = sp["ins"][ipin][opin] == "rise"
                ttype, sense = TTYPE[sp["ins"][ipin][opin]]
                dk = "cell_rise" if rise else "cell_fall"
                tk = "rise_transition" if rise else "fall_transition"
                d_tbl, t_tbl = [], []
                for si in range(len(SLEWS)):
                    v = res.get(f"{cell}_{ipin}_{opin}_s{si}", {})
                    d_tbl.append([v.get(f"d{k}") for k in range(len(LOADS))])
                    t_tbl.append([v.get(f"t{k}") for k in range(len(LOADS))])
                miss = sum(1 for r in d_tbl + t_tbl for x in r if x is None)
                if miss:
                    print(f"  ! {cell} {ipin}->{opin}: 測定できていない点が {miss} 個")
                    ng += 1
                arc = {"related_pin": ipin, "pin": opin, "type": ttype,
                       "sense": sense, dk: d_tbl, tk: t_tbl}
                out["arcs"].append(arc)

            # --- 最小 High パルス幅 ---
            want_hi = sp["ins"][ipin]["Q"] == "rise"      # S なら Q=H、R なら Q=L
            got = None
            for k, w in enumerate(MPW_W):
                q = res.get(f"{cell}_{ipin}_mpw_{k:03d}", {}).get("qfin")
                if q is None:
                    continue
                ok = q > 0.9 * VDD if want_hi else q < 0.1 * VDD
                if ok:
                    got = w
                    break
            out["mpw"][ipin] = got
            if got is None:
                print(f"  ! {cell} {ipin}: 掃引した範囲 "
                      f"({MPW_W[0]}..{MPW_W[-1]}ns) で状態が変わらなかった")
                ng += 1

        os.makedirs(f"{HERE}/char", exist_ok=True)
        json.dump(out, open(f"{HERE}/char/{cell}.json", "w"), indent=1)

        # --- 格子の外での検算 ---
        print(f"--- {cell} ---")
        caps = " ".join(f"{p}:{v:.1f}" for p, v in out["cap"].items() if v is not None)
        print(f"  入力容量 [fF]  {caps}    "
              f"(hold {out['cap_hold']} / switch {out['cap_switch']})")
        mpws = " ".join(f"{p}:{v}" for p, v in out["mpw"].items() if v is not None)
        print(f"  最小 High パルス幅 [ns]  {mpws}  (等比 10% 刻みの掃引なので分解能 10%)")
        si, li = SLEWS.index(0.6), LOADS.index(50)
        for a in out["arcs"]:
            dk = "cell_rise" if "cell_rise" in a else "cell_fall"
            v = a[dk][si][li]
            s = f"{v * 1e9:.3f}" if v is not None else "-"
            print(f"  {a['related_pin']}->{a['pin']:<3} {a['type']:<7} "
                  f"遅延(slew0.6/CL50) {s} ns")
            vf = res.get(f"{cell}_{a['related_pin']}_{a['pin']}_vfy", {}).get("d0")
            if vf is None or a[dk][0][0] is None:
                continue
            est = interp2(SLEWS, LOADS, a[dk], VFY_SLEW, VFY_LOAD)
            err = abs(est - vf) / abs(vf) * 100 if vf else 0.0
            mark = "" if err < 15 else "   ** 15% 超"
            print(f"       格子外 (slew {VFY_SLEW}/CL {VFY_LOAD:g}): "
                  f"実測 {vf * 1e9:.3f} / 表から {est * 1e9:.3f} ns  ずれ {err:.1f}%{mark}")
            if err >= 15:
                ng += 1
        print(f"  -> {HERE}/char/{cell}.json")
    print("逸脱なし" if ng == 0 else f"** {ng} 件")
    return ng


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "collect"])
    ap.add_argument("-o", "--out", default=f"{HERE}/pack_rslatch")
    ap.add_argument("-p", "--pack", default=f"{HERE}/pack_rslatch")
    ap.add_argument("cells", nargs="*", default=None)
    a = ap.parse_args()
    cells = a.cells or sorted(LATCH)
    bad = [c for c in cells if c not in LATCH]
    if bad:
        raise SystemExit(f"知らないセル: {', '.join(bad)}")
    if a.cmd == "gen":
        gen(a.out, cells)
    else:
        sys.exit(1 if collect(a.pack, cells) else 0)


if __name__ == "__main__":
    main()

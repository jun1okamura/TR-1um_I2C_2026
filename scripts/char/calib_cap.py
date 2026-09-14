#!/usr/bin/env python3
"""入力容量 `capacitance` を「遅延計算に使える値」に較正する。

  usage: python3 calib_cap.py       char/*.json の "cap_cal" を埋める

電荷から出した入力容量（char_comb.py の測定値）は、**遅延計算に使うと
10〜17% ずれる**ことが verify_lib.py で分かった。ゲート入力は純粋な容量では
なく、遷移中にミラー電流が流れるため、電荷で測ると過大に出る。

Liberty の `capacitance` は「そのピンが前段に見せる負荷」であって、
遅延表は**純粋な容量**で引かれる。なので正しい定義は
「前段の遅延が実測と一致するような等価容量」。ここではそれを求める。

やり方:
  INV_X1（基準ドライバ）で対象ピンを N 個駆動して遅延を実測
  -> INV_X1 の遅延表を逆に引いて「その遅延になる純容量」を求める
  -> N で割る
N=2 と 4 で求めて平均する。両者がずれるならその旨を出す。
"""
from __future__ import annotations
import json, os, sys
import cellspec
from charlib import HERE, VDD, SLEWS, LOADS, header, run_ngspice, full_ramp, arcs_of

DRV = "INV_X1"          # 基準ドライバ
SLEW_IN = 0.6           # ドライバに与える入力遷移 [ns]（表の index_1 と同じ定義）
FANOUTS = (2, 4)
T0 = 100.0


def invert_row(idx_load, row, target):
    """遅延 target になる負荷を、表の 1 行から線形補間で逆に引く"""
    vv = [v for v in row if v is not None]
    if len(vv) < 2:
        return None
    for i in range(len(vv) - 1):
        a, b = vv[i], vv[i + 1]
        if (a - target) * (b - target) <= 0 and b != a:
            f = (target - a) / (b - a)
            return idx_load[i] + f * (idx_load[i + 1] - idx_load[i])
    # 表の外なら端の傾きで外挿
    if target < vv[0]:
        s = (vv[1] - vv[0]) / (idx_load[1] - idx_load[0])
        return max(0.0, idx_load[0] + (target - vv[0]) / s)
    s = (vv[-1] - vv[-2]) / (idx_load[-1] - idx_load[-2])
    return idx_load[-1] + (target - vv[-1]) / s


def build_deck(cell, pin, side, n):
    """INV_X1 -> (cell の pin) x n のデッキを組む（実行はしない）。"""
    from check_comb import to_xm, all_ports_of, CELLDIR, CELLEXT
    L = [f"* {DRV} -> {cell}.{pin} x{n} 等価容量の較正"]
    L.append(f".include {HERE}/models/ip62_models")
    L.append("")
    L.append(to_xm(f"{CELLDIR}/{DRV}{CELLEXT}"))
    if cell != DRV:
        L.append(to_xm(f"{CELLDIR}/{cell}{CELLEXT}"))
    L += ["", f".temp 25", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]
    tf = full_ramp(SLEW_IN)
    L.append(f"Vin src 0 PWL(0 0 {T0:g}n 0 {T0+tf:g}n {VDD:g})")
    L.append("Rin src A 0.001")
    # ポート順はネットリストの宣言順に従う（KLayout は ... vss vdd の順）
    drv_ports = ["A" if p == "A" else ("NET" if p == "Y" else p) for p in all_ports_of(DRV)]
    L.append("XD " + " ".join(drv_ports) + f" {DRV}")
    for k in range(n):
        pl = []
        for p in all_ports_of(cell):
            if p == pin:
                pl.append("NET")
            elif p in ("vdd", "vss"):
                pl.append(p)
            elif p in side:
                pl.append(f"sv{'H' if side[p] else 'L'}")
            else:
                # 出力や、抽出がピンに昇格させた内部ネットは各インスタンス固有にする
                pl.append(f"nc{k}_{p}")
        L.append(f"XL{k} " + " ".join(pl) + f" {cell}")
    L.append(f"VsvH svH 0 {VDD}")
    L.append("VsvL svL 0 0")
    L.append(f".tran 0.02n {T0+tf+200:g}n")
    L.append(f".meas tran d TRIG v(A) VAL={VDD/2:g} RISE=1 TARG v(NET) VAL={VDD/2:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


def measure(cell, pin, side, n, tag):
    """デッキを組んでその場で走らせる（逐次実行用）。"""
    vals, _ = run_ngspice(build_deck(cell, pin, side, n), tag)
    return vals.get("d")


def main():
    # 引数でセルを絞れる（RSLATCH だけ測り直す、など）。既定は全セル。
    want = set(sys.argv[1:])
    drv = json.load(open(f"{HERE}/char/{DRV}.json"))
    row = drv["arcs"][0]["cell_fall"][SLEWS.index(SLEW_IN)]     # 入力立上り -> 出力立下り
    print(f"基準ドライバ {DRV} / 入力遷移 {SLEW_IN}ns の cell_fall 行を逆引きに使う")
    print(f"{'cell':<10}{'pin':<10}{'電荷から':>9}{'較正後':>9}{'比':>7}  N=2/N=4 のばらつき")
    from check_comb import CELLDIR, CELLEXT
    for f in sorted(os.listdir(f"{HERE}/char")):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        d = json.load(open(f"{HERE}/char/{f}"))
        cell = d["cell"]
        if want and cell not in want:
            continue
        if not os.path.exists(f"{CELLDIR}/{cell}{CELLEXT}"):
            continue
        if d.get("latch"):
            # SR ラッチ。**反対側の入力を High に張って測る。**
            # 例えば S を測るなら R=1。この条件で S を振ると S=R=1 の状態と
            # R だけの状態を行き来し、QB が実際に振れる（S のゲートは QB 側の
            # Tr に付いている）ので、ミラー帰還込みの、駆動側から見た本当の
            # 負荷になる。R を 0 に張ると初期状態が決まらない（両安定）ので使えない。
            import char_latch
            sp = char_latch.LATCH[cell]
            pins = sorted(sp["ins"])
            sides = {p: {sp["other"][p]: 1} for p in pins}
            raws = {p: (d.get("cap") or {}).get(p) for p in pins}
        elif d.get("seq"):
            # 順序セルは char_seq.py が容量を測っていないので、ここで全入力ピンを測る。
            # 非同期ピンは非アクティブ側に固定する。
            idle = {"RSTB": 1, "SET": 0, "S": 0, "B": 0}
            pins = ["CK"] + cellspec.SEQ_PINS[cell]["data"] + cellspec.SEQ_PINS[cell]["async"]
            sides = {p: {k: v for k, v in idle.items() if k != p} for p in pins}
            raws = {p: None for p in pins}
        else:
            outs = cellspec.COMB[cell]
            sides = {i: s for o, i, s, _ in arcs_of(cell, outs)}
            raws = d["cap"]
        cal = {}
        for pin, raw in raws.items():
            raw = raw or 0.0
            est = []
            for n in FANOUTS:
                t = measure(cell, pin, sides.get(pin, {}), n, f"cal_{cell}_{pin}_{n}")
                if t is None:
                    continue
                c = invert_row(LOADS, row, t)
                if c:
                    est.append(c / n)
            if not est:
                cal[pin] = raw or None
                print(f"{cell:<10}{pin:<10}{raw:8.1f}{'':>9}{'':>7}  ** 測れず")
                continue
            v = sum(est) / len(est)
            cal[pin] = v
            spread = (max(est) - min(est)) / v if len(est) > 1 else 0.0
            ratio = f"{v/raw:7.2f}" if raw else f"{'-':>7}"
            print(f"{cell:<10}{pin:<10}{raw:8.1f}{v:9.1f}{ratio}  {spread:.1%}"
                  f"{'  ** ばらつきが大きい' if spread > 0.15 else ''}")
        d["cap_charge"] = d.get("cap", {})
        d["cap_cal"] = cal
        json.dump(d, open(f"{HERE}/char/{f}", "w"), indent=1)
    print("\n各 json に cap_cal を書いた。mklib.py はこちらを使う。")


if __name__ == "__main__":
    main()

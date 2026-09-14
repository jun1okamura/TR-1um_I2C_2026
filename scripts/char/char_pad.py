#!/usr/bin/env python3
"""パッドセル `OSS_ESD_5V_DIO` の特性化（NLDM）。

  usage: python3 scripts/char/char_pad.py [-n gio_sim.spi] [-o char/OSS_ESD_5V_DIO.json]

標準セルの `char_comb.py` と測るものは同じだが、**格子が違う**。

  入力遷移 index_1 : 標準セルと同じ 0.1〜16 ns（20-80%）。OUT / HIZ を駆動するのは
                     コア側の標準セルなので、ここを揃えておくと表が繋がる。
  出力負荷 index_2 : **1〜50 pF**。標準セルの 10〜800 fF とは桁が 2 つ違う。
                     ボンディングパッド + パッケージ + 基板 + 測定プローブを想定した
                     実用域（ワイヤボンド 1〜2 pF / DIP パッケージ 3〜10 pF /
                     基板配線 10〜30 pF / オシロのプローブ 10〜15 pF）。
                     **ここは想定値なので、実装が決まったら見直すこと。**

3 ステートの扱い:
  Liberty では `function : "OUT"` + `three_state : "HIZ"` と書き、HIZ->PAD に
  `three_state_enable` / `three_state_disable` のアークを持たせる。
    enable  : HIZ が下がってドライバが効き始め、PAD が 50% を通るまで。
              測定前の PAD は弱いプル（1Mohm）で逆の電位にしておく。
    disable : HIZ が上がってドライバが放すまで。**放した瞬間は波形が動かない**ので
              50% では測れない。駆動していたレールから **0.5V（VDD の 10%）**
              離れるまでの時間を取る。そのために 10kohm で逆レールに引いておく。
              この 0.5V と 10kohm は測定条件なので .lib のコメントに残す。
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
VDD, TEMP = 5.0, 25
CELL = "OSS_ESD_5V_DIO"
MODELS = os.environ.get("TR1UM_MODELS", f"{HERE}/models")
# パッドセルの面積。標準セルの cell_area.json（STDCELL の GDS 実測）には
# 入っていないので、フレームの LEF の MACRO ... SIZE から読む。
FRAME_LEF = os.environ.get("TR1UM_FRAME_LEF",
                           os.path.join(HERE, "..", "..", "lef", "TR-1um_frame.lef"))


def pad_area(cell=None):
    cell = cell or CELL
    m = re.search(rf"^MACRO {cell}\b(.*?)^END {cell}\b", open(FRAME_LEF).read(),
                  re.S | re.M)
    if not m:
        raise SystemExit(f"{FRAME_LEF} に MACRO {cell} が無い")
    w, h = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", m.group(1)).groups()
    return float(w) * float(h)

# 入力遷移 [ns]（20-80%）— 標準セルと同じ
SLEWS = [0.1, 0.25, 0.6, 1.5, 4.0, 8.0, 16.0]
# PAD 負荷 [fF]
LOADS = [1000, 2000, 5000, 10000, 20000, 35000, 50000]
# 3 ステートは格子を粗く
SLEWS_T = [0.25, 1.5, 8.0]

TH_DELAY, TH_LO, TH_HI = 50, 20, 80
SLEW_FRAC = (TH_HI - TH_LO) / 100
# disable は「ドライバが電流を出さなくなるまで」で測る。
#
# **電圧で測ってはいけない。** 最初 10kohm で逆レールに引いて「駆動レールから
# 0.5V 離れるまで」を測ったが、出てきたのは CL=50pF で 68ns —— これは
# 10kohm x 50pF の RC（53ns）そのもので、**測定系の時定数であってセルの特性ではない**。
# 負荷を変えると値が動くのも RC のせい。
#
# そこで PAD を VDD/2 の電圧源で押さえ、ドライバに電流を出させておいて、
# **その電流が DIS_I を下回るまで**を測る。放したかどうかを直接見ているので
# 負荷にも外付け抵抗にも依らない。3 ステートの disable が STA で使われるのは
# バス競合の判定なので、「いつ駆動をやめたか」こそが欲しい量。
DIS_I = 100e-6          # disable の判定: PAD に流れる電流がこれを下回ったら「放した」[A]
ENA_R = 1e6             # enable の前に PAD を逆レールに置いておく弱いプル
T0, SETTLE = 200.0, 400.0


def full_ramp(s):
    return s / SLEW_FRAC


def ramp(t0, slew, rise):
    a, b = (0, VDD) if rise else (VDD, 0)
    tf = full_ramp(slew)
    return f"PWL(0 {a:g} {t0:g}n {a:g} {t0+tf:g}n {b:g})"


def run(deck, tag, netlist):
    os.makedirs(f"{HERE}/decks", exist_ok=True)
    os.makedirs(f"{HERE}/logs", exist_ok=True)
    p = f"{HERE}/decks/{tag}.spi"
    open(p, "w").write(deck)
    r = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=900)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{tag}.log", "w").write(log)
    v = {}
    for ln in log.splitlines():
        m = re.match(r"^\s*([a-z]\w*)\s*=\s*([-\d.eE+]+)", ln)
        if m:
            try: v[m.group(1)] = float(m.group(2))
            except ValueError: pass
    return v


def header(netlist):
    return [f".include {MODELS}/ip62_models", f".include {netlist}", "",
            f".temp {TEMP}", f"Vvdd VDD 0 {VDD}", "Vvss VSS 0 0"]


def build_delay(netlist, slew, rise_in):
    """OUT -> PAD。負荷 7 点を 1 デッキに並べる。"""
    L = [f"* {CELL} OUT->PAD 入力遷移 {slew}ns  -- char_pad.py 生成"]
    L += header(netlist)
    L.append(f"Vin src 0 {ramp(T0, slew, rise_in)}")
    L.append("Rin src OUT 0.001")      # 理想源を急峻に振るとソルバが落ちる
    L.append("Vhiz HIZ 0 0")           # 駆動モード
    for k, cl in enumerate(LOADS):
        L.append(f"X{k} pad{k} VDD OUT HIZ VSS {CELL}")
        L.append(f"C{k} pad{k} 0 {cl}f")
    tend = T0 + full_ramp(slew) + SETTLE
    L.append(f".tran {max(min(slew, 0.5) / 20, 0.02):g}n {tend:g}n")
    vt = VDD * TH_DELAY / 100
    lo, hi = VDD * TH_LO / 100, VDD * TH_HI / 100
    trig = "RISE=1" if rise_in else "FALL=1"
    for k in range(len(LOADS)):
        o = f"pad{k}"
        for edge, tg in (("RISE=1", "r"), ("FALL=1", "f")):
            L.append(f".meas tran d{tg}{k} TRIG v(OUT) VAL={vt:g} {trig} "
                     f"TARG v({o}) VAL={vt:g} {edge}")
        L.append(f".meas tran tr{k} TRIG v({o}) VAL={lo:g} RISE=1 TARG v({o}) VAL={hi:g} RISE=1")
        L.append(f".meas tran tf{k} TRIG v({o}) VAL={hi:g} FALL=1 TARG v({o}) VAL={lo:g} FALL=1")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_cap(netlist, pin, hiz):
    """入力ピンに流れ込む電荷から容量を出す"""
    sl = 2.0
    L = [f"* {CELL} {pin} 入力容量 -- char_pad.py 生成"]
    L += header(netlist)
    other = {"OUT": "HIZ", "HIZ": "OUT"}[pin]
    L.append(f"Vin {pin}_src 0 {ramp(T0, sl, True)}")
    L.append(f"Rin {pin}_src {pin} 0.001")
    L.append(f"V_{other} {other} 0 {hiz*VDD:g}")
    L.append(f"XU PAD VDD OUT HIZ VSS {CELL}")
    L.append(f"CL PAD 0 {LOADS[3]}f")            # 代表負荷 10pF
    L.append(f".tran 0.02n {T0+full_ramp(sl)+200:g}n")
    L.append(f".meas tran q INTEG i(Vin) FROM={T0:g}n TO={T0+full_ramp(sl):g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_padcap(netlist):
    """HIZ=1（高Z）のとき PAD が外に見せる容量。ボード設計の資料になる。"""
    sl = 20.0
    L = [f"* {CELL} PAD の容量（高Z時） -- char_pad.py 生成"]
    L += header(netlist)
    L.append("Vout OUT 0 0")
    L.append(f"Vhiz HIZ 0 {VDD}")
    L.append(f"Vpad padsrc 0 {ramp(T0, sl, True)}")
    L.append("Rp padsrc PAD 0.001")
    L.append(f"XU PAD VDD OUT HIZ VSS {CELL}")
    L.append(f".tran 0.05n {T0+full_ramp(sl)+200:g}n")
    L.append(f".meas tran q INTEG i(Vpad) FROM={T0:g}n TO={T0+full_ramp(sl):g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_tristate(netlist, mode, slew, out_lvl, cl, i0=None):
    """HIZ -> PAD の enable / disable。

    enable  : HIZ を 1->0。PAD は 1Mohm で逆レールに置いてある。50% 通過まで。
    disable : HIZ を 0->1。PAD は 10kohm で逆レールに引いてある。
              駆動していたレールから DIS_DV [V] 離れるまで。
    """
    rail = VDD if out_lvl else 0.0
    L = [f"* {CELL} HIZ {mode} OUT={int(out_lvl)} 遷移 {slew}ns"
         + (f" CL={cl}fF" if mode == "enable" else " (PAD を VDD/2 で押さえて電流で判定)")]
    L += header(netlist)
    L.append(f"Vout OUT 0 {rail:g}")
    L.append(f"Vhiz src 0 {ramp(T0, slew, mode == 'disable')}")
    L.append("Rhiz src HIZ 0.001")
    L.append(f"XU PAD VDD OUT HIZ VSS {CELL}")
    tend = T0 + full_ramp(slew) + SETTLE
    vt = VDD * TH_DELAY / 100
    if mode == "enable":
        # 測定前の PAD は弱いプルで逆レールに置く（DC 動作点で決まる）
        L.append(f"CL PAD 0 {cl}f")
        L.append(f"Vpull pull 0 {0.0 if out_lvl else VDD:g}")
        L.append(f"Rpull PAD pull {ENA_R:g}")
        L.append(f".tran {max(min(slew,0.5)/20, 0.02):g}n {tend:g}n")
        edge = "RISE=1" if out_lvl else "FALL=1"
        L.append(f".meas tran d TRIG v(HIZ) VAL={vt:g} FALL=1 TARG v(PAD) VAL={vt:g} {edge}")
        # enable の遷移。PAD は逆レールから駆動レールまでフルスイングするので、
        # 通常の出力遷移と同じ 20-80% で測れる。
        lo, hi = VDD * TH_LO / 100, VDD * TH_HI / 100
        if out_lvl:
            L.append(f".meas tran t TRIG v(PAD) VAL={lo:g} RISE=1 TARG v(PAD) VAL={hi:g} RISE=1")
        else:
            L.append(f".meas tran t TRIG v(PAD) VAL={hi:g} FALL=1 TARG v(PAD) VAL={lo:g} FALL=1")
    else:
        L.append(f"Vpad PAD 0 {VDD/2:g}")
        L.append(f".tran {max(min(slew,0.5)/20, 0.02):g}n {tend:g}n")
        # OUT=1 は PMOS が PAD へ流し込む -> i(Vpad) は **正**（実測 +15.8mA）で、
        # 放すと 0 へ落ちる。OUT=0 は NMOS が吸うので負から 0 へ上がる。
        L.append(f".meas tran i0 AVG i(Vpad) FROM={T0-50:g}n TO={T0-1:g}n")
        L.append(f".meas tran d TRIG v(HIZ) VAL={vt:g} RISE=1 "
                 f"TARG i(Vpad) VAL={DIS_I if out_lvl else -DIS_I:g} "
                 f"{'FALL=1' if out_lvl else 'RISE=1'}")
        # disable の「遷移」。放した瞬間は電圧が動かない（PAD を VDD/2 で
        # 押さえているので当然）ので、**駆動電流が i0 の 80% から 20% まで
        # 落ちる時間**を遷移とする。遅延を電流で定義したのと同じ理屈で、
        # 負荷にも外付け抵抗にも依らない。OUT=1 は i0 が正で下がり、
        # OUT=0 は負から 0 へ上がるので、どちらも同じ向きの通過になる。
        #
        # ngspice の .meas は他の .meas の結果を VAL の式に使えない
        # （Undefined parameter [i0] で落ちる）ので 2 パスにする。
        # 1 パス目で i0 を測り、2 パス目にその数値を渡す。
        if i0 is not None:
            ed = "FALL=1" if out_lvl else "RISE=1"
            L.append(f".meas tran t TRIG i(Vpad) VAL={0.8*i0:.6g} {ed} "
                     f"TARG i(Vpad) VAL={0.2*i0:.6g} {ed}")
    L += ["", ".end", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--netlist", default=f"{HERE}/cells_pad/OSS_FRAME_GIO_sim.spi")
    ap.add_argument("-o", "--out", default=f"{HERE}/char/{CELL}.json")
    ap.add_argument("--only", choices=["delay", "tri", "cap"], help="一部だけ流す（確認用）")
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    n = len(LOADS)
    PAD_AREA = pad_area()
    res = {"cell": CELL, "pad": True, "slews": SLEWS, "loads": LOADS,
           "slews_t": SLEWS_T, "dis_i": DIS_I,
           "arc": {"cell_rise": [], "cell_fall": [],
                   "rise_transition": [], "fall_transition": []},
           "enable": {"rise": [], "fall": [], "rise_transition": [], "fall_transition": []},
           "disable": {"rise": [], "fall": [], "rise_transition": [], "fall_transition": []},
           "area": PAD_AREA, "cap": {}}

    print(f"{'入力遷移':>8}  {'CL=1pF':>18}  {'CL=10pF':>18}  {'CL=50pF':>18}")
    for si, sl in enumerate(SLEWS):
        row = {}
        for rise in (True, False):
            v = run(build_delay(a.netlist, sl, rise), f"pad_d_s{si}_{'r' if rise else 'f'}",
                    a.netlist)
            k = "r" if rise else "f"
            row[k] = ([v.get(f"d{k}{i}") for i in range(n)],
                      [v.get(f"{'tr' if rise else 'tf'}{i}") for i in range(n)])
        res["arc"]["cell_rise"].append(row["r"][0])
        res["arc"]["rise_transition"].append(row["r"][1])
        res["arc"]["cell_fall"].append(row["f"][0])
        res["arc"]["fall_transition"].append(row["f"][1])
        f = lambda v: f"{v*1e9:.2f}" if v is not None else "-"
        print(f"{sl:>8}  " + "  ".join(
            f"r {f(row['r'][0][i]):>6} / f {f(row['f'][0][i]):>6}" for i in (0, 3, 6)))

    # 3 ステート
    print(f"\n{'':>8}  {'enable [ns]':>26}  {'disable [ns]':>26}")
    for mode in ("enable", "disable"):
        for lvl, key in ((1, "rise"), (0, "fall")):
            tbl, ttbl = [], []
            for sl in SLEWS_T:
                if mode == "enable":
                    vs = [run(build_tristate(a.netlist, mode, sl, lvl, cl),
                              f"pad_{mode}_{key}_{sl}_{cl}", a.netlist) for cl in LOADS]
                    tbl.append([v.get("d") for v in vs])
                    ttbl.append([v.get("t") for v in vs])
                else:
                    # disable は負荷に依らない（電流で判定するため）。
                    # Liberty の表は負荷軸を持つので同じ値を並べる。
                    v = run(build_tristate(a.netlist, mode, sl, lvl, 0),
                            f"pad_{mode}_{key}_{sl}", a.netlist)
                    # 2 パス目: 1 パス目の i0 を閾値に入れて遷移を測る
                    t = None
                    if v.get("i0"):
                        t = run(build_tristate(a.netlist, mode, sl, lvl, 0, v["i0"]),
                                f"pad_{mode}_{key}_{sl}_t", a.netlist).get("t")
                    tbl.append([v.get("d")] * len(LOADS))
                    ttbl.append([t] * len(LOADS))
                    if sl == SLEWS_T[0] and lvl == 1:
                        res["dis_i0"] = v.get("i0")
            res[mode][key] = tbl
            res[mode][f"{key}_transition"] = ttbl
    g = lambda v: f"{v*1e9:.2f}" if v is not None else "-"
    for key in ("rise", "fall"):
        i = SLEWS_T.index(1.5)
        print(f"  {key:<6}  CL=1pF {g(res['enable'][key][i][0]):>7} / "
              f"CL=10pF {g(res['enable'][key][i][3]):>7} / CL=50pF {g(res['enable'][key][i][6]):>7}"
              f"   ||  {g(res['disable'][key][i][0]):>7} / "
              f"{g(res['disable'][key][i][3]):>7} / {g(res['disable'][key][i][6]):>7}")

    # 入力容量
    for pin, hiz in (("OUT", 0), ("HIZ", 0)):
        q = run(build_cap(a.netlist, pin, hiz), f"pad_cap_{pin}", a.netlist).get("q")
        res["cap"][pin] = abs(q) / VDD * 1e15 if q is not None else None
    q = run(build_padcap(a.netlist), "pad_cap_PAD", a.netlist).get("q")
    res["cap"]["PAD"] = abs(q) / VDD * 1e15 if q is not None else None
    print("\n入力容量（電荷から）: " + " / ".join(
        f"{k} {v:.1f} fF" for k, v in res["cap"].items() if v))

    # 既にある JSON は**上書きせず併合する**。calib_cap.py が後から書き足す
    # cap_cal / cap_charge をここで消してしまわないように
    # （一度消して .lib の capacitance が電荷ベースの値に戻った）。
    if os.path.exists(a.out):
        old = json.load(open(a.out))
        for k, v in old.items():
            if k not in res:
                res[k] = v
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""順序セル（DFF 系 / RSLATCH / TLAT）を ngspice のシナリオで確認する。

  usage: python3 check_seq.py [セル名 ...]

組合せセルと違って「全組合せを並べる」では足りないので、セルごとに
波形シナリオを書く。各シナリオは

    STIM  : [(時刻ns, {ピン: 0/1}), ...]      入力の変化点
    CHECK : [(時刻ns, ピン, 期待値, 説明), ...] その時刻での期待値

で書き、PWL と `.meas ... FIND` に落とす。期待値 None は
「Hi-Z なので値を問わない」の意味で、代わりに前後で動いていないことを見る。

回路の期待動作は**抽出ネットリストの構造から読んだもの**:
  DFFRB  M1/M14 `vdd RSTB QB vdd pmos`  -> RSTB=0 で QB=H、つまり Q=0（**アクティブ Low**）
  DFFS   M28    `vss SET  QB vss nmos`  -> SET=1  で QB=L、つまり Q=1（**アクティブ High**）
  RSLATCH  Q=NOR(QB,R) / QB=NOR(Q,S)    -> R/S とも**アクティブ High** の NOR 型
シミュレーションがこれと食い違えば、読み違いかレイアウトのどちらかが誤り。
"""
from __future__ import annotations
import re, subprocess, sys, os

VDD = 5.0
EDGE = 0.5
CL = "20f"
RAIL_TOL = 0.25
HERE = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, HERE)
from check_comb import ports_of, all_ports_of, to_xm, CELLDIR, CELLEXT          # noqa: E402

CK = "CK"
T = 40          # クロック 1 周期の半分 [ns]


def clk(n, t0=100):
    """t0 から n 発のクロック（立上りは t0 + i*2T + T）"""
    out = []
    for i in range(n):
        out.append((t0 + i * 2 * T, {CK: 0}))
        out.append((t0 + i * 2 * T + T, {CK: 1}))
    return out


def dff_scenario(extra_pins=(), rst=None, setp=None, dpin="D", dmap=None):
    """DFF 系の共通シナリオ。dmap: D を作るための追加ピン設定関数"""
    stim, chk = [(0, {CK: 0})], []
    t = 100

    def drive(v):
        return dmap(v) if dmap else {dpin: v}

    for i, dv in enumerate([1, 0, 1, 1, 0]):
        stim.append((t, drive(dv)))                    # データを先に確定
        stim.append((t + T, {CK: 1}))                  # 立上りで取り込む
        stim.append((t + 2 * T, {CK: 0}))
        chk.append((t + T + 30, "Q", dv, f"立上り {i}: D={dv} を取り込む"))
        chk.append((t + T + 30, "QB", 1 - dv, f"立上り {i}: QB=!Q"))
        # クロックが low の間に D を反転させても Q は動かないこと
        stim.append((t + 2 * T + 5, drive(1 - dv)))
        chk.append((t + 2 * T + 30, "Q", dv, f"保持 {i}: CK=0 中に D を変えても Q は不変"))
        stim.append((t + 2 * T + 35, drive(dv)))
        t += 3 * T
    return stim, chk, t


def build_dff(cell, rstpin=None, rst_active=0, setpin=None, set_active=1, mux=False):
    dmap = None
    if mux:
        # D = S ? B : A。A/B/S を動かして両経路を使う
        def dmap(v):
            return {"A": v, "B": 1 - v, "S": 0}        # S=0 -> A を選ぶ
    stim, chk, t = dff_scenario(dmap=dmap)

    # 非同期リセット / セットの確認
    if rstpin:
        stim.append((t, {rstpin: rst_active}))
        chk.append((t + 30, "Q", 0, f"{rstpin}={rst_active} で非同期リセット -> Q=0"))
        chk.append((t + 30, "QB", 1, f"{rstpin}={rst_active} で QB=1"))
        stim.append((t + 50, {rstpin: 1 - rst_active}))
        t += 100
        # リセット解除後にちゃんと取り込めるか
        stim.append((t, ({"A": 1, "B": 0, "S": 0} if mux else {"D": 1})))
        stim.append((t + T, {CK: 1}))
        chk.append((t + T + 30, "Q", 1, "リセット解除後に D=1 を取り込める"))
        stim.append((t + 2 * T, {CK: 0}))
        t += 3 * T
    if setpin:
        stim.append((t, {setpin: set_active}))
        chk.append((t + 30, "Q", 1, f"{setpin}={set_active} で非同期セット -> Q=1"))
        chk.append((t + 30, "QB", 0, f"{setpin}={set_active} で QB=0"))
        stim.append((t + 50, {setpin: 1 - set_active}))
        t += 100
        stim.append((t, {"D": 0}))
        stim.append((t + T, {CK: 1}))
        chk.append((t + T + 30, "Q", 0, "セット解除後に D=0 を取り込める"))
        stim.append((t + 2 * T, {CK: 0}))
        t += 3 * T

    if mux:
        # S=1 側（B を選ぶ）も通す
        stim.append((t, {"A": 0, "B": 1, "S": 1}))
        stim.append((t + T, {CK: 1}))
        chk.append((t + T + 30, "Q", 1, "S=1 で B=1 を選んで取り込む"))
        stim.append((t + 2 * T, {CK: 0}))
        t += 3 * T
        stim.append((t, {"A": 1, "B": 0, "S": 1}))
        stim.append((t + T, {CK: 1}))
        chk.append((t + T + 30, "Q", 0, "S=1 で B=0 を選ぶ（A=1 は無視される）"))
        stim.append((t + 2 * T, {CK: 0}))
        t += 3 * T
    return stim, chk, t


def build_rslatch():
    stim, chk = [(0, {"R": 1, "S": 0})], []
    t = 100
    chk.append((t - 10, "Q", 0, "R=1 で Q=0"))
    stim.append((t, {"R": 0}))
    chk.append((t + 40, "Q", 0, "R=0/S=0 は保持（Q=0 のまま）"))
    t += 80
    stim.append((t, {"S": 1}))
    chk.append((t + 40, "Q", 1, "S=1 で Q=1"))
    chk.append((t + 40, "QB", 0, "そのとき QB=0"))
    t += 80
    stim.append((t, {"S": 0}))
    chk.append((t + 40, "Q", 1, "S=0 に戻しても保持（Q=1 のまま）"))
    t += 80
    stim.append((t, {"R": 1}))
    chk.append((t + 40, "Q", 0, "R=1 で Q=0 に戻る"))
    chk.append((t + 40, "QB", 1, "そのとき QB=1"))
    t += 80
    stim.append((t, {"R": 0}))
    chk.append((t + 40, "Q", 0, "再び保持"))
    t += 80
    return stim, chk, t


def build_tlat():
    """WR/WRB で D を取り込み、RD/RDB で Q に出す。
    WR=1/WRB=0 が書込、RD=1/RDB=0 が読出。読出 OFF のときの Q は Hi-Z。"""
    stim = [(0, {"WR": 0, "WRB": 1, "RD": 1, "RDB": 0, "D": 0})]
    chk = []
    t = 100
    for dv in (1, 0, 1):
        stim.append((t, {"D": dv}))
        stim.append((t + 20, {"WR": 1, "WRB": 0}))          # 書込ウィンドウを開く
        stim.append((t + 60, {"WR": 0, "WRB": 1}))          # 閉じる
        chk.append((t + 90, "Q", dv, f"D={dv} を書いて読める"))
        # 書込を閉じたまま D を反転しても保持されること
        stim.append((t + 95, {"D": 1 - dv}))
        chk.append((t + 130, "Q", dv, f"保持: 書込を閉じた後に D を変えても Q={dv}"))
        stim.append((t + 140, {"D": dv}))
        t += 180
    # 読出を閉じると Q は Hi-Z（負荷容量が前の値を保つ）
    stim.append((t, {"RD": 0, "RDB": 1}))
    stim.append((t + 20, {"D": 0}))
    stim.append((t + 40, {"WR": 1, "WRB": 0}))              # 中身を 0 に書き換える
    stim.append((t + 80, {"WR": 0, "WRB": 1}))
    chk.append((t + 120, "Q", 1, "読出 OFF: Q は Hi-Z なので容量に残った 1 のまま"))
    stim.append((t + 140, {"RD": 1, "RDB": 0}))             # 読出を開く
    chk.append((t + 180, "Q", 0, "読出を開くと書き換えた 0 が出る"))
    t += 220
    return stim, chk, t


SCEN = {
    "DFF":      lambda: build_dff("DFF"),
    "DFFRB":    lambda: build_dff("DFFRB", rstpin="RSTB", rst_active=0),
    "DFFS":     lambda: build_dff("DFFS", setpin="SET", set_active=1),
    "MUXDFFRB": lambda: build_dff("MUXDFFRB", rstpin="RSTB", rst_active=0, mux=True),
    "RSLATCH":  build_rslatch,
    "TLAT":     build_tlat,
}
# 初期値（シナリオで触らないピンはこの値に固定する）
IDLE = {"RSTB": 1, "SET": 0, "D": 0, "A": 0, "B": 0, "S": 0, CK: 0,
        "WR": 0, "WRB": 1, "RD": 1, "RDB": 0, "R": 0}


def pwl(points, tstop):
    s, prev = [], None
    for t, v in points:
        if prev is None:
            s.append(f"0 {v*VDD:g}")
        else:
            s.append(f"{t}n {prev*VDD:g}")
            s.append(f"{t+EDGE}n {v*VDD:g}")
        prev = v
    return "PWL(" + " ".join(s) + ")"


def build(cell, stim, chk, tstop):
    ports = ports_of(cell)
    outs = [p for p in ports if p in ("Q", "QB")]
    # **KLayout の抽出は内部ネットもピンに昇格させる**（DFF なら CKB/CKP/QM/QS）。
    # ここを駆動するとフリップフロップが壊れるので、本当の入力だけ動かし、
    # 残りは結線せず開放のままにする。IDLE に名前があるものを入力とみなす。
    ins = [p for p in ports if p not in outs and p in IDLE]
    floating = [p for p in ports if p not in outs and p not in ins]

    wave = {p: [(0, IDLE.get(p, 0))] for p in ins}
    for t, d in stim:
        for p, v in d.items():
            if p not in wave or wave[p][-1][1] == v:
                continue
            if t <= wave[p][-1][0]:
                wave[p][-1] = (wave[p][-1][0], v)   # 同時刻なら差し替え（PWL の時刻は単調増加）
            else:
                wave[p].append((t, v))

    L = [f"* {cell} 順序動作チェック -- check_seq.py 生成",
         (f"* 抽出がピンに昇格させた内部ネット（開放にする）: {' '.join(floating)}"
          if floating else "*"),
         f".include {HERE}/models/ip62_models", "",
         to_xm(f"{CELLDIR}/{cell}{CELLEXT}"), "",
         ".temp 25", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]
    for i, p in enumerate(ins):
        L.append(f"V{i} {p} 0 {pwl(wave[p], tstop)}")
    for p in outs:
        L.append(f"C{p} {p} 0 {CL}")
    L += ["", "XU " + " ".join(all_ports_of(cell)) + f" {cell}", ""]
    L.append(f".tran 0.1n {tstop}n")
    for i, (t, p, exp, why) in enumerate(chk):
        L.append(f".meas tran c{i:03d} FIND v({p}) AT={t}n   $ {why}")
    L += ["", ".end", ""]
    return "\n".join(L)


RE_M = re.compile(r"^\s*(c\d+)\s*=\s*([-\d.eE+]+)")


def run(cell):
    stim, chk, tstop = SCEN[cell]()
    deck = build(cell, stim, chk, tstop)
    dpath = f"{HERE}/decks/{cell}_seq.spi"
    open(dpath, "w").write(deck)
    r = subprocess.run(["ngspice", "-b", dpath], capture_output=True, text=True, timeout=600)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{cell}_seq.log", "w").write(log)
    vals = {}
    for ln in log.splitlines():
        m = RE_M.match(ln)
        if m:
            try: vals[m.group(1)] = float(m.group(2))
            except ValueError: pass

    npass = nfail = 0
    bad = []
    for i, (t, p, exp, why) in enumerate(chk):
        v = vals.get(f"c{i:03d}")
        if v is None:
            nfail += 1; bad.append((why, p, exp, None, "測定値なし")); continue
        got = 1 if v > VDD / 2 else 0
        rail = (v >= VDD - RAIL_TOL) if got else (v <= RAIL_TOL)
        if got == exp and rail:
            npass += 1
        else:
            nfail += 1
            bad.append((why, p, exp, v,
                        "論理が違う" if got != exp else "レールまで振れていない"))
    return npass, nfail, bad, len(chk)


def main():
    want = sys.argv[1:] or list(SCEN)
    missing = [c for c in want if not os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")]
    want = [c for c in want if c not in missing]
    tp = tf = 0
    print("=" * 76)
    print(" 順序セル 動作チェック (ngspice / TR-1um IP62 BSIM3 / 5V / 25degC)")
    print("=" * 76)
    print(f"{'cell':<10}{'検査項目':>8}  {'PASS':>5}{'FAIL':>5}  判定")
    for cell in want:
        p, f, bad, n = run(cell)
        tp += p; tf += f
        print(f"{cell:<10}{n:>8}  {p:>5}{f:>5}  {'OK' if f == 0 else '** NG **'}")
        for why, pin, exp, v, msg in bad[:8]:
            sv = f"{v:.3f}V" if v is not None else "-"
            print(f"           ! {why} : {pin} 期待 {exp} / 実測 {sv} ({msg})")
    print("-" * 76)
    if missing:
        print(f"ネットリストが無くて飛ばしたセル: {', '.join(missing)}")
    print(f"合計 PASS {tp} / FAIL {tf}   （{len(want)} セル）")
    return 1 if tf else 0


if __name__ == "__main__":
    sys.exit(main())

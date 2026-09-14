#!/usr/bin/env python3
"""組合せセルの真理値表を ngspice で全網羅チェックする。

  usage: python3 check_comb.py [セル名 ...]      （省略で cellspec.COMB 全部）

やり方: 入力の全組合せを階段状に印加する過渡解析を 1 本だけ流し、
各ステップの終わり（十分に落ち着いたところ）で `.meas ... FIND` する。
DC 解析だと収束点が一意でないラッチ構造で嘘をつくので、必ず過渡で見る。

判定は 2 つ:
  1. 論理値が cellspec の期待どおりか（VDD/2 で 0/1 に丸める）
  2. **フルレールに振れているか**（H は VDD-0.25V 以上、L は 0.25V 以下）
     しきい値落ちやレシオ比の不足はここで出る。組合せセルなら必ず振り切る。
"""
from __future__ import annotations
import itertools, re, subprocess, sys, os
import cellspec

VDD = 5.0
STEP = 20.0        # 1 組合せあたり [ns]
EDGE = 0.5         # 入力の遷移時間 [ns]
MEAS_BACK = 1.0    # ステップ末尾から何 ns 手前で測るか
CL = "20f"         # 出力にぶら下げる負荷
RAIL_TOL = 0.25    # フルレール判定 [V]
HERE = os.path.dirname(os.path.abspath(__file__))
# 既定は GDS から抽出した cells/*.spi。環境変数で lef/simulation/*.spice に
# 切り替えられる（生成した LVS ソースそのものを検証するため）。
# 抽出ネットリストの置き場。既定は cells_ext（loadext.py の出力）。
# 以前は {HERE}/cells を既定にしていたが、そんなディレクトリは無く、
# TR1UM_CELLDIR を設定しないと全セルが「ネットリストが無い」で飛んでいた。
CELLDIR = os.environ.get(
    "TR1UM_CELLDIR",
    f"{HERE}/cells_ext" if os.path.isdir(f"{HERE}/cells_ext") else f"{HERE}/cells")
CELLEXT = os.environ.get("TR1UM_CELLEXT", ".spi")


def all_ports_of(cell):
    """`.subckt` 行のポートを**宣言順のまま**返す。

    **電源の並び順はネットリストによって違う。**
    こちらの簡易抽出は `... vdd vss`、KLayout の抽出は `... vss vdd`。
    インスタンス行は必ずこの順に合わせること（入れ替えると電源が逆になり、
    真理値表が壊れる）。
    """
    for s in open(f"{CELLDIR}/{cell}{CELLEXT}"):
        t = s.split()
        if t and t[0].lower() == ".subckt":
            return t[2:]
    raise SystemExit(f"{cell}: .subckt 行が見つからない")


def ports_of(cell):
    """信号ピンだけ返す（電源は除く）"""
    return [p for p in all_ports_of(cell) if p not in ("vdd", "vss")]


def classify(cell, ports, ins, outs):
    """ポートを「駆動する入力 / 負荷を付ける出力 / 触らないもの」に分ける。

    **KLayout の抽出は内部ネットもピンに昇格させる。**
    DFF なら CKB / CKP / QM / QS が .SUBCKT のポートに出てくる。
    これを 0V 電源で駆動すると回路が壊れるので、
    cellspec が知っている入出力だけを扱い、残りは開放のまま結線する。
    """
    known = set(ins) | set(outs)
    return [p for p in ports if p not in known]


def to_xm(path):
    """抽出ネットリストの M 行を XM 呼び出しに直す（PDK は PMOS/NMOS がサブサーキット）"""
    out = []
    for ln in open(path):
        t = ln.split()
        if t and re.match(r"^M\w", t[0]) and len(t) >= 6:
            d, g, s, b, model = t[1:6]
            pars = " ".join(x.lower() if "=" in x else x for x in t[6:])
            out.append(f"X{t[0]} {d} {g} {s} {b} {model.upper()} {pars}")
        else:
            out.append(ln.rstrip("\n"))
    return "\n".join(out)


def build(cell, outs):
    """outs: {出力ピン: (入力ピン, fn)} を 1 本のデッキにまとめる"""
    ins = sorted({p for _, (ips, _) in outs.items() for p in ips})
    combos = list(itertools.product([0, 1], repeat=len(ins)))
    ports = ports_of(cell)

    L = [f"* {cell} 真理値表 全網羅 ({len(combos)} 通り) -- check_comb.py 生成",
         f".include {HERE}/models/ip62_models", ""]
    L.append(to_xm(f"{CELLDIR}/{cell}{CELLEXT}"))
    # 電源レールの綴りを gnd -> vss に統一したので **Vvss で明示的に接地する**。
    # ngspice は `gnd` だけを節点 0 の別名として自動で扱う。`vss` は扱わない。
    L += ["", ".temp 25", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]

    for k, p in enumerate(ins):
        pts = []
        for i, cb in enumerate(combos):
            t0 = i * STEP
            v = cb[k] * VDD
            if i == 0:
                pts.append(f"0 {v:g}")
            else:
                pts.append(f"{t0:g}n {combos[i-1][k]*VDD:g}")
                pts.append(f"{t0+EDGE:g}n {v:g}")
        L.append(f"V{k} {p} 0 PWL({' '.join(pts)})")

    # 使わない**入力**ピンだけ 0 に留める。
    # KLayout の抽出は内部ネットもピンに昇格させる（DFF の CKB/CKP/QM/QS など）ので、
    # そこを 0V 電源で駆動すると回路が壊れる。cellspec が知っている入出力だけ扱う。
    known_in = {q for _, (ips, _) in cellspec.COMB.get(cell, {}).items() for q in ips}
    driven = set(ins) | set(outs)
    for p in ports:
        if p not in driven and p in known_in:
            L.append(f"V_{p} {p} 0 0   $ このチェックでは使わない入力")
    for p in outs:
        L.append(f"C{p} {p} 0 {CL}")

    L.append("")
    L.append("XU " + " ".join(all_ports_of(cell)) + f" {cell}")
    L.append("")
    tstop = len(combos) * STEP
    L.append(f".tran 0.1n {tstop:g}n")
    for i in range(len(combos)):
        at = (i + 1) * STEP - MEAS_BACK
        for p in outs:
            L.append(f".meas tran {p}_{i:03d} FIND v({p}) AT={at:g}n")
    L += ["", ".end", ""]
    return "\n".join(L), ins, combos


RE_M = re.compile(r"^\s*([a-z]\w*)\s*=\s*([-\d.eE+]+)")


def run(cell, outs, verbose=False):
    deck, ins, combos = build(cell, outs)
    dpath = f"{HERE}/decks/{cell}_func.spi"
    open(dpath, "w").write(deck)
    r = subprocess.run(["ngspice", "-b", dpath], capture_output=True, text=True, timeout=300)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{cell}_func.log", "w").write(log)
    vals = {}
    for ln in log.splitlines():
        m = RE_M.match(ln)
        if m:
            try: vals[m.group(1)] = float(m.group(2))
            except ValueError: pass

    npass = nfail = 0
    bad = []
    for i, cb in enumerate(combos):
        env = dict(zip(ins, cb))
        for p, (ips, fn) in outs.items():
            key = f"{p.lower()}_{i:03d}"
            if key not in vals:
                bad.append((i, env, p, None, fn(*[env[x] for x in ips]), "測定値なし"))
                nfail += 1
                continue
            v = vals[key]
            exp = fn(*[env[x] for x in ips])
            got = 1 if v > VDD / 2 else 0
            rail = (v >= VDD - RAIL_TOL) if got else (v <= RAIL_TOL)
            if got == exp and rail:
                npass += 1
                if verbose:
                    print(f"    ok {env} -> {p}={v:.3f}V ({got})")
            else:
                nfail += 1
                why = "論理が違う" if got != exp else f"レールまで振れていない ({v:.3f}V)"
                bad.append((i, env, p, v, exp, why))
    return npass, nfail, bad, len(combos)


def main():
    want = sys.argv[1:] or sorted(cellspec.COMB)
    missing = [c for c in want if not os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")]
    want = [c for c in want if c not in missing]
    tp = tf = 0
    print("=" * 76)
    print(" 組合せセル 真理値表チェック (ngspice / TR-1um IP62 BSIM3 / 5V)")
    print("=" * 76)
    print(f"{'cell':<10}{'入力':>4}{'組合せ':>7}{'出力':>5}  {'PASS':>5}{'FAIL':>5}  判定")
    for cell in want:
        outs = cellspec.COMB[cell]
        ins = sorted({p for _, (ips, _) in outs.items() for p in ips})
        p, f, bad, nc = run(cell, outs)
        tp += p; tf += f
        print(f"{cell:<10}{len(ins):>4}{nc:>7}{len(outs):>5}  {p:>5}{f:>5}  "
              f"{'OK' if f == 0 else '** NG **'}")
        for i, env, pin, v, exp, why in bad[:6]:
            sv = f"{v:.3f}V" if v is not None else "-"
            print(f"           ! {env} -> {pin} 期待 {exp} / 実測 {sv} : {why}")
    print("-" * 76)
    if missing:
        print(f"ネットリストが無くて飛ばしたセル: {', '.join(missing)}")
    print(f"合計 PASS {tp} / FAIL {tf}   （{len(want)} セル）")
    return 1 if tf else 0


if __name__ == "__main__":
    sys.exit(main())

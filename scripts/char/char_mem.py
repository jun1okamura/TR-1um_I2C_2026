#!/usr/bin/env python3
"""`REG8x16`（16 ワード x 8 ビットの命令メモリマクロ）の特性化。

  usage: python3 scripts/char/char_mem.py [-n cells_mem/REG8x16.spi]
                                          [-o char/REG8x16.json] [-j 2]

P&R の本命 `td4_soc_arr_bb` は `REG8x16` をマクロとして持つので、
**これのタイミングが `.lib` に無いと STA が当てられない**。ここで測る。

セルの素性（`lef/simulation/REG8x16.spice`）:
  ラッチ型 12T ビットセル `TLAT` を 16 行 x 8 列。**クロックは無い。**
    リード  ADD[3:0] -> 行デコーダ -> RD/RDB -> TG -> ql[7:0] -> REGBUF -> Q[7:0]
            組合せ（非同期）。CPI=1 のためこれが必須。
    ライト  `WR = NOR2(RDB, WEB)` — WEB=0（アクティブロー）の間だけ選択行が
            素通しになり、**WEB の立上りでラッチ**される。

測るもの:
  1. ADD[j] -> Q[i]  リードアクセス時間（組合せアーク）。7 スルー x 7 負荷。
  2. WEB -> Q[i]     書込み中に Q が追従する経路。
  3. D / ADD の WEB 立上りに対する setup / hold。
  4. 入力容量 ADD / WEB / D。

測り方の要点:
  * **アレイにリセットが無い**ので、読む前に必ず書く。
    word0 = 0x00 / word1,2,4,8 = 0xFF を書いておくと、ADD=0 から
    ADD[j] を 1 本立てるだけで **全 8 ビットが 0x00 -> 0xFF に振れる**。
    4 本のアドレスビットすべてを 1 つの書込みパターンで賄える。
  * 負荷掃引は **Q[0..6] に別々の容量をぶら下げて 1 デッキで済ませる**。
    8 ビットは同じ列構造なので、7 個のインスタンスを並べるより 2 桁速い。
    ビット間のばらつきは Q[7] に Q[0] と同じ負荷を付けて監視する。
  * `.meas` には必ず `TD=` を入れる。入れないと書込みフェーズの
    エッジを拾ってしまう（実際に踏んだ）。

**未解決: 抽出ネットリストでは書込みが効かない。原因は PS/PD。**
  `lef/simulation/REG8x16.spice`（設計ネットリスト）では期待どおり動く
  —— word0 に 0x00、word1/2/4/8 に 0xFF を書いて読み戻せる。
  ところが `lef/extracted/REG8x16.extracted` を同じ刺激で回すと
  **どのアドレスを読んでも 5V** になる。切り分けた結果:

    そのまま         動かない
    AS/AD だけ外す   動かない
    PS/PD だけ外す   **動く**（22.28ns -> 21.81ns）

  `PS`/`PD`（接合の周長）が原因。`PS < W` のような異常値は 1876 素子中 0 件で、
  値そのものは PDK の既定式 `2*(sdwidth+w)` と桁も合う。PDK のモデル
  (`models_IP62_mos_v2.lib` の `.subckt PMOS` -> `M1 ... ps=ps pd=pd`) の
  解釈を追う必要がある。当面は設計ネットリスト（既定）で測る。

  （抽出が実行ごとに揺れるという以前の推測は**誤り**。3 回流して同一で、
    REG8x16 の抽出もバイト一致。順が違って見えたのは抽出スコープの違い。）
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
VDD, TEMP = 5.0, 25
CELL = "REG8x16"
MODELS = os.environ.get("TR1UM_MODELS", f"{HERE}/models")
FRAME_LEF = None            # マクロなので面積は cell_area.json から取る

SLEWS = [0.1, 0.25, 0.6, 1.5, 4.0, 8.0, 16.0]      # 標準セルと同じ格子
LOADS = [10, 20, 50, 100, 200, 400, 800]           # fF。Q はコアの標準セルを駆動する
SLEWS_C = [0.6, 1.5, 4.0]                          # setup/hold の格子
TH, LO, HI = 50, 20, 80
SLEW_FRAC = (HI - LO) / 100
EDGE = 0.1              # 書込みフェーズの矩形波の立上り [ns]
IDLE = 100.0            # 最初の書込みの前に置く待ち時間 [ns]
TW = 120.0              # 1 ワードの書込みに使う時間 [ns]
SETTLE = 100.0          # 書込み後に落ち着かせる時間 [ns]
TAIL = 400.0            # 測定エッジの後ろに取る時間 [ns]
WORDS = [(0, 0x00), (1, 0xFF), (2, 0xFF), (4, 0xFF), (8, 0xFF)]

APIN = [f"A{j}" for j in range(4)]
DPIN = [f"DD{i}" for i in range(8)]
QPIN = [f"QQ{i}" for i in range(8)]
# **ポート順はネットリストによって違う。**
#   抽出 (lef/extracted/REG8x16.extracted): ADD D Q WEB vdd vss
#   設計 (lef/simulation/REG8x16.spice):     ADD WEB D Q vdd vss
PORTS_EXT = " ".join(APIN + DPIN + QPIN + ["WEB", "vdd", "vss"])
PORTS_SRC = " ".join(APIN + ["WEB"] + DPIN + QPIN + ["vdd", "vss"])
PORTS = PORTS_SRC


def full_ramp(s):
    return s / SLEW_FRAC


def pwl(pts):
    """[(t_ns, v)] -> PWL 文字列"""
    return "PWL(" + " ".join(f"{t:g}n {v:g}" for t, v in pts) + ")"


def step(seq):
    """[(t_ns, v)] を**区間一定**の波形に直す（PWL は点間を線形補間するので、
    そのまま渡すと 40ns かけてだらだら遷移してしまう）。"""
    out = []
    for k, (t, v) in enumerate(seq):
        if k == 0:
            out.append((t, v))
        else:
            pv = seq[k - 1][1]
            if v != pv:
                out.append((t - EDGE, pv))
            out.append((t, v))
    return out


def write_phase():
    """word0=0x00 / word1,2,4,8=0xFF を書く波形。(add, d, web, t_end) を返す。

    **最初に IDLE の待ちが要る。** 動作点から立ち上がった直後は内部の WEB
    バッファ（16 個の DEC2 の NOR2 を駆動する）がまだ遷移中で、書込みが
    効かない。IDLE=0 / WEB 低 24ns で試したときは word0 だけ書けず、
    全アドレスが 0xFF に見えていた。
    """
    add = [[] for _ in range(4)]
    dat = [[] for _ in range(8)]
    web = [(0.0, VDD)]
    for j in range(4):
        add[j].append((0.0, 0))
    for i in range(8):
        dat[i].append((0.0, 0))
    t = IDLE
    for a, d in WORDS:
        for j in range(4):
            add[j].append((t, VDD if (a >> j) & 1 else 0))
        for i in range(8):
            dat[i].append((t, VDD if (d >> i) & 1 else 0))
        web += [(t, VDD), (t + 20, 0), (t + TW - 20, 0), (t + TW - 5, VDD)]
        t += TW
    return add, dat, web, t


def header(netlist):
    return [f".include {MODELS}/ip62_models", f".include {netlist}", "",
            f".temp {TEMP}", f"Vvdd vdd 0 {VDD}", "Vvss vss 0 0"]


def drive(L, name, pin, pts):
    L.append(f"V{name} {name}s 0 {pwl(step(pts))}")
    L.append(f"R{name} {name}s {pin} 0.001")


def build_read(netlist, bit, slew, rise):
    """ADD[bit] -> Q[0..7]。負荷は Q[0..6] に 7 点、Q[7] は Q[0] と同じ（ばらつき監視）。"""
    add, dat, web, t = write_phase()
    T0 = t + SETTLE
    tf = full_ramp(slew)
    a0 = 0 if rise else (1 << bit)
    a1 = (1 << bit) if rise else 0
    for j in range(4):
        add[j].append((t, VDD if (a0 >> j) & 1 else 0))
    web.append((t, VDD))

    L = [f"* {CELL} ADD[{bit}] -> Q  入力遷移 {slew}ns {'rise' if rise else 'fall'}"
         f"  -- char_mem.py 生成"]
    L += header(netlist)
    for j in range(4):
        pts = step(add[j])
        if j == bit:            # 測定エッジだけは指定のスルーで振る
            pts += [(T0, VDD if (a0 >> j) & 1 else 0),
                    (T0 + tf, VDD if (a1 >> j) & 1 else 0)]
        else:
            pts += [(T0 + tf, pts[-1][1])]
        L.append(f"Va{j} a{j}s 0 {pwl(pts)}")
        L.append(f"Ra{j} a{j}s A{j} 0.001")
    for i in range(8):
        drive(L, f"d{i}", f"DD{i}", dat[i] + [(T0 + tf + TAIL, dat[i][-1][1])])
    drive(L, "web", "WEB", web + [(T0 + tf + TAIL, VDD)])
    L.append(f"XU {PORTS} {CELL}")
    for i, cl in enumerate(LOADS):
        L.append(f"C{i} QQ{i} 0 {cl}f")
    L.append(f"C7 QQ7 0 {LOADS[0]}f")

    tend = T0 + tf + TAIL
    L.append(f".tran {max(min(slew, 0.5) / 20, 0.05):g}n {tend:g}n")
    vt, lo, hi = VDD * TH / 100, VDD * LO / 100, VDD * HI / 100
    td = T0 - 1.0                       # 書込みフェーズのエッジを拾わないため
    ed = "RISE=1" if rise else "FALL=1"
    for i in range(8):
        L.append(f".meas tran d{i} TRIG v(A{bit}) VAL={vt:g} {ed} TD={td:g}n "
                 f"TARG v(QQ{i}) VAL={vt:g} {ed} TD={td:g}n")
        if rise:
            L.append(f".meas tran t{i} TRIG v(QQ{i}) VAL={lo:g} RISE=1 TD={td:g}n "
                     f"TARG v(QQ{i}) VAL={hi:g} RISE=1 TD={td:g}n")
        else:
            L.append(f".meas tran t{i} TRIG v(QQ{i}) VAL={hi:g} FALL=1 TD={td:g}n "
                     f"TARG v(QQ{i}) VAL={lo:g} FALL=1 TD={td:g}n")
    # 書込みが効いているかの確認。読出し直前の Q[0] は word0 = 0x00 -> 0V のはず
    L.append(f".meas tran chk FIND v(QQ0) AT={T0 - 5:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def build_cap(netlist, pin_idx, kind):
    """入力ピンに流れ込む電荷から容量を出す。kind は 'add' / 'web' / 'd'。"""
    sl = 2.0
    add, dat, web, t = write_phase()
    T0 = t + SETTLE
    tf = full_ramp(sl)
    L = [f"* {CELL} {kind}{pin_idx} 入力容量 -- char_mem.py 生成"]
    L += header(netlist)
    tgt = {"add": f"A{pin_idx}", "web": "WEB", "d": f"DD{pin_idx}"}[kind]
    for j in range(4):
        pts = step(add[j]) + [(t, add[j][-1][1])]
        if kind == "add" and j == pin_idx:
            pts += [(T0, 0), (T0 + tf, VDD)]
        else:
            pts += [(T0 + tf + 200, pts[-1][1])]
        L.append(f"V{'in' if (kind=='add' and j==pin_idx) else f'a{j}'} "
                 f"{'insrc' if (kind=='add' and j==pin_idx) else f'a{j}s'} 0 {pwl(pts)}")
        L.append(f"R{'in' if (kind=='add' and j==pin_idx) else f'a{j}'} "
                 f"{'insrc' if (kind=='add' and j==pin_idx) else f'a{j}s'} A{j} 0.001")
    for i in range(8):
        pts = dat[i] + [(t, dat[i][-1][1])]
        if kind == "d" and i == pin_idx:
            pts = step(pts) + [(T0, 0), (T0 + tf, VDD)]
            L.append(f"Vin insrc 0 {pwl(pts)}"); L.append(f"Rin insrc DD{i} 0.001")
        else:
            drive(L, f"d{i}", f"DD{i}", pts + [(T0 + tf + 200, pts[-1][1])])
    wpts = web + [(t, VDD)]
    if kind == "web":
        wpts = step(wpts) + [(T0, VDD), (T0 + tf, 0)]
        L.append(f"Vin insrc 0 {pwl(wpts)}"); L.append("Rin insrc WEB 0.001")
    else:
        drive(L, "web", "WEB", wpts + [(T0 + tf + 200, VDD)])
    L.append(f"XU {PORTS} {CELL}")
    for i in range(8):
        L.append(f"C{i} QQ{i} 0 {LOADS[2]}f")
    L.append(f".tran 0.05n {T0+tf+200:g}n")
    L.append(f".meas tran q INTEG i(Vin) FROM={T0:g}n TO={T0+tf:g}n")
    L += ["", ".end", ""]
    return "\n".join(L)


def run(deck, tag, need=True):
    """1 デッキ回して .meas の結果を返す。

    **失敗は握りつぶさない。** ngspice が落ちても空の dict を返していたため、
    ネットリストが 1 つ無いだけで 56 デッキぶん静かに空回りしたことがある
    （`cells_mem/REG8x16_src.spi` の include に失敗していた）。
    """
    os.makedirs(f"{HERE}/decks", exist_ok=True)
    os.makedirs(f"{HERE}/logs", exist_ok=True)
    p = f"{HERE}/decks/{tag}.spi"
    open(p, "w").write(deck)
    r = subprocess.run(["ngspice", "-b", p], capture_output=True, text=True, timeout=3600)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{tag}.log", "w").write(log)
    v = {}
    for ln in log.splitlines():
        m = re.match(r"^\s*([a-z]\w*)\s*=\s*([-\d.eE+]+)", ln)
        if m:
            try: v[m.group(1)] = float(m.group(2))
            except ValueError: pass
    if need and not v:
        why = [ln for ln in log.splitlines()
               if re.search(r"(?i)\b(error|could not|fatal|no such)\b", ln)]
        raise SystemExit(
            f"** {tag}: ngspice が値を 1 つも返さなかった（exit {r.returncode}）\n"
            + "\n".join(f"   {w}" for w in why[:5])
            + f"\n   デッキ: {p}\n   ログ:   {HERE}/logs/{tag}.log")
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--netlist", default=f"{HERE}/cells_mem/{CELL}_src.spi",
                    help="既定は設計ネットリスト由来。--ext で抽出由来に切り替える")
    ap.add_argument("--ext", action="store_true",
                    help="抽出ネットリスト（cells_mem/REG8x16.spi）を使う。"
                         "**現状これは書込みが効かない。下の注意を参照**")
    ap.add_argument("-o", "--out", default=f"{HERE}/char/{CELL}.json")
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--only", choices=["read", "cap"])
    a = ap.parse_args()
    global PORTS
    if not os.path.exists(a.netlist):
        raise SystemExit(
            f"** ネットリストが無い: {a.netlist}\n"
            f"   設計ネットリストから作るには（リポジトリルートで）:\n"
            f"     python3 scripts/char/mkmemsrc.py lef/simulation/{CELL}.spice \\\n"
            f"             -o scripts/char/cells_mem/{CELL}_src.spi\n"
            f"   抽出ネットリストから作るには:\n"
            f"     python3 scripts/char/loadext.py lef/extracted -o scripts/char/cells_mem")
    if a.ext:
        PORTS = PORTS_EXT
        a.netlist = f"{HERE}/cells_mem/{CELL}.spi"
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    res = {"cell": CELL, "netlist": os.path.basename(a.netlist), "macro": True, "slews": SLEWS, "loads": LOADS,
           "read": {}, "cap": {}, "bit_spread": {}}

    if a.only in (None, "read"):
        jobs = [(b, si, sl, rise)
                for b in range(4) for si, sl in enumerate(SLEWS) for rise in (True, False)]
        def one(j):
            b, si, sl, rise = j
            tag = f"mem_a{b}_s{si}_{'r' if rise else 'f'}"
            return j, run(build_read(a.netlist, b, sl, rise), tag)
        out = {}
        with ThreadPoolExecutor(max_workers=a.jobs) as ex:
            for k, (j, v) in enumerate(ex.map(one, jobs)):
                out[j[:1] + j[1:2] + j[3:]] = v
                print(f"  [{k+1:>2}/{len(jobs)}] ADD[{j[0]}] slew {j[2]:>5}ns "
                      f"{'rise' if j[3] else 'fall'}  d(CL=100fF) = "
                      f"{(v.get('d3') or 0)*1e9:.2f} ns  chk = {v.get('chk')}", flush=True)
        for b in range(4):
            arc = {}
            for key, rise in (("cell_rise", True), ("cell_fall", False)):
                arc[key] = [[out[(b, si, rise)].get(f"d{i}") for i in range(7)]
                            for si in range(len(SLEWS))]
                tk = "rise_transition" if rise else "fall_transition"
                arc[tk] = [[out[(b, si, rise)].get(f"t{i}") for i in range(7)]
                           for si in range(len(SLEWS))]
            res["read"][f"ADD[{b}]"] = arc
            # ビット間のばらつき: Q[7] は Q[0] と同じ負荷
            sp = []
            for si in range(len(SLEWS)):
                for rise in (True, False):
                    v = out[(b, si, rise)]
                    if v.get("d0") and v.get("d7"):
                        sp.append(abs(v["d7"] - v["d0"]) / v["d0"])
            res["bit_spread"][f"ADD[{b}]"] = max(sp) if sp else None

    if a.only in (None, "cap"):
        for kind, n in (("add", 4), ("web", 1), ("d", 8)):
            for i in range(n):
                q = run(build_cap(a.netlist, i, kind), f"mem_cap_{kind}{i}").get("q")
                nm = {"add": f"ADD[{i}]", "web": "WEB", "d": f"D[{i}]"}[kind]
                res["cap"][nm] = abs(q) / VDD * 1e15 if q is not None else None
        print("\n入力容量: " + " / ".join(f"{k} {v:.1f} fF"
                                          for k, v in res["cap"].items() if v))

    got = sum(1 for arc in res["read"].values() for tbl in arc.values()
              for row in tbl for x in row if x is not None)
    if a.only in (None, "read") and got == 0:
        raise SystemExit("** 測定値が 1 点も取れなかった。logs/ を見てください")

    if os.path.exists(a.out):
        old = json.load(open(a.out))
        for k, v in old.items():
            if k not in res:
                res[k] = v
    json.dump(res, open(a.out, "w"), indent=1)
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""論理を持たないセル（TAP / FILL）を確認する。

論理が無いので真理値表は引けない。代わりに見るのは 3 つ:

  1. **vdd と vss が短絡していないこと** — DC で vdd に 5V を掛け、
     流れ込む電流を測る。短絡していれば mA オーダーになる。
  2. **電源レールが左右に導通していること** — セルを横に abut して
     使うので、左端と右端でレールが繋がっていないと電源が切れる。
     （幾何で確認: レール M1 がセル境界の左右に達しているか）
  3. **デキャップの容量** — FILL2/FILL3 は MOS 容量。小信号 AC で
     vdd から見た容量を測り、Cox×ゲート面積の手計算と突き合わせる。
"""
from __future__ import annotations
import re, subprocess, sys, os
import gdstk
import cellspec

VDD = 5.0
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from check_comb import to_xm, ports_of, all_ports_of, CELLDIR, CELLEXT    # noqa: E402

COX = 1.77          # fF/µm²
def _gds():
    """セルライブラリの GDS。実体は lef/ にある。
    `{HERE}/TR-1um_STDCELL.gds` を直に開いていたため、新規チェックアウトでは
    OSError で動かなかった（mklib.py の cell_area.json と同じ穴）。"""
    for p in (os.environ.get("TR1UM_GDS"),
              f"{HERE}/TR-1um_STDCELL.gds",
              f"{HERE}/../../lef/TR-1um_STDCELL.gds"):
        if p and os.path.exists(p):
            return p
    raise SystemExit("TR-1um_STDCELL.gds が見つからない（TR1UM_GDS で指定可）")


GDS = _gds()
L_M1, L_BOUND = (13, 0), (235, 0)


def rail_reach(cell):
    """電源レール M1 がセル境界の左右端まで届いているか（横 abut で繋がるか）"""
    lib = gdstk.read_gds(GDS)
    c = {x.name: x for x in lib.cells}[cell]
    sel = lambda ld: [p for p in c.polygons if (p.layer, p.datatype) == ld]
    b = sel(L_BOUND)[0].bounding_box()
    x0, x1, y0, y1 = b[0][0], b[1][0], b[0][1], b[1][1]
    out = {}
    # 電源レールは prBoundary の上下端そのものには届かない（内側に寄せてある）。
    # 縦につながるのではなく**横 abut でつながる**ので、見るのは
    # 「セルの上/下 1/4 にあって、左端から右端まで通っている M1 があるか」。
    h = y1 - y0
    for tag, lo, hi in (("vss", y0, y0 + h / 4), ("vdd", y1 - h / 4, y1)):
        hit = [p.bounding_box() for p in sel(L_M1)
               if lo - 1e-6 <= (p.bounding_box()[0][1] + p.bounding_box()[1][1]) / 2 <= hi + 1e-6]
        left = any(abs(h_[0][0] - x0) < 1e-6 for h_ in hit)
        right = any(abs(h_[1][0] - x1) < 1e-6 for h_ in hit)
        out[tag] = (left, right)
    return out


def gate_area(cell):
    lib = gdstk.read_gds(GDS)
    c = {x.name: x for x in lib.cells}[cell]
    sel = lambda ld: [p for p in c.polygons if (p.layer, p.datatype) == ld]
    tot = 0.0
    for ld, op in (((3, 1), "and"), ((3, 2), "not")):
        act = gdstk.boolean(sel(ld), sel((140, 0)), op, precision=1e-3)
        for g in gdstk.boolean(sel((8, 1)), act, "and", precision=1e-3):
            tot += abs(float(g.area()))
    return tot


def ntr_of(cell):
    """素子数。素子を持たないセルは LVS ソース (.spice) を作らないので、
    そちらを見ているときはファイルが無い = 素子なし として扱う。"""
    p = f"{CELLDIR}/{cell}{CELLEXT}"
    if not os.path.exists(p):
        return 0
    return sum(1 for ln in open(p) if re.match(r"^X?M\w", ln))


DVDD = 0.1        # 容量測定で vdd に重ねる電圧 [V]
TRAMP = 10.0      # その傾斜時間 [ns]  -> dV/dt = DVDD/TRAMP


def leak_and_cap(cell):
    """過渡で vdd 電流を測る。

    AC 解析の `.meas` は frequency を参照できず面倒なので、**時間領域**で見る。
      前半: vdd を 5V で保持 -> 流れる電流 = リーク（短絡があればここで跳ねる）
      後半: vdd を DVDD だけ傾斜させる -> I = I_leak + C * dV/dt
    差を dV/dt で割れば容量。1MHz 相当の実効周波数になる。
    """
    if ntr_of(cell) == 0:
        return None, None, "デバイス無し（タップ／純フィラー）。短絡も容量も測るものが無い。"
    ports = ports_of(cell)
    t0, t1 = 200.0, 200.0 + TRAMP
    L = [f"* {cell} 電源チェック -- check_pass.py 生成",
         f".include {HERE}/models/ip62_models", "",
         to_xm(f"{CELLDIR}/{cell}{CELLEXT}"), "",
         ".temp 25",
         f"Vvdd vdd 0 PWL(0 {VDD} {t0}n {VDD} {t1}n {VDD+DVDD})",
         "Vvss vss 0 0"]
    for p in ports:
        L.append(f"V_{p} {p} 0 0")
    L += ["", "XU " + " ".join(all_ports_of(cell)) + f" {cell}", "",
          f".tran 0.05n {t1+20:g}n",
          f".meas tran i_leak AVG i(Vvdd) FROM={t0-50:g}n TO={t0-1:g}n",
          f".meas tran i_ramp AVG i(Vvdd) FROM={t0+1:g}n TO={t1-1:g}n",
          "", ".end", ""]
    dpath = f"{HERE}/decks/{cell}_pwr.spi"
    open(dpath, "w").write("\n".join(L))
    r = subprocess.run(["ngspice", "-b", dpath], capture_output=True, text=True, timeout=120)
    log = r.stdout + r.stderr
    open(f"{HERE}/logs/{cell}_pwr.log", "w").write(log)

    def g(name):
        m = re.search(rf"^\s*{name}\s*=\s*([-\d.eE+]+)", log, re.M)
        return float(m.group(1)) if m else None

    il, ir = g("i_leak"), g("i_ramp")
    cap = None
    if il is not None and ir is not None:
        cap = abs(ir - il) / (DVDD / (TRAMP * 1e-9))
    return (abs(il) if il is not None else None), cap, log


def main():
    print("=" * 76)
    print(" 論理を持たないセル（TAP / FILL）の確認")
    print("=" * 76)
    print(f"{'cell':<8}{'Tr':>3}  {'リーク':>10}  {'容量 実測':>10}  {'うちゲート分':>13}  "
          f"{'レール':>7}  判定")
    ng = 0
    for cell in sorted(cellspec.PASS):
        ntr = ntr_of(cell)
        idc, cap, log = leak_and_cap(cell)
        nodev = isinstance(log, str) and log.startswith("デバイス無し")
        ga = gate_area(cell)
        chand = ga * COX                      # fF
        rr = rail_reach(cell)
        ok_rail = all(l and r for l, r in rr.values())
        # 判定
        msgs = []
        if idc is None and not nodev:
            msgs.append("電流が測れていない")
        elif idc is not None and idc > 1e-6:
            msgs.append(f"vdd-vss 短絡の疑い ({idc*1e3:.3f} mA)")
        if not ok_rail:
            msgs.append("レールがセル端に届いていない: " +
                        ", ".join(f"{k}{'左' if not v[0] else ''}{'右' if not v[1] else ''}"
                                  for k, v in rr.items() if not (v[0] and v[1])))
        # 実測はゲート容量に**拡散の接合容量・オーバーラップ容量**が上乗せされるので、
        # 手計算（Cox×ゲート面積）より必ず大きくなる。下回ったら繋がっていない。
        if chand > 0 and cap:
            if cap * 1e15 < chand * 0.8:
                msgs.append(f"実測容量 {cap*1e15:.0f} fF が Cox×面積 {chand:.0f} fF を下回る"
                            "（ゲートかレールが繋がっていない疑い）")
        si = f"{idc*1e12:8.2f} pA" if idc is not None else "       -"
        sc = f"{cap*1e15:8.1f} fF" if cap else "       -"
        sh = f"{chand:10.1f} fF" if chand else "         -"
        note = cellspec.PASS[cell]
        print(f"{cell:<8}{ntr:>3}  {si}  {sc}  {sh}  "
              f"{'OK' if ok_rail else '×':>10}  "
              f"{'OK' if not msgs else '** ' + ' / '.join(msgs)}   {note}")
        ng += bool(msgs)
    print("-" * 76)
    print("  リーク: vdd から流れ込む静的電流。pA オーダーなら vdd-vss 短絡なし。")
    print("  容量 実測: vdd を 0.1V/10ns で振ったときの電流から C = dI/(dV/dt)。")
    print("  うちゲート分: Cox 1.77 fF/µm² × ゲート面積。")
    print("  実測 - ゲート分 = 拡散の接合/オーバーラップ容量。FILL2/FILL3 とも約 130 fF で、")
    print("  両者の W が同じ（15.8/13.1µm）ことと整合する。")
    print("  レール: 電源 M1 がセル左右端まで通っているか（横 abut で繋がるか）。")
    print(f"  判定: {'全数 OK' if ng == 0 else f'{ng} 件 要確認'}")
    return 1 if ng else 0


if __name__ == "__main__":
    sys.exit(main())

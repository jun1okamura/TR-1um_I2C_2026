#!/usr/bin/env python3
"""特性化に必要な ngspice デッキを**全部まとめて**書き出す。

  usage: python3 genjobs.py -o <出力ディレクトリ>

なぜ 3 段（生成 → 実行 → 回収）に分けるか:

  ngspice はこのクラウドコンテナ（2 コア）だと並列で 50 倍遅くなるので
  逐次でしか流せず、全セルで 30 分以上かかっていた。
  デッキを先に全部書き出してしまえば、**手元の Mac（18 コア）で
  `xargs -P` 並列に流せる**。結果は .meas の行だけ 1 ファイルに集めて
  持ち帰り、`collect.py` が JSON に落とす。ログ本体は持ち帰らない。

setup/hold は二分探索をやめて**掃引**にした。二分探索は前の結果に依存するので
並列にできない。掃引なら全点が独立なので一度に流せる。
境界の近くだけ細かく刻んであるので、分解能は二分探索より良い。
"""
from __future__ import annotations
import argparse, json, os, sys
import cellspec
import char_comb, char_seq
from charlib import SLEWS, LOADS, SLEWS_C, VDD
from check_comb import CELLDIR, CELLEXT, all_ports_of

# setup/hold の掃引点 [ns]。境界（0 付近）を細かく、外側は粗く。
DT_SWEEP = ([-20.0, -16.0, -12.0, -9.0, -7.0]
            + [round(-5.0 + 0.25 * i, 2) for i in range(81)]      # -5.0 .. 15.0
            + [17.0, 20.0, 24.0, 30.0, 40.0, 60.0])


MODELS_TOKEN = "__MODELS__"


def emit(jobs, outdir, tag, deck, meta):
    """デッキを書き出す。モデルの絶対パスはプレースホルダにしておき、
    実行する機械（Mac）の PDK パスを runjobs.sh が埋める。"""
    from charlib import HERE
    deck = deck.replace(f"{HERE}/models", MODELS_TOKEN)
    open(f"{outdir}/decks/{tag}.spi", "w").write(deck)
    jobs.append({"tag": tag, **meta})


def gen_comb(jobs, outdir, cells):
    for cell in cells:
        outs = cellspec.COMB[cell]
        opins = set(outs)
        from charlib import arcs_of
        seen = set()
        for opin, ipin, side, sense in arcs_of(cell, outs):
            for si, slew in enumerate(SLEWS):
                for out_rise in (True, False):
                    rise_in = (not out_rise) if sense == "negative_unate" else out_rise
                    tag = f"{cell}_{ipin}_{opin}_s{si}_{'r' if out_rise else 'f'}"
                    emit(jobs, outdir, tag,
                         char_comb.build_delay(cell, opin, ipin, side, slew, rise_in, opins),
                         {"kind": "delay", "cell": cell, "opin": opin, "ipin": ipin,
                          "sense": sense, "si": si, "rise": out_rise})
            if ipin not in seen:
                seen.add(ipin)
                tag = f"{cell}_{ipin}_cap"
                emit(jobs, outdir, tag, char_comb.build_cap(cell, ipin, side, opins),
                     {"kind": "cap", "cell": cell, "ipin": ipin})


def gen_seq(jobs, outdir, cells):
    for cell in cells:
        spec = char_seq.SEQ[cell]
        for si, sl in enumerate(SLEWS):
            for d_rise in (True, False):
                tag = f"{cell}_ckq_s{si}_{'r' if d_rise else 'f'}"
                emit(jobs, outdir, tag, char_seq.build_ckq(cell, spec, sl, d_rise),
                     {"kind": "ckq", "cell": cell, "si": si, "rise": d_rise})
        for d_rise in (True, False):
            for di, ds in enumerate(SLEWS_C):
                for ci, cs in enumerate(SLEWS_C):
                    for mode in ("setup", "hold"):
                        for k, dt in enumerate(DT_SWEEP):
                            tag = (f"{cell}_{mode}_{di}_{ci}_"
                                   f"{'r' if d_rise else 'f'}_{k:03d}")
                            emit(jobs, outdir, tag,
                                 char_seq.build_constraint(cell, spec, cs, ds,
                                                           d_rise, dt, mode),
                                 {"kind": mode, "cell": cell, "di": di, "ci": ci,
                                  "rise": d_rise, "dt": dt})


def gen_calib(jobs, outdir, cells):
    """入力容量の較正: INV_X1 で対象ピンを N 個駆動する"""
    import calib_cap
    from charlib import arcs_of
    for cell in cells:
        if cell in cellspec.FF:
            idle = {"RSTB": 1, "SET": 0, "S": 0, "B": 0}
            pins = ["CK"] + cellspec.SEQ_PINS[cell]["data"] + cellspec.SEQ_PINS[cell]["async"]
            sides = {p: {k: v for k, v in idle.items() if k != p} for p in pins}
        elif cell in cellspec.COMB:
            sides = {i: s for o, i, s, _ in arcs_of(cell, cellspec.COMB[cell])}
            pins = list(sides)
        else:
            continue
        for pin in pins:
            for n in calib_cap.FANOUTS:
                tag = f"cal_{cell}_{pin}_{n}"
                deck = calib_cap.build_deck(cell, pin, sides.get(pin, {}), n)
                emit(jobs, outdir, tag, deck,
                     {"kind": "calib", "cell": cell, "ipin": pin, "n": n})


VFY_CELLS = ("INV_X1", "NAND2", "NOR2", "MUX2", "XOR2", "AND2_X1")
VFY_SLEW, VFY_CL = 1.0, 150.0


def gen_verify(jobs, outdir, cells):
    """.lib の検算用。格子の**間**（遷移 1.0ns / 負荷 150fF）と、
    INV_X1 で INV_X1 を N 個駆動したときの実負荷遅延。"""
    from charlib import arcs_of, header, full_ramp
    for cell in VFY_CELLS:
        if cell not in cells:
            continue
        outs = cellspec.COMB[cell]
        opin, ipin, side, sense = arcs_of(cell, outs)[0]
        for out_rise in (True, False):
            rise_in = (not out_rise) if sense == "negative_unate" else out_rise
            deck = char_comb.build_delay(cell, opin, ipin, side, VFY_SLEW,
                                         rise_in, set(outs))
            deck = deck.replace(f"C0 o0_{opin} 0 {LOADS[0]}f",
                                f"C0 o0_{opin} 0 {VFY_CL:g}f")
            emit(jobs, outdir, f"vfy_{cell}_{'r' if out_rise else 'f'}", deck,
                 {"kind": "verify", "cell": cell, "opin": opin, "ipin": ipin,
                  "rise": out_rise})
    for n in (1, 2, 4, 8):
        L = [f"* INV_X1 -> INV_X1 x{n} 実負荷での遅延"]
        L += header("INV_X1")
        L.append(f"Vin src 0 PWL(0 0 100n 0 {100+full_ramp(0.6):g}n 5)")
        L.append("Rin src A 0.001")
        L.append("XU " + " ".join("A" if p == "A" else ("Y" if p == "Y" else p)
                                  for p in all_ports_of("INV_X1")) + " INV_X1")
        for k in range(n):
            L.append("XL%d " % k + " ".join("Y" if p == "A" else
                                            (f"nc{k}" if p == "Y" else p)
                                            for p in all_ports_of("INV_X1")) + " INV_X1")
            L.append(f"Cn{k} nc{k} 0 20f")
        L.append(".tran 0.02n 260n")
        L.append(".meas tran d TRIG v(A) VAL=2.5 RISE=1 TARG v(Y) VAL=2.5 FALL=1")
        L += ["", ".end", ""]
        emit(jobs, outdir, f"vfy_fo{n}", "\n".join(L),
             {"kind": "fanout", "cell": "INV_X1", "n": n})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="/home/claude/char/pack")
    ap.add_argument("-c", "--cells", default="",
                    help="カンマ区切りでセルを絞る（動作確認用）")
    a = ap.parse_args()
    only = {c for c in a.cells.split(",") if c}
    os.makedirs(f"{a.out}/decks", exist_ok=True)

    have = lambda c: (os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")
                      and (not only or c in only))
    comb = [c for c in sorted(cellspec.COMB)
            if c not in cellspec.BLOCK_ONLY and have(c)]
    seq = [c for c in char_seq.SEQ if have(c)]
    ex = lambda c: os.path.exists(f"{CELLDIR}/{c}{CELLEXT}")
    skipped = ([c for c in sorted(cellspec.COMB)
                if c not in cellspec.BLOCK_ONLY and not ex(c)]
               + [c for c in char_seq.SEQ if not ex(c)])

    jobs = []
    gen_comb(jobs, a.out, comb)
    gen_seq(jobs, a.out, seq)
    gen_calib(jobs, a.out, comb + seq)
    gen_verify(jobs, a.out, comb)

    json.dump({"jobs": jobs, "dt_sweep": DT_SWEEP,
               "slews": SLEWS, "loads": LOADS, "slews_c": SLEWS_C,
               "comb": comb, "seq": seq, "skipped": skipped},
              open(f"{a.out}/jobs.json", "w"), indent=1)
    from collections import Counter
    c = Counter(j["kind"] for j in jobs)
    print(f"デッキ {len(jobs)} 本を {a.out}/decks に書いた")
    for k, v in sorted(c.items()):
        print(f"  {k:<8}{v:>6}")
    if skipped:
        print(f"\nネットリストが無くて外したセル: {', '.join(sorted(set(skipped)))}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""gen_chip_sim_ready.py -- **抽出ネットリストを ngspice で読める形にする**。

    layout/chip/step3_top_pins.gds
  -> layout/chip/simulation/<top>_extracted.spice   （KLayout の素の抽出）
  -> layout/chip/simulation/<top>_sim.spice         （ngspice 用）

LVS に使った `<top>.extracted`（`lvs_pnr.py -o` の出力）ではなく、
`scripts/klayout_extract.py` で**もう一度抽出し直す**。理由は名前:
LVS 用の方は比較のために平坦化しているので網が `1` `2` `3` …の番号に
なっていて、`v(xdut.x2.busy)` のように中を覗けない。klayout_extract は
階層とラベルを残すので、`tx_data[4]` や `rst_n` や `busy` がそのまま
網の名前として出てくる。

## 直すところ（V10 の `gen_chip_sim_ready_v9/v10.py` と同じ 5 点）

 1. **`\\$123` のエスケープ名**。KLayout は名前の無い網を `$123` と書き、
    SPICE 書き出しで `\\$` とエスケープする。ngspice はこれを読めない。
    `n123` にする（`$` を含む素子名・セル名も同じ。`via_1$6` -> `via_1_6`）。
 2. **角括弧のベクタ名** `tx_data[4]` -> `tx_data_4`。潰した先が元から
    別の網として存在していたら黙って短絡するので、必ず衝突を見る。
 3. **ダイオードの `A=` / `P=`** -> `AREA=` / `PJ=`。KLayout の書き出しは
    短縮形だが ngspice は受け付けない（フレームの ESD ダイオード）。
 4. **`NMOSE` というモデル名**。PDK のモデルライブラリにあるのは `MNE`
    （`models_IP62_mos_v2.lib` の `.subckt MNE d g s b`）。フレームの
    ESD セルの大きい NMOS 3 個がこれ。`MPE` 側は出てこない。
 5. **素子を 1 個も持たないセル**（OpenSUSI ロゴ、ダイシール、via の
    PCell）。ポートが 0 本の `.SUBCKT` を ngspice が嫌うので落とす。
    **ポートが 2 本以上あるものは落とさない**（中で網を繋いでいる
    可能性があるので）。

回路そのものは一切変えない。W/L と AS/AD/PS/PD は**抽出した実物の寸法**
がそのまま入っているので、拡散容量は設計値ではなくレイアウトの実測。

  usage: python3 scripts/pnr/gen_chip_sim_ready.py [--gds ...] [--top ...]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import i2c_config as cfg                                    # noqa: E402

SIM = os.path.join(cfg.CHIP, "simulation")
EXTRACT = os.path.join(os.path.dirname(HERE), "klayout_extract.py")
MODEL_RENAME = {"NMOSE": "MNE", "PMOSE": "MPE"}


def sanitize(text):
    """`\\$123` / `$` を含む識別子を ngspice が読める形に。"""
    n = [0]

    def repl(m):
        n[0] += 1
        return "n" + m.group(1)

    # `\$123`（網）と `$123`（素子名・セル名の接尾辞）の両方
    text = re.sub(r"\\\$(\w+)", repl, text)
    text = re.sub(r"\$(\w+)", lambda m: (n.__setitem__(0, n[0] + 1) or "_" + m.group(1)),
                  text)
    return text, n[0]


def debracket(text):
    """`tx_data[4]` -> `tx_data_4`。潰した先が元から居たら止める。"""
    rx = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\[(\d+)\]")
    occ = rx.findall(text)
    new = sorted({f"{b}_{i}" for b, i in occ})
    clash = [x for x in new
             if re.search(r"(?<![A-Za-z0-9_])" + re.escape(x) + r"(?![A-Za-z0-9_\[])",
                          text)]
    if clash:
        raise SystemExit(f"角括弧を潰すと元からある名前と衝突する: {clash}")
    out, k = rx.subn(r"\1_\2", text)
    return out, len({f"{b}[{i}]" for b, i in occ}), k


def fix_diodes(text):
    """`D... n+ n- MODEL A=12.96P P=14.4U` -> `AREA=` / `PJ=`。"""
    n = [0]

    def repl(m):
        n[0] += 1
        return f"{m.group(1)}AREA={m.group(2)} PJ={m.group(3)}"

    out = re.sub(r"^([Dd]\S*\s+\S+\s+\S+\s+\S+\s+)A=(\S+)\s+P=(\S+)\s*$",
                 repl, text, flags=re.M)
    return out, n[0]


def rename_models(text):
    n = 0
    for old, new in MODEL_RENAME.items():
        out, k = re.subn(rf"(?<![A-Za-z0-9_]){old}(?![A-Za-z0-9_])", new, text)
        # コメント行の "device instance ... NMOSE" も一緒に変わるが害は無い
        text, n = out, n + k
    return text, n


def drop_empty_subckts(text):
    """素子を持たないセルのうち**ポートが 0 か 1 本**のものを落とす。

    2 本以上あるものは中で網を繋いでいるかもしれないので触らない。
    落としたセルを呼んでいるインスタンス行も一緒に消す。"""
    blocks = re.findall(r"^\.SUBCKT\s+(\S+)([^\n]*(?:\n\+[^\n]*)*)\n(.*?)^\.ENDS.*?$\n?",
                        text, re.S | re.M)
    has_dev, ports, sub_of = {}, {}, {}
    for name, hdr, body in blocks:
        ports[name] = hdr.replace("+", " ").split()
        has_dev[name] = bool(re.search(r"^[XxDd]?[MmDd]_", body, re.M)) or \
            bool(re.search(r"^\s*X?M_\S+\s", body, re.M))
        sub_of[name] = set(re.findall(r"^X\S+\s+.*?\s(\S+)\s*$", body, re.M))

    def live(name, seen=None):
        seen = seen or set()
        if name in seen:
            return False
        seen.add(name)
        return has_dev.get(name, True) or any(live(s, seen) for s in sub_of.get(name, ()))

    dead = [n for n in ports if not live(n) and len(ports[n]) <= 1]
    for name in dead:
        text = re.sub(rf"^\.SUBCKT\s+{re.escape(name)}\b.*?^\.ENDS.*?$\n?",
                      "", text, flags=re.S | re.M)
        text = re.sub(rf"^X\S+(?:[^\S\n]+\S+)*[^\S\n]+{re.escape(name)}[^\S\n]*$\n?",
                      "", text, flags=re.M)
    return text, dead


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gds", default=os.path.join(cfg.CHIP, "step3_top_pins.gds"))
    ap.add_argument("--top", default=cfg.CHIP_TOP_CELL)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("--keep-extracted", action="store_true")
    # I2C の回帰は SCL=100kHz を 544 µs 流す。RING_OSC は ENB=rst_n=1 で
    # ずっと発振しているので、入れたままだと刻みが潰れて何時間も終わらない
    # （V10 も「RING_OSC を除いたファイルを用意してください」と同じ理由で
    #  分けている）。発振の確認は別の短い TB でやる。
    ap.add_argument("--no-ringosc", action="store_true",
                    help="RING_OSC のインスタンスを外す（I2C の長い回帰用）")
    a = ap.parse_args()

    os.makedirs(SIM, exist_ok=True)
    raw = os.path.join(SIM, a.top + "_extracted.spice")
    out = a.out or os.path.join(
        SIM, a.top + ("_noosc_sim.spice" if a.no_ringosc else "_sim.spice"))

    print(f"=== 抽出 {os.path.relpath(a.gds, cfg.ROOT)} ({a.top})")
    r = subprocess.run([sys.executable, EXTRACT, a.gds, a.top, "-o", raw],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:])
        raise SystemExit("klayout_extract が失敗した")
    text = open(raw, encoding="utf-8").read()

    text, n_names, n_occ = debracket(text)
    text, n_esc = sanitize(text)
    text, n_di = fix_diodes(text)
    text, n_mod = rename_models(text)
    text, dead = drop_empty_subckts(text)
    n_ro = 0
    if a.no_ringosc:
        # `\s` は改行にも当たるので **必ず** [^\S\n] で 1 行に閉じ込める。
        # 2026-09-14 に `\s` で書いてトップの X_1/X_2 ごと 23 行消した。
        text, n_ro = re.subn(
            rf"^X\S+(?:[^\S\n]+\S+)*[^\S\n]+{re.escape(cfg.RING_OSC_CELL)}[^\S\n]*$\n?",
            "", text, flags=re.M)
        if n_ro != 1:
            raise SystemExit(f"RING_OSC のインスタンスが 1 個でない: {n_ro}")

    header = [
        f"* {a.top} -- ngspice 用（**レイアウト抽出から**）",
        "* scripts/pnr/gen_chip_sim_ready.py が生成。手で編集しないこと。",
        f"*   もと : {os.path.relpath(a.gds, cfg.ROOT)}",
        "*   W/L と AS/AD/PS/PD は抽出した実物の寸法。拡散容量は実測。",
        "*",
        "* 使うときは PDK のモデルを先に読むこと:",
        "*   .include $TR1UM_PDK/libs.tech/spice/models/ip62_models",
        "",
    ]
    open(out, "w", encoding="utf-8").write("\n".join(header) + text)
    if not a.keep_extracted:
        pass
    print(f"wrote {os.path.relpath(out, cfg.ROOT)}")
    print(f"  角括弧 {n_names} 種 / {n_occ} 箇所 -> `_`")
    print(f"  `$` を含む識別子 {n_esc} 箇所 -> 潰した")
    print(f"  ダイオード A=/P= -> AREA=/PJ=  {n_di} 個")
    print(f"  モデル名の読み替え {n_mod} 箇所 ({MODEL_RENAME})")
    print(f"  素子を持たないセルを落とした: {dead}")
    if a.no_ringosc:
        print(f"  RING_OSC のインスタンスを外した（{n_ro} 個）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

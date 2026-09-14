#!/usr/bin/env python3
"""フレームの `.extracted` を ngspice で回せる形に直す。

  usage: python3 scripts/frame2sim.py lef/extracted/OSS_FRAME_GIO.extracted -o cells_pad/

`scripts/char/loadext.py`（標準セル用）との違いは 2 つ:

1. **ESD 素子はモデルが違う。** PDK には `PMOS`/`NMOS` とは別に `MPE`/`MNE` が
   あり、BSIM3 のパラメータが 60〜70 個違う（別物）。ESD 認識層 (63,2) の中に
   ある素子はそちらを使う。抽出結果では NMOS 側は `NMOSE` と区別されているが、
   **PMOS 側は ESD でも `PMOS` と書かれる**（LVS のデバイスクラス名が同じため）。
   どのサブサーキットが ESD 領域かは幾何で確認した:
     OSS_PCH_DRV / OSS_PCH_ESD -> MPE、OSS_NCH_DRV / OSS_NCH_ESD -> MNE
   プリドライバ OSS_DRV は ESD 領域の外なので通常の PMOS/NMOS。

2. ネット名 `\\$8` や素子名 `XM$1` に加えて、**`GND|gnd` のような
   「ラベルが複数付いたネット」**が出てくる。`|` は SPICE で使えないので潰す。

`AS/AD/PS/PD` は必ず残すこと。`MPE`/`MNE` のサブサーキットは既定値が **0** なので、
落とすと接合容量がまるごと消える（`PMOS`/`NMOS` は `w*sdwidth` で概算してくれる）。
"""
from __future__ import annotations
import argparse, os, re, sys

# ESD 領域にあるサブサーキット -> 使うモデル
ESD_MODEL = {
    "OSS_PCH_DRV": {"PMOS": "MPE"},
    "OSS_PCH_ESD": {"PMOS": "MPE"},
    "OSS_NCH_DRV": {"NMOSE": "MNE"},
    "OSS_NCH_ESD": {"NMOSE": "MNE"},
}
GLOBAL_MODEL = {"NMOSE": "MNE"}          # 念のため（上に載っていない場合）


def sanitize(s):
    s = re.sub(r"\\\$(\w+)", r"n\1", s)      # \$8 -> n8
    s = re.sub(r"\$(\d+)", r"\1", s)         # XM$1 -> XM1 / X$5 -> X5
    s = re.sub(r"(\w+)\|(\w+)", r"\2", s)    # GND|gnd -> gnd（後ろを採る）
    return s


def convert(text):
    # 行継続（+）をまとめてから処理する
    lines, buf = [], ""
    for ln in text.splitlines():
        if ln.startswith("+"):
            buf += " " + ln[1:].strip()
        else:
            if buf:
                lines.append(buf)
            buf = ln
    if buf:
        lines.append(buf)

    out, cur = [], None
    for ln in lines:
        s = sanitize(ln)
        m = re.match(r"^\.SUBCKT\s+(\S+)", s, re.I)
        if m:
            cur = m.group(1)
        if re.match(r"^\.ENDS", s, re.I):
            cur = None
        # ダイオード: KLayout は `A=..p P=..u`、ngspice は `area=` / `pj=`
        dd = re.match(r"^(D\w+)\s+(\S+)\s+(\S+)\s+(D[NP])\s+A=(\S+)\s+P=(\S+)\s*$", s)
        if dd:
            i, a_, c_, mod, ar, pe = dd.groups()
            s = f"{i} {a_} {c_} {mod} area={ar} pj={pe}"
        d = re.match(r"^(XM\w+)\s+(.*?)\s+(PMOS|NMOS|NMOSE)\s+(.*)$", s)
        if d:
            inst, nets, model, par = d.groups()
            model = ESD_MODEL.get(cur, {}).get(model) or GLOBAL_MODEL.get(model) or model
            s = f"{inst} {nets} {model} {par}"
        out.append(s)
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    txt = convert(open(a.src).read())
    open(a.out, "w").write(txt)
    n = len(re.findall(r"^XM", txt, re.M))
    print(f"wrote {a.out}  ({n} devices)")
    for mod in ("PMOS", "NMOS", "MPE", "MNE"):
        c = len(re.findall(rf"\s{mod}\s", txt))
        print(f"  {mod:<6}{c:>4}")


if __name__ == "__main__":
    main()

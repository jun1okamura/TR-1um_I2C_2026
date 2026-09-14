#!/usr/bin/env python3
"""KLayout のエンジンで GDS からネットリストを抽出する（TR-1um / IP62）。

  usage: python3 scripts/klayout_extract.py <gds> <top> -o out.spice [--flat]

なぜこれが要るか:
  `scripts/gds_extract.py` は標準セル向けの簡易抽出で、フレームのパッドセル
  （`OSS_ESD_5V_DIO` など）には通用しない。実際に踏んだ不具合:

    - poly が横向きに走るので W と L が入れ替わる（W=500µm の出力段が W=2µm に）
    - **ゲートを持たない P+ in Nwell を MOS の S/D と誤認**して、
      そこを通じて VDD と VSS が短絡した。PDK のランセットではこれは
      `DP = (AP.not_interacting(GC) & WN)` すなわち**ダイオード**である。
    - ESD 認識層 (63,2) を見ていないので、通常 MOS と ESD MOS を区別できない。

  これらは「簡易抽出のチューニング」で潰せる類ではないので、
  **KLayout 本体の抽出エンジンを使う**。層の導出は PDK のランセット
  （`libs.tech/klayout/tech/drc/00_Layers.drc` と `02_Device.drc`、
  `tech/lvs/01_Extract.lvs`）をそのまま写している。

  MOS とダイオードだけを見る。抵抗 (3,3)/(8,2) と容量 (3,4) はフレームにも
  標準セルにも出てこないので実装していない（出てきたら気づけるよう検査する）。
"""
from __future__ import annotations
import re
import argparse, os, sys

try:
    import klayout.db as db
except ImportError:
    sys.exit("pip install klayout")

# 00_Layers.drc の入力層
LAYERS = {
    "ESD": (63, 2), "WN": (140, 0), "AP": (3, 1), "AN": (3, 2),
    "AR": (3, 3), "AC": (3, 4), "GC": (8, 1), "GR": (8, 2),
    "CO": (11, 0), "M1": (13, 0), "V1": (19, 0), "M2": (20, 0), "PO": (14, 0),
}
LBL = {"M1_LBL": (48, 0), "M2_LBL": (49, 0)}
UNSUPPORTED = {"AR": "抵抗 RR", "AC": "容量 CSIO", "GR": "抵抗 RS"}


def build(gds, top, flat=False):
    ly = db.Layout()
    ly.read(gds)
    tc = ly.cell(top)
    if tc is None:
        sys.exit(f"top cell {top} が GDS に無い: {[c.name for c in ly.each_cell()]}")

    l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(ly, tc, []))
    if not flat:
        l2n.include_floating_subcircuits = True

    def lay(name):
        li = ly.layer(*LAYERS[name])
        return l2n.make_layer(li, name)

    R = {k: lay(k) for k in LAYERS}
    for k, what in UNSUPPORTED.items():
        if not R[k].is_empty():
            print(f"** {what}の層 {LAYERS[k]} に図形がある。このスクリプトは"
                  f"抽出しないので、KLayout のランセットを使ってください。")

    # ラベルはテキストとして読む
    txt = {}
    for k, (l, d) in LBL.items():
        txt[k] = l2n.make_text_layer(ly.layer(l, d), k)

    # DRC の `BULK = extent`。バックゲート端子としてはグローバルネットに繋ぐ
    # 空の層を使い、層演算用には版全体の矩形を使う。
    BULK = db.Region()                     # 基板（グローバルネット VSS）
    l2n.register(BULK, "BULK")
    WN, AP, AN, GC, CO, M1, V1, M2, ESD, PO = (
        R["WN"], R["AP"], R["AN"], R["GC"], R["CO"], R["M1"],
        R["V1"], R["M2"], R["ESD"], R["PO"])
    # DRC の `WP = BULK - WN`（BULK = extent）。図形は必ず extent の中にあるので
    # 「WP と交わる」は「WN の外」と同じ。deep region を保つためこう書く。

    # 02_Device.drc
    MP = (AP.interacting(GC) & WN) - ESD           # 通常 PMOS の拡散
    MN = (AN.interacting(GC) - WN) - ESD           # 通常 NMOS の拡散
    MPE = (AP.interacting(GC) & WN) & ESD          # ESD PMOS
    MNE = (AN.interacting(GC) - WN) & ESD          # ESD NMOS
    GP = AN & WN                                   # PMOS のバックゲート接続（Nwell tie）
    GN = AP - WN                                    # NMOS のバックゲート接続（基板 tie）
    DP = AP.not_interacting(GC) & WN               # **ゲートの無い P+ in Nwell = ダイオード**
    DN = AN.not_interacting(GC) - WN               # ゲートの無い N+ in 基板 = ダイオード
    SDP, SDN = MP - GC, MN - GC
    SDPE, SDNE = MPE - GC, MNE - GC
    M2P = (M2 & PO).sized(int(round(5.0 / ly.dbu)))   # PAD（5µm 太らせる）

    for name, reg in (("MP", MP), ("MN", MN), ("MPE", MPE), ("MNE", MNE),
                      ("GP", GP), ("GN", GN), ("DP", DP), ("DN", DN),
                      ("SDP", SDP), ("SDN", SDN), ("SDPE", SDPE), ("SDNE", SDNE),
                      ("M2P", M2P)):
        l2n.register(reg, name)

    # 01_Extract.lvs
    def mos(cls, sd, mdiff, well, tb):
        l2n.extract_devices(db.DeviceExtractorMOS4Transistor(cls), {
            "SD": mdiff - GC, "G": mdiff & GC,
            "W": (mdiff & GC & well) if well is not None else (mdiff & GC),
            "tS": sd, "tD": sd, "tG": GC, "tB": tb})

    mos("PMOS", SDP, MP, WN, WN)
    mos("NMOS", SDN, MN, None, BULK)
    mos("PMOS", SDPE, MPE, WN, WN)
    mos("NMOSE", SDNE, MNE, None, BULK)
    l2n.extract_devices(db.DeviceExtractorDiode("DP"),
                        {"P": DP, "N": DP, "tA": DP, "tC": WN})
    # DRC の `"P" => (DN & BULK)` は BULK=extent なので DN そのもの
    l2n.extract_devices(db.DeviceExtractorDiode("DN"),
                        {"P": DN, "N": DN, "tA": BULK, "tC": DN})

    # 02_Device.drc の connect 群
    l2n.connect_global(BULK, "VSS")
    l2n.connect_global(GN, "VSS")
    l2n.connect(WN, GP)
    for a, b in ((SDP, CO), (SDN, CO), (SDPE, CO), (SDNE, CO),
                 (GP, CO), (GN, CO), (DP, CO), (DN, CO),
                 (GC, CO), (CO, M1), (M1, V1), (V1, M2), (M2, M2P)):
        l2n.connect(a, b)
    for r in (GC, CO, M1, V1, M2, SDP, SDN, SDPE, SDNE, DP, DN, GP, GN, WN):
        l2n.connect(r)                    # 同一層内の導通
    l2n.connect(M1, txt["M1_LBL"])
    l2n.connect(M2, txt["M2_LBL"])

    l2n.extract_netlist()
    return l2n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gds"); ap.add_argument("top")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--flat", action="store_true", help="階層を潰して抽出する")
    a = ap.parse_args()

    l2n = build(a.gds, a.top, a.flat)
    nl = l2n.netlist()
    nl.make_top_level_pins()
    nl.combine_devices()
    nl.purge()
    nl.purge_nets()
    if a.flat:
        nl.flatten()
        # flatten() でピンに繋がるネットの**名前が落ちる**（ピン自身は名前を
        # 保っているのに .SUBCKT 行がネット番号になり、そのままでは使えない）。
        # ピン名をネット名に書き戻す。
        for c in nl.each_circuit():
            for pin in c.each_pin():
                net = c.net_for_pin(pin.id())
                if net is not None and pin.name() and not net.name:
                    net.name = pin.name()

    w = db.NetlistSpiceWriter()
    # 既定はネット番号。これだと .SUBCKT 行まで番号になって ngspice に持って
    # いけない（--flat で顕著）。名前の付いたネットは名前で書かせる。
    # lef/extracted/*.extracted（PDK の LVS ランセット出力）と同じ書き方になる。
    w.use_net_names = True
    nl.write(a.out, w, f"TR-1um {a.top} — KLayout 抽出 (scripts/klayout_extract.py)")
    # MOS を `M...` で書くが、PDK の PMOS/NMOS は `.model` ではなく
    # **サブサーキット**なので `XM...` でないと ngspice に持っていけない。
    # lef/extracted/ の既存ファイル（PDK の LVS ランセット出力）も XM なので
    # 同じ綴りに揃える。
    txt = open(a.out).read()
    txt = re.sub(r"^M(?=[\w$])", "XM", txt, flags=re.M)
    open(a.out, "w").write(txt)
    print(f"wrote {a.out}")
    for c in nl.each_circuit():
        nd = sum(1 for _ in c.each_device())
        ns = sum(1 for _ in c.each_subcircuit())
        nn = sum(1 for _ in c.each_net())
        print(f"  {c.name:<20} device {nd:>5}  subckt {ns:>3}  net {nn:>5}  "
              f"pins {[p.name() for p in c.each_pin()]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""gen_chip_tb_batch14.py -- V10 の 14 項目回帰を今のチップへ移植する。

    reference/v10/tb_chip_i2c_batch14_v10.spice        （刺激だけ借りる）
  + reference/v10/spice_batch14_v10_expected.json      （14 項目の定義）
  + layout/chip/simulation/<top>_noosc_sim.spice       （抽出 -> ngspice）
  -> layout/chip/simulation/tb_batch14.spice
  -> layout/chip/simulation/spice_batch14_expected.json

## 何をそのまま借りて、何を差し替えるか

**刺激（PWL）はそのまま**。パッドの割り当ては V10 と同じ（P1 SCL /
P2 SDA / P3-P6・P11-P14 データ / P7 DIS / P15 RSTN / P9 OSCD / P10 OSC /
P8 VSS / P16 VDD）で、`layout/chip/gio_connections.json` と一致している。
SCL=100kHz、A0/A1/22 の 3 トランザクション:

    WRITE : S, ADDR+W(0xA0), ACK, DATA=0xA5, ACK, P
    READ  : S, ADDR+R(0xA1), ACK, DATA=0x3C（スレーブが出す）, NACK, P
    NEG   : S, ADDR+W(0x22 = 別アドレス 0x11), NACK が返ること, P

刺激が同じなので `.measure` の時刻も V10 のまま使える。

**差し替えるのは網の名前だけ**。V10 は未ボンドのコア出力を `NC_CORE_busy`
のような名前で、rx_data をフレームの `NC_OUT3` … で覗いていた。こちらは
**レイアウト抽出**から作った階層付きのネットリストなので、コアの
インスタンス（`X_1`）の中の本当の名前で覗ける:

    xdut.NC_CORE_busy        -> xdut.x_1.busy
    xdut.NC_CORE_addr_match  -> xdut.x_1.addr_match
    xdut.NC_CORE_rw          -> xdut.x_1.rw
    xdut.NC_OUT3 … NC_OUT14  -> xdut.x_1.rx_data_0 … rx_data_7
    P2                       -> そのまま（SDA のボンドパッド）

V10 が持っていた 1000 本超の診断用 `.measure`（`shreg_*` や `_087_` など）は
**落とす**。あれは V10 の合成結果に固有の内部網で、こちらは合成をやり直して
いるので同じ名前は存在しない。14 項目の判定に要るのは 28 本だけ。

## RING_OSC は外す

`--no-ringosc` で作ったネットリストを使う。ENB = P15 = rst_n なので、
入れたままだと 544 µs のあいだ 190 段が発振し続けて刻みが潰れる。
V10 も同じ理由で分けている。P9 / P10 は浮くので 1 GΩ で落とす。

  usage: python3 scripts/pnr/gen_chip_tb_batch14.py [--tmax 10n] [--until 544u]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i2c_config as cfg                                    # noqa: E402

REF = os.path.join(cfg.ROOT, "reference", "v10")
V10_TB = os.path.join(REF, "tb_chip_i2c_batch14_v10.spice")
V10_JSON = os.path.join(REF, "spice_batch14_v10_expected.json")
SIM = os.path.join(cfg.CHIP, "simulation")

CORE_INST = "x_1"          # 抽出ネットリストでのコアのインスタンス名
# rx_data のビット -> V10 がそれを覗いていたフレームの OUT 端子
RX_PAD = (3, 4, 5, 6, 11, 12, 13, 14)


def core_pin_nets(netlist):
    """コアの `.subckt` のポート名 -> **チップでの網の名前**。

    `busy` / `addr_match` / `rw` はコアの外に出ていない内部網なので
    `xdut.x_1.busy` で覗ける。一方 `rx_data_*` は**ポート**なので、
    ngspice は subckt の中に節点を作らない（親の網の別名になる）。
    `v(xdut.x_1.rx_data_0)` は "no such vector" になるので、トップの
    インスタンス行と `.subckt` のポート順を突き合わせて親側の名前
    （`n117` のような抽出名）に直す。2026-09-14 に実際に踏んだ。"""
    t = open(netlist, encoding="utf-8").read()

    def header(name):
        m = re.search(rf"^\.SUBCKT\s+{re.escape(name)}([^\n]*(?:\n\+[^\n]*)*)",
                      t, re.M)
        return m.group(1).replace("+", " ").split()

    ports = header(cfg.TOP_CELL_NAME)
    m = re.search(rf"^(X\S+(?:[^\S\n]+\S+)*[^\S\n]+{re.escape(cfg.TOP_CELL_NAME)}"
                  r"[^\S\n]*)$", t, re.M)
    if m is None:                       # 継続行に分かれている場合
        m = re.search(rf"^(X\S+[^\n]*(?:\n\+[^\n]*)*{re.escape(cfg.TOP_CELL_NAME)})"
                      r"[^\S\n]*$", t, re.M)
    inst = m.group(1).replace("\n+", " ").replace("+", " ").split()
    nets = inst[1:-1]                   # 先頭はインスタンス名、末尾はセル名
    if len(nets) != len(ports):
        raise SystemExit(f"コアのポート {len(ports)} 本 vs 実線 {len(nets)} 本")
    return dict(zip(ports, nets))


def make_map(netlist):
    pin = core_pin_nets(netlist)
    m = {f"xdut.NC_CORE_{n}": f"xdut.{CORE_INST}.{n}"
         for n in ("busy", "addr_match", "rw", "rx_valid")}
    for b, p in enumerate(RX_PAD):
        want = f"rx_data_{b}"
        if want not in pin:
            raise SystemExit(f"コアに {want} のポートが無い")
        m[f"xdut.NC_OUT{p}"] = f"xdut.{pin[want]}"
    return m


def remap(net, m):
    if net in m:
        return m[net]
    if re.fullmatch(r"P\d+|VDD|VSS", net):
        return net
    raise SystemExit(f"どこへ写せばいいか分からない網: {net!r}")


def stimulus(path):
    """V10 の TB から刺激だけ切り出す（`.param` から `xdut` の手前まで）。"""
    lines = open(path, encoding="utf-8").read().splitlines()
    try:
        a = next(i for i, l in enumerate(lines) if l.startswith(".param"))
        b = next(i for i, l in enumerate(lines) if l.startswith("xdut "))
    except StopIteration:
        raise SystemExit(f"{path} の形が想定と違う")
    # `.include` はこちらで書き直すので落とす
    return [l for l in lines[a:b] if not l.startswith(".include")]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tmax", default="10n",
                    help="ngspice の最大刻み（V10 は 1n。粗いと setup 余裕を"
                         "取りこぼす。既定 10n）")
    ap.add_argument("--until", default="544u", help="いつまで流すか")
    ap.add_argument("--netlist", default=None)
    ap.add_argument("-o", "--out", default=os.path.join(SIM, "tb_batch14.spice"))
    ap.add_argument("--models", default=None,
                    help="PDK のモデル（既定: $TR1UM_PDK から絶対パスで）")
    a = ap.parse_args()

    if a.models is None:
        pdk = os.environ.get("TR1UM_PDK") or os.path.join(cfg.ROOT, "TR-1um")
        a.models = os.path.join(pdk, "libs.tech", "spice", "models", "ip62_models")
    net = a.netlist or os.path.join(SIM, cfg.CHIP_TOP_CELL + "_noosc_sim.spice")
    if not os.path.exists(net):
        raise SystemExit(f"{net} が無い。先に\n"
                         f"  python3 scripts/pnr/gen_chip_sim_ready.py --no-ringosc")
    nmap = make_map(net)
    checks = json.load(open(V10_JSON, encoding="utf-8"))
    if len(checks) != 14:
        raise SystemExit(f"14 項目でない: {len(checks)}")

    # トップの `.subckt` のポート順は KLayout が決めるので、決め打ちしない
    hdr = re.search(rf"^\.SUBCKT\s+{re.escape(cfg.CHIP_TOP_CELL)}"
                    r"([^\n]*(?:\n\+[^\n]*)*)", open(net, encoding="utf-8").read(),
                    re.M).group(1)
    ports = hdr.replace("+", " ").split()

    meas, out_checks = [], []
    for c in checks:
        c = dict(c)
        if c["kind"] == "level":
            c["net"] = remap(c["net"], nmap)
            meas.append((c["name"], c["net"], c["t"], c["desc"]))
        else:
            c["nets"] = [remap(n, nmap) for n in c["nets"]]
            for k, (n, t) in enumerate(zip(c["nets"], c["t_per_bit"]
                                           if "t_per_bit" in c else
                                           [c["t"]] * len(c["nets"]))):
                meas.append((f'{c["name"]}_bit{k}', n, t, f'{c["desc"]} bit{k}'))
        out_checks.append(c)

    # byte の各ビットの時刻は V10 の TB の `.measure` 行から拾う（JSON には
    # まとめた 1 つしか入っていない）。名前が `<check>_bit<k>` で並んでいる。
    v10 = open(V10_TB, encoding="utf-8").read()
    per_bit = {}
    for m in re.finditer(r"^\.measure tran (\w+) FIND v\(([^)]+)\) AT=(\S+)", v10, re.M):
        per_bit[m.group(1)] = (m.group(2), float(m.group(3)))
    meas = []
    for c in out_checks:
        if c["kind"] == "level":
            meas.append((c["name"], c["net"], c["t"], c["desc"]))
            continue
        for k in range(len(c["nets"])):
            key = f'{c["name"]}_bit{k}'
            if key not in per_bit:
                raise SystemExit(f"V10 の TB に {key} の .measure が無い")
            meas.append((key, c["nets"][k], per_bit[key][1], f'{c["desc"]} bit{k}'))

    body = [
        "* tb_batch14.spice -- scripts/pnr/gen_chip_tb_batch14.py が生成。",
        "* 手で編集しないこと。",
        "*",
        "* V10 の 14 項目回帰（reference/v10/）の刺激をそのまま、",
        "* **レイアウト抽出から作ったネットリスト**に当てる。",
        "*   WRITE : S, ADDR+W(0xA0), ACK, DATA=0xA5, ACK, P",
        "*   READ  : S, ADDR+R(0xA1), ACK, DATA=0x3C（スレーブが出す）, NACK, P",
        "*   NEG   : S, ADDR+W(0x22 = 別アドレス 0x11), NACK, P",
        "* SCL = 100 kHz。RING_OSC は外してある（P9 / P10 は 1G で落とす）。",
        "",
        # `.include` は **TB と同じディレクトリからの相対**で書く。
        # `cd layout/chip/simulation && ngspice -b tb_batch14.spice` で流す。
        f".include '{a.models}'",
        f".include '{os.path.basename(net)}'",
        "",
    ] + stimulus(V10_TB) + [
        "",
        "xdut " + " ".join(ports) + f" {cfg.CHIP_TOP_CELL}",
        "",
        f".tran 50n {a.until} 0 {a.tmax}",
        "",
        "* ---- 14 項目 ----",
    ]
    for name, netname, t, desc in meas:
        body.append(f".measure tran {name} FIND v({netname}) AT={t:g}  $ {desc}")
    body += ["", ".end", ""]

    os.makedirs(SIM, exist_ok=True)
    open(a.out, "w", encoding="utf-8").write("\n".join(body))
    js = os.path.join(SIM, "spice_batch14_expected.json")
    json.dump(out_checks, open(js, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"wrote {os.path.relpath(a.out, cfg.ROOT)}")
    print(f"wrote {os.path.relpath(js, cfg.ROOT)}")
    print(f"  ネットリスト {os.path.relpath(net, cfg.ROOT)}")
    print(f"  トップのポート {len(ports)} 本: {' '.join(ports)}")
    print(f"  .measure {len(meas)} 本 / 判定 {len(out_checks)} 項目")
    print(f"  .tran 50n {a.until} 0 {a.tmax}")
    print(f"  流し方: cd {os.path.relpath(SIM, cfg.ROOT)} && "
          f"ngspice -b {os.path.basename(a.out)} > batch14.log 2>&1")
    print("  網の読み替え: " + ", ".join(f"{k}->{v}" for k, v in sorted(nmap.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())

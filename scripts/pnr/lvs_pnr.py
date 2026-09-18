#!/usr/bin/env python3
"""lvs_pnr.py -- 配置配線したコアの LVS（レイアウト抽出 vs 設計意図）。

  usage: python3 scripts/pnr/lvs_pnr.py <gds> <top> <src.spice> [-o <lay.spice>]

`scripts/lvs_check.py` と目的は同じだが、**P&R したコア**向けに 3 つ違う:

  1. `combine_devices()` を掛けない（`--combine` で掛けられる）。
     掛けると KLayout が
       `Internal error: Terminal still connected after removing device in
        device combination: name=, circuit=DFFRB, terminal=D`
     で落ちる。この設計のセルは全部シングルフィンガで、直列/並列の
     まとめが要る形（マルチフィンガ）が無いので、**両側とも掛けなければ**
     比較の意味は変わらない。
  2. 不一致のとき**どこが合わないか**を出す。`GenericNetlistCompareLogger` を
     継承して、照合できなかったネット・デバイス・ピンを拾う。
  3. 抽出結果を `-o` で保存できる（既定は保存しない）。

ソース側は `scripts/pnr/mklvsnet.py` が作ったもの。
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE)))   # scripts/
import i2c_config as cfg                                    # noqa: E402

import klayout.db as db                                     # noqa: E402
import klayout_extract                                      # noqa: E402


class Logger(db.GenericNetlistCompareLogger):
    """不一致だけを溜める。

    KLayout はコールバック名で呼ぶので、**溜める入れ物にコールバックと同じ名前を
    使ってはいけない**（属性がメソッドを隠して呼べなくなる）。"""

    def __init__(self):
        super().__init__()
        self.m = {"circuit": [], "pin": [], "device": [], "subcircuit": [], "net": []}
        self.errors = []

    @staticmethod
    def _n(x):
        if x is None:
            return "(なし)"
        for attr in ("expanded_name", "name"):
            try:
                v = getattr(x, attr)()
                if v:
                    return str(v)
            except Exception:
                pass
        return str(x)

    def _add(self, kind, a, b):
        self.m[kind].append((self._n(a), self._n(b)))

    # --- KLayout が呼ぶ ---
    def circuit_mismatch(self, a, b, msg=None):
        self._add("circuit", a, b)

    def net_mismatch(self, a, b, msg=None):
        self._add("net", a, b)

    def match_ambiguous_nets(self, a, b, msg=None):
        self.m["net"].append((self._n(a) + " (曖昧)", self._n(b) + " (曖昧)"))

    def device_mismatch(self, a, b, msg=None):
        self._add("device", a, b)

    def pin_mismatch(self, a, b, msg=None):
        self._add("pin", a, b)

    def subcircuit_mismatch(self, a, b, msg=None):
        self._add("subcircuit", a, b)

    def log_entry(self, level, msg):
        if level != db.GenericNetlistCompareLogger.Info:
            self.errors.append(f"[{level}] {msg}")


def normalize(nl, combine=False, flat=True):
    nl.make_top_level_pins()
    if combine:
        nl.combine_devices()
    nl.purge()
    nl.purge_nets()
    if flat:
        nl.flatten()
    return nl


def summary(nl, top):
    c = nl.circuit_by_name(top)
    devs = sum(len(list(x.each_device())) for x in nl.each_circuit())
    nets = sum(len(list(x.each_net())) for x in nl.each_circuit())
    return (sum(1 for _ in nl.each_circuit()),
            sum(1 for _ in c.each_pin()) if c else 0, devs, nets)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gds")
    ap.add_argument("top", nargs="?", default=cfg.TOP_CELL_NAME)
    ap.add_argument("src")
    ap.add_argument("-o", "--out", default=None, help="抽出ネットをここへ書く")
    ap.add_argument("--combine", action="store_true",
                    help="combine_devices() を掛ける（この設計では落ちる）")
    ap.add_argument("--hier", action="store_true", help="平坦化せずに比べる")
    ap.add_argument("--tie-floating-power", action="store_true",
                    help="トップピンを持たない電源の島を VDD / GND に**仮に**繋いでから"
                         "比べる（電源を配線する前に、他が合っているかを見るため）")
    a = ap.parse_args()

    print(f"=== 抽出 {os.path.relpath(a.gds, cfg.ROOT)} ({a.top})")
    l2n = klayout_extract.build(a.gds, a.top)
    lay = l2n.netlist().dup()
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
        l2n.netlist().write(a.out, db.NetlistSpiceWriter(),
                            f"TR-1um {a.top} — KLayout 抽出 (lvs_pnr.py)")
        print(f"  wrote {os.path.relpath(a.out, cfg.ROOT)}")
    normalize(lay, combine=a.combine, flat=not a.hier)

    print(f"=== ソース {os.path.relpath(a.src, cfg.ROOT)}")
    sch = db.Netlist()
    sch.read(a.src, db.NetlistSpiceReader())
    normalize(sch, combine=a.combine, flat=not a.hier)

    # --- 電源の島（トップピンを持たない大きなネット）を探す --------------------
    # P&R したコアで真っ先に出るのはこれ。マクロを横に置くと、マクロの
    # 電源ポートは行のレールと**金属では繋がっていない**ので、抽出すると
    # マクロ内部の vdd が「ピンを持たない巨大なネット」として独立する。
    # 実測（縦置き）: VDD 1757 端子 + `$3.vdd` 1476 端子に割れていた。
    islands = []
    c = lay.circuit_by_name(a.top)
    if c is not None:
        for n in c.each_net():
            if len(list(n.each_pin())) == 0 and len(list(n.each_terminal())) >= 100:
                islands.append(n)
    if islands:
        print(f"\n  ** 電源の島が {len(islands)} 個ある（トップピンに繋がっていない）:")
        for n in islands:
            print(f"       {n.expanded_name()}  端子 {len(list(n.each_terminal()))} 本")
        print("     -> 金属で電源が繋がっていない。--tie-floating-power で"
              "仮に繋いで残りを確かめられる。")
        if a.tie_floating_power:
            tgt = None
            for n in c.each_net():
                if n.expanded_name() in ("VDD", "GND"):
                    tgt = tgt or n
            for n in islands:
                nm = n.expanded_name()
                want = "GND" if nm.lower().endswith("vss") or "gnd" in nm.lower() else "VDD"
                dst = next((x for x in c.each_net() if x.expanded_name() == want), tgt)
                print(f"     (仮) {nm} を {dst.expanded_name()} に繋いだ")
                c.join_nets(dst, n)

    lc, lp, ld, ln = summary(lay, a.top)
    sc, sp, sd, sn = summary(sch, a.top)
    print(f"  レイアウト: circuit {lc} / top pin {lp} / device {ld} / net {ln}")
    print(f"  ソース    : circuit {sc} / top pin {sp} / device {sd} / net {sn}")

    log = Logger()
    cmp_ = db.NetlistComparer(log)
    ok = cmp_.compare(lay, sch)

    print("\n=== LVS: " + ("**一致**" if ok else "**不一致**"))
    if not ok:
        for title in ("circuit", "pin", "device", "subcircuit", "net"):
            rows = log.m[title]
            if not rows:
                continue
            print(f"\n  {title} が合わない: {len(rows)} 件（先頭 20 件）")
            for x, y in rows[:20]:
                print(f"    レイアウト {x:40s}  ソース {y}")
        if log.errors:
            print(f"\n  ログ: {len(log.errors)} 件（先頭 20 件）")
            for e in log.errors[:20]:
                print("    " + e)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

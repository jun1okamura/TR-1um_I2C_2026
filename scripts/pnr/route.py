#!/usr/bin/env python3
"""route.py -- placement GDS -> routed core, following the I2C pipeline.

The stage order and every routing script are those of
TR-1um_Async_I2C/script/run_v10_pipeline.py; only the paths, the top cell
name and the per-design net sets are this project's (see scripts/PORTING.md).

Stages, each leaving its own GDS:

  step5  配置 JSON 変換 + 配置 GDS + チャネル注釈
  step6  channel routing (5 internal passes,  route_channels_nrow_fm.py
         each checkpointed as its own GDS)
  step7  short rip-up / re-route              ripup_reroute_shorts.py
  step8  top-level pin pull-out               route_top_pins_nrow_fm.py
  step9  VDD/GND chip-level pins              add_power_pins_nrow_fm.py
  step10 channel compaction                   squeeze_channels_nrow_fm.py
  step11 マクロ電源の接続                     connect_macro_power.py
         then two coverage checks: every top-level port has a pin marker,
         and every pin marker really reaches its cell pin
         (PIN markers and their labels are protected from the compaction --
          see scripts/port_rules.py)

  usage:
    scripts/route.py                 # all stages
    scripts/route.py --to 6          # stop after channel routing
    scripts/route.py --from 7        # resume
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spi_config as cfg  # noqa: E402

# --- per-design routing hints -------------------------------------------
# Both are empirical on the I2C chip and MUST be re-derived here; start
# empty and add nets only when verify_connectivity reports a short that the
# rip-up pass cannot clear (see run_v10_pipeline.py's own note).
# TD4: clk_buf は 25 個の DFF の CK を、rst_n_buf は同じ 25 個の RSTB を叩く。
# どちらも全行にシンクがあるので、行ごとにローカルなスパインへ分けさせる。
def _macro_nets():
    """`MEMPORT` につながる 21 本。配置 JSON のマクロのピンから取る。"""
    import json as _j
    try:
        pl = _j.load(open(cfg.PLACEMENT_JSON))
    except Exception:
        return set()
    # マクロは row0 とは限らない（縦置きの `TD4_MACRO_ROW`）。全行を見る。
    for row in pl["rows"]:
        for i in row:
            if i["type"] == cfg.MACRO_CELL:
                return {p["net"] for p in i["pins"].values() if p["net"]}
    return set()


# clk_buf / rst_n_buf に加えて**マクロの 21 本も per-row-local にする**。
#
# これらはパッドが帯の上辺（= ch[0] の下）にしか無いので spine は ch[0] 固定。
# そこから row1..row3 のシンクへ登るたびに draw_jog が新しいトラックを取り、
# x が 5.4 ずつずれる階段になる。実測（普通の spanning 扱い）:
#   縦 M2 セグメント  マクロ系 15.2 本/ネット vs その他 5.2 本/ネット
#   rom_data[4] は 41 本・15 列（623.7…683.1 に 10 列連続）
# per-row-local は行ごとに専用の guarded トラックを持つので、同じ扇形でも
# clk_buf は 2.6 本/ピンで済んでいる（rom_data[4] は 8 本/ピン）。
# **per-row-local にするネットは配置から自動で決める。**
#
# 既定の spanning 扱いは「ピン 1 本ごとに行を跨いで、そのたび新しいトラックを
# 取る」ので、同じ行に複数のピンがあるネットは**同じ行を何度も跨ぐ**。
# 実測（手で 10 本だけ指定していたとき）: 行またぎ 113 本のうち **45 本 (40%)
# が重複**。`\u_core.pc [1]` は row0 を 5 回跨ぎ、ch[1] に 5 本の平行トランク
# （y 373.0/378.4/383.8/389.2/394.6）を持っていた。x 395.2…438.4 に 10.8 µm
# 間隔で 5 本の縦 M2 が並ぶ、あの形がこれ。
#
# per-row-local は行ごとに専用トラックを 1 本持つので重複しない。ただし専用
# トラックはチャネルを太らせるので、**ピン数が多く複数行にまたがるものだけ**に
# 絞る。しきい値は `TD4_PRL_MIN_PINS`（既定 5）。
PRL_MIN_PINS = int(os.environ.get("TD4_PRL_MIN_PINS", "5"))


def _prl_nets():
    import collections
    try:
        pl = json.load(open(cfg.PLACEMENT_JSON))
    except Exception:
        return set()
    npin = collections.Counter()
    nrow = collections.defaultdict(set)
    for r, row in enumerate(pl["rows"]):
        for i in row:
            if i["type"] == cfg.MACRO_CELL:
                continue
            for p in i["pins"].values():
                if p["use"] in ("POWER", "GROUND") or not p["net"]:
                    continue
                npin[p["net"]] += 1
                nrow[p["net"]].add(r)
    return {n for n in npin if npin[n] >= PRL_MIN_PINS and len(nrow[n]) >= 2}


def side_bus_nets():
    """コア右の縦 M2 バスに乗せるネット（縦置きのみ）。

    マクロの `Q[*]`（= `rom_data[*]`）。実測でチャネル span が大きいのは
    この 8 本だけで、`D[*]` `nib_lo[*]` は ch[0…2] に収まる。
    **stage6 の中で呼ぶこと**（`per_row_local_nets` と同じ理由）。
    """
    if getattr(cfg, "MACRO_MODE", "landscape") != "portrait":
        return set()
    if getattr(cfg, "SIDE_BUS_TRACKS", 0) <= 0:
        return set()
    try:
        pl = json.load(open(cfg.PLACEMENT_JSON))
    except Exception:
        return set()
    pref = tuple(os.environ.get("TD4_SIDE_BUS_PINS", "Q[").split(","))
    for row in pl["rows"]:
        for i in row:
            if i["type"] != cfg.MACRO_CELL:
                continue
            return {p["net"] for pn, p in i["pins"].items()
                    if p["net"] and pn.startswith(pref)}
    return set()


def per_row_local_nets():
    """`PER_ROW_LOCAL_NETS`。**stage6 の中で呼ぶこと。**

    モジュールの読み込み時に確定させてはいけない。`_prl_nets()` が読む
    `cfg.PLACEMENT_JSON` は **stage5 が作り直す**ので、import 時点では
    1 つ前の実行のものが残っている。実測: 縦置き（5 行）を試した直後に
    横倒しを流したら、同じ配置 (md5 e371a97d) なのに per-row-local が
    19 → 24 本になり、短絡 0 → 3 になった。
    """
    # 縦バスに乗せるネットは**必ず per-row-local**にする。行ごとのトランクと
    # spine の仕組みをそのまま使い、spine だけを帯へ逃がすため。
    #
    # `TD4_PRL_NETS`（','区切り）で**名指しの追加**ができる。しきい値を下げる
    # のとは別物: 実測で `PRL_MIN_PINS` を 5 → 4 にすると 24 → 37 本に増え、
    # チャネルのトラックを一気に食う。一方 `ld_addr[2]` は 4 ピン/3 行で
    # しきい値にわずかに届かず、兄弟の `ld_addr[0]`(6 ピン)/`ld_addr[1]`(5 ピン)
    # だけが専用ガード付きトランクを持っていて、そいつが短絡していた。
    # こういう「1 本だけ足したい」場合に使う。
    return ({"clk_buf", "rst_n_buf"} | _prl_nets() | side_bus_nets()
            | {n for n in os.environ.get("TD4_PRL_NETS", "").split(",") if n.strip()})
FORCE_HIGH_FO_NETS = set()
# --- TD4 移植 (19): フォールバックしたネットを pass 3 送りにする -----------
# `draw_jog` が「departure leg が clear なトラックが無い」と言って**無検査
# フォールバック**に落ちると、そのネットはほぼ確実に短絡する。`FORCE_JOG_NETS`
# に入れたネットは **pass 3**（全ネットを描き終えた後）で live チェック付きで
# 描き直されるので、この取りこぼしを拾える。
#
# 使い方: step6 を 1 回流して WARNING に出たネット名を `TD4_FORCE_JOG` に
# 渡して流し直す（`route.py --from 5 --to 6` を 2 回）。`sweep_height.py` は
# これを自動でやる。
FORCE_JOG_NETS = {n for n in os.environ.get("TD4_FORCE_JOG", "").split("\x1f") if n}

# Top-level port directions as seen from the GIO frame.  Derived from the
# netlist's own port declarations by the ported highlight_top_pins module,
# so it cannot drift out of step with the design (see scripts/PORTING.md).
def _port_dir():
    import highlight_top_pins_nrow_fm as h
    return dict(h.PORT_DIR_DERIVED)


def expected_ports():
    """every top-level pin the layout must expose: scalars + bus bits."""
    import highlight_top_pins_nrow_fm as h
    out = list(h.SCALAR_PORTS)
    for bus, w in h.BUS_PORTS.items():
        out += [f"{bus}[{i}]" for i in range(w)]
    return sorted(out)


def check_port_pins(gds, extra=("VDD", "GND")):
    """Fail loudly if a top-level port never made it to the core boundary.

    This is the check that would have caught the ported top-pin router
    still carrying the I2C design's hardcoded port names (design_notes
    14.5): only the buses were pulled out, and the nine scalar ports --
    including the BUFTH input nets sclk/cs_n/sdio_in -- were skipped in
    silence.
    """
    import klayout.db as db
    ly = db.Layout()
    ly.read(gds)
    top = ly.cell(cfg.TOP_CELL_NAME)
    labels = set()
    for lay, dt in ((49, 0), (48, 0)):
        for t in top.shapes(ly.layer(lay, dt)).each():
            if t.is_text():
                labels.add(t.dtext.string)
    want = expected_ports()
    missing = [p for p in want if p not in labels]
    print(f"\n=== top-level pin coverage ({os.path.relpath(gds, cfg.ROOT)}) ===")
    print(f"  ports expected : {len(want)}")
    print(f"  pin labels     : {len(labels)}  ({', '.join(sorted(labels - set(extra))[:6])}...)")
    if missing:
        print(f"  !! MISSING {len(missing)}: {', '.join(missing)}")
        return False
    print("  OK: every top-level port has a pin label")
    for e in extra:
        if e not in labels:
            print(f"  note: no '{e}' pin label (added by step9)")
    return True


def stage5(ch_heights):
    # Convert place.py's own step4 output into the schema the I2C router
    # reads, FIRST.  This used to be a separate command you had to remember
    # after re-running place.py; forgetting it routed the previous design's
    # placement against the current netlist, and the only symptom was a
    # top-level port quietly missing from the layout at step8.
    import gen_placement_json as gpj
    gpj.main(out_json=cfg.PLACEMENT_JSON)

    import gen_placement_gds_nrow_fm as g
    os.makedirs(os.path.dirname(cfg.PLACEMENT_GDS), exist_ok=True)
    g.CELL_GDS = cfg.CELL_GDS
    g.TOP_CELL_NAME = cfg.TOP_CELL_NAME
    g.main(placement_json=cfg.PLACEMENT_JSON, out_gds=cfg.PLACEMENT_GDS,
           ch_heights=ch_heights)


def stage6(ch_heights):
    import route_channels_nrow_fm as rc
    d = os.path.dirname(cfg.ROUTED_RAW_GDS)
    os.makedirs(d, exist_ok=True)
    rc.main(placement_json=cfg.PLACEMENT_JSON, in_gds=cfg.PLACEMENT_GDS,
            out_gds=cfg.ROUTED_RAW_GDS, ch_heights=ch_heights,
            force_jog_nets=FORCE_JOG_NETS,
            per_row_local_nets=per_row_local_nets(),
            side_bus_nets=side_bus_nets(),
            force_high_fo_nets=FORCE_HIGH_FO_NETS,
            pin_map_path=cfg.PIN_MAP_JSON,
            net_shapes_path=cfg.NET_SHAPES_JSON,
            channel_usage_path=cfg.CHANNEL_USAGE_JSON,
            force_jog_events_path=cfg.FORCE_JOG_EVENTS_JSON,
            compaction_info_path=cfg.COMPACTION_INFO_JSON,
            checkpoint_dir=d, checkpoint_prefix="route_step_2")


def stage7(ch_heights):
    import ripup_reroute_shorts as rr
    os.makedirs(os.path.dirname(cfg.RIPUP_GDS), exist_ok=True)
    sys.argv = ["ripup_reroute_shorts.py", cfg.ROUTED_RAW_GDS, cfg.PIN_MAP_JSON,
                cfg.NET_SHAPES_JSON, cfg.PLACEMENT_JSON,
                ",".join(str(h) for h in ch_heights), cfg.RIPUP_GDS,
                cfg.PIN_MAP_RR_JSON, cfg.NET_SHAPES_RR_JSON, "60"]
    rr.main()


def stage8(ch_heights):
    import route_top_pins_nrow_fm as rt
    os.makedirs(os.path.dirname(cfg.TOPPINS_GDS), exist_ok=True)
    rt.PORT_DIR = _port_dir()
    rt.main(placement_json=cfg.PLACEMENT_JSON, in_gds=cfg.RIPUP_GDS,
            out_gds=cfg.TOPPINS_GDS, ch_heights=ch_heights,
            net_shapes_json=cfg.NET_SHAPES_RR_JSON, net_file=cfg.NET_PATH,
            out_net_shapes_json=cfg.NET_SHAPES_TP_JSON)
    # --- TD4: step8 の後にもう一度 rip-up ------------------------------------
    # トップピンのルータは「どのトラックも衝突するので一番マシなものを選んだ」
    # という無検査フォールバックを持っていて（ログの `[CHECK]`）、そこで引いた
    # riser が他ネットの列を貫通することがある。実測: step7 で短絡 0 だったのに
    # step8 で 1 件（`out_port[0]` の riser x=170.1 が `_050_` を貫通）。
    # step8 が描いた形状を net_shapes に足したので、同じ rip-up / ドッグレッグを
    # そのまま掛けられる。
    if os.environ.get("TD4_RIPUP_AFTER_TOPPINS", "1") != "0":
        import ripup_reroute_shorts as rr2
        print("=== step8b: rip-up after top pins ===")
        sys.argv = ["ripup_reroute_shorts.py", cfg.TOPPINS_GDS, cfg.PIN_MAP_RR_JSON,
                    cfg.NET_SHAPES_TP_JSON, cfg.PLACEMENT_JSON,
                    ",".join(str(h) for h in ch_heights), cfg.TOPPINS_GDS,
                    cfg.PIN_MAP_TP_JSON, cfg.NET_SHAPES_TP2_JSON, "30"]
        rr2.main()


    if not check_port_pins(cfg.TOPPINS_GDS):
        raise SystemExit("!! top-level ports missing from the layout")


def stage9(ch_heights):
    import add_power_pins_nrow_fm as ap
    os.makedirs(os.path.dirname(cfg.POWERPINS_GDS), exist_ok=True)
    ap.main(placement_json=cfg.PLACEMENT_JSON, in_gds=cfg.TOPPINS_GDS,
            out_gds=cfg.POWERPINS_GDS, core_h=routed_core_h(ch_heights))


def stage10(ch_heights):
    """channel compaction: drop the Y slices no wire actually uses, without
    re-routing (the I2C flow's STEP7)."""
    import squeeze_channels_nrow_fm as sq
    os.makedirs(os.path.dirname(cfg.SQUEEZED_GDS), exist_ok=True)
    # ハードマクロの y 範囲は identity 写像で残す（マクロは参照なので中身が
    # 縮まらない。中で潰すとマクロだけ下がって配線がピンから外れる）。
    _mx0, _my0, _mx1, _my1 = cfg.macro_box()
    sq.main(in_gds=cfg.POWERPINS_GDS,
            compaction_info_path=cfg.COMPACTION_INFO_JSON,
            out_gds=cfg.SQUEEZED_GDS,
            pin_map_in=cfg.PIN_MAP_RR_JSON, pin_map_out=cfg.PIN_MAP_SQ_JSON,
            net_shapes_in=cfg.NET_SHAPES_RR_JSON,
            net_shapes_out=cfg.NET_SHAPES_SQ_JSON,
            extra_protect=[(_my0, _my1)])


def routed_core_h(ch):
    p = json.load(open(cfg.PLACEMENT_JSON))
    h = sum(ch) + len(p["rows"]) * p["row_height"]
    # 縦置きではマクロが行スタックより高くなりうる
    return max(h, p["macro"]["box"][3])


def checks(gds, pin_map, ch, squeezed=False):
    print("\n=== DRC ===")
    subprocess.run([sys.executable, os.path.join(HERE, "drc_check_nrow_fm.py"),
                    gds, cfg.TOP_CELL_NAME])
    print("\n=== connectivity (M1-then-M2 pin search) ===")
    p = json.load(open(cfg.PLACEMENT_JSON))
    # the scan window must cover the ROUTED core, not the placement estimate
    if squeezed:
        import gdstk
        top = [c for c in gdstk.read_gds(gds).cells
               if c.name == cfg.TOP_CELL_NAME][0]
        hi = top.bounding_box()[1][1] + 10
    else:
        hi = routed_core_h(ch) + 10
    subprocess.run([sys.executable,
                    os.path.join(HERE, "verify_connectivity_nrow_fm_m1m2.py"),
                    gds, pin_map, "0", str(hi),
                    # 縦置きではマクロが行スタックの**右**にあるので、
                    # 行幅だけではスキャン窓に入らない（コア幅で取る）。
                    str(max(p["row_width"], p.get("core_w", 0)) + 30)])


def stage11(ch_heights):
    """マクロの電源をコアの電源レールに繋ぐ。

    **圧縮（step10）の後**であること。前に入れると y が動く/削られる。
    縦置きではマクロが行スタックの横に居るので、マクロの vdd / vss は
    金属では何にも繋がっていない（`lvs_pnr.py` が「電源の島」として検出する）。
    """
    if not getattr(cfg, "MACRO_POWER", False):
        print("  TD4_MACRO_POWER=0 -- マクロ電源の接続はしない")
        return
    import connect_macro_power as cmp_mod
    os.makedirs(os.path.dirname(cfg.MACROPWR_GDS), exist_ok=True)
    sys.argv = ["connect_macro_power.py", cfg.SQUEEZED_GDS, "-o", cfg.MACROPWR_GDS]
    cmp_mod.main()


STAGES = {5: stage5, 6: stage6, 7: stage7, 8: stage8, 9: stage9,
          10: stage10, 11: stage11}


def main(first=5, last=10, ch=None):
    ch = ch or cfg.ROUTE_CH_HEIGHTS
    # `cfg.PLACEMENT_JSON` は **stage5 が作り直す**ので、ここで見ると
    # 1 つ前の実行のものが残っている。行数を変えて回すと「need 5 channel
    # heights, got 6」と嘘のアサートで落ちた。行数は place.py の生出力
    # （step4）から取る。
    src = (os.path.join(cfg.LAYOUT, "step4", "place_step4_fill.json")
           if first <= 5 else cfg.PLACEMENT_JSON)
    n_rows = len(json.load(open(src))["rows"])
    assert len(ch) == n_rows + 1, f"need {n_rows + 1} channel heights, got {len(ch)}"
    print(f"routing channel budget: {ch}  (placement estimate was "
          f"{json.load(open(src)).get('ch_heights')})")
    for n in range(first, last + 1):
        print(f"\n{'=' * 60}\n=== step{n} ===\n{'=' * 60}")
        STAGES[n](ch)
    if last >= 10:
        # step11 は電源の図形を足すだけで信号は触らないので、圧縮後のピンマップが
        # そのまま使える。検査は**最終 GDS**に対して掛ける。
        final = cfg.FINAL_GDS if last >= 11 else cfg.SQUEEZED_GDS
        checks(final, cfg.PIN_MAP_SQ_JSON, ch, squeezed=True)
        if not check_port_pins(final):
            raise SystemExit("!! top-level ports missing from the final layout")
        print()
        import verify_port_connectivity as vpc
        if vpc.main(final) != 0:
            raise SystemExit("!! a top-level port does not reach its cell pin")
    elif last >= 9:
        checks(cfg.POWERPINS_GDS, cfg.PIN_MAP_RR_JSON, ch)
    elif last >= 8:
        checks(cfg.TOPPINS_GDS, cfg.PIN_MAP_RR_JSON, ch)
    elif last >= 7:
        checks(cfg.RIPUP_GDS, cfg.PIN_MAP_RR_JSON, ch)
    elif last >= 6:
        checks(cfg.ROUTED_RAW_GDS, cfg.PIN_MAP_JSON, ch)


if __name__ == "__main__":
    # --- 決定性: PYTHONHASHSEED を固定して自分を起動し直す ----------------
    # ルータのどこかで**集合を反復している**（未特定）。集合の反復順は
    # PYTHONHASHSEED で毎回変わるので、**同じ配置 JSON から走らせても結果が
    # 変わる**。実測: seed=1 の同一配置 (md5 31d6cb77…) で step6 が
    # 3 短絡 → 0 短絡と揺れた。ここで固定して、再現しない結果を掴まされない
    # ようにする。
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable] + sys.argv)
    ap_ = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap_.add_argument("--from", dest="first", type=int, default=5)
    ap_.add_argument("--to", dest="last", type=int, default=11)
    ap_.add_argument("--ch-heights", default=None,
                     help="comma-separated channel budget, bottom margin first")
    a = ap_.parse_args()
    main(a.first, a.last,
         [float(x) for x in a.ch_heights.split(",")] if a.ch_heights else None)

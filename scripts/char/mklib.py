#!/usr/bin/env python3
"""char/*.json から Liberty (.lib) を書き出す。

  usage: python3 mklib.py [-o out.lib]

単位: 時間 ns / 容量 fF / 電圧 V / 面積 µm²。
コーナーは typ 1 本（TR-1um の PDK に ss/ff のモデルが無いため）。

しきい値は特性化時と揃える必要がある（char_comb.py / charlib.py と同じ値を書く）:
  遅延 50%、遷移 20%-80%
"""
from __future__ import annotations
import argparse, json, os, sys
import cellspec
from charlib import HERE, VDD, TEMP, SLEWS, LOADS, SLEWS_C, TH_DELAY, TH_SLEW_LO, TH_SLEW_HI

def _areas():
    """セル面積表。実体は scripts/cell_area.json（cellinfo.py が GDS から生成）。
    `{HERE}/cell_area.json` を直に開いていたため Mac では
    FileNotFoundError で起動すらできなかった。"""
    for p in (f"{HERE}/cell_area.json", f"{HERE}/../cell_area.json"):
        if os.path.exists(p):
            return json.load(open(p))["cells"]
    raise SystemExit("cell_area.json が見つからない。"
                     "scripts/cellinfo.py で生成してください")


AREAS = _areas()
IND = "  "


def fmt_table(rows, scale=1e9, nan=None):
    """[[v,...],...] -> Liberty の values(...) 文字列。None は前後から埋める。"""
    out = []
    for r in rows:
        vals = []
        for v in r:
            vals.append(v * scale if v is not None else None)
        # 欠損は同じ行の直近の値で埋める（無ければ 0）
        last = None
        for i, v in enumerate(vals):
            if v is None:
                vals[i] = last if last is not None else 0.0
            else:
                last = vals[i]
        out.append(", ".join(f"{v:.5f}" for v in vals))
    return out


def values_block(rows, ind, scale=1e9):
    lines = fmt_table(rows, scale)
    body = ",\\\n".join(f'{ind}  "{l}"' for l in lines)
    return f"{ind}values(\\\n{body});"


def idx(vals):
    return ", ".join(f"{v:g}" for v in vals)


# 既定と違う入力遷移の格子を持つセル（charlib.CELL_SLEWS）。
# **BUFTH はシュミットトリガで外部入力を受けるので 1000ns まで測ってある。**
# 既定の 16ns までのテンプレートに押し込むと遅い縁の遅延が 45% 過大になる。
def tmpl_of(cell, data):
    return ("delay_template_7x7" if data.get("slews", SLEWS) == SLEWS
            else f"delay_template_{cell}")


# シュミットトリガの入出力レベル。DC で往復させて測った実測値。
SCHMITT = {"BUFTH": {"vt_rise": 3.709, "vt_fall": 1.201}}


def emit_comb(cell, data, o):
    fns = cellspec.LIBFUNC.get(cell, {})
    tmpl = tmpl_of(cell, data)
    # cap_cal（遅延が合うように較正した等価容量）があればそちらを使う。
    # 電荷から出した cap はミラー分を含むので遅延計算には過大。
    caps = data.get("cap_cal") or data.get("cap", {})
    area = AREAS[cell]["area"]
    o.append(f'{IND}cell ({cell}) {{')
    o.append(f'{IND*2}area : {area:.1f};')
    if cell in cellspec.BLOCK_ONLY:
        o.append(f'{IND*2}dont_use : true;   /* アレイ内部専用。LEF も CLASS BLOCK */')
        o.append(f'{IND*2}dont_touch : true;')
    ins = sorted({a["related_pin"] for a in data["arcs"]})
    outs = sorted({a["pin"] for a in data["arcs"]})
    for p in ins:
        c = caps.get(p)
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : input;')
        if c:
            o.append(f'{IND*3}capacitance : {c:.3f};')
        o.append(f'{IND*3}max_transition : {data.get("slews", SLEWS)[-1]:g};')
        if cell in SCHMITT:
            v = SCHMITT[cell]
            o.append(f'{IND*3}/* シュミットトリガ。立上りは {v["vt_rise"]:.2f}V で、')
            o.append(f'{IND*3}   立下りは {v["vt_fall"]:.2f}V で切り替わる（ヒステリシス '
                     f'{v["vt_rise"]-v["vt_fall"]:.2f}V）。')
            o.append(f'{IND*3}   ライブラリ共通の input_threshold_pct 50 とは一致しないので、')
            o.append(f'{IND*3}   遅延はその分を含めて入力遷移の軸で吸収させている。 */')
            o.append(f'{IND*3}input_signal_level : "{cell}_in";')
        o.append(f'{IND*2}}}')
    for p in outs:
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : output;')
        if p in fns:
            o.append(f'{IND*3}function : "{fns[p]}";')
        o.append(f'{IND*3}max_capacitance : {LOADS[-1]:g};')
        for a in data["arcs"]:
            if a["pin"] != p:
                continue
            o.append(f'{IND*3}timing () {{')
            o.append(f'{IND*4}related_pin : "{a["related_pin"]}";')
            o.append(f'{IND*4}timing_sense : {a["sense"]};')
            for key, tbl in (("cell_rise", a["cell_rise"]), ("rise_transition", a["rise_transition"]),
                             ("cell_fall", a["cell_fall"]), ("fall_transition", a["fall_transition"])):
                o.append(f'{IND*4}{key} ({tmpl}) {{')
                o.append(values_block(tbl, IND * 5))
                o.append(f'{IND*4}}}')
            o.append(f'{IND*3}}}')
        o.append(f'{IND*2}}}')
    o.append(f'{IND}}}')


def seqcap(data, pin, default=80.0):
    c = (data.get("cap_cal") or data.get("cap") or {}).get(pin)
    return c if c else default


def emit_seq(cell, data, o):
    spec = cellspec.FF[cell]
    area = AREAS[cell]["area"]
    q = data["q"]
    o.append(f'{IND}cell ({cell}) {{')
    o.append(f'{IND*2}area : {area:.1f};')
    o.append(f'{IND*2}ff (IQ, IQN) {{')
    o.append(f'{IND*3}next_state : "{spec["next_state"]}";')
    o.append(f'{IND*3}clocked_on : "{spec["clocked_on"]}";')
    if "clear" in spec:
        o.append(f'{IND*3}clear : "{spec["clear"]}";')
    if "preset" in spec:
        o.append(f'{IND*3}preset : "{spec["preset"]}";')
    o.append(f'{IND*2}}}')

    dpin = data["d"]
    # 入力ピン
    o.append(f'{IND*2}pin (CK) {{')
    o.append(f'{IND*3}direction : input;')
    o.append(f'{IND*3}clock : true;')
    o.append(f'{IND*3}capacitance : {seqcap(data, "CK"):.3f};')
    o.append(f'{IND*3}max_transition : {SLEWS[-1]:g};')
    o.append(f'{IND*2}}}')

    data_pins = [p for p in cellspec.SEQ_PINS[cell]["data"]]
    for p in data_pins:
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : input;')
        o.append(f'{IND*3}capacitance : {seqcap(data, p):.3f};')
        o.append(f'{IND*3}max_transition : {SLEWS[-1]:g};')
        if p == dpin:
            for tt, tbl in (("setup_rising", data["setup"]), ("hold_rising", data["hold"])):
                o.append(f'{IND*3}timing () {{')
                o.append(f'{IND*4}related_pin : "CK";')
                o.append(f'{IND*4}timing_type : {tt};')
                for k, key in (("rise", "rise_constraint"), ("fall", "fall_constraint")):
                    o.append(f'{IND*4}{key} (constraint_template_3x3) {{')
                    o.append(values_block(tbl[k], IND * 5, scale=1.0))
                    o.append(f'{IND*4}}}')
                o.append(f'{IND*3}}}')
        o.append(f'{IND*2}}}')
    for p in cellspec.SEQ_PINS[cell]["async"]:
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : input;')
        o.append(f'{IND*3}capacitance : {seqcap(data, p):.3f};')
        o.append(f'{IND*3}max_transition : {SLEWS[-1]:g};')
        o.append(f'{IND*2}}}')

    for p, fn in (("Q", "IQ"), ("QB", "IQN")):
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : output;')
        o.append(f'{IND*3}function : "{fn}";')
        o.append(f'{IND*3}max_capacitance : {LOADS[-1]:g};')
        o.append(f'{IND*3}timing () {{')
        o.append(f'{IND*4}related_pin : "CK";')
        o.append(f'{IND*4}timing_type : rising_edge;')
        ck = data["ckq"]
        # QB は Q の反転なので rise/fall を入れ替える
        swap = (p == "QB")
        pairs = (("cell_rise", "cell_fall" if swap else "cell_rise"),
                 ("rise_transition", "fall_transition" if swap else "rise_transition"),
                 ("cell_fall", "cell_rise" if swap else "cell_fall"),
                 ("fall_transition", "rise_transition" if swap else "fall_transition"))
        for key, src in pairs:
            o.append(f'{IND*4}{key} (delay_template_7x7) {{')
            o.append(values_block(ck[src], IND * 5))
            o.append(f'{IND*4}}}')
        o.append(f'{IND*3}}}')
        o.append(f'{IND*2}}}')
    o.append(f'{IND}}}')


def emit_pad(cell, d, o):
    """パッドセル（3 ステートの双方向 IO）。

    標準セルと**格子が違う**ので専用のテンプレートを使う（負荷が pF 台）。
    `function` + `three_state` で 3 ステート出力を表し、HIZ->PAD に
    `three_state_enable` / `three_state_disable` のアークを持たせる。
    """
    caps = d.get("cap_cal") or d.get("cap", {})
    o.append(f'{IND}cell ({cell}) {{')
    # 面積は lef/TR-1um_frame.lef の MACRO ... SIZE が正（標準セルの
    # cell_area.json は STDCELL の GDS から作るのでパッドセルが入っていない）。
    # char_pad.py が JSON に書くが、古い JSON でも落ちないよう LEF を見に行く。
    area = d.get("area")
    if area is None:
        from char_pad import pad_area
        area = pad_area(cell)
    o.append(f'{IND*2}area : {area:.1f};')
    o.append(f'{IND*2}pad_cell : true;')
    o.append(f'{IND*2}dont_use : true;    /* フレームに固定配置。合成が勝手に挿さないように */')
    o.append(f'{IND*2}dont_touch : true;')
    for p in ("OUT", "HIZ"):
        o.append(f'{IND*2}pin ({p}) {{')
        o.append(f'{IND*3}direction : input;')
        o.append(f'{IND*3}capacitance : {caps[p]:.3f};')
        o.append(f'{IND*3}max_transition : {d["slews"][-1]:g};')
        o.append(f'{IND*2}}}')
    o.append(f'{IND*2}pin (PAD) {{')
    o.append(f'{IND*3}direction : inout;')
    o.append(f'{IND*3}is_pad : true;')
    o.append(f'{IND*3}/* 高Z のとき PAD が外に見せる容量（パッド + ESD 素子） */')
    o.append(f'{IND*3}capacitance : {d["cap"]["PAD"]:.1f};')
    o.append(f'{IND*3}function : "OUT";')
    o.append(f'{IND*3}three_state : "HIZ";')
    o.append(f'{IND*3}max_capacitance : {d["loads"][-1]:g};')
    o.append(f'{IND*3}timing () {{')
    o.append(f'{IND*4}related_pin : "OUT";')
    o.append(f'{IND*4}timing_sense : positive_unate;')
    for key in ("cell_rise", "rise_transition", "cell_fall", "fall_transition"):
        o.append(f'{IND*4}{key} (pad_template_7x7) {{')
        o.append(values_block(d["arc"][key], IND * 5))
        o.append(f'{IND*4}}}')
    o.append(f'{IND*3}}}')
    for mode, tt in (("enable", "three_state_enable"), ("disable", "three_state_disable")):
        o.append(f'{IND*3}timing () {{')
        o.append(f'{IND*4}related_pin : "HIZ";')
        o.append(f'{IND*4}timing_type : {tt};')
        o.append(f'{IND*4}timing_sense : non_unate;')
        for k, key in (("rise", "cell_rise"), ("rise_transition", "rise_transition"),
                       ("fall", "cell_fall"), ("fall_transition", "fall_transition")):
            if d[mode].get(k) is None:
                continue
            o.append(f'{IND*4}{key} (pad_tri_template_3x7) {{')
            o.append(values_block(d[mode][k], IND * 5))
            o.append(f'{IND*4}}}')
        o.append(f'{IND*3}}}')
    o.append(f'{IND*2}}}')
    o.append(f'{IND}}}')


def emit_macro(cell, d, o):
    """メモリマクロ（`REG8x16`）。

    クロックを持たないラッチアレイなので、Liberty では
      ADD[j] -> Q  を **組合せアーク**（non_unate）として書く。
    これが P&R の本命 `td4_soc_arr_bb` のクリティカルパスの主成分になる。

    **ピンは `bus` グループで宣言する。** `pin (ADD[0])` を並べただけだと
    OpenSTA が Verilog 側の `.ADD({...})` をバスとして解決できず
    「instance u_mem port ADD not found」で接続が落ちる。

    `timing` は `bus (Q)` の中に置く（全ビットに効く）。ビット間の差は
    測定でも 0.0% だったので、4 本のアドレスビットぶんだけ書けば足りる。

    **まだ入っていないもの**（`char_mem.py` が測っていない）:
      * `D` / `ADD` の `WEB` 立上りに対する setup / hold
      * `WEB` -> `Q`（書込み中に Q が追従する経路）
      * `WEB` の最小ローパルス幅
    書込みタイミングを STA で見るにはこれらが要る。読出しパスだけなら足りる。
    """
    area = AREAS[cell]["area"]
    caps = d["cap"]
    adds = sorted(d["read"], key=lambda k: int(k.strip("ADD[]")))
    nadd, nd = len(adds), 8
    cap_add = max(caps[a] for a in adds)
    cap_d = max(v for k, v in caps.items() if k.startswith("D["))
    o.append(f'{IND}cell ({cell}) {{')
    o.append(f'{IND*2}area : {area:.1f};')
    o.append(f'{IND*2}dont_use : true;   /* 座標指定で置くマクロ。合成が挿してはいけない */')
    o.append(f'{IND*2}dont_touch : true;')
    o.append(f'{IND*2}is_macro_cell : true;')
    o.append(f'{IND*2}/* 測定: {d.get("netlist", "?")} / 書込み後に ADD を振って読出し */')
    o.append(f'{IND*2}/* ADD のビット間は {min(caps[a] for a in adds):.1f}-'
             f'{cap_add:.1f} fF。大きい方を採った */')
    o.append(f'{IND*2}bus (ADD) {{')
    o.append(f'{IND*3}bus_type : bus{nadd};')
    o.append(f'{IND*3}direction : input;')
    o.append(f'{IND*3}capacitance : {cap_add:.3f};')
    o.append(f'{IND*3}max_transition : {d["slews"][-1]:g};')
    o.append(f'{IND*2}}}')
    o.append(f'{IND*2}pin (WEB) {{')
    o.append(f'{IND*3}direction : input;')
    o.append(f'{IND*3}capacitance : {caps["WEB"]:.3f};')
    o.append(f'{IND*3}max_transition : {d["slews"][-1]:g};')
    o.append(f'{IND*2}}}')
    o.append(f'{IND*2}bus (D) {{')
    o.append(f'{IND*3}bus_type : bus{nd};')
    o.append(f'{IND*3}direction : input;')
    o.append(f'{IND*3}capacitance : {cap_d:.3f};')
    o.append(f'{IND*3}max_transition : {d["slews"][-1]:g};')
    o.append(f'{IND*2}}}')
    o.append(f'{IND*2}bus (Q) {{')
    o.append(f'{IND*3}bus_type : bus{nd};')
    o.append(f'{IND*3}direction : output;')
    o.append(f'{IND*3}max_capacitance : {d["loads"][-1]:g};')
    for ad in adds:
        arc = d["read"][ad]
        o.append(f'{IND*3}timing () {{')
        o.append(f'{IND*4}related_pin : "{ad}";')
        o.append(f'{IND*4}timing_sense : non_unate;')
        o.append(f'{IND*4}timing_type : combinational;')
        for key in ("cell_rise", "rise_transition", "cell_fall", "fall_transition"):
            o.append(f'{IND*4}{key} (mem_template_7x7) {{')
            o.append(values_block(arc[key], IND * 5))
            o.append(f'{IND*4}}}')
        o.append(f'{IND*3}}}')
    o.append(f'{IND*2}}}')
    o.append(f'{IND}}}')


def emit_plain(cell, o, kind):
    """論理も遅延も持たないセル（TAP / FILL）"""
    area = AREAS[cell]["area"]
    o.append(f'{IND}cell ({cell}) {{')
    o.append(f'{IND*2}area : {area:.1f};')
    o.append(f'{IND*2}dont_use : true;')
    o.append(f'{IND*2}dont_touch : true;')
    if kind == "fill":
        o.append(f'{IND*2}pad_cell : false;')
    o.append(f'{IND*2}pin (vdd) {{ direction : input; }}')
    o.append(f'{IND}}}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default=f"{HERE}/tr1um_typ_5v0_25c.lib")
    a = ap.parse_args()

    o = []
    o.append("/* TR-1um (IP62) 標準セルライブラリ — Liberty")
    o.append(" *")
    o.append(" * scripts/char/mklib.py が char/*.json から自動生成。手で編集しないこと。")
    o.append(" * 元データは KLayout が DRC/LVS クリーンなレイアウトから抽出した")
    o.append(" * ネットリスト (lef/extracted/*.extracted) を ngspice (BSIM3 level49) で")
    o.append(" * 特性化したもの。拡散の実面積・周長 (AS/AD/PS/PD) を含む。")
    o.append(" * 回路の正しさは真理値表 140 点 / 順序 79 点 / TAP・FILL 全数で確認済み。")
    o.append(" *")
    o.append(" * 遅延が負の升目が 2 つある (NAND3 C->Y / NAND4 D->Y の 16ns 入力・10fF)。")
    o.append(" * 鈍い入力を軽い負荷で受けると、入力が 50% を通る前に出力が 50% を通る。")
    o.append(" * 測定どおりの物理的な値なので、丸めていない。")
    o.append(" *")
    o.append(f" * コーナー: typical / {VDD}V / {TEMP}degC （PDK に ss/ff のモデルが無いので 1 本のみ）")
    o.append(f" * 遅延の測定点: 入力 {TH_DELAY}% -> 出力 {TH_DELAY}%")
    o.append(f" * 遷移の測定点: {TH_SLEW_LO}% -> {TH_SLEW_HI}%")
    o.append(" * 単位: 時間 ns / 容量 fF / 面積 um^2")
    o.append(" *")
    o.append(" * OSS_ESD_5V_DIO の 3 ステートアークの測定条件:")
    o.append(" *   enable  遅延 HIZ 50% -> PAD 50%。PAD は 1Mohm で逆レールに置いてから。")
    o.append(" *           遷移は PAD の 20-80%（逆レールから駆動レールへのフルスイング）。")
    o.append(" *   disable 遅延 HIZ 50% -> 駆動電流が 100uA を切るまで。PAD を VDD/2 の")
    o.append(" *           電圧源で押さえて電流で判定するので負荷に依らない。")
    o.append(" *           **遷移は電圧では定義できない**（放しても波形が動かない）ので、")
    o.append(" *           駆動電流が初期値の 80% -> 20% に落ちる時間を入れてある。")
    o.append(" *")
    o.append(" * 入っていないセル: ADDBUF / REGBUF / TLAT / DEC0 / DEC2 / DEC16 など")
    o.append(" *   アレイ内部で abut して使う CLASS BLOCK のセル。P&R の行に流さないので")
    o.append(" *   タイミングを持たせる意味がない（機能は ngspice で確認済み）。")
    o.append(" */")
    o.append("")
    o.append("library (tr1um_typ_5v0_25c) {")
    o.append(f"{IND}technology (cmos);")
    o.append(f"{IND}delay_model : table_lookup;")
    o.append(f'{IND}bus_naming_style : "%s[%d]";')
    o.append(f'{IND}time_unit : "1ns";')
    o.append(f'{IND}voltage_unit : "1V";')
    o.append(f'{IND}current_unit : "1mA";')
    o.append(f'{IND}pulling_resistance_unit : "1kohm";')
    o.append(f'{IND}leakage_power_unit : "1nW";')
    o.append(f"{IND}capacitive_load_unit (1, ff);")
    o.append("")
    o.append(f"{IND}nom_process : 1.0;")
    o.append(f"{IND}nom_temperature : {TEMP};")
    o.append(f"{IND}nom_voltage : {VDD};")
    o.append(f"{IND}default_max_transition : {SLEWS[-1]:g};")
    o.append(f"{IND}default_max_fanout : 16;")
    o.append("")
    for e in ("rise", "fall"):
        o.append(f"{IND}slew_lower_threshold_pct_{e} : {TH_SLEW_LO};")
        o.append(f"{IND}slew_upper_threshold_pct_{e} : {TH_SLEW_HI};")
        o.append(f"{IND}input_threshold_pct_{e} : {TH_DELAY};")
        o.append(f"{IND}output_threshold_pct_{e} : {TH_DELAY};")
    o.append(f"{IND}slew_derate_from_library : 1.0;")
    o.append("")
    o.append(f"{IND}operating_conditions (typ) {{")
    o.append(f"{IND*2}process : 1.0;")
    o.append(f"{IND*2}temperature : {TEMP};")
    o.append(f"{IND*2}voltage : {VDD};")
    o.append(f"{IND*2}tree_type : balanced_tree;")
    o.append(f"{IND}}}")
    o.append(f"{IND}default_operating_conditions : typ;")
    o.append("")
    o.append(f"{IND}lu_table_template (delay_template_7x7) {{")
    o.append(f"{IND*2}variable_1 : input_net_transition;")
    o.append(f"{IND*2}variable_2 : total_output_net_capacitance;")
    o.append(f'{IND*2}index_1 ("{idx(SLEWS)}");')
    o.append(f'{IND*2}index_2 ("{idx(LOADS)}");')
    o.append(f"{IND}}}")
    # 既定と違う格子を持つセルのテンプレートと、シュミットの入出力レベル
    for f in sorted(os.listdir(f"{HERE}/char")):
        if not f.endswith(".json") or f.startswith("_"):
            continue
        dd = json.load(open(f"{HERE}/char/{f}"))
        sl = dd.get("slews", SLEWS)
        if sl == SLEWS or dd.get("pad"):
            continue
        nm = f[:-5]
        o.append(f"{IND}/* {nm} は入力遷移の格子が違う（外部入力を受けるので遅い縁まで） */")
        o.append(f"{IND}lu_table_template (delay_template_{nm}) {{")
        o.append(f"{IND*2}variable_1 : input_net_transition;")
        o.append(f"{IND*2}variable_2 : total_output_net_capacitance;")
        o.append(f'{IND*2}index_1 ("{idx(sl)}");')
        o.append(f'{IND*2}index_2 ("{idx(LOADS)}");')
        o.append(f"{IND}}}")
    for nm, v in sorted(SCHMITT.items()):
        o.append(f"{IND}input_voltage ({nm}_in) {{")
        o.append(f"{IND*2}vil : {v['vt_fall']:.3f};   /* 立下りのしきい値 VT- */")
        o.append(f"{IND*2}vih : {v['vt_rise']:.3f};   /* 立上りのしきい値 VT+ */")
        o.append(f"{IND*2}vimin : -0.3;")
        o.append(f"{IND*2}vimax : {VDD + 0.3:g};")
        o.append(f"{IND}}}")
    o.append("")

    pad = None
    pp = f"{HERE}/char/OSS_ESD_5V_DIO.json"
    if os.path.exists(pp):
        pad = json.load(open(pp))
        o.append(f"{IND}/* パッドセル用。負荷が pF 台なので標準セルとは別の格子 */")
        o.append(f"{IND}lu_table_template (pad_template_7x7) {{")
        o.append(f"{IND*2}variable_1 : input_net_transition;")
        o.append(f"{IND*2}variable_2 : total_output_net_capacitance;")
        o.append(f'{IND*2}index_1 ("{idx(pad["slews"])}");')
        o.append(f'{IND*2}index_2 ("{idx(pad["loads"])}");')
        o.append(f"{IND}}}")
        o.append(f"{IND}lu_table_template (pad_tri_template_3x7) {{")
        o.append(f"{IND*2}variable_1 : input_net_transition;")
        o.append(f"{IND*2}variable_2 : total_output_net_capacitance;")
        o.append(f'{IND*2}index_1 ("{idx(pad["slews_t"])}");')
        o.append(f'{IND*2}index_2 ("{idx(pad["loads"])}");')
        o.append(f"{IND}}}")
    mem = None
    mp = f"{HERE}/char/REG8x16.json"
    if os.path.exists(mp):
        m = json.load(open(mp))
        if any(v is not None for a in m.get("read", {}).values()
               for t in a.values() for r in t for v in r):
            mem = m
            o.append(f"{IND}/* マクロ用。負荷の格子が標準セルと 1 点だけ違う（25 -> 20 fF） */")
            o.append(f"{IND}lu_table_template (mem_template_7x7) {{")
            o.append(f"{IND*2}variable_1 : input_net_transition;")
            o.append(f"{IND*2}variable_2 : total_output_net_capacitance;")
            o.append(f'{IND*2}index_1 ("{idx(mem["slews"])}");')
            o.append(f'{IND*2}index_2 ("{idx(mem["loads"])}");')
            o.append(f"{IND}}}")
            for n in (4, 8):
                o.append(f"{IND}type (bus{n}) {{")
                o.append(f"{IND*2}base_type : array;")
                o.append(f"{IND*2}data_type : bit;")
                o.append(f"{IND*2}bit_width : {n};")
                o.append(f"{IND*2}bit_from : {n-1};")
                o.append(f"{IND*2}bit_to : 0;")
                o.append(f"{IND*2}downto : true;")
                o.append(f"{IND}}}")
    o.append(f"{IND}lu_table_template (constraint_template_3x3) {{")
    o.append(f"{IND*2}variable_1 : constrained_pin_transition;")
    o.append(f"{IND*2}variable_2 : related_pin_transition;")
    o.append(f'{IND*2}index_1 ("{idx(SLEWS_C)}");')
    o.append(f'{IND*2}index_2 ("{idx(SLEWS_C)}");')
    o.append(f"{IND}}}")
    o.append("")

    ncell = 0
    skipped = []
    for cell in sorted(os.listdir(f"{HERE}/char")):
        if not cell.endswith(".json") or cell.startswith("_"):
            continue
        name = cell[:-5]
        d = json.load(open(f"{HERE}/char/{cell}"))
        if d.get("macro"):
            if not any(v is not None for a in d.get("read", {}).values()
                       for t in a.values() for r in t for v in r):
                # 測定が空のまま（失敗した実行の書き残しなど）。
                # 黙って emit_comb に流すと "arcs" が無くて落ちる。
                skipped.append(name)
                continue
            emit_macro(name, d, o)
            ncell += 1
            continue
        if d.get("pad"):
            emit_pad(name, d, o)
        elif d.get("seq"):
            emit_seq(name, d, o)
        else:
            emit_comb(name, d, o)
        ncell += 1
    for name in sorted(cellspec.PASS):
        emit_plain(name, o, "fill" if name.startswith("FILL") else "tap")
        ncell += 1
    o.append("}")
    open(a.out, "w").write("\n".join(o) + "\n")
    print(f"wrote {a.out}  ({ncell} cells, {len(o)} lines)")
    for n in skipped:
        print(f"  ! {n}: マクロなので飛ばした（Liberty への出力は未実装）")


if __name__ == "__main__":
    main()

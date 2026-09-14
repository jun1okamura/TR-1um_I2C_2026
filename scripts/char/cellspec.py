#!/usr/bin/env python3
"""TR-1um 標準セルの「期待される振る舞い」定義。

ngspice での機能チェック（check_cells.py）と Liberty 生成（mklib.py）が
両方ともこの 1 ファイルを見る。**論理式をここ以外に書かないこと。**

  COMB : 組合せセル  {cell: {出力ピン: (入力ピンの並び, 真理値関数)}}
  SEQ  : 順序セル（個別にシナリオを書く）
  PASS : 論理を持たないセル（TAP / FILL）

論理式は genlib（scripts/tr1um.genlib）と同じものを Python で書き直したもの。
食い違えば機能チェックが落ちるので、genlib 側の誤りもここで捕まる。
"""
from __future__ import annotations

def _and(*v):
    r = 1
    for x in v: r &= x
    return r

def _or(*v):
    r = 0
    for x in v: r |= x
    return r

# --- 組合せセル -----------------------------------------------------------
# cell -> { 出力ピン: (入力ピンのタプル, lambda) }
COMB = {
    "INV_X1":  {"Y": (("A",),           lambda a: 1 - a)},
    "INV_X2":  {"Y": (("A",),           lambda a: 1 - a)},
    "BUF_X1":  {"Y": (("A",),           lambda a: a)},
    "BUF_X2":  {"Y": (("A",),           lambda a: a)},
    "BUFTH":   {"Y": (("A",),           lambda a: a)},
    "DEL1":    {"Y": (("A",),           lambda a: a)},

    "NAND2":   {"Y": (("A", "B"),           lambda *v: 1 - _and(*v))},
    "NAND3":   {"Y": (("A", "B", "C"),      lambda *v: 1 - _and(*v))},
    "NAND4":   {"Y": (("A", "B", "C", "D"), lambda *v: 1 - _and(*v))},
    "NOR2":    {"Y": (("A", "B"),           lambda *v: 1 - _or(*v))},
    "NOR3":    {"Y": (("A", "B", "C"),      lambda *v: 1 - _or(*v))},
    "NOR4":    {"Y": (("A", "B", "C", "D"), lambda *v: 1 - _or(*v))},
    "AND2_X1": {"Y": (("A", "B"),           lambda *v: _and(*v))},
    "AND3_X1": {"Y": (("A", "B", "C"),      lambda *v: _and(*v))},
    "AND4_X1": {"Y": (("A", "B", "C", "D"), lambda *v: _and(*v))},
    "OR2":     {"Y": (("A", "B"),           lambda *v: _or(*v))},
    "OR3":     {"Y": (("A", "B", "C"),      lambda *v: _or(*v))},
    "OR4":     {"Y": (("A", "B", "C", "D"), lambda *v: _or(*v))},
    "XOR2":    {"Y": (("A", "B"),           lambda a, b: a ^ b)},
    "XNOR2":   {"Y": (("A", "B"),           lambda a, b: 1 - (a ^ b))},

    # **S=0 で A、S=1 で B**。ngspice で確認済み（回路も AOI で
    #   n2 = !((A & !S) | (B & S)) 、Y = !n2 = (A*!S)+(B*S)）。
    # genlib には長らく Y=(A*S)+(B*!S) と A/B 逆に書いてあった。
    # abc -g simple で合成していたので実害は出ていなかったが、
    # genlib マッピングに切り替えた瞬間に MUX の入力が入れ替わる。
    "MUX2":    {"Y": (("A", "B", "S"),  lambda a, b, s: b if s else a)},

    # 2 段インバータ = 非反転バッファ 2 本。入力 D/Q、出力 DD/QQ。
    # （配列では D=外部データ入力 -> DD=ビット線 dl、Q=ビット線 ql -> QQ=外部出力）
    "REGBUF":  {"DD": (("D",), lambda d: d),
                "QQ": (("Q",), lambda q: q)},

    # アドレスバッファ: 各ビットで真値と補値を作る。5 チャネル x 4T = 20T。
    "ADDBUF":  {**{f"A{k}":  ((f"A{k}_PIN",), lambda a: a)     for k in range(4)},
                **{f"AB{k}": ((f"A{k}_PIN",), lambda a: 1 - a) for k in range(4)},
                "WEB": (("WEB_PIN",), lambda w: w)},
}

# --- 論理を持たないセル ---------------------------------------------------
PASS = {
    "TAP2":  "基板/ウェルタップのみ（Tr なし）",
    "TAP2S": "基板/ウェルタップのみ（Tr なし、アレイ用）",
    "TAP3":  "基板/ウェルタップのみ（Tr なし）",
    "FILL1": "純フィラー（Tr なし）",
    "FILL2": "デキャップ 164 fF",
    "FILL3": "デキャップ 440 fF",
}

# --- 抽出できない / 単体で成立しないセル ----------------------------------
SKIP = {
    "DEC0": "隣とミラーで拡散を共有する半セル。単体では成立しないので DEC2 が最小単位",
}

# --- 順序セル -------------------------------------------------------------
# check_cells_seq.py が個別にシナリオを持つ
SEQ = {
    "DFF":      "立上りエッジ D->Q、QB=!Q",
    "DFFRB":    "同上 + RSTB=0 で非同期リセット（Q=0）",
    "DFFS":     "同上 + SET=1 で非同期セット（Q=1）",
    "MUXDFFRB": "入力が MUX2（S で A/B 選択）+ DFFRB",
    "RSLATCH":  "S/R ラッチ。Q/QB",
    "TLAT":     "レベルセンシティブ。WR/WRB で D を取込、RD/RDB で Q に出す",
}

ALL_ROW_CELLS = sorted(set(COMB) | set(PASS) | set(SEQ) | set(SKIP))


# --- Liberty 用の論理式 ---------------------------------------------------
# Liberty の演算子: ! = NOT, * = AND, + = OR, ^ = XOR
LIBFUNC = {
    "INV_X1": {"Y": "!A"},      "INV_X2": {"Y": "!A"},
    "BUF_X1": {"Y": "A"},       "BUF_X2": {"Y": "A"},
    "BUFTH":  {"Y": "A"},       "DEL1":   {"Y": "A"},
    "NAND2":  {"Y": "!(A*B)"},        "NAND3": {"Y": "!(A*B*C)"},
    "NAND4":  {"Y": "!(A*B*C*D)"},
    "NOR2":   {"Y": "!(A+B)"},        "NOR3":  {"Y": "!(A+B+C)"},
    "NOR4":   {"Y": "!(A+B+C+D)"},
    "AND2_X1": {"Y": "A*B"},          "AND3_X1": {"Y": "A*B*C"},
    "AND4_X1": {"Y": "A*B*C*D"},
    "OR2":    {"Y": "A+B"},           "OR3":   {"Y": "A+B+C"},
    "OR4":    {"Y": "A+B+C+D"},
    "XOR2":   {"Y": "A^B"},           "XNOR2": {"Y": "!(A^B)"},
    "MUX2":   {"Y": "(A*!S)+(B*S)"},          # S=0 -> A / S=1 -> B（ngspice で確認）
    "REGBUF": {"DD": "D", "QQ": "Q"},
    "ADDBUF": {**{f"A{k}": f"A{k}_PIN" for k in range(4)},
               **{f"AB{k}": f"!A{k}_PIN" for k in range(4)},
               "WEB": "WEB_PIN"},
}

# 順序セルの Liberty モデル
FF = {
    "DFF":      dict(next_state="D", clocked_on="CK"),
    "DFFRB":    dict(next_state="D", clocked_on="CK", clear="!RSTB"),
    "DFFS":     dict(next_state="D", clocked_on="CK", preset="SET"),
    # MUX 入りの FF。S=0 で A、S=1 で B（MUX2 と同じ極性）
    "MUXDFFRB": dict(next_state="(A*!S)+(B*S)", clocked_on="CK", clear="!RSTB"),
}
# NOR 型 SR ラッチ。S/R ともアクティブ High（ngspice で確認）
LATCH = {"RSLATCH": dict(preset="S", clear="R")}

# LEF で CLASS BLOCK にしてあるセル = P&R の行に流さない。
# .lib には出すが `dont_use` を付けて、合成が勝手に使わないようにする。
BLOCK_ONLY = {"ADDBUF", "REGBUF", "TAP2S", "TLAT", "DEC0"}

# 順序セルのピン分類（Liberty 出力用）
SEQ_PINS = {
    "DFF":      {"data": ["D"],          "async": []},
    "DFFRB":    {"data": ["D"],          "async": ["RSTB"]},
    "DFFS":     {"data": ["D"],          "async": ["SET"]},
    "MUXDFFRB": {"data": ["A", "B", "S"], "async": ["RSTB"]},
}

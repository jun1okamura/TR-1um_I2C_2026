# -*- coding: utf-8 -*-
"""ADDBUF のピンにラベルを付ける（LVS の曖昧性解消）— KLayout マクロ

KLayout の Macro Development ウィンドウ（Python）で、
lef/TR-1um_STDCELL.gds を開いた状態で実行する。実行後に保存すること。

なぜ必要か:
  ADDBUF は 4 本のアドレス channel（INV 2段）が構造的に完全に同一で、
  レイアウト側のピンに名前が無い。KLayout の LVS は ADDBUF を単体で先に
  比較するので、4 channel の対応を名前無しで恣意的に決めてしまう。
  その決定がトップに持ち上がると ADD[0..3] のポートが入れ替わって見える。
  ピンに名前を付ければ、名前で対応が確定する。

  ※ レイアウトの結線自体は正しい（ADD[0] が LSB）。名前が無いだけ。
"""
CELL = "ADDBUF"
TEXT_LAYER = (49, 0)          # TLAT / REGBUF と同じテキストレイヤ

# (x, y, ラベル)   座標は ADDBUF セルローカル [um]
LABELS = [
    # 出力ピン（y = 28.0..31.4 のピン矩形の中心）
    (-18.9, 29.7, "A3"),
    (-13.5, 29.7, "AB3"),
    ( -8.1, 29.7, "A2"),
    ( -2.7, 29.7, "AB2"),
    (  2.7, 29.7, "AB1"),
    (  8.1, 29.7, "A1"),
    ( 13.5, 29.7, "AB0"),
    ( 18.9, 29.7, "A0"),
    ( 24.3, 29.7, "WEB"),
    # 入力ピン（y = 50.9..58.3 のピン矩形）
    (-13.5, 56.6, "A3_PIN"),
    ( -2.7, 56.6, "A2_PIN"),
    (  2.7, 56.6, "A1_PIN"),
    ( 13.5, 56.6, "A0_PIN"),
    ( 29.7, 56.6, "WEB_PIN"),
]

# vss レール上に載ってしまっている誤ラベル（layer 48/0 の "vdd"）
BOGUS = [(35.10, 2.50, "vdd", 48, 0), (-2.70, 2.50, "vdd", 48, 0)]

import pya

ly = pya.CellView.active().layout()
cell = ly.cell(CELL)
if cell is None:
    raise RuntimeError("cell %s が見つかりません" % CELL)

dbu = ly.dbu
li = ly.layer(*TEXT_LAYER)

# 1) 誤ラベルを削除
removed = 0
for x, y, txt, lyr, dt in BOGUS:
    idx = ly.find_layer(lyr, dt)
    if idx is None:
        continue
    sh = cell.shapes(idx)
    for s in list(sh.each()):
        if s.is_text() and s.text.string == txt:
            t = s.text
            if abs(t.x * dbu - x) < 0.2 and abs(t.y * dbu - y) < 0.2:
                sh.erase(s); removed += 1

# 2) ピンラベルを追加（既に同名があればスキップ）
existing = set()
for s in cell.shapes(li).each():
    if s.is_text():
        existing.add(s.text.string)

added = 0
for x, y, txt in LABELS:
    if txt in existing:
        print("  skip (already): %s" % txt); continue
    cell.shapes(li).insert(pya.Text(txt, pya.Trans(pya.Point(int(round(x / dbu)),
                                                             int(round(y / dbu))))))
    added += 1

print("ADDBUF: ラベル %d 個追加 / 誤ラベル %d 個削除" % (added, removed))
print("→ 保存してから LVS を再実行してください")

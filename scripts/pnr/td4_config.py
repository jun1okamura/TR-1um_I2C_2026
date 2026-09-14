"""td4_config.py -- P&R のパス・幾何定数の単一ソース。

`TR-1um_SCLK_SPI/scripts/spi_config.py` と同じ役割。配線スクリプトは
`TR-1um_Async_I2C/script/` → `TR-1um_SCLK_SPI/scripts/` と渡ってきた移植物で、
中で `import spi_config as _cfg` と書いてある。**原本を書き換えないため**、
同じディレクトリに `spi_config.py`（このモジュールを再輸出するだけの薄皮）を
置いてある。触るのはこのファイルだけ。

環境変数:
  TR1UM_PDK   PDK チェックアウト（via_1 PCell ライブラリ用）
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- 設計の同定 ----------------------------------------------------------
TOP_CELL_NAME = "td4_soc_arr_nrow_fm"        # 配置配線したコアセル
CHIP_TOP_CELL = "tr_1um_jun1okamura"         # info.yaml の gds.top_cell
#   MPW のテンプレートが「tr_1um_ で始まり GitHub ユーザ名を含むこと」と
#   決めている（シャトル上で名前がぶつからないように）。

# ---- 入力 ----------------------------------------------------------------
# ライブラリ本体（`scripts/mklef.py` が作る。P&R は直接読まない）
LIB_LEF = os.path.join(ROOT, "lef", "TR-1um_cells.lef")
LIB_GDS = os.path.join(ROOT, "lef", "TR-1um_STDCELL.gds")
# P&R が読むもの = ライブラリ + `MEMPORT`。`scripts/pnr/mkmemport.py` が作る。
LEF_PATH = os.path.join(ROOT, "lef", "TR-1um_PNR.lef")
CELL_GDS = os.path.join(ROOT, "lef", "TR-1um_PNR.gds")
NET_PATH = os.path.join(ROOT, "out", "td4_soc_arr_pnr.v")
FRAME_GDS = os.path.join(ROOT, "lef", "TR-1um_frame_25x25.gds")
FRAME_LEF = os.path.join(ROOT, "lef", "TR-1um_frame.lef")
FRAME_CELL = "OSS_FRAME_GIO"                 # 16 パッドの GIO リング

# ---- 成果物 --------------------------------------------------------------
LAYOUT = os.path.join(ROOT, "layout")
CELL_INFO = os.path.join(LAYOUT, "cell_info.json")      # mkcellinfo.py が生成

PLACEMENT_JSON = os.path.join(LAYOUT, "placement_nrow_fm.json")
PLACEMENT_GDS = os.path.join(LAYOUT, "step5", "route_step_1_placement.gds")
ROUTED_RAW_GDS = os.path.join(LAYOUT, "step6", "route_step_2_routed_raw.gds")
RIPUP_GDS = os.path.join(LAYOUT, "step7", "route_step_3_ripup_reroute.gds")
TOPPINS_GDS = os.path.join(LAYOUT, "step8", "route_step_4_top_pins.gds")
POWERPINS_GDS = os.path.join(LAYOUT, "step9", "route_step_5_power_pins.gds")
SQUEEZED_GDS = os.path.join(LAYOUT, "step10", "route_step_6_squeezed.gds")

PIN_MAP_JSON = os.path.join(LAYOUT, "pin_map_nrow_fm.json")
NET_SHAPES_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm.json")
CHANNEL_USAGE_JSON = os.path.join(LAYOUT, "channel_usage_nrow_fm.json")
FORCE_JOG_EVENTS_JSON = os.path.join(LAYOUT, "force_jog_events_nrow_fm.json")
PIN_MAP_RR_JSON = os.path.join(LAYOUT, "pin_map_nrow_fm_rr.json")
PIN_MAP_SQ_JSON = os.path.join(LAYOUT, "pin_map_nrow_fm_sq.json")
NET_SHAPES_SQ_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_sq.json")
NET_SHAPES_RR_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_rr.json")
# TD4: step8 (トップピン) が描いた分を足したもの。step8 の後にもう一度
# ripup を掛けるために要る。
NET_SHAPES_TP_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_tp.json")
PIN_MAP_TP_JSON = os.path.join(LAYOUT, "pin_map_nrow_fm_tp.json")
NET_SHAPES_TP2_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_tp2.json")
COMPACTION_INFO_JSON = os.path.join(LAYOUT, "compaction_info_nrow_fm.json")

# ---- セルライブラリの幾何 ------------------------------------------------
# **SCLK_SPI と行高が違う。** あちらは 64.8、TR-1um_TD4 の STDCELL は 59.4。
# prBoundary の実測値（lef/TR-1um_STDCELL.gds、35 セルすべて 59.4）。
ROW_HEIGHT_UM = 59.4
SITE_UM = 5.4
TRACK_PITCH = float(os.environ.get("TD4_TRACK_PITCH", "5.4"))   # チャネルの M1 トラック間隔（x のサイトとは別物）
TAP_CELL = "TAP2"
TAP_W = 10.8
TAP_PITCH = 534.6              # I2C 実チップ実測。SCLK_SPI から踏襲
# 隙間埋めに使う FILL（広い順）。**FILL1 (5.4) を入れておく。**
# FILL2/FILL3 だけだと隙間が 10.8 の倍数系に限られ、優先コリドーを増やして
# 区画が細かくなると詰め切れずに step3 が落ちる。FILL1 は容量ゼロの純フィラー
# なので、デキャップとしては FILL2/FILL3 が先に使われるこの順で問題ない。
# `TD4_USE_FILL1=1` で FILL1 (5.4) も使う。既定は入れない（入れると隙間の
# 刻みが変わって**配置が丸ごと変わる**ので、確定した横倒しの結果を壊さない）。
FILLS = [("FILL3", 16.2), ("FILL2", 10.8)]
if os.environ.get("TD4_USE_FILL1") == "1":
    FILLS = FILLS + [("FILL1", 5.4)]
# 優先 M2 コリドーに使うセル。`TD4_PRI_CELL` で振れる。
# FILL2 (10.8 = 2 トラック) だと上側トラックの via パッド（半幅 1.7 + 隙間 2.0）
# が隣のセルへ 1.0 µm はみ出すので、隣に M2 があると実質 1 本しか使えない。
# **FILL3 (16.2 = 3 トラック) なら真ん中の 1 本が必ず両側とも空く。**
_PRI_W = {"FILL1": 5.4, "FILL2": 10.8, "FILL3": 16.2}
# 実測（横倒し・seed 1、step10 の実 BBOX / 短絡 / DRC）:
#   FILL2  1655.8 / 0 / 0   行またぎジョグ 28、コリドー 12 track
#   FILL3  1645.0 / 0 / 0   行またぎジョグ 26、コリドー 18 track   <- 既定
PRI_CELL = os.environ.get("TD4_PRI_CELL", "FILL3")
if PRI_CELL not in _PRI_W:
    raise SystemExit(f"TD4_PRI_CELL は {sorted(_PRI_W)} のどれか（今 {PRI_CELL}）")
PRI_W = _PRI_W[PRI_CELL]
# 優先 M2 コリドーのピッチ。TAP 直後の 1 枠だけでは行またぎの空き列が足りない
# （実測: 155 回の行またぎのうち 63 回が clear な x を見つけられず遠くへ逃げ、
#  短絡の主因になっていた）。全行同じ x に 2 トラック分を等間隔で予約する。
# 実測（5 行・配置率 79%）:
#   ピッチ 108 (コリドー 11 本/行)  行またぎの clear x 失敗 63 -> 63、短絡 32 -> 40
#   TAP 直後のみ (3 本/行)          短絡 32   <- いまはこちら
# コリドーを増やしても**同じ x に集まりすぎて互いに衝突する**ので効かなかった。
# 効くのは配置率そのもの。1e9 にすると「TAP 直後の 1 枠だけ」= 移植元と同じ。
PRI_PITCH = float(os.environ.get("TD4_PRI_PITCH", "1e9"))
# コリドーの置き方。"after" = TAP 直後だけ（移植元と同じ）、
# "both" = **TAP の両側**。行末の TAP の手前にも 1 枠できるので、
# 行の右端にも縦に抜ける列ができる（ユーザ指摘）。
# `TD4_PRI_MODE`。"both" は 1 行あたり 6 本、"after" は 3 本。
# 縦バスを入れると行幅が減るので、コリドーを 3 本に戻して取り返せる
# （FILL3 なら 48.6 µm/行）。
PRI_MODE = os.environ.get("TD4_PRI_MODE", "both")
# **狙い撃ちの追加コリドー**（`TD4_PRI_X="135.0,..."`, µm, サイトグリッドに丸める）。
# ピッチを詰めると「同じ x に集まりすぎて互いに衝突」して逆効果（上のメモ）だが、
# 短絡が実際に出ている x（実測: ch2/ch3 の x≈137）にだけ 1 本足すのは話が別。
# 1 本 = 行あたり 16.2 µm しか食わず、パーティション上限 (= 全セル幅/行数 ×
# (1+tol) ≈ 878 µm) の方が実効行幅よりずっと小さいので**実質タダ**。
PRI_EXTRA_X = [round(round(float(v) / SITE_UM) * SITE_UM, 3)
               for v in os.environ.get("TD4_PRI_X", "").split(",") if v.strip()]

# ---- フロアプラン --------------------------------------------------------
# **メモリは横倒しにして行スタックの下に敷く。**
#
# `REG8x16` は 399.6 x 933.0 で信号ピン 21 本が下辺の水平 1 列。縦置きで行の
# 横に並べるとコア幅 1598.4 のうち 421.2 µm を食い、行幅が 1177.2 にしかならず
# **配置率が 79% まで上がって行またぎの空き x が枯れる**（M2 の無い x が
# 216 トラック中 48 本しかない）。これが短絡 31 件の直接の原因だった。
#
# R90 して 933.0 x 399.6 にすると行はコア幅いっぱい使える。回すとピン列は
# 垂直になってチャネルルータが扱えないので、`scripts/pnr/mkmemport.py` が
# マクロ右の空き地で M1/M2 に振り替え、**上辺に水平なパッド列を持つ
# ハードマクロ `MEMPORT` (1598.4 x 399.6)** にまとめる。中継はマクロの横に
# 置くので高さの持ち出しはゼロ。
#
# 帯は**ルータの座標系の下**（y -399.6 … 0）に置く。こうするとルータの ch[0]
# はマクロの上から始まり、トラック割当が帯の中に食い込まない。パッドは
# y -4.5 … -1.1 にあり、ルータからは「row0 のセルのピンが下に飛び出している」
# ように見える（ストラブは min/max で描かれるので向きは問題にならない）。
#
# **チャネル予算は多めでよい。** 帯がチャネルの y 範囲にかからないので、
# step10 の圧縮が全チャネルに効く（縦置きのときはマクロが y 200…1133 を
# 塞いで 507.6 µm のうち 249.8 µm しか削れなかった）。実測の必要量は 891 µm。
# ---- マクロの置き方 ------------------------------------------------------
# `TD4_MACRO_MODE`:
#   "landscape"（既定）  R90 して行スタックの**下に帯として敷く**（= `MEMPORT`）
#   "portrait"           そのまま行スタックの**右に縦置き**（= `REG8x16`）
#
# 縦置きは最初に試して短絡 31 件で行き詰まった案。その後ルータを直したので
# もう一度測れるように残してある（`scripts/pnr/README.md`「縦置き再訪」）。
# 縦置きの得失:
#   + 帯（502.2 + 隙間 27.0 = 529.2 µm）が丸ごと要らない
#   − 行幅が 1598.4 → 1177.2 に縮み、配置率が 71% → 78% に上がる
#   − マクロ（933 µm）は参照なので **step10 の圧縮がそこを貫通できない**
MACRO_MODE = os.environ.get("TD4_MACRO_MODE", "landscape")
if MACRO_MODE not in ("landscape", "portrait"):
    raise SystemExit(f"TD4_MACRO_MODE は landscape か portrait（今 {MACRO_MODE}）")
_PORTRAIT = MACRO_MODE == "portrait"

# --- step11: マクロの電源をコアのレールに繋ぐ -----------------------------
# 縦置きはマクロが行スタックの横に居て、その電源ポート（上下辺の M2）が
# **金属では何にも繋がらない**。`scripts/pnr/connect_macro_power.py` が
# TAP の柱からマクロ下辺のポートまでストラップを通す。
# 横倒し（確定済みの結果）は既定で触らない。
MACRO_POWER = os.environ.get("TD4_MACRO_POWER", "1" if _PORTRAIT else "0") != "0"
MACROPWR_GDS = os.path.join(LAYOUT, "step11", "route_step_7_macro_power.gds")
FINAL_GDS = MACROPWR_GDS if MACRO_POWER else SQUEEZED_GDS

# 実験用の上書き。`TD4_N_ROWS=5 python3 scripts/pnr/place.py` のように使う。
N_ROWS = int(os.environ.get("TD4_N_ROWS", "5" if _PORTRAIT else "4"))
CORE_WIDTH_UM = 1598.4

MACRO_NET_CELL = "REG8x16"     # ネットリストに出てくる名前
if _PORTRAIT:
    MACRO_CELL = "REG8x16"     # 回さずそのまま置く
    MACRO_W, MACRO_H = 399.6, 933.0
    # --- コア右の縦 M2 バス（`TD4_SIDE_BUS`、既定 8 本） -------------------
    # 行スタックとマクロの間の帯には**セルが 1 つも無い**ので、ここを縦に
    # 走る M2 は行を 1 つも跨がない。マクロの `Q[*]`（`rom_data`）は
    # ch[1] から row0…row4 まで散り、行またぎ失敗の主犯なのでここへ逃がす。
    #
    # **本数は実測で決めた。** マクロ 21 本のチャネル span:
    #   span>=2 が 13 本 / span>=3 が 7 本 / span>=4 は Q[3] の 1 本だけ。
    #   `D[*]` `nib_lo[*]` は ch[0…2] に収まるのでバスは要らない。
    #   y 区間パッキングは効かない（全部が出口 ch[1] から始まるので必ず重なる）
    #   → **バスの幅 = 本数**。
    # 幅はそのまま行幅から引かれる（コア幅 1598.4 / マクロ 399.6 は固定）:
    #   バス 0 本 行 1177.2 充填率 83.0%（コリドー 6 本）/ 79.3%（3 本）
    #   バス 8 本 行 1134.0        86.6%              / **82.6%**
    #   バス16 本 行 1090.8        90.6%              / 86.2%  ← 配置が組めない
    SIDE_BUS_TRACKS = int(os.environ.get("TD4_SIDE_BUS", "9"))
    # 帯の余り（バス本体 `SIDE_BUS_TRACKS × 5.4` の外側に足す分）。
    # **ここは 21.6 µm も要らない。** KLayout で実測すると、バスの右端と
    # マクロの間に 19.9 µm の空きが残っていた（ユーザ指摘）。必要なのは
    #   行側: via の M1 パッド 3.4/2 + M1 最小間隔 1.4 = **3.1 µm**
    #   マクロ側: 同上 3.1（`REG8x16` の M1 は prBoundary の左端 x=0.0 から。
    #             M2 は x=1.0 からなので M2 同士なら 2.7 で足りるが、
    #             via のパッドが効くので 3.1 が拘束）
    # 実測値: `REG8x16` の左端は M1 0.00 / M2 1.00 / V1 2.00 / GC 2.50。
    # 余り 5.4 なら「行側 3.7 / マクロ側 5.4」で両側とも足りる。
    SIDE_BUS_SLACK = float(os.environ.get("TD4_SIDE_BUS_SLACK", "5.4"))
    MACRO_SIDE_GAP = round(SIDE_BUS_SLACK + SIDE_BUS_TRACKS * SITE_UM, 3)
    # **コア幅 1600 を超えるとフレーム開口が 1840 → 1600 に落ちる**ので、
    # 行幅は残り全部（`frame_opening()` で実測した崖）。
    ROW_WIDTH_UM = round(CORE_WIDTH_UM - MACRO_W - MACRO_SIDE_GAP, 3)
    # TAP は等間隔。534.6 刻みだと最後の区間だけ極端に狭くなり、そこへ回された
    # セルが入らず step3 で落ちる（実測: 「1 個が行に入りきらない」）。
    _tap_last = round(ROW_WIDTH_UM - TAP_W, 3)
    _tap_step = round(round(_tap_last / 3 / SITE_UM) * SITE_UM, 3)
    TAP_X_DEFAULT = [0.0, _tap_step, round(2 * _tap_step, 3), _tap_last]
else:
    MACRO_CELL = "MEMPORT"     # 実際に置く物理セル（R90 + 中継）
    MACRO_W, MACRO_H = 1598.4, 502.2   # mkmemport.py の出力と一致させること
    MACRO_SIDE_GAP = 0.0
    ROW_WIDTH_UM = CORE_WIDTH_UM   # 行はコア幅いっぱい（マクロが横に無いので）
    TAP_X_DEFAULT = [0.0, 534.6, 1069.2, 1587.6]
# 帯の上端と ch[0] の下端 (y=0) の間に空ける隙間。
# **0 にしてはいけない。** ルータは ch[0] の最初のトラックを y=2.0 に置き、
# TAP の M2 電源メッシュを y=0 から立てるので、帯の上辺の金属と 1.4/2.0 µm を
# 割る（実測: M1 間隔違反 17 件・M2 間隔違反 13 件が全部 y≈0、x<933 に出た）。
#
# ここには **VDD/VSS の電源バスバー 2 本（M1・幅 10 µm）** を通す
# （ユーザ指示）。帯の上辺と ch[0] の間は M2 のライザが縦に抜けるだけで
# M1 は 1 本も無いので、横向きの M1 バーを通すのに都合がよい。
# 必要量: 1.4 + 10 + 1.4 + 10 + 1.4 = 24.2 µm → サイト grid に丸めて 27.0。
POWER_BAR_W = 10.0             # バー 1 本の M1 幅
POWER_BAR_GAP = 2.0            # バー間 / 帯とバーの間（M1 最小 1.4 に余裕）
# 縦置きのとき、マクロの**底面をどの行の底面に合わせるか**（`TD4_MACRO_ROW`）。
# マクロの信号ピンは下辺 1 列なので、合わせた行 k の底面 = ch[k] を向く。
#   k=0  ピンが ch[0] を向く。**マクロの 21 本が全部 row0 を越えて上へ抜ける**
#        ので row0 の行またぎが詰まる（実測: clear-x 失敗 24 本のうち 10 本が row0）
#   k=1  ピンが ch[1] を向く。row0 へは下り、row1…row4 へは上り、と分かれる
# 行スタックより高くなると（マクロ上端 > スタック高）コアがその分だけ伸びる。
MACRO_ALIGN_ROW = int(os.environ.get("TD4_MACRO_ROW", "0"))
MACRO_GAP_UM = 0.0 if _PORTRAIT else 27.0
# ルータ座標での帯の下端。縦置きでは帯が無いので使わない（macro_box() 参照）。
MACRO_Y0 = 0.0 if _PORTRAIT else -(MACRO_H + MACRO_GAP_UM)

# チャネル予算。横倒しでは**圧縮で使わないトラックは丸ごと消える**ので多めで
# よい。最後だけ 250 なのは上端マージン（トップピンの引き出しにしか使わない）。
#
# **縦置きでは多めにしてはいけない。** マクロは参照なので圧縮がその y 範囲を
# 貫通できず、マクロが跨ぐチャネルの余りはそのままコア高に乗る。
# `TD4_CH_HEIGHTS="200,290,330,250,250,90"` のようにカンマ区切りで渡せる。
_ch_env = os.environ.get("TD4_CH_HEIGHTS")
if _ch_env:
    CH_HEIGHTS = [float(v) for v in _ch_env.split(",")]
elif _PORTRAIT:
    CH_HEIGHTS = [200.0] + [400.0] * (N_ROWS - 1) + [250.0]
else:
    CH_HEIGHTS = [600.0] * N_ROWS + [250.0]

TAP_X = TAP_X_DEFAULT                        # 行ローカル。tap_positions() と一致

# 配線で使うチャネル予算。配置と同じでなければならない（行の y が変わるため）。
ROUTE_CH_HEIGHTS = list(CH_HEIGHTS)

# 信号ピンが 1 辺にしか出ていないインスタンス。`MEMPORT` のパッドは帯の上辺
# （ルータ座標では row0 の下）にしか無いので、**ch[0] からしか出られない**。
# ルータが行だけ見て上の ch に割り振らないよう名指しする
# （`route_channels_nrow_fm.py` の「TD4 移植 (3)」）。
DOWN_FACING_INSTS = {"u_mem"}

# コアの下に `MEMPORT` の帯を敷くので、**BBOX の下辺はチップから見るとコアの
# 内側**になる。トップピンを下辺に出さない（`route_top_pins_nrow_fm.py` の
# 「TD4 移植 (8)」）。下辺のパッド 3 本 (D[0]/RSTN/OUT[0]) はチップ側で回り込む。
# 縦置きではコアの下辺は素通しなので下辺にもポートを出せる。
NO_BOTTOM_PORTS = not _PORTRAIT

# ---- 派生値 --------------------------------------------------------------
def row_y():
    """各行の prBoundary 下端 y（コアローカル）と、行スタックの総高。"""
    ys, y = [], 0.0
    for i in range(N_ROWS):
        y += CH_HEIGHTS[i]
        ys.append(round(y, 3))
        y += ROW_HEIGHT_UM
    return ys, round(y + CH_HEIGHTS[-1], 3)


def macro_box():
    """マクロの prBoundary (x0, y0, x1, y1)（コアローカル）。

    横倒し: 行スタックの**下**の帯。y は負で、上端は -MACRO_GAP_UM。
    縦置き: 行スタックの**右**。**底面を row0 の底面と面一**にする
            （y0 = CH_HEIGHTS[0]）ので、マクロの下辺ピン列が row0 の
            セルのピン列と同じ ch[0] を向く。
    """
    if _PORTRAIT:
        x0 = ROW_WIDTH_UM + MACRO_SIDE_GAP
        y0 = row_y()[0][MACRO_ALIGN_ROW]
        return (x0, y0, round(x0 + MACRO_W, 3), round(y0 + MACRO_H, 3))
    return (0.0, MACRO_Y0, MACRO_W, round(MACRO_Y0 + MACRO_H, 3))


def side_bus_x():
    """コア右の縦 M2 バスのトラック中心 x（縦置きのみ）。

    行スタックの右端 `ROW_WIDTH_UM` とマクロの左端の間に取る。行のセルは
    `ROW_WIDTH_UM` で終わり、マクロの金属は左端 +2.8 から始まるので、
    ここは**上下に素通し**。行を跨がないので `find_row_clear_x` を通らない。
    """
    if not _PORTRAIT or SIDE_BUS_TRACKS <= 0:
        return []
    return [round(ROW_WIDTH_UM + SITE_UM + k * SITE_UM, 3)
            for k in range(SIDE_BUS_TRACKS)]


def power_bars():
    """帯の上辺と ch[0] の間に確保した **M1 電源バスバー 2 本**の
    (name, y0, y1)。下が VSS、上が VDD（帯側が GND なのはマクロの
    電源が帯の右端から出るため。チップ側で受けるときに合わせること）。

    ルータはここに何も描かない（ch[0] は y>=0 から始まる）。実際の
    バーはチップ組み立てで TAP の M2 柱とマクロ右端の電源に繋ぐ。
    """
    if _PORTRAIT:
        return []                             # 帯が無いので隙間も無い
    top_of_band = MACRO_Y0 + MACRO_H          # = -MACRO_GAP_UM
    y = top_of_band + POWER_BAR_GAP
    out = []
    for name in ("GND", "VDD"):
        out.append((name, round(y, 3), round(y + POWER_BAR_W, 3)))
        y += POWER_BAR_W + POWER_BAR_GAP
    return out


def core_size():
    """ルータが扱う領域の幅・高さ。横倒しの帯は含まない（y<0 なので）。
    縦置きではマクロが行スタックより高くなりうるので max を取る。"""
    _, stack_h = row_y()
    if _PORTRAIT:
        return CORE_WIDTH_UM, round(max(stack_h, macro_box()[3]), 3)
    return CORE_WIDTH_UM, stack_h


def chip_core_box():
    """チップに落とすときのコア外形。横倒しは**帯を含む**ので下端が負。"""
    w, h = core_size()
    return (0.0, 0.0 if _PORTRAIT else MACRO_Y0, w, h)


def chip_core_height():
    _, b, _, t = chip_core_box()
    return round(t - b, 3)


def check():
    """フロアプランの内部矛盾を潰す。import 時に毎回回す。"""
    msg = []
    if len(CH_HEIGHTS) != N_ROWS + 1:
        msg.append(f"CH_HEIGHTS は {N_ROWS+1} 本要る（今 {len(CH_HEIGHTS)}）")
    if MACRO_W > CORE_WIDTH_UM + 1e-6:
        msg.append(f"マクロ幅 {MACRO_W} がコア幅 {CORE_WIDTH_UM} を超える")
    if not _PORTRAIT and MACRO_Y0 >= 0:
        msg.append(f"マクロ帯はルータ座標の下（y<0）に置くこと（今 {MACRO_Y0}）")
    if _PORTRAIT:
        mx0, my0, mx1, my1 = macro_box()
        if mx1 > CORE_WIDTH_UM + 1e-6:
            msg.append(f"縦置きのマクロ右端 {mx1} がコア幅 {CORE_WIDTH_UM} を超える")
        _ys, _stack = row_y()
        if not (0 <= MACRO_ALIGN_ROW < N_ROWS):
            msg.append(f"TD4_MACRO_ROW {MACRO_ALIGN_ROW} が行の範囲外（0…{N_ROWS-1}）")
        _bus = side_bus_x()
        if _bus:
            # 拘束は **via の M1 パッド**（半幅 1.7 + M1 最小間隔 1.4 = 3.1）。
            # `REG8x16` の M1 は prBoundary の左端そのもの（実測 x=0.00）。
            if _bus[0] - 3.1 < ROW_WIDTH_UM - 1e-9:
                msg.append(f"縦バスの左端 {_bus[0]} が行スタックの右端 "
                           f"{ROW_WIDTH_UM} に近すぎる（via パッド 1.7 + "
                           f"M1 最小間隔 1.4 = 3.1 要る）")
            if _bus[-1] + 3.1 > mx0 + 1e-9:
                msg.append(f"縦バスの右端 {_bus[-1]} がマクロの M1 左端 "
                           f"{mx0} に近すぎる（3.1 要る）")
        if not (0 <= MACRO_ALIGN_ROW < N_ROWS):
            pass
        elif abs(my0 - _ys[MACRO_ALIGN_ROW]) > 1e-6:
            msg.append(f"縦置きのマクロ底面 {my0} が row{MACRO_ALIGN_ROW} の底面 "
                       f"{_ys[MACRO_ALIGN_ROW]} と面一でない"
                       f"（下辺のピン列が ch[{MACRO_ALIGN_ROW}] を向かなくなる）")
    # 電源バスバーが帯の上辺と ch[0] の間に収まるか（横倒しだけ）
    _need = 2 * POWER_BAR_W + 3 * POWER_BAR_GAP
    if not _PORTRAIT and MACRO_GAP_UM + 1e-9 < _need:
        msg.append(f"MACRO_GAP_UM {MACRO_GAP_UM} では M1 電源バー 2 本 "
                   f"({POWER_BAR_W} µm x2 + 間隔 {POWER_BAR_GAP} x3 = {_need}) が入らない")
    if power_bars() and power_bars()[-1][2] > -1.4:
        msg.append(f"電源バーの上端 {power_bars()[-1][2]} が ch[0] (y=0) に近すぎる"
                   f"（M1 最小間隔 1.4 µm）")
    if not _PORTRAIT and abs(MACRO_GAP_UM / SITE_UM - round(MACRO_GAP_UM / SITE_UM)) > 1e-9:
        msg.append(f"MACRO_GAP_UM {MACRO_GAP_UM} がサイトグリッド {SITE_UM} に乗っていない")
    if any(abs(t / SITE_UM - round(t / SITE_UM)) > 1e-9 for t in TAP_X):
        msg.append("TAP_X がサイトグリッドに乗っていない")
    if msg:
        raise SystemExit("td4_config: フロアプランが矛盾している\n  - "
                         + "\n  - ".join(msg))


def check_opening():
    """圧縮後のコア高がフレーム開口に収まるか。**配線が終わってから**使う
    （配線中は予算を多めに積むので、この時点では超えていて当たり前）。"""
    lo, hi = frame_opening(CORE_WIDTH_UM)
    h = chip_core_height()
    return h, hi - lo, (hi - lo) - h


# ---- チップ統合（コアを GIO パッドリングに落とす） -----------------------
CHIP = os.path.join(LAYOUT, "chip")
# チップに載せるコア。**step11（マクロ電源）を走らせたならそれが正**。
# `TD4_MACRO_MODE` の既定は landscape なので、環境変数を付け忘れると
# `FINAL_GDS` が step10 を指し、**マクロの vdd/vss が金属で何にも繋がって
# いないコア**を載せてしまう（2026-09-14 に実際にやって、組み上げた
# チップに step11 のストラップが入っていなかった）。あるなら step11。
CHIP_CORE_GDS = MACROPWR_GDS if os.path.exists(MACROPWR_GDS) else FINAL_GDS
# **チップに載せるときはフレームのセル名を `OSS_FRAME` に付け替える。**
# `scripts/pre_check.py`（MPW のチェッカ）の `FRAME_CELL_NAMES` は
# {OSS_FRAME, OSS_FRAME_TEG} で、GIO 版の名前が入っていない。フレーム GDS には
# `OSS_FRAME`（アナログ 16 パッド）と `OSS_FRAME_GIO`（HIZ/OUT 付き）の両方が
# 入っているが、チップに取り込むのは GIO 版だけなので名前はぶつからない。
# LVS のソース側（mkchipnet.py）も同じ名前に合わせる。
FRAME_CELL_CHIP = "OSS_FRAME"
GIO_PIN_RADIUS = 921.7         # P/HIZ/OUT 端子の半径（ダイ中心から）
PTECT_LAYER = (63, 1)


def core_bbox_um(gds=None, cell=None):
    import klayout.db as db
    ly = db.Layout()
    ly.read(gds or SQUEEZED_GDS)
    c = ly.cell(cell or TOP_CELL_NAME)
    if c is None:
        raise SystemExit(f"{cell or TOP_CELL_NAME} が {gds or SQUEEZED_GDS} に無い")
    b = c.bbox()
    return (b.left * ly.dbu, b.bottom * ly.dbu, b.right * ly.dbu, b.top * ly.dbu)


_FRAME_REGION = {}

# 「コアが当たってはいけない」層。ウェル (140,0) も入れる（重なりは論外だし、
# 実測では M1/M2 と同じ ±920 なので実質効かない）。
FRAME_HARD_LAYERS = ((3, 1), (3, 2), (8, 1), (11, 0), (13, 0), (14, 0),
                     (19, 0), (20, 0), (48, 1), (49, 1), (140, 0))


def frame_region(gds=None, cell=None):
    """フレームの実ジオメトリ（`FRAME_HARD_LAYERS` の和）。結果はキャッシュ。"""
    import klayout.db as db
    key = (gds or FRAME_GDS, cell or FRAME_CELL)
    if key not in _FRAME_REGION:
        ly = db.Layout()
        ly.read(key[0])
        top = ly.cell(key[1])
        if top is None:
            raise SystemExit(f"{key[1]} が {key[0]} に無い")
        r = db.Region()
        for lay in FRAME_HARD_LAYERS:
            r += db.Region(top.begin_shapes_rec(ly.layer(*lay)))
        r.merge()
        _FRAME_REGION[key] = (r, ly.dbu)
    return _FRAME_REGION[key]


def frame_clear(x0, y0, x1, y1, gds=None, cell=None):
    """その矩形がフレームの実ジオメトリと重ならないか。"""
    import klayout.db as db
    r, u = frame_region(gds, cell)
    box = db.Region(db.Box(int(round(x0 / u)), int(round(y0 / u)),
                           int(round(x1 / u)), int(round(y1 / u))))
    return (r & box).is_empty()


def frame_opening(width_um=CORE_WIDTH_UM, gds=None, cell=None):
    """幅 width_um のコアが収まる最大の y 帯（ダイ中心基準）。**実ジオメトリ実測。**

    `frame_opening_lef()`（OBS 宣言）と違い、四隅の L 字を正しく見る。
    実測: 原点中心 1840 x 1840 は**全層で完全に空き**、1844 で当たる。
    つまり開口は**四隅まで含めて 1840 角**。`CORE_WIDTH_UM = 1598.4` は
    OBS の崖を避けて決めた値なので、実際にはもっと広げられる（が、余裕を
    持たせたまま据え置く — ユーザ判断 2026-09-14）。
    """
    lo, hi = 0.0, 1250.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if frame_clear(-width_um / 2, -mid, width_um / 2, mid, gds, cell):
            lo = mid
        else:
            hi = mid
    return (-round(lo, 3), round(lo, 3))


def frame_inner_wall(box, gds=None, cell=None):
    """コアの箱 (x0,y0,x1,y1) の四方で、フレームの実ジオメトリが来ている位置。

    返すのは (left, right, bottom, top)。LEF の OBS ではなく図形を測る。"""
    import klayout.db as db
    r, u = frame_region(gds, cell)
    x0, y0, x1, y1 = box
    out = {}
    for side, probe in (
            ("left",   (-1250.0, y0, x0, y1)),
            ("right",  (x1, y0, 1250.0, y1)),
            ("bottom", (x0, -1250.0, x1, y0)),
            ("top",    (x0, y1, x1, 1250.0))):
        reg = r & db.Region(db.Box(int(round(probe[0] / u)), int(round(probe[1] / u)),
                                   int(round(probe[2] / u)), int(round(probe[3] / u))))
        if reg.is_empty():
            out[side] = None
            continue
        b = reg.bbox()
        out[side] = {"left": b.right * u, "right": b.left * u,
                     "bottom": b.top * u, "top": b.bottom * u}[side]
    return out


def frame_opening_lef(width_um=CORE_WIDTH_UM, lef=None):
    """**LEF の OBS 宣言**から見た開口（ダイ中心基準）。比較用に残してある。

    **これを設計の根拠に使ってはいけない。** OBS は四隅を 360x360 の矩形
    （x 800…1160, y 800…1160）で粗く塞いでいるが、`OSS_FRAME_CNR` の実際の
    図形は**外側 2 辺に沿った L 字**で、内側の角は空いている（実測: (780…860)^2
    には何も無い）。そのため OBS を読むと
        幅 1598.4 -> ±920 / 幅 1604.7 -> ±800
    という「崖」が出るが、**実在しない**。実ジオメトリの開口は四隅まで含めて
    1840 x 1840 の正方形（`frame_opening()` が実測する）。
    """
    import re
    txt = open(lef or FRAME_LEF).read()
    body = re.search(rf"MACRO {FRAME_CELL}(.*?)END {FRAME_CELL}", txt, re.S).group(1)
    obs = re.search(r"OBS(.*?)END", body, re.S).group(1)
    die = float(re.search(r"SIZE\s+([\d.]+)\s+BY", body).group(1))
    c = die / 2
    rects = sorted({tuple(float(v) - c for v in q) for q in
                    re.findall(r"RECT\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)"
                               r"\s+(-?[\d.]+)\s*;", obs)})
    x0, x1 = -width_um / 2, width_um / 2
    ys = [(a, b) for (p, a, q, b) in rects if q > x0 + 1e-9 and p < x1 - 1e-9]
    pts = sorted({-c, c} | {v for p in ys for v in p})
    best = (0.0, 0.0)
    for a, b in zip(pts, pts[1:]):
        m = (a + b) / 2
        if not any(lo < m < hi for lo, hi in ys) and b - a > best[1] - best[0]:
            best = (a, b)
    return best


def frame_obs_rects(lef=None):
    """`OSS_FRAME_GIO` の OBS 矩形（**ダイ中心が原点**）。"""
    import re
    txt = open(lef or FRAME_LEF).read()
    body = re.search(rf"MACRO {FRAME_CELL}(.*?)END {FRAME_CELL}", txt, re.S).group(1)
    obs = re.search(r"OBS(.*?)END", body, re.S).group(1)
    die = float(re.search(r"SIZE\s+([\d.]+)\s+BY", body).group(1))
    c = die / 2
    return die, sorted({tuple(float(v) - c for v in q) for q in
                        re.findall(r"RECT\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)"
                                   r"\s+(-?[\d.]+)\s*;", obs)})


def chip_geometry(gds=None, cell=None):
    """コアをパッドリングの開口の**中央**に置いたときの寸法一式。

    `OSS_FRAME_GIO` はセル自身がダイ中心を原点に持つ（bbox -1250…+1250）ので、
    フレームは **(0,0) にそのまま置く**。コアだけオフセットする。

    開口は十字型で、OBS の実測から:
        |y| <= 800   -> |x| <= 920 が空き（幅 1840）
        800 < |y| <= 920 -> |x| <= 800 が空き（幅 1600）
    コアの実 bbox は **1604.7 x 1347.4**（x が 1598.4 でなく 1604.7 なのは
    いちばん左のセルの N ウェル (140,0) が x=-6.3 まで出ているため）。
    幅が 1600 を超えるので使えるのは |y| <= 800 の帯だが、高さ 1347.4 は
    そこに余裕で収まる。**SCLK_SPI と同じく native bbox を対称にする。**
    """
    l, b, r, t = core_bbox_um(gds or CHIP_CORE_GDS, cell)
    ox = round(-(l + r) / 2.0, 3)
    oy = round(-(b + t) / 2.0, 3)
    box = (round(l + ox, 3), round(b + oy, 3), round(r + ox, 3), round(t + oy, 3))
    die = frame_obs_rects()[0]
    # 壁は**実ジオメトリ**で測る。LEF の OBS は四隅を 360x360 の矩形で粗く
    # 塞いでいて、そのまま読むと「幅 1600 超なら |y| <= 800」という実在しない
    # 崖が出る（`frame_opening_lef()` の注意書き）。
    w = frame_inner_wall(box)
    return {
        "die": die,
        "core_offset": (ox, oy),
        "core_native_bbox": (l, b, r, t),
        "core_chip_bbox": box,
        "wall": {k: (round(v, 3) if v is not None else None) for k, v in w.items()},
        "channel_left": (round(box[0] - w["left"], 3) if w["left"] is not None else None,
                         round(box[0] + GIO_PIN_RADIUS, 3)),
        "channel_right": (round(w["right"] - box[2], 3) if w["right"] is not None else None,
                          round(GIO_PIN_RADIUS - box[2], 3)),
        "channel_bottom": (round(box[1] - w["bottom"], 3) if w["bottom"] is not None else None,
                           round(box[1] + GIO_PIN_RADIUS, 3)),
        "channel_top": (round(w["top"] - box[3], 3) if w["top"] is not None else None,
                        round(GIO_PIN_RADIUS - box[3], 3)),
    }


def chip_fits(geom=None):
    """コアがフレームの**実ジオメトリ**と重ならないか。[(理由, 情報)]（空なら OK）。

    OBS 宣言ではなく図形で見る。参考までに OBS 側の判定も添える
    （四隅を粗く塞いでいるので、実測が OK でも OBS では当たることがある）。"""
    g = geom or chip_geometry()
    box = g["core_chip_bbox"]
    bad = []
    if not frame_clear(*box):
        bad.append(("コアがフレームの実ジオメトリと重なる", box))
    obs = [p for p in frame_obs_rects()[1]
           if p[0] < box[2] - 1e-9 and p[2] > box[0] + 1e-9
           and p[1] < box[3] - 1e-9 and p[3] > box[1] + 1e-9]
    if obs and not bad:
        print(f"  note: LEF の OBS では {len(obs)} 個の矩形と重なるが、"
              f"実ジオメトリでは当たっていない（四隅の粗い宣言）")
    return bad


def pdk_tech_python():
    """PDK の KLayout PCell パッケージ（`from cells import tr_1um`）。
    ルータのビアは全部この PCell のインスタンスなので必須。"""
    env = os.environ.get("TR1UM_PDK")
    cands = []
    if env:
        cands.append(os.path.join(env, "libs.tech", "klayout", "tech", "python"))
        cands.append(os.path.join(env, "klayout", "tech", "python"))
        cands.append(env)
    cands += [
        os.path.expanduser("~/Dropbox/91_OpenPDK/TR-1um/libs.tech/klayout/tech/python"),
        os.path.join(os.path.dirname(ROOT), "TR-1um", "libs.tech", "klayout", "tech", "python"),
        os.path.expanduser("~/TR-1um/libs.tech/klayout/tech/python"),
    ]
    for c in cands:
        if os.path.isdir(os.path.join(c, "cells")):
            return c
    raise SystemExit("TR-1um PDK の KLayout PCell パッケージが見つからない。\n"
                     "  TR1UM_PDK を PDK チェックアウトに向けること。\n"
                     f"  試した場所: {cands}")


def artifact(basename):
    """移植元が絶対パスで持っていた中間ファイルは全部 layout/ に落とす。"""
    return os.path.join(LAYOUT, basename)


def channel_heights(placement_json=PLACEMENT_JSON):
    import json
    return json.load(open(placement_json))["ch_heights"]


# フロアプランの内部矛盾は import のたびに潰す。frame_opening() を使うので
# 定義が全部そろった最後に呼ぶ。
check()

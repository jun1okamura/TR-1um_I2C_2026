"""i2c_config.py -- P&R のパス・幾何定数の単一ソース。

`TR-1um_TD4/scripts/pnr/td4_config.py` を Async I2C 用に書き直したもの。
配線スクリプトは `TR-1um_Async_I2C/script/` → `TR-1um_SCLK_SPI/scripts/` →
`TR-1um_TD4/scripts/pnr/` と渡ってきた移植物で、中で `import spi_config as _cfg`
と書いてある。**原本を書き換えないため**、同じディレクトリに `spi_config.py`
（このモジュールを再輸出するだけの薄皮）を置いてある。触るのはこのファイルだけ。

## TD4 版との違い

**ハードマクロが無い。** TD4 は 16x8bit のレジスタアレイ `REG8x16` を行スタックの
下（または右）に置くので、`i2c_config.py` の半分はその置き方の話だった。I2C の
コアは標準セルだけ（120 個）で、RING_OSC は**チップ組み立て側**でパッドリングの
チャネルに置く別ブロックなので、コアの P&R には出てこない。

マクロ関連の定数と関数は**値を潰した形で残してある**（`MACRO_MODE = "none"`、
`macro_box()` が縮退した箱を返す）。移植してきた配線スクリプトがあちこちで
`cfg.MACRO_CELL` や `cfg.macro_box()` を参照しており、**原本を触らない方針**を
保つには、参照先が無害な値で存在している方が安全なため。

## フロアプランの出どころ

V10（実際にテープアウトして SPICE 14/14 PASS した版）の値を踏襲する:

    N_ROWS 4 / ROW_WIDTH 1620.0 (= 5.4 x 300) / TRACK_PITCH 5.4
    CH_HEIGHTS [131.6, 700, 1000, 700, 153.2]  (`run_v10_pipeline.py`)

チャネル予算が大きいのは step10 の圧縮で削られる前提だから。V10 は圧縮後に
コア高 884.9 µm まで落ちている。

環境変数:
  TR1UM_PDK   PDK チェックアウト（via_1 PCell ライブラリ用）
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- 設計の同定 ----------------------------------------------------------
TOP_CELL_NAME = "i2c_slave_async_nrow_fm"     # 配置配線したコアセル
CHIP_TOP_CELL = "tr_1um_jun1okamura_i2c"      # info.yaml の gds.top_cell
#   MPW のテンプレートが「tr_1um_ で始まり GitHub ユーザ名を含むこと」と
#   決めている（シャトル上で名前がぶつからないように）。

# ---- 入力 ----------------------------------------------------------------
LIB_LEF = os.path.join(ROOT, "lef", "TR-1um_cells.lef")
LIB_GDS = os.path.join(ROOT, "lef", "TR-1um_STDCELL.gds")
# P&R が読むもの。マクロが無いのでライブラリそのもの。
LEF_PATH = os.path.join(ROOT, "lef", "TR-1um_PNR.lef")
CELL_GDS = os.path.join(ROOT, "lef", "TR-1um_PNR.gds")
NET_PATH = os.path.join(ROOT, "out", "i2c_slave_async_pnr.v")
FRAME_GDS = os.path.join(ROOT, "lef", "TR-1um_frame_25x25.gds")
FRAME_LEF = os.path.join(ROOT, "lef", "TR-1um_frame.lef")
FRAME_CELL = "OSS_FRAME_GIO"                  # 16 パッドの GIO リング

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
# step8 (トップピン) が描いた分を足したもの。step8 の後にもう一度 ripup を
# 掛けるために要る。
NET_SHAPES_TP_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_tp.json")
PIN_MAP_TP_JSON = os.path.join(LAYOUT, "pin_map_nrow_fm_tp.json")
NET_SHAPES_TP2_JSON = os.path.join(LAYOUT, "net_shapes_nrow_fm_tp2.json")
COMPACTION_INFO_JSON = os.path.join(LAYOUT, "compaction_info_nrow_fm.json")

# ---- セルライブラリの幾何 ------------------------------------------------
# prBoundary の実測値（lef/TR-1um_STDCELL.gds、全セル 59.4）。TD4 と同じ
# STDCELL を使うので同じ。SCLK_SPI 世代は 64.8 だったので混ぜないこと。
ROW_HEIGHT_UM = 59.4
SITE_UM = 5.4
TRACK_PITCH = float(os.environ.get("I2C_TRACK_PITCH", "5.4"))   # チャネルの M1 トラック間隔
TAP_CELL = "TAP2"
TAP_W = 10.8
TAP_PITCH = 534.6              # I2C 実チップ実測（V10）
# 隙間埋めに使う FILL（広い順）。`I2C_USE_FILL1=1` で FILL1 (5.4) も使う。
FILLS = [("FILL3", 16.2), ("FILL2", 10.8)]
if os.environ.get("I2C_USE_FILL1") == "1":
    FILLS = FILLS + [("FILL1", 5.4)]
# 優先 M2 コリドーに使うセル。FILL3 (16.2 = 3 トラック) なら真ん中の 1 本が
# 必ず両側とも空く（FILL2 だと via パッドが隣にはみ出して実質 1 本しか使えない）。
_PRI_W = {"FILL1": 5.4, "FILL2": 10.8, "FILL3": 16.2}
PRI_CELL = os.environ.get("I2C_PRI_CELL", "FILL3")
if PRI_CELL not in _PRI_W:
    raise SystemExit(f"I2C_PRI_CELL は {sorted(_PRI_W)} のどれか（今 {PRI_CELL}）")
PRI_W = _PRI_W[PRI_CELL]
# 優先 M2 コリドーのピッチ。1e9 で「TAP 直後の 1 枠だけ」= 移植元と同じ。
PRI_PITCH = float(os.environ.get("I2C_PRI_PITCH", "1e9"))
# コリドーの置き方。"after" = TAP 直後だけ、"both" = TAP の両側。
PRI_MODE = os.environ.get("I2C_PRI_MODE", "both")
# 狙い撃ちの追加コリドー（`I2C_PRI_X="135.0,..."`, µm, サイトグリッドに丸める）。
PRI_EXTRA_X = [round(round(float(v) / SITE_UM) * SITE_UM, 3)
               for v in os.environ.get("I2C_PRI_X", "").split(",") if v.strip()]

# ---- フロアプラン --------------------------------------------------------
# **ハードマクロは無い。** 下のマクロ定数は移植元スクリプトが参照するための
# 縮退値。`MACRO_NET_CELL` はネットリストに絶対出てこない名前にしてあるので、
# `if i["type"] == cfg.MACRO_CELL` の類は必ず空振りする。
MACRO_MODE = "none"
_PORTRAIT = False
MACRO_NET_CELL = "__NO_MACRO__"
MACRO_CELL = "__NO_MACRO__"
MACRO_W = MACRO_H = 0.0
MACRO_SIDE_GAP = 0.0
MACRO_GAP_UM = 0.0
MACRO_Y0 = 0.0
MACRO_ALIGN_ROW = 0
SIDE_BUS_TRACKS = 0
SIDE_BUS_SLACK = 0.0
POWER_BAR_W = 10.0
POWER_BAR_GAP = 2.0
MACRO_POWER = False
MACROPWR_GDS = os.path.join(LAYOUT, "step11", "route_step_7_macro_power.gds")
FINAL_GDS = SQUEEZED_GDS       # マクロ電源の段が無いので step10 が最終

# V10 と同じ 4 行。`I2C_N_ROWS=5 python3 scripts/pnr/place.py` で振れる。
N_ROWS = int(os.environ.get("I2C_N_ROWS", "4"))
# 行幅。**V10 は 1620.0 (= 5.4 x 300) だったが、TD4 と同じ 1598.4 を採る。**
# 1620 だと TAP 4 本（0 / 534.6 / 1069.2 / 行末 1609.2）の最後の間隔が 540.0 に
# なり、実測で決めた TAP_PITCH 534.6 を超える。TAP を 5 本に増やせば収まるが
# 1 行あたり 10.8 µm を余計に食う。1598.4 なら TD4 の並びがそのまま使えて
# 最後の間隔も 518.4 に収まる。充填率は 4 行で 67% 程度あり 21.6 µm の差は効かない。
CORE_WIDTH_UM = float(os.environ.get("I2C_CORE_WIDTH", "1598.4"))
ROW_WIDTH_UM = CORE_WIDTH_UM   # マクロが横に無いので行はコア幅いっぱい
# 行末の TAP は「行幅 - TAP_W」。最後の区間だけ極端に狭いとそこへ回された
# セルが入らず step3 が落ちるので、等間隔 3 本 + 行末の 4 本にする。
_tap_last = round(ROW_WIDTH_UM - TAP_W, 3)
TAP_X_DEFAULT = [0.0, TAP_PITCH, round(2 * TAP_PITCH, 3), _tap_last]

# チャネル予算。V10 (`run_v10_pipeline.py`) の値。多めで構わない
# （マクロが y 範囲を塞がないので step10 の圧縮が全チャネルに効く）。
# `I2C_CH_HEIGHTS="131.6,700,1000,700,153.2"` のようにカンマ区切りで渡せる。
_ch_env = os.environ.get("I2C_CH_HEIGHTS")
if _ch_env:
    CH_HEIGHTS = [float(v) for v in _ch_env.split(",")]
else:
    # **上下の余白はトラック格子に乗せる。** V10 の 131.6 / 153.2 をそのまま
    # 使うと、ch0 のいちばん上のトラックが row0 のセルの M1 に 1.2 µm まで
    # 寄って **M1 間隔違反が 3 件出る**（実測: y 132.6 に幅 12.8 / 104.6 /
    # 185.6 µm の 0.2 µm 隙間。step6 で発生し step10 まで残る）。
    # 5.4 の倍数（140.4 = 26 トラック / 162.0 = 30 トラック）にすると 0 件になる。
    CH_HEIGHTS = [140.4] + [700.0, 1000.0, 700.0][:max(N_ROWS - 1, 0)] \
                 + [700.0] * max(N_ROWS - 4, 0) + [162.0]
    if len(CH_HEIGHTS) != N_ROWS + 1:          # N_ROWS を変えたとき用の埋め合わせ
        CH_HEIGHTS = [140.4] + [700.0] * (N_ROWS - 1) + [162.0]

TAP_X = TAP_X_DEFAULT                        # 行ローカル。tap_positions() と一致
ROUTE_CH_HEIGHTS = list(CH_HEIGHTS)          # 配線と配置で同じでなければならない

# 信号ピンが 1 辺にしか出ていないインスタンス（TD4 の `MEMPORT` 用）。無し。
DOWN_FACING_INSTS = set()
# **コアの下辺にはポートを出さない。**
# チップではコアの下に OpenSUSI のロゴ（1595 x 325、M2 の独立ドット 319x65）と
# RING_OSC を積むので、下辺から真下に降りる配線はロゴの帯を横切ってしまう。
# `route_top_pins_nrow_fm.py` の「TD4 移植 (8)」がこのフラグを見て、row0 も
# 中間行と同じ扱い（左右へ逃がす）にする。上辺は従来どおり使う。
NO_BOTTOM_PORTS = os.environ.get("I2C_NO_BOTTOM_PORTS", "1") != "0"


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
    """マクロの prBoundary。**マクロが無いので縮退した箱**。

    移植元スクリプトは `mx0, my0, mx1, my1 = cfg.macro_box()` と受けてから
    `my1 > 1e-6` や `i["type"] == cfg.MACRO_CELL` で存在を確かめるので、
    全ゼロを返せば「マクロは無い」と解釈される。
    """
    return (0.0, 0.0, 0.0, 0.0)


def side_bus_x():
    """コア右の縦 M2 バス（TD4 の縦置き用）。マクロが無いので空。"""
    return []


def power_bars():
    """帯の上辺と ch[0] の間の M1 電源バー（TD4 の横倒し用）。帯が無いので空。"""
    return []


def core_size():
    """ルータが扱う領域の幅・高さ。"""
    _, stack_h = row_y()
    return CORE_WIDTH_UM, stack_h


def chip_core_box():
    """チップに落とすときのコア外形。帯が無いので下端は 0。"""
    w, h = core_size()
    return (0.0, 0.0, w, h)


def chip_core_height():
    _, b, _, t = chip_core_box()
    return round(t - b, 3)


def check():
    """フロアプランの内部矛盾を潰す。import 時に毎回回す。"""
    msg = []
    if len(CH_HEIGHTS) != N_ROWS + 1:
        msg.append(f"CH_HEIGHTS は {N_ROWS+1} 本要る（今 {len(CH_HEIGHTS)}）")
    if ROW_WIDTH_UM > CORE_WIDTH_UM + 1e-6:
        msg.append(f"行幅 {ROW_WIDTH_UM} がコア幅 {CORE_WIDTH_UM} を超える")
    if abs(CORE_WIDTH_UM / SITE_UM - round(CORE_WIDTH_UM / SITE_UM)) > 1e-9:
        msg.append(f"コア幅 {CORE_WIDTH_UM} がサイトグリッド {SITE_UM} に乗っていない")
    if any(abs(t / SITE_UM - round(t / SITE_UM)) > 1e-9 for t in TAP_X):
        msg.append("TAP_X がサイトグリッドに乗っていない")
    if TAP_X and TAP_X[-1] + TAP_W > ROW_WIDTH_UM + 1e-6:
        msg.append(f"行末の TAP ({TAP_X[-1]} + {TAP_W}) が行幅 {ROW_WIDTH_UM} を超える")
    if msg:
        raise SystemExit("i2c_config: フロアプランが矛盾している\n  - "
                         + "\n  - ".join(msg))


def check_opening():
    """圧縮後のコア高がフレーム開口に収まるか。**配線が終わってから**使う
    （配線中は予算を多めに積むので、この時点では超えていて当たり前）。"""
    lo, hi = frame_opening(CORE_WIDTH_UM)
    h = chip_core_height()
    return h, hi - lo, (hi - lo) - h


# ---- チップ統合（コアを GIO パッドリングに落とす） -----------------------
CHIP = os.path.join(LAYOUT, "chip")
# チップに載せるコア。マクロが無いので step11（マクロ電源）は走らない。
CHIP_CORE_GDS = FINAL_GDS
# **チップに載せるときはフレームのセル名を `OSS_FRAME` に付け替える。**
# `scripts/pre_check.py`（MPW のチェッカ）の `FRAME_CELL_NAMES` は
# {OSS_FRAME, OSS_FRAME_TEG} で、GIO 版の名前が入っていない。フレーム GDS には
# `OSS_FRAME`（アナログ 16 パッド）と `OSS_FRAME_GIO`（HIZ/OUT 付き）の両方が
# 入っているが、チップに取り込むのは GIO 版だけなので名前はぶつからない。
# LVS のソース側（mkchipnet.py）も同じ名前に合わせる。
FRAME_CELL_CHIP = "OSS_FRAME"
GIO_PIN_RADIUS = 921.7         # P/HIZ/OUT 端子の半径（ダイ中心から）

# ---- RING_OSC（チップ側に置くテスト構造） --------------------------------
# `TR-1um_Async_I2C/ring_osc/RING_OSC.gds` をそのまま持ってきたもの。
# 97 段リングが 2 本（INV_X1 ベースの高速 OUT と INV3D ベースの低速 OUTD）。
# セル 1620.0 x 244.8、bbox は原点基準で x -6.3…1626.3 / y -120.0…124.8。
# ENB は RSTN と共有（リセット解除で発振開始）。
RING_OSC_GDS = os.path.join(ROOT, "lef", "RING_OSC.gds")
RING_OSC_LEF = os.path.join(ROOT, "lef", "RING_OSC.lef")
RING_OSC_CELL = "RING_OSC"
# 置く原点（ダイ中心基準）。**V10 と同じ (-810, -650)。**
# 絶対フットプリントは x -816.3…816.3 / y -770.0…-525.2 になる。
# V10 のコアは上寄せ（下端 -140）で下チャネルが広かったが、こちらはコアを
# 開口の中央に置くので下端は -490.8。RING_OSC の上端 -525.2 との隙間は 34.6 µm。
# リング配線のレーンは R 847…880（= 下辺では y -880…-847）を通るので、
# RING_OSC (…-770) とは干渉しない。
RING_OSC_ORIGIN = (float(os.environ.get("I2C_RINGOSC_X", "-810.0")),
                   float(os.environ.get("I2C_RINGOSC_Y", "-650.0")))


# ---- OpenSUSI ロゴ -------------------------------------------------------
# V10 と同じフルサイズ（等倍）。`lef/opensusi_logo.txt` を
# ピッチ 5.0 µm で描くので **1583.0 x 313.0 µm**。各 ON セルは 3.0 µm 角の
# 独立した M2 ドット（幅 3.0 = M2 最小幅ちょうど、隣との隙間 2.0 = 最小間隔
# ちょうど、斜めは 2.83 µm）。塗り潰しではなくドットなので斜め接触が原理的に無い。
LOGO_PITCH = 5.0
LOGO_DOT = 3.0
LOGO_BITMAP = os.path.join(ROOT, "lef", "opensusi_logo.txt")


def logo_size():
    """ビットマップから実寸 (幅, 高さ) を出す。**決め打ちにしない。**
    `lef/opensusi_logo.txt` は V10 の 319 x 65 から空の縁を落として 317 x 63
    になっており、等倍なら (317-1)*5+3 = 1583.0 x (63-1)*5+3 = 313.0 µm。"""
    rows = [l.rstrip("\n") for l in open(LOGO_BITMAP, encoding="utf-8")
            if not l.startswith("%") and l.strip()]
    w, h = max(len(r) for r in rows), len(rows)
    return (round((w - 1) * LOGO_PITCH + LOGO_DOT, 3),
            round((h - 1) * LOGO_PITCH + LOGO_DOT, 3))

# ---- チップの縦積み ------------------------------------------------------
# 下から RING_OSC / ロゴ / コア。V10 と同じ順序で、コアは**中央ではなく上寄せ**。
#
#   壁 -920 ── 下辺のリングレーン ── RING_OSC -770…-525.2 ── ロゴ ── コア ── 壁 +920
#
# 隙間は 20 µm ずつ。コア高 970.3 µm（重み 16 / seed 4）で計算すると
#   ロゴ  -505.2 … -180.2
#   コア  -160.2 … +810.1
#   上チャネル 109.9 µm（20 トラック。上辺のリングレーンは 4〜6 本）
# コア高が変わればコアの上端と上チャネルが動く（下は固定）。
LOGO_GAP = float(os.environ.get("I2C_LOGO_GAP", "20.0"))      # RING_OSC <-> ロゴ
CORE_LOGO_GAP = float(os.environ.get("I2C_CORE_LOGO_GAP", "20.0"))  # ロゴ <-> コア


def ringosc_box():
    """RING_OSC の絶対フットプリント (x0, y0, x1, y1)。GDS の bbox を実測。"""
    import klayout.db as db
    ly = db.Layout()
    ly.read(RING_OSC_GDS)
    c = ly.cell(RING_OSC_CELL)
    b, u = c.bbox(), ly.dbu
    ox, oy = RING_OSC_ORIGIN
    return (ox + b.left * u, oy + b.bottom * u,
            ox + b.right * u, oy + b.top * u)


def logo_box():
    """ロゴの帯 (x0, y0, x1, y1)。RING_OSC の上に LOGO_GAP 空けて、x は中央寄せ。"""
    w, h = logo_size()
    y0 = round(ringosc_box()[3] + LOGO_GAP, 3)
    return (round(-w / 2, 3), y0, round(w / 2, 3), round(y0 + h, 3))


def core_bottom_y():
    """コアの下端（チップ座標）。ロゴの上に CORE_LOGO_GAP 空ける。"""
    return round(logo_box()[3] + CORE_LOGO_GAP, 3)
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
    # **縦は中央ではない。** コアの下に OpenSUSI ロゴと RING_OSC を積むので、
    # コアの下端を `core_bottom_y()` に合わせて上寄せにする（V10 と同じ順序）。
    # `I2C_CORE_CENTER=1` で従来どおりの中央寄せに戻せる。
    if os.environ.get("I2C_CORE_CENTER") == "1":
        oy = round(-(b + t) / 2.0, 3)
    else:
        oy = round(core_bottom_y() - b, 3)
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
        os.path.join(os.path.dirname(ROOT), "TR-1um", "libs.tech", "klayout", "tech", "python"),
        os.path.expanduser("~/TR-1um/libs.tech/klayout/tech/python"),
    ]
    for c in cands:
        if os.path.isdir(os.path.join(c, "cells")):
            return c
    raise SystemExit("TR-1um PDK の KLayout PCell パッケージが見つからない。\n"
                     "  TR1UM_PDK を PDK チェックアウトに向けること。\n"
                     f"  試した場所: {cands}")


def pdk_spice_models():
    """PDK の ngspice モデル（`ip62_models`）があるディレクトリ。"""
    env = os.environ.get("TR1UM_PDK")
    cands = []
    if env:
        cands.append(os.path.join(env, "libs.tech", "spice", "models"))
    cands += [
        os.path.join(os.path.dirname(ROOT), "TR-1um", "libs.tech", "spice", "models"),
        os.path.expanduser("~/TR-1um/libs.tech/spice/models"),
    ]
    for c in cands:
        if os.path.exists(os.path.join(c, "ip62_models")):
            return c
    raise SystemExit("PDK の ngspice モデル ip62_models が見つからない。\n"
                     "  TR1UM_PDK を PDK チェックアウトに向けること。\n"
                     f"  試した場所: {cands}")


def write_models_shim(out_dir, name="models.spice"):
    """TB の隣に `models.spice`（PDK のモデルへの `.include` 1 行）を書く。

    ★ **回した機械の絶対パスをこの 1 ファイルに閉じ込める**ので、TB 自身は
    `.include 'models.spice'` だけで済む（U24）。ngspice の `.include` は
    環境変数を展開しないため、素直に書くと TB にパスが焼き付き、
    **他の機械では読めないものがコミットされる**。生成物なので
    `.gitignore` に入れてある。戻り値は TB に書く相対名。

    APRtools の `apr/chip_tb_lib.write_models_shim()` と同じ形。TD4 / SCLK_SPI
    はそちらを使う（この repo の scripts/pnr/ は移植した旧世代のフローで、
    APRtools を import しないので、同じものをここに置いてある）。
    """
    path = os.path.join(out_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("* 自動生成。回した機械の PDK を指す **1 行だけ**の橋渡し。\n"
                "* TR1UM_PDK を変えて生成し直せば更新される。\n"
                f".include '{os.path.join(pdk_spice_models(), 'ip62_models')}'\n")
    return name


def artifact(basename):
    """移植元が絶対パスで持っていた中間ファイルは全部 layout/ に落とす。"""
    return os.path.join(LAYOUT, basename)


def channel_heights(placement_json=PLACEMENT_JSON):
    import json
    return json.load(open(placement_json))["ch_heights"]


# フロアプランの内部矛盾は import のたびに潰す。frame_opening() を使うので
# 定義が全部そろった最後に呼ぶ。
check()

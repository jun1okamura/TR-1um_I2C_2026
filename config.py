"""config.py -- TR-1um_I2C_2026 を APRtools で再現するための検証用設定。

**移行の手順 1「素通しで md5 一致を確認する」専用**（`docs/04_naming.md` §4）。
`~/HogeHoge/LSI_Design/TR-1um_I2C_2026/config.py` に置いて使う。

    cd ~/HogeHoge/LSI_Design/TR-1um_I2C_2026
    export TR1UM_PDK=~/HogeHoge/OpenPDK/TR-1um
    export PYTHONHASHSEED=0                      # ★ ルータは非決定的
    APR=~/HogeHoge/OpenPDK/TR-1um_APRtools
    python3 $APR/apr/place.py
    python3 $APR/apr/route.py
    md5 layout/step10/route_step_6_squeezed.gds  # 移行前と一致するはず

旧 `i2c_config.py` と**同じ挙動になるように**書いてある:
  - 成果物のファイル名は新（`placement.json` 等）。トップセル名だけ旧のまま
  - トップセル名も旧のまま（提出済みなので変えない）
  - フレームは APRtools が解決（いまは `pdk/pending-upstream/`）
"""
import os

from config_base import *          # noqa: F401,F403

ROOT = os.path.dirname(os.path.abspath(__file__))

# ---- 設計の同定 ----------------------------------------------------------
TOP_CELL_NAME = "i2c_slave_async_nrow_fm"     # 提出済み。改名しない
CHIP_TOP_CELL = "tr_1um_jun1okamura_i2c"
NET_PATH = os.path.join(ROOT, "out", "i2c_slave_async_pnr.v")

# ---- 合成 / STA（`$APRTOOLS/syn/syn.sh` が読む）--------------------------
# 以前はこれらが `syn.sh` に直書きだった。TD4 と SCLK_SPI では回らない。
SYN_TOP = "i2c_slave_async"                   # コアの RTL のトップ（*_nrow_fm は剥がす）
SYN_RTL = [os.path.join(ROOT, "hdl", "rtl", "i2c_slave_async.v")]
# RTL が**セルを直接インスタンス化している**（NOR2 のクロス結合 SR ラッチ、
# MUX2 / NAND2 / INV_X1 / AND2_X1）。`.VDD`/`.GND` まで繋いで書いてあるので
# `--power`、クロス結合を iverilog で収束させるのに `--delay 1` が要る。
SYN_CELLS_V = os.path.join(ROOT, "hdl", "rtl", "tr1um_cells.v")
SYN_CELLS_GEN = True
SYN_CELLS_ARGS = ["--power", "--delay", "1"]
SYN_CELLS_IN_SYNTH = True                     # セルを論理まで展開して ABC に貼り直させる
SYN_BLACKBOX = ["RSLATCH"]                    # セルのまま残す（展開すると生ループに化ける）
SYN_TB_RTL = [os.path.join(ROOT, "hdl", "tb", "tb_i2c_slave_async.v")]
SYN_TB_NET = [os.path.join(ROOT, "hdl", "tb", "tb_i2c_slave_async_net.v")]
BUFTH_NETS = ["scl", "sda_in"]                # 外部プルアップで縁が鈍い 2 本
SYN_REF_NETLIST = os.path.join(ROOT, "reference", "v10",
                               "i2c_slave_async_net_v10_final.v")
STA_CLK_PORT = "scl"
STA_PERIOD_NS = 2500.0                        # Fast-mode 400 kHz
STA_FALSE_PATH_FROM = ["rst_n"]

# ---- フロアプラン --------------------------------------------------------
N_ROWS = 4
CORE_WIDTH_TRACKS = 296                       # x 5.4 = 1598.4（実績値）
CH_HEIGHTS = [140.4, 700.0, 1000.0, 700.0, 162.0]
NO_BOTTOM_PORTS = True                        # 下にロゴと RING_OSC を積むため

# ---- チップ側に載せるブロック --------------------------------------------
RING_OSC_ORIGIN = (-810.0, -650.0)
LOGO_GAP = 20.0
CORE_LOGO_GAP = 20.0

# ---- フレーム ------------------------------------------------------------
# **指定しない。** `config_base.pdk_frame_gds()` が解決する:
#   1. APR_FRAME_GDS  2. pdk/pending-upstream/…  3. PDK
# いまは 2（`OSS_DRV` の修正版。上流 PR がマージされたら 3 に戻る）。
# `docs/07_frame_issue.md`
FRAME_LEF = os.path.join(ROOT, "lef", "TR-1um_frame.lef")

# ---- 成果物の名前 --------------------------------------------------------
# `*_nrow_fm` は剥がした（`docs/04_naming.md` §2）。`config_base` の既定
# （`placement.json` / `pin_map*.json` / `net_shapes*.json` …）をそのまま使う。
LAYOUT = os.path.join(ROOT, "layout")

# ---- 配線の名指し（設計固有）--------------------------------------------
PER_ROW_LOCAL_NETS = set()            # 旧版は route.py が配置 JSON から作る

# ---- ボンドパッドの表（設計固有。U20 で config.py へ移した）--------------
# V10 の確定ピン表（README のピン配置表）。P8=VSS / P16=VDD はフレーム固定。
# 物理パッド番号の昇順と bit 番号が単調対応する（P3…P6 = bit0-3、P11…P14 = bit4-7）。
#
#   P     パッドの入力センス線 -> コアの入力ネット
#   OUT   コア（か RING_OSC）の出力ネット -> パッドのドライバ入力
#         "GND" と書いたらレール直結（SDA のオープンドレイン）
#   HIZ   "VDD" / "GND" はレール直結。それ以外は**ネット名**で、動的制御
PAD_MAP = {
    1:  {"role": "SCL",   "P": "scl",                                  "HIZ": "VDD"},
    2:  {"role": "SDA",   "P": "sda_in",    "OUT": "GND",              "HIZ": "sda_oe"},
    3:  {"role": "D0",    "P": "tx_data[0]", "OUT": "rx_data[0]",      "HIZ": "DIS"},
    4:  {"role": "D1",    "P": "tx_data[1]", "OUT": "rx_data[1]",      "HIZ": "DIS"},
    5:  {"role": "D2",    "P": "tx_data[2]", "OUT": "rx_data[2]",      "HIZ": "DIS"},
    6:  {"role": "D3",    "P": "tx_data[3]", "OUT": "rx_data[3]",      "HIZ": "DIS"},
    7:  {"role": "DIS",   "P": "DIS",                                  "HIZ": "VDD"},
    9:  {"role": "OSCD",  "OUT": "RING_OSC.OUTD",                      "HIZ": "GND"},
    10: {"role": "OSC",   "OUT": "RING_OSC.OUT",                       "HIZ": "GND"},
    11: {"role": "D4",    "P": "tx_data[4]", "OUT": "rx_data[4]",      "HIZ": "DIS"},
    12: {"role": "D5",    "P": "tx_data[5]", "OUT": "rx_data[5]",      "HIZ": "DIS"},
    13: {"role": "D6",    "P": "tx_data[6]", "OUT": "rx_data[6]",      "HIZ": "DIS"},
    14: {"role": "D7",    "P": "tx_data[7]", "OUT": "rx_data[7]",      "HIZ": "DIS"},
    15: {"role": "RSTN",  "P": ["rst_n", "RING_OSC.ENB"],              "HIZ": "VDD"},
}
# コアには出ているがパッドに繋がないもの（16 本に収まらない）
UNBONDED = {"addr_match", "busy", "rw", "rx_valid"}

# ---- 配置の再現（★ 提出した配置を作った値）------------------------------
# **引数も環境変数も無しで `place.py` を回して提出物が再現する**こと。
# 2026-09-15、`APR_PAD_WEIGHT=16` を export し忘れた 1 回が別の配置
# （cut 131 -> 88 / HPWL 142,391 -> 121,867 um）になった。数字としては
# 「良い」方へ動くので、**出力を見ても間違いだと気づけない**。
# 掃引したいときは環境変数（`APR_PAD_WEIGHT` / `APR_PLACE_SEED`）で上書きする。
PAD_WEIGHT = 16.0                     # パッド近接の重み（docs/21_flow_place.md §6）
PLACE_SEED = 4                        # 提出時の種。再現のため固定（U61 §7）

finalize(globals())

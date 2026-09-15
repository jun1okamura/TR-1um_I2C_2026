"""config.py -- TR-1um_I2C_2026 を APRtools で再現するための検証用設定。

**移行の手順 1「素通しで md5 一致を確認する」専用**（`docs/04_naming.md` §4）。
`~/Dropbox/98_LSI_Design/TR-1um_I2C_2026/config.py` に置いて使う。

    cd ~/Dropbox/98_LSI_Design/TR-1um_I2C_2026
    export TR1UM_PDK=~/Dropbox/91_OpenPDK/TR-1um
    export PYTHONHASHSEED=0                      # ★ ルータは非決定的
    APR=~/Dropbox/91_OpenPDK/TR-1um_APRtools
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

finalize(globals())

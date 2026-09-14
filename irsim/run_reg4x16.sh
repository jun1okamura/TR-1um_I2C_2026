#!/bin/sh
# REG4x16 全レジスタアクセス検証（IRSIM スイッチレベル）
#
#   ./irsim/run_reg4x16.sh            … 実行して合否まで表示
#   ./irsim/run_reg4x16.sh TR-1um.prm … .prm を指定
#   ./irsim/run_reg4x16.sh '' -v      … 全チェックを1行ずつ表示
#
# hdl/ 側の Verilog 版（sh hdl/run_reg4x16.sh）と同じベクタ・同じ期待値。
# Verilog 版は論理と接続、こちらは実 R/C モデルでの遅延を見る。
set -eu
cd "$(dirname "$0")/.."
PRM="${1:-irsim/TR-1um.prm}"
[ -n "$PRM" ] || PRM=irsim/TR-1um.prm
SIM=irsim/reg4x16.sim
LOG=irsim/reg4x16_run.log
VERBOSE="${2:-}"

# .sim が無い／ネットリストの方が新しければ作り直す
if [ ! -f "$SIM" ] || [ spice/REG4x16_src.spi -nt "$SIM" ]; then
  echo "generating $SIM from spice/REG4x16_src.spi" >&2
  python3 scripts/spi2sim.py spice/REG4x16_src.spi REG4x16 > "$SIM"
fi

echo "irsim $PRM $SIM  (irsim/reg4x16.cmd -> $LOG)" >&2
# NOTE: "-@ cmdfile" の CLI フラグは環境によって効かないので、
#       参照プロジェクト（TR-1um_Async_I2C）と同じく stdin の heredoc で渡す。
irsim "$PRM" "$SIM" > "$LOG" 2>&1 << 'EOT'
@ irsim/reg4x16.cmd
EOT

python3 scripts/check_irsim_log.py "$LOG" $VERBOSE

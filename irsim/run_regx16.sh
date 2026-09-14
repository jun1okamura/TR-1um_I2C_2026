#!/bin/sh
# REG4x16 / REG8x16 全レジスタアクセス検証（IRSIM スイッチレベル）
#
#   sh irsim/run_regx16.sh        … 4bit（既定）
#   sh irsim/run_regx16.sh 8      … 8bit
#   sh irsim/run_regx16.sh 8 -v   … 全チェックを1行ずつ表示
#
# hdl/ 側の Verilog 版（sh hdl/run_regx16.sh <bits>）と同じベクタ・同じ期待値。
# Verilog 版は論理と接続、こちらは実 R/C モデルでの遅延を見る。
set -eu
cd "$(dirname "$0")/.."
BITS="${1:-4}"
VERBOSE="${2:-}"
PRM=irsim/TR-1um.prm
TOP=REG${BITS}x16
SIM=irsim/reg${BITS}x16.sim
CMD=irsim/reg${BITS}x16.cmd
LOG=irsim/reg${BITS}x16_run.log
SRC=spice/${TOP}_src.spi

# .sim / .cmd が無い、または LVS ソースの方が新しければ作り直す
if [ ! -f "$SIM" ] || [ "$SRC" -nt "$SIM" ]; then
  echo "generating $SIM from $SRC" >&2
  python3 scripts/spi2sim.py "$SRC" "$TOP" > "$SIM"
fi
[ -f "$CMD" ] || python3 scripts/gen_irsim_cmd.py "$CMD" --bits "$BITS"

echo "irsim $PRM $SIM  ($CMD -> $LOG)" >&2
# NOTE: "-@ cmdfile" の CLI フラグは環境によって効かないので、
#       参照プロジェクト（TR-1um_Async_I2C）と同じく stdin の heredoc で渡す。
irsim "$PRM" "$SIM" > "$LOG" 2>&1 << EOT
@ $CMD
EOT

python3 scripts/check_irsim_log.py "$LOG" $VERBOSE

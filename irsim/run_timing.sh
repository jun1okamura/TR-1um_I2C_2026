#!/bin/sh
# REG4x16 タイミング測定（読出アクセス時間 / 書込レイテンシ / 最小 WEB パルス幅）
set -eu
cd "$(dirname "$0")/.."
PRM="${1:-irsim/TR-1um.prm}"
SIM=irsim/reg4x16.sim
LOG=irsim/reg4x16_timing_run.log

if [ ! -f "$SIM" ] || [ spice/REG4x16_src.spi -nt "$SIM" ]; then
  python3 scripts/spi2sim.py spice/REG4x16_src.spi REG4x16 > "$SIM"
fi

echo "irsim $PRM $SIM  (irsim/reg4x16_timing.cmd -> $LOG)" >&2
irsim "$PRM" "$SIM" > "$LOG" 2>&1 << 'EOT'
@ irsim/reg4x16_timing.cmd
EOT

python3 scripts/check_irsim_timing.py "$LOG"

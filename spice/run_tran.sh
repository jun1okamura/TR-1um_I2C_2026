#!/bin/sh
# REG4x16 / REG8x16 タイミング確認（ngspice, 実デバイスモデル, 0.1ns 刻み）
#
#   sh spice/run_tran.sh              … 4bit, CBL = 0/50/100/200 fF
#   sh spice/run_tran.sh 8            … 8bit, 同上
#   sh spice/run_tran.sh 8 "0 200"    … 掃引する CBL を指定
#
# 配線容量はネットリストに入っていないので集中容量として外付けし、
# 遅延がどれだけ効くかを掃引で見る。CBL=0 が IRSIM と同じ条件。
# 8bit は 1,876 Tr あるので 1 点あたり数分〜十数分かかる。
set -eu
cd "$(dirname "$0")/.."
BITS="${1:-4}"
LIST="${2:-0 50 100 200}"
MODELS="${MODELS:-${TR1UM_PDK:-$HOME/TR-1um}/libs.tech/spice/models/ip62_models}"
TOP=REG${BITS}x16
SRC=spice/${TOP}_src.spi
NET=spice/${TOP}_ngspice.spi

# LVS ソースが新しければ ngspice 用ネットリストを作り直す
if [ ! -f "$NET" ] || [ "$SRC" -nt "$NET" ]; then
  echo "generating $NET" >&2
  python3 scripts/spi2ngspice.py "$SRC" > "$NET"
fi

LOGS=""
for c in $LIST; do
  DECK=spice/${TOP}_tran_$c.spi
  LOG=spice/${TOP}_tran_$c.log
  python3 scripts/gen_ngspice_tran.py "$c" "$DECK" "$MODELS" "$NET" "$BITS"
  echo "ngspice -b $DECK  -> $LOG" >&2
  ngspice -b "$DECK" > "$LOG" 2>&1
  LOGS="$LOGS $LOG"
done
python3 scripts/check_ngspice.py tran $LOGS

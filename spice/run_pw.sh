#!/bin/sh
# REG4x16 最小 WEB パルス幅（ngspice, 0.1ns 刻み）
#
#   sh spice/run_pw.sh                    … CBL=100fF, 幅 2,4,6,10,16,24 ns
#   sh spice/run_pw.sh 100 6,7,8,9,10,12  … 幅を細かく刻む
set -eu
cd "$(dirname "$0")/.."
MODELS="${MODELS:-$HOME/Dropbox/91_OpenPDK/TR-1um/libs.tech/spice/models/ip62_models}"
NET=spice/REG4x16_ngspice.spi
CBL="${1:-100}"
PWS="${2:-2,4,6,10,16,24}"

if [ ! -f "$NET" ] || [ spice/REG4x16_src.spi -nt "$NET" ]; then
  python3 scripts/spi2ngspice.py spice/REG4x16_src.spi > "$NET"
fi

DECK=spice/REG4x16_pw_$CBL.spi
LOG=spice/REG4x16_pw_$CBL.log
python3 scripts/gen_ngspice_pw.py "$CBL" "$DECK" "$MODELS" "$NET" "$PWS"
echo "ngspice -b $DECK  -> $LOG" >&2
ngspice -b "$DECK" > "$LOG" 2>&1
python3 scripts/check_ngspice.py pw "$LOG"

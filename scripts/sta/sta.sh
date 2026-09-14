#!/bin/sh
# OpenSTA を当てる。
#   usage: sh scripts/sta/sta.sh <netlist> <top> <period_ns> [report.tcl]
#          sh scripts/sta/sta.sh out/td4_soc_arr.v td4_soc_arr 100
#
# OpenSTA 本体はこのリポジトリには入っていない。ビルド手順は scripts/sta/README.md。
# $STA で実行ファイルを指定できる（既定は PATH の `sta`）。
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
NET=$1; TOP=$2; PER=$3; RPT=${4:-$HERE/report.tcl}
[ -n "$PER" ] || { echo "usage: $0 <netlist> <top> <period_ns> [report.tcl]" >&2; exit 1; }
STA=${STA:-sta}
command -v "$STA" >/dev/null 2>&1 || { echo "$STA が無い。scripts/sta/README.md を見てください" >&2; exit 1; }
T=$(mktemp "${TMPDIR:-/tmp}/sta_XXXXXX.tcl")
{ echo "set NET $NET"; echo "set TOP $TOP"; echo "set PER $PER"
  echo "set HERE $HERE"; cat "$HERE/setup.tcl"; cat "$RPT"; } > "$T"
"$STA" -no_splash -exit "$T"
rm -f "$T"

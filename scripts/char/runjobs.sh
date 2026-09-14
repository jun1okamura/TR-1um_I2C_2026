#!/bin/bash
# 生成済みデッキを手元の機械で並列に流し、.meas の結果だけを 1 ファイルに集める。
#
#   usage: ./runjobs.sh [-j 並列数] [-m モデルのディレクトリ] [-p pack ディレクトリ]
#
# 出力は <pack>/results.txt の 1 本だけ。1 行が `タグ 測定名 値`。
# ログ本体は残さないので、14000 本流しても数 MB で済む。
#
# 途中で止めてもよい。既に結果のあるデッキは飛ばすので、もう一度叩けば続きから走る。
#
# 注意: ngspice は 1 プロセスで複数スレッドを使おうとする。コア数を超えると
# バリアのスピン待ちで極端に遅くなる（クラウド 2 コアで実測 50 倍）ので、
# 1 プロセス 1 スレッドに固定して、プロセスの数で並べる。
set -u

HERE="$(cd "$(dirname "$0")" && pwd)"
PACK="$HERE/pack"
MODELS="$HERE/models"
NGSPICE="${NGSPICE:-ngspice}"
J=""

while getopts "j:m:p:h" o; do
  case "$o" in
    j) J="$OPTARG" ;;
    m) MODELS="$OPTARG" ;;
    p) PACK="$OPTARG" ;;
    h) sed -n '2,12p' "$0"; exit 0 ;;
    *) exit 2 ;;
  esac
done

# 並列数の既定値: 物理コア数
if [ -z "$J" ]; then
  J=$(sysctl -n hw.physicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)
fi

DECKS="$PACK/decks"
OUT="$PACK/out"
RES="$PACK/results.txt"

[ -d "$DECKS" ] || { echo "デッキが無い: $DECKS  先に python3 genjobs.py を流してください" >&2; exit 1; }
[ -f "$MODELS/ip62_models" ] || { echo "モデルが無い: $MODELS/ip62_models  -m で指定してください" >&2; exit 1; }
command -v "$NGSPICE" >/dev/null || { echo "ngspice が見つからない（NGSPICE=... で指定できます）" >&2; exit 1; }

MODELS="$(cd "$MODELS" && pwd)"
DECKS="$(cd "$DECKS" && pwd)"
PACK="$(cd "$PACK" && pwd)"
OUT="$PACK/out"; RES="$PACK/results.txt"
mkdir -p "$OUT"

# ngspice の OpenMP スレッド数を 1 に固定する。
# 環境変数（OMP_NUM_THREADS）では効かず、.spiceinit の set num_threads だけが効く。
# 1 プロセス複数スレッドでコア数を超えると、バリアのスピン待ちで桁違いに遅くなる。
printf 'set num_threads=1\n' > "$PACK/.spiceinit"
cd "$PACK"       # ngspice はカレントの .spiceinit を読む

N=$(find "$DECKS" -name '*.spi' | wc -l | tr -d ' ')
echo "デッキ $N 本 / 並列 $J / モデル $MODELS"
echo "$("$NGSPICE" -v 2>&1 | head -1)"

# --- デッキ中のモデルのパスを実機のものに置き換える -------------------------
# genjobs.py は移植できるよう __MODELS__ というプレースホルダで書いている。
echo "モデルのパスを埋めています..."
find "$DECKS" -name '*.spi' -print0 \
  | MODELS="$MODELS" xargs -0 -n 400 -P "$J" perl -pi -e 's{__MODELS__}{$ENV{MODELS}}g'

# --- 1 本走らせる -----------------------------------------------------------
run_one() {
  d="$1"
  t="$(basename "$d" .spi)"
  o="$OUT/$t.out"
  [ -s "$o" ] && return 0           # もう結果がある（再開時）
  log="$("$NGSPICE" -b "$d" 2>&1)"
  rc=$?
  printf '%s\n' "$log" | awk -v t="$t" -v rc="$rc" '
    {
      i = index($0, "=")
      if (i > 0) {
        n = substr($0, 1, i - 1)
        gsub(/[ \t]/, "", n)
        if (n ~ /^[a-z][a-zA-Z0-9_]*$/) {
          split(substr($0, i + 1), a, " ")
          if (a[1] ~ /^[-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?$/)
            print t, n, a[1]
        }
      }
    }
    END { if (rc != 0) print t, "__rc", rc }' > "$o.tmp"
  mv "$o.tmp" "$o"
}
export -f run_one
export NGSPICE OUT

# --- 進捗 -------------------------------------------------------------------
t0=$(date +%s)
(
  while :; do
    sleep 20
    c=$(find "$OUT" -name '*.out' 2>/dev/null | wc -l | tr -d ' ')
    [ "$c" -ge "$N" ] && break
    el=$(( $(date +%s) - t0 ))
    [ "$el" -eq 0 ] && el=1
    r=$(( c / el ))
    left="?"
    [ "$r" -gt 0 ] && left=$(( (N - c) / r / 60 ))
    printf '  %6d / %d  (%d 本/秒, 残り約 %s 分)\n' "$c" "$N" "$r" "$left"
  done
) &
PROG=$!

# -n 1 で 1 本ずつ渡す。-I{} は BSD xargs だと -P が効かないことがあるので使わない。
find "$DECKS" -name '*.spi' -print0 \
  | xargs -0 -n 1 -P "$J" bash -c 'run_one "$0"'

kill "$PROG" 2>/dev/null; wait "$PROG" 2>/dev/null

# --- 回収 -------------------------------------------------------------------
find "$OUT" -name '*.out' -exec cat {} + > "$RES"
el=$(( $(date +%s) - t0 ))
nl=$(wc -l < "$RES" | tr -d ' ')
nrc=$(grep -c ' __rc ' "$RES" 2>/dev/null); nrc=${nrc:-0}
echo "----------------------------------------------------------------"
echo "所要 $((el / 60)) 分 $((el % 60)) 秒 / 測定値 $nl 行 -> $RES"
if [ "$nrc" -gt 0 ]; then
  echo "** ngspice が異常終了したデッキ $nrc 本（collect.py が該当点を空として扱います）"
fi
echo "この results.txt を Claude に渡してください。"
exit 0

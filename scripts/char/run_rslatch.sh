#!/bin/bash
# RSLATCH を ngspice で特性化して lef/tr1um_typ_5v0_25c.lib に足す。
#
#   usage: cd scripts/char && ./run_rslatch.sh [-j 並列数] [-m モデルのディレクトリ]
#
# Mac（ngspice がある機械）で流す前提。デッキは 250 本ほどなので
# 18 コアなら 1 分かからない。
#
# 何をするか:
#   1. lef/extracted/RSLATCH.extracted -> cells_ext/RSLATCH.spi（無ければ）
#   2. char_latch.py gen      デッキを pack_rslatch/decks/ に書き出す
#   3. runjobs.sh             並列に流して pack_rslatch/results.txt に集める
#   4. char_latch.py collect  char/RSLATCH.json を作り、格子の外で検算する
#   4.5 calib_cap.py          入力容量を遅延計算に使える等価容量へ較正する
#   5. mklib.py               char/*.json から .lib を作り直す（RSLATCH が増える）
#   6. verify_lib.py          .lib の検算
#
# 途中で止めても、もう一度叩けば続きから走る（結果のあるデッキは飛ばす）。
# やり直したいときは pack_rslatch/ を消してください。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

PACK="$HERE/pack_rslatch"
LIB="$HERE/../../lef/tr1um_typ_5v0_25c.lib"
MODELS="$HERE/models"
J=""
while getopts "j:m:h" o; do
  case "$o" in
    j) J="$OPTARG" ;;
    m) MODELS="$OPTARG" ;;
    h) sed -n '2,20p' "$0"; exit 0 ;;
    *) exit 2 ;;
  esac
done
[ -n "$J" ] || J=$(sysctl -n hw.physicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)

say() { printf '\n\033[1m===== %s\033[0m\n' "$*"; }
die() { printf '** %s\n' "$*" >&2; exit 1; }

command -v ngspice >/dev/null || die "ngspice が無い。brew install ngspice"
command -v python3 >/dev/null || die "python3 が無い"
[ -f "$MODELS/ip62_models" ] || die "モデルが無い: $MODELS/ip62_models（-m で指定できます）"
[ -f "$LIB" ] || die "元の .lib が無い: $LIB"

say "0. セルの SPICE ネットリスト"
if [ ! -f "$HERE/cells_ext/RSLATCH.spi" ]; then
  python3 loadext.py ../../lef/extracted -o cells_ext || die "loadext.py に失敗"
fi
grep -q '^\.SUBCKT RSLATCH' "$HERE/cells_ext/RSLATCH.spi" \
  || die "cells_ext/RSLATCH.spi が壊れている"
echo "  cells_ext/RSLATCH.spi: $(grep -c '^XM' "$HERE/cells_ext/RSLATCH.spi") 素子"

say "1. デッキ生成"
python3 char_latch.py gen -o "$PACK" || die "デッキ生成に失敗"

say "2. ngspice（並列 $J）"
./runjobs.sh -j "$J" -m "$MODELS" -p "$PACK" || die "ngspice の実行に失敗"

say "3. 回収と検算"
python3 char_latch.py collect -p "$PACK"
RC=$?

say "3.5 入力容量の較正（INV_X1 で N 個駆動して逆引き）"
# 電荷から出した容量はミラー分を含み遅延計算には過大。組合せセルと同じ較正を掛ける。
mkdir -p "$HERE/decks" "$HERE/logs"
python3 calib_cap.py RSLATCH || die "calib_cap.py に失敗"

say "4. .lib の作り直し"
cp -f "$LIB" "$LIB.bak"
python3 mklib.py -o "$LIB" || die "mklib.py に失敗"
# RSLATCH 以外が変わっていないことを確かめる。**ここが変わるのは異常。**
python3 - "$LIB.bak" "$LIB" <<'PY'
import re, sys
def cells(p):
    s, out, depth, cur, buf = open(p).read(), {}, 0, None, []
    for ln in s.splitlines():
        m = re.match(r"\s*cell \((\w+)\) \{", ln)
        if m and cur is None:
            cur, depth, buf = m.group(1), 1, [ln]; continue
        if cur is not None:
            buf.append(ln); depth += ln.count("{") - ln.count("}")
            if depth == 0:
                out[cur] = "\n".join(buf); cur = None
    return out
a, b = cells(sys.argv[1]), cells(sys.argv[2])
added = sorted(set(b) - set(a)); removed = sorted(set(a) - set(b))
changed = sorted(c for c in set(a) & set(b) if a[c] != b[c])
print(f"  セル {len(a)} -> {len(b)}")
print(f"  増えた: {', '.join(added) or 'なし'}")
if removed: print(f"  ** 消えた: {', '.join(removed)}")
if changed: print(f"  ** 中身が変わった: {', '.join(changed)}（RSLATCH 以外が変わるのは異常）")
sys.exit(1 if removed or changed else 0)
PY
[ $? -eq 0 ] || echo "  ** 差分を確認してください（元は $LIB.bak）"

say "5. .lib の検算"
python3 verify_lib.py "$LIB"

say "できたもの"
echo "  char/RSLATCH.json"
echo "  $LIB   （元は $LIB.bak）"
echo
echo "RSLATCH のアーク:"
awk '/^  cell \(RSLATCH\)/,/^  }$/' "$LIB" \
  | grep -E "timing_type|related_pin|capacitance :|area :|preset|clear" | sed 's/^/  /'
exit $RC

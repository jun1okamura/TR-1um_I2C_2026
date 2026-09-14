#!/bin/sh
# Async I2C / TR-1um: 合成 → 実セルへのマッピング → 後処理 → 検証 → 面積 → STA
# usage: sh scripts/syn.sh          (リポジトリルートで)
#
# TR-1um_TD4 の scripts/syn.sh を I2C 用に書き換えたもの。TD4 との違い:
#
#   * RTL が**セルを直接インスタンス化している**（NOR2 でクロス結合の SR ラッチ、
#     MUX2、NAND2、INV_X1、AND2_X1）。`.VDD`/`.GND` まで繋いで書いてあるので、
#     セルモデルは `--power` 付きで生成する。SR ラッチのループを iverilog で
#     収束させるため `--delay 1` も要る。
#   * **合成後に 2 段の後処理が入る**（TR-1um_Async_I2C から移植）:
#       dedup_gates.py             ABC が撒いた重複ゲートを 1 個にまとめる
#       merge_muxdffrb_rslatch.py  MUX2+DFFRB -> MUXDFFRB、
#                                  クロス結合 NOR2 対 -> RSLATCH
#     どちらも V10 で実績のある変換。dedup は**必ず最初に**通すこと
#     （design_notes 108.37: 飛ばすと配線が詰まる真の原因になる）。
#   * TD4 のメモリマクロ差し替え（mem_wrap.py）と面積比較（mem_array_estimate.py）
#     は無い。
#   * 行バッファ挿入（insert_row_buffers.py）はここには入れない。**配置と
#     結びついている**ので P&R 側（STEP 3）で扱う。
set -e
LIB=lef/tr1um_typ_5v0_25c.lib
CONSTR=scripts/abc.constr
CELLS=hdl/rtl/tr1um_cells.v
RTL="hdl/rtl/i2c_slave_async.v"
TOP=i2c_slave_async
PER=${PER:-2500}          # STA の周期 [ns]。既定は I2C Fast-mode 400 kHz
mkdir -p out

LOG=out/SYN_RESULTS.txt
if [ -z "${SYN_TEE:-}" ]; then
  SYN_TEE=1; export SYN_TEE
  sh "$0" "$@" 2>&1 | tee "$LOG"
  tail -1 "$LOG" | grep -q '^完了' || {
    echo "** 途中で止まった。$LOG を見てください" >&2; exit 1; }
  exit 0
fi

[ -f "$LIB" ] || { echo "$LIB が無い。scripts/char/RUN.md の手順で作ってください" >&2; exit 1; }
grep -q "cell (RSLATCH)" "$LIB" || {
  echo "** $LIB に RSLATCH が無い。scripts/char/run_rslatch.sh を先に流してください" >&2
  exit 1; }

# --- Yosys を探す（TD4 の syn.sh と同じ） -----------------------------------
find_yosys() {
  for c in $YOSYS yowasp-yosys yosys; do
    [ -n "$c" ] && command -v "$c" >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  for d in "$HOME/.local/bin" "$HOME/Library/Python"/*/bin /opt/homebrew/bin \
           /usr/local/bin "$HOME/.pyenv/shims"; do
    for c in yowasp-yosys yosys; do
      [ -x "$d/$c" ] && { echo "$d/$c"; return 0; }
    done
  done
  if python3 -c "import yowasp_yosys" >/dev/null 2>&1; then
    W="${TMPDIR:-/tmp}/tr1um-yowasp-yosys"
    printf '#!/bin/sh\nexec python3 -c %s "$@"\n' \
      "'import sys,yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))'" > "$W"
    chmod +x "$W"
    echo "$W"; return 0
  fi
  return 1
}
YS=$(find_yosys) || {
  echo "Yosys が見つからない。次のどれかをしてください:" >&2
  echo "  pip3 install yowasp-yosys        (または brew install yosys)" >&2
  echo "  YOSYS=/path/to/yosys sh scripts/syn.sh" >&2
  exit 1; }
echo "Yosys: $YS  ($($YS -V 2>&1 | head -1))"
command -v iverilog >/dev/null 2>&1 || echo "** iverilog が無いので段 1 と段 5 を飛ばします"
echo "ABC 制約: $(tr '\n' ' ' < $CONSTR)"

echo
echo "##################### 0. セルの Verilog モデルを生成"
# cellspec.py（ngspice で実レイアウトと突き合わせ済み）から起こす。
#   --power  RTL が .VDD/.GND まで繋いでいるので電源ピンを持たせる
#   --delay  クロス結合 NOR2 を iverilog で収束させる単位遅延
python3 scripts/char/mkcellverilog.py --power --delay 1 -o $CELLS

echo
echo "##################### 1. RTL の機能検証"
if command -v iverilog >/dev/null 2>&1; then
  iverilog -g2012 -o /tmp/i2c_tb_rtl.vvp hdl/tb/tb_i2c_slave_async.v $RTL $CELLS
  vvp /tmp/i2c_tb_rtl.vvp | grep -E "PASS|FAIL|OK:|NG:" | tail -5
else
  echo "  iverilog が無いので飛ばす"
fi

echo
echo "##################### 2. 合成 → 実セルへマッピング"
# セルモデルは **ライブラリ (-lib) ではなく普通の Verilog として**読む。
# RTL のクロス結合 NOR2 を論理まで展開し、ABC に貼り直させるため。
# -lib で読むとブラックボックスのまま残り、後段の merge が効かない。
# `blackbox RSLATCH` は RSLATCH を**セルのまま残す**ための指定。これが無いと
# tr1um_cells.v の振る舞いモデルが展開され、ABC が入力ゲートごと吸収して
# NOR3/NAND3 の生ループに化ける（RTL が RSLATCH を使っていない場合は無害）。
$YS -p "read_verilog $CELLS $RTL; blackbox RSLATCH; hierarchy -check -top $TOP; \
        synth -top $TOP -flatten; \
        dfflibmap -liberty $LIB; abc -liberty $LIB -constr $CONSTR; opt_clean; \
        write_verilog -noattr out/$TOP.v; tee -o out/$TOP.stat stat -liberty $LIB" \
    > out/$TOP.synlog 2>&1 || { echo "** 合成に失敗"; tail -30 out/$TOP.synlog; exit 1; }
grep -iE "combinational loop|warning: found" out/$TOP.synlog | sort -u | head -5
if grep -qE '^\s+\$_[A-Z]' out/$TOP.stat; then
  echo "** マップできていないセルが残っている"; grep -E '^\s+\$_[A-Z]' out/$TOP.stat
fi
NT=$(grep -cE "\.[A-Z]+\(1'[hb][01]\)" out/$TOP.v || true)
python3 scripts/syn_report.py $TOP --brief
[ "$NT" = 0 ] || echo "    ** 定数に繋がったセル入力ピンが $NT 個ある（TIEHI/TIELO が要る）"

echo
echo "##################### 3. 重複ゲートの整理（dedup_gates.py）"
# **必ずここで通す。** ABC は同じ入力に繋がった同じセルを何個も撒くことがあり、
# それが配線の混雑と短絡の真の原因になる（design_notes 108.37）。
python3 scripts/dedup_gates.py out/$TOP.v out/${TOP}_dedup.v

echo
echo "##################### 4. MUXDFFRB / RSLATCH への畳み込み"
#   MUX2 -> DFFRB.D（単一ファンアウト）      -> MUXDFFRB 1 個
#   クロス結合 NOR2 対                        -> RSLATCH 1 個
python3 scripts/merge_muxdffrb_rslatch.py --in out/${TOP}_dedup.v --out out/${TOP}_merged.v

echo
echo "##################### 5. ゲートレベル TB（畳み込み後）"
if command -v iverilog >/dev/null 2>&1; then
  iverilog -g2012 -o /tmp/i2c_tb_net.vvp hdl/tb/tb_i2c_slave_async_net.v \
           out/${TOP}_merged.v $CELLS
  vvp /tmp/i2c_tb_net.vvp | grep -E "PASS|FAIL|OK:|NG:" | tail -5
else
  echo "  iverilog が無いので飛ばす"
fi

echo
echo "##################### 6. BUFTH で外部入力を受ける"
# OSS_ESD_5V_DIO には入力バッファが無く、PAD の 4.8 pF を外部ドライバが直接振る。
# I2C は 10k の外部プルアップで受動的に立ち上がるので縁が特に鈍い（実測 15-20ns）。
# BUFTH は立上り 3.71V / 立下り 1.20V（ヒステリシス 2.51V）。
python3 scripts/insert_bufth.py out/${TOP}_merged.v out/${TOP}_pnr.v --nets scl,sda_in
python3 scripts/syn_report.py $TOP -n out/${TOP}_pnr.v --brief

echo
echo "##################### 7. 面積と使用率"
python3 scripts/syn_report.py $TOP -n out/${TOP}_pnr.v

echo
echo "##################### 8. V10（テープアウト実績）との突き合わせ"
python3 scripts/cmp_cells.py reference/v10/i2c_slave_async_net_v10_final.v out/${TOP}_pnr.v

echo
echo "##################### 9. STA"
if command -v "${STA:-sta}" >/dev/null 2>&1; then
  # **必ず merge 後のネットリストに当てる。** 畳み込み前は NOR2 のクロス結合が
  # 生のループとして残っていて、OpenSTA が勝手にアークを 1 本切る。
  sh scripts/sta/sta.sh out/${TOP}_pnr.v $TOP $PER 2>&1 | grep -vE "Warning (1210|503)"
else
  echo "  OpenSTA が無いので飛ばす（scripts/sta/README.md にビルド手順）"
fi

echo
echo "完了"

#!/bin/sh
# TD4 / TR-1um: 合成 → 実セルへのマッピング → 等価性検証 → 面積
# usage: sh scripts/syn.sh [top ...]   (リポジトリルートで)
#
# **`abc -g simple` から `.lib` での実マッピングに切り替えた。**
#   旧: 抽象ゲート（$_AND_ など）に落として area_estimate.py で面積を**概算**。
#       ライブラリに無い $_ANDNOT_ / $_ORNOT_ が出ても読み替えでごまかせた。
#   新: `dfflibmap` + `abc -liberty` で**実セルのネットリスト**を作る。
#       これがそのまま P&R の入力になるので、面積は概算ではなく実数になり、
#       代わりに「RTL と本当に同じか」を確かめる必要が出た（段 3・段 4）。
#
# 検証の鎖:
#   RTL  ≡ マップ後ネットリスト   段 3（形式等価）と段 4（ゲートレベル TB）
#   セルモデル ≡ レイアウト        scripts/char/check_comb.py ほか（ngspice）
#   どちらも出どころは scripts/char/cellspec.py の 1 箇所。
set -e
LIB=lef/tr1um_typ_5v0_25c.lib
# ABC に駆動元と負荷を教えるファイル。**これが無いと ABC はタイミングを見ない。**
# Yosys の abc パスは -constr があるときだけ ABC のスクリプトを
#   ... &nf {D}; &put; buffer; upsize {D}; dnsize {D}; stime -p
# というゲートサイジング付きの版に切り替える。付けないと buffer/upsize/dnsize が
# 走らず、面積だけで貼った netlist になる。td4_soc_arr の reg->reg 所要周期で
# 85.0ns -> 63.9ns（-25%）、面積は +3.3%。OpenSTA で実測（scripts/sta/）。
CONSTR=scripts/abc.constr
CELLS=hdl/rtl/tr1um_cells.v
RTL="hdl/rtl/td4_core.v hdl/rtl/td4_mem.v hdl/rtl/td4_soc_rom.v \
     hdl/rtl/td4_soc_ff.v hdl/rtl/td4_soc_arr.v"
TOPS=${*:-"td4_core td4_soc_rom td4_soc_ff td4_soc_arr"}
mkdir -p out

# 実行ログを out/SYN_RESULTS.txt に残す。**手で tee するのを忘れると、
# out/*.v と out/SYN_RESULTS.txt が別々の実行のものになる。**
# 実際に一度そうなり、td4_core が 102 セルと 94 セルで食い違って見えた。
LOG=out/SYN_RESULTS.txt
if [ -z "${SYN_TEE:-}" ]; then
  SYN_TEE=1; export SYN_TEE
  sh "$0" "$@" 2>&1 | tee "$LOG"
  tail -1 "$LOG" | grep -q '^完了' || {
    echo "** 途中で止まった。$LOG を見てください" >&2; exit 1; }
  exit 0
fi

[ -f "$LIB" ] || { echo "$LIB が無い。scripts/char/RUN.md の手順で作ってください" >&2; exit 1; }
[ -f "$CONSTR" ] || { echo "$CONSTR が無い" >&2; exit 1; }

# --- Yosys を探す -----------------------------------------------------------
# `sh scripts/syn.sh` は対話シェルの設定（.zshrc など）を読まないので、
# pip --user や pipx で入れた yowasp-yosys が PATH に無いことがある。
# 実行ファイルが見つからなければ Python モジュールから直接呼ぶ。
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
    W="${TMPDIR:-/tmp}/tr1um-yowasp-yosys"      # リポジトリの外に置く
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
  exit 1
}
echo "Yosys: $YS  ($($YS -V 2>&1 | head -1))"
command -v iverilog >/dev/null 2>&1 || echo "** iverilog が無いので段 1 と段 4 を飛ばします"

echo "ABC 制約: $(tr '\n' ' ' < $CONSTR)"
echo
echo "##################### 0. セルの Verilog モデルを生成"
# cellspec.py（ngspice で実レイアウトと突き合わせ済み）から起こす。
python3 scripts/char/mkcellverilog.py -o $CELLS

echo
echo "##################### 1. RTL の機能検証"
if command -v iverilog >/dev/null 2>&1; then
  iverilog -g2012 -o /tmp/td4_tb1.vvp hdl/tb/tb_td4_core.v hdl/rtl/td4_core.v
  vvp /tmp/td4_tb1.vvp | tail -2
  iverilog -g2012 -o /tmp/td4_tb2.vvp hdl/tb/tb_td4_soc_arr.v \
           hdl/rtl/td4_soc_arr.v hdl/rtl/td4_mem.v hdl/rtl/td4_core.v
  vvp /tmp/td4_tb2.vvp | tail -2
else
  echo "  iverilog が無いので飛ばす"
fi

echo
echo "##################### 2. 合成 → 実セルへマッピング"
for T in $TOPS; do
  # dfflibmap が FF を、abc -liberty が組合せ論理を、それぞれ .lib のセルに割り当てる。
  # .lib の dont_use（FILL / TAP）は ABC 側で自動的に外れる。
  $YS -p "read_verilog $RTL; hierarchy -check -top $T; synth -top $T -flatten; \
          dfflibmap -liberty $LIB; abc -liberty $LIB -constr $CONSTR; opt_clean; \
          write_verilog -noattr out/$T.v; tee -o out/$T.stat stat -liberty $LIB" \
      > out/$T.synlog 2>&1 || { echo "** $T: 合成に失敗"; tail -20 out/$T.synlog; exit 1; }
  # ライブラリに無いセル（$_ で始まる Yosys 内部セル）が残っていないか
  if grep -qE '^\s+\$_[A-Z]' out/$T.stat; then
    echo "** $T: マップできていないセルが残っている"; grep -E '^\s+\$_[A-Z]' out/$T.stat
  fi
  # セル数と面積はネットリストから数える（Yosys の stat の書式はバージョンで変わる）
  # 定数に繋がったセル入力があれば TIEHI / TIELO が要る
  NT=$(grep -cE "\.[A-Z]+\(1'[hb][01]\)" out/$T.v || true)
  python3 scripts/syn_report.py $T --brief
  [ "$NT" = 0 ] || echo "    ** 定数に繋がったセル入力ピンが $NT 個ある（TIEHI/TIELO が要る）"
done

echo
echo "##################### 3. 形式等価（RTL ⇔ マップ後）"
for T in $TOPS; do
  YOSYS=$YS python3 scripts/syn_equiv.py $T -r "$RTL" || true
done

echo
echo "##################### 4. マップ後ネットリストでの TB"
if command -v iverilog >/dev/null 2>&1; then
  for P in "tb_td4_core td4_core" "tb_td4_soc_arr td4_soc_arr"; do
    set -- $P
    if [ -f out/$2.v ]; then
      iverilog -g2012 -o /tmp/g_$2.vvp hdl/tb/$1.v out/$2.v $CELLS
      echo "  $2: $(vvp /tmp/g_$2.vvp | grep -E 'PASSED|FAIL' | tail -1)"
    fi
  done
fi

echo
echo "##################### 5. 面積と使用率"
for T in $TOPS; do
  python3 scripts/syn_report.py $T
  echo
done

echo "##################### 6. td4_mem をブラックボックス化した周辺ロジック"
$YS -p "read_verilog $RTL; blackbox td4_mem; hierarchy -check -top td4_soc_arr; \
        synth -top td4_soc_arr -flatten; dfflibmap -liberty $LIB; abc -liberty $LIB -constr $CONSTR; \
        opt_clean; write_verilog -noattr out/td4_soc_arr_bb.v; \
        tee -o out/td4_soc_arr_bb.stat stat -liberty $LIB" > out/arr_bb.synlog 2>&1 \
  || { echo "** ブラックボックス版の合成に失敗"; tail -20 out/arr_bb.synlog; exit 1; }
python3 scripts/syn_report.py td4_soc_arr_bb -n out/td4_soc_arr_bb.v

echo
echo "##################### 6.5 REG8x16 マクロへの差し替え（P&R 入力）"
# RTL の td4_mem と実物の REG8x16 はピン互換ではない。グルーを入れて差し替える。
python3 scripts/mem_wrap.py out/td4_soc_arr_bb.v -o out/td4_soc_arr_mw.v

# 外部入力 9 本をシュミット (BUFTH) で受ける。OSS_ESD_5V_DIO には入力バッファが
# 入っておらず、PAD の 4.8 pF を外部ドライバが直接振る。鈍った波形をそのまま
# 各段に配ると貫通電流が増え、CLK/RSTN にチャタリングが乗れば誤動作する。
# BUFTH は立上り 3.71V / 立下り 1.20V（ヒステリシス 2.51V）。
python3 scripts/insert_bufth.py out/td4_soc_arr_mw.v out/td4_soc_arr_pnr.v
python3 scripts/syn_report.py td4_soc_arr -n out/td4_soc_arr_pnr.v --brief
if command -v iverilog >/dev/null 2>&1; then
  iverilog -g2012 -o /tmp/g_pnr.vvp hdl/tb/tb_td4_soc_arr.v out/td4_soc_arr_pnr.v \
           $CELLS hdl/rtl/reg8x16.v
  echo "  差し替え後の TB: $(vvp /tmp/g_pnr.vvp | grep -E 'PASSED|FAIL' | tail -1)"
fi

echo
echo "##################### 7. 命令メモリ カスタムアレイ化の効果"
python3 scripts/mem_array_estimate.py

echo
echo "##################### 8. STA（OpenSTA があれば）"
if command -v "${STA:-sta}" >/dev/null 2>&1; then
  for T in $TOPS; do
    sh scripts/sta/sta.sh out/$T.v $T 100 2>&1 | grep -vE "Warning (1210|503)"
  done
  # P&R に入れるのはこれ。REG8x16 を通るパスが見える唯一の版
  [ -f out/td4_soc_arr_pnr.v ] && \
    sh scripts/sta/sta.sh out/td4_soc_arr_pnr.v td4_soc_arr 100 2>&1 \
      | grep -vE "Warning (1210|503)"
else
  echo "  OpenSTA が無いので飛ばす（scripts/sta/README.md にビルド手順）"
fi

echo
echo "完了"

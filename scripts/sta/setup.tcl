# 読み込みと制約。sta.sh が NET / TOP / PER を先頭で定義してから連結する。
#
# **このコアはクロックレス（非同期）**。フリップフロップは
#   scl_gated (= scl & 有効条件)  posedge
#   scl_n     (= ~scl)            posedge  ← scl の立下り
# の 2 つで叩かれる。どちらも scl から組合せ回路で作られるので、
# **scl ポートに create_clock を 1 本置けば、そこから先はクロックネットワークとして
# 自動で伝播する**（AND で削られた枝も、INV で反転した枝も）。
# create_generated_clock は要らない。分周も位相調整もしていないし、
# 合成後のインスタンス名（_385_ のような自動名）に制約を貼ると、
# 再合成のたびに剥がれるため。
read_liberty lef/tr1um_typ_5v0_25c.lib
read_verilog $NET
link_design $TOP

# I2C の SCL。既定は Fast-mode の 400 kHz = 2500 ns（sta.sh の第 3 引数）。
create_clock -name scl -period $PER [get_ports scl]

# デューティ 50% で見ている。scl_gated 段 -> scl_n 段は半周期のパスになるが、
# それは波形から自動で出る。**実際の I2C は Low 期間の方が長い**（規格の
# 最小 tLOW > tHIGH）ので、半周期パスはここでの見積りより緩い。
set_ideal_network [get_ports scl]

# 入力の駆動元。外部入力は BUFTH（シュミット）を通してから配るので、
# BUFTH 挿入後のネットリストでは BUFTH がドライバになる。挿入前の版に当てる
# ときのために BUF_X2 を仮置きする。
# VDD / GND は RTL のポートだが、構造インスタンスの電源ピンを繋ぐためだけの
# ものでタイミングには関係しないので外す。
foreach p [all_inputs] {
  set n [get_full_name $p]
  if {$n eq "scl" || $n eq "VDD" || $n eq "GND"} continue
  set_driving_cell -lib_cell BUF_X2 -pin Y $p
  set_input_delay -clock scl [expr {$PER * 0.2}] $p
}

# rst_n は非同期リセット。DFFRB の RSTB に組合せ回路経由で入る。
# **recovery / removal は特性化していない**（scripts/char/ が測っていない）ので、
# ここで見ても意味のある数字にならない。パスとしては外し、リセットの解除タイミングは
# ngspice のチップレベル TB（reference/v10/tb_chip_i2c_batch14_v10.spice 相当）で見る。
set_false_path -from [get_ports rst_n]

# 出力は OSS_ESD_5V_DIO の OUT ピン容量 36.2 fF を負荷にする
foreach p [all_outputs] {
  set_load 36.2 $p
  set_output_delay -clock scl [expr {$PER * 0.2}] $p
}

# 配線容量はまだ入れていない（P&R 前）。TR-1um の M2 は幅 3.4 um と太いので
# 実配線が乗ると悪化する。P&R 後にネットごとの容量を set_load で入れ直すこと。
#
# **SR ラッチについて。** merge_muxdffrb_rslatch.py を通す前のネットリストには
# NOR2 のクロス結合が生のループとして残っていて、OpenSTA が
# 「combinational loop」を報告してアークを 1 本切る。切る場所は OpenSTA 任せなので、
# **STA は必ず merge 後（RSLATCH に畳んだ後）のネットリストに当てること。**
# RSLATCH はセルの中にループが閉じていて、外から見れば preset / clear のアークになる。

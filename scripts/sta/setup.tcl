# 読み込みと制約。sta.sh が NET / TOP / PER を先頭で定義してから連結する。
read_liberty lef/tr1um_typ_5v0_25c.lib
read_verilog $NET
link_design $TOP

create_clock -name clk -period $PER [get_ports clk]

# クロックツリーはまだ無い。行バッファ（insert_row_buffers 相当）を入れるまで
# ideal / skew 0 で見る。P&R 後に引き直すこと。
set_ideal_network [get_ports clk]

# 入力の駆動元。PAD をコア入力に直結する方針だが、外部入力は BUFTH を通す
# （reference/05_pin_io_plan.md §2）。ここでは BUF_X2 を仮置き。
foreach p [all_inputs] {
  if {[get_full_name $p] eq "clk"} continue
  set_driving_cell -lib_cell BUF_X2 -pin Y $p
  set_input_delay -clock clk [expr {$PER * 0.2}] $p
}
# 出力は OSS_ESD_5V_DIO の OUT ピン容量 36.2 fF を負荷にする
foreach p [all_outputs] {
  set_load 36.2 $p
  set_output_delay -clock clk [expr {$PER * 0.2}] $p
}

# 配線容量はまだ入れていない（P&R 前）。TR-1um の M2 は幅 3.4 um と太いので
# 実配線が乗ると悪化する。P&R 後にネットごとの容量を set_load で入れ直すこと。

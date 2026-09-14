# reg->reg / in->reg / reg->out / hold の最悪 slack と、reg->reg が要求する最小周期。
#
# **「最小周期 = PER - slack」は使えない。**
# このコアは scl_gated (posedge scl) と scl_n (negedge scl) の 2 つの縁で叩かれる。
# 片方から片方へ渡る経路は**半周期**しか与えられないので、周期を T にすると
# slack は T ではなく T/2 に比例して動く。実測 (2026-09-14, OpenSTA 3.1.0):
# 遅延 24.5ns の経路を、この式で計算すると「所要周期 1274ns / Fmax 0.78MHz」に
# 化けた（正しくは半周期 > 24.5ns、つまり周期 > 49ns）。
#
# なので**周期を変えて 2 回測る**。slack は周期 T の 1 次式
#     slack(T) = a*T + b
# になり、a はその経路がもらえる周期の割合（全周期なら 1.0、半周期なら 0.5）。
# 2 点あれば a も b も出るので、slack = 0 になる T が最小周期。
# a がそのまま「全周期パスか半周期パスか」の答えにもなる。
proc path_of {args} {
  set ps [eval [concat find_timing_paths $args -group_path_count 1]]
  if {[llength $ps] == 0} { return "" }
  return [lindex $ps 0]
}

proc show {label args} {
  set p [eval [concat path_of $args]]
  if {$p eq ""} { puts [format "  %-11s (パスなし)" $label]; return }
  puts [format "  %-11s slack %9.3f ns   %s -> %s" $label [get_property $p slack] \
        [get_property [get_property $p startpoint] full_name] \
        [get_property [get_property $p endpoint] full_name]]
}

puts "######## $TOP   $NET   period = $PER ns"
show "reg->reg"  -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins]
show "in->reg"   -path_delay max -from [all_inputs]                -to [all_registers -data_pins]
show "reg->out"  -path_delay max -from [all_registers -clock_pins] -to [all_outputs]
show "hold r->r" -path_delay min -from [all_registers -clock_pins] -to [all_registers -data_pins]

# --- reg->reg の最小周期（2 点法） ---------------------------------------
set P1 $PER
set P2 [expr {$PER * 0.5}]
set p1 [path_of -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins]]
if {$p1 ne ""} {
  set s1 [get_property $p1 slack]
  set e1 [get_property [get_property $p1 endpoint] full_name]
  apply_period $P2
  set p2 [path_of -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins]]
  set s2 [get_property $p2 slack]
  set e2 [get_property [get_property $p2 endpoint] full_name]
  apply_period $PER
  set a [expr {($s1 - $s2) / ($P1 - $P2)}]
  if {$a > 1.0e-6} {
    set b    [expr {$s1 - $a * $P1}]
    set tmin [expr {-$b / $a}]
    set kind [expr {$a < 0.75 ? "半周期パス（scl_n <-> scl_gated）" : "全周期パス（同じ縁どうし）"}]
    puts [format "  => reg->reg が要求する最小周期 %.3f ns  (%.2f MHz)" $tmin [expr {1000.0/$tmin}]]
    puts [format "     周期係数 a = %.2f -> %s。経路の実遅延は %.3f ns" \
          $a $kind [expr {$a * $tmin}]]
    if {$e1 ne $e2} {
      puts "     ** 2 点で最悪パスが入れ替わった（$e1 / $e2）。1 次式の当てはめが甘い"
    }
  } else {
    puts "  => 周期を変えても slack が動かない（クロックに紐づかない経路）。最小周期は出せない"
  }
}

proc row {label args} {
  set ps [eval [concat find_timing_paths $args -group_path_count 1]]
  if {[llength $ps] == 0} { puts [format "  %-11s (パスなし)" $label]; return }
  set p [lindex $ps 0]
  puts [format "  %-11s slack %9.3f ns   %s -> %s" $label [get_property $p slack] \
        [get_property [get_property $p startpoint] full_name] \
        [get_property [get_property $p endpoint] full_name]]
}
puts "######## $TOP   $NET   period = $PER ns"
row "reg->reg"  -path_delay max -from [all_registers -clock_pins] -to [all_registers -data_pins]
row "in->reg"   -path_delay max -from [all_inputs]                -to [all_registers -data_pins]
row "reg->out"  -path_delay max -from [all_registers -clock_pins] -to [all_outputs]
row "hold r->r" -path_delay min -from [all_registers -clock_pins] -to [all_registers -data_pins]
set ps [find_timing_paths -path_delay max -from [all_registers -clock_pins] \
                          -to [all_registers -data_pins] -group_path_count 1]
if {[llength $ps]} {
  set need [expr {$PER - [get_property [lindex $ps 0] slack]}]
  puts [format "  => reg->reg の所要周期 %.3f ns  (Fmax %.2f MHz)" $need [expr {1000.0/$need}]]
}

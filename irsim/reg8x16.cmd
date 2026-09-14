| reg8x16.cmd -- REG8x16 全レジスタアクセス検証（IRSIM 版）
| scripts/gen_irsim_cmd.py が生成。手で編集しないこと。
| hdl/tb/tb_regx16.v と同じベクタ・同じ順序・同じ期待値。
|
| 合否判定:  python3 scripts/check_irsim_log.py irsim/reg8x16_run.log
| 読出のたびに print で期待値を刻み、assert でその場で判定し、
| d で実際の値を残す。IRSIM の .cmd 言語には条件分岐も算術も無いので、
| pass/fail の集計だけをログのオフライン突合せで行う。
|
| stepsize 1  -> 時間分解能 1ns。以降の `s <n>` の n はすべて ns。
| settle 10   -> TLAT の帰還ノード（n2/n3）が背中合わせインバータに
|                なっているので、一瞬の競合で X と判定されないよう
|                落ち着く時間を与える。
stepsize 1
settle 10
|
| 電源と初期状態。TLAT は電源投入直後 n3 が X だが、ratioless なので
| 最初の書込で TG-W が強制的に上書きして解ける（forcing は不要）。
h Vdd
l Gnd
h WEB
l ADD0
l ADD1
l ADD2
l ADD3
l D0
l D1
l D2
l D3
l D4
l D5
l D6
l D7
s 200
|
| 表示用ベクタ。d AV QV で「読んだ番地」と「読めた値」が同時に出る。
vector AV ADD3 ADD2 ADD1 ADD0
vector QV Q7 Q6 Q5 Q4 Q3 Q2 Q1 Q0

| ================================================================
| T1  全ワード書込 / 読出（値と番地を違えてある）
| ================================================================
h D1
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
l D0
l D1
h D4
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
l D0
h D1
h D2
h D4
h D5
l D6
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
l D0
l D1
h D4
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
l D0
h D1
l D2
l D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
l D0
l D1
h D4
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
l D0
h D1
h D2
h D4
h D5
l D6
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
l D0
l D1
h D4
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
h D0
l D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T1_readback add=0000 exp=11111010
assert QV 11111010
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=0001 exp=11101011
assert QV 11101011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T1_readback add=0010 exp=11011000
assert QV 11011000
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=0011 exp=11001001
assert QV 11001001
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T1_readback add=0100 exp=10111110
assert QV 10111110
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=0101 exp=10101111
assert QV 10101111
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T1_readback add=0110 exp=10011100
assert QV 10011100
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=0111 exp=10001101
assert QV 10001101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T1_readback add=1000 exp=01110010
assert QV 01110010
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=1001 exp=01100011
assert QV 01100011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T1_readback add=1010 exp=01010000
assert QV 01010000
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=1011 exp=01000001
assert QV 01000001
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T1_readback add=1100 exp=00110110
assert QV 00110110
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=1101 exp=00100111
assert QV 00100111
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T1_readback add=1110 exp=00010100
assert QV 00010100
d AV QV
h ADD0
s 50
print CHECK tag=T1_readback add=1111 exp=00000101
assert QV 00000101
d AV QV
| 逆順でもう一度（読出が直前の書込に依存していないこと）
s 50
print CHECK tag=T1_reverse add=1111 exp=00000101
assert QV 00000101
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=1110 exp=00010100
assert QV 00010100
d AV QV
h ADD0
l ADD1
s 50
print CHECK tag=T1_reverse add=1101 exp=00100111
assert QV 00100111
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=1100 exp=00110110
assert QV 00110110
d AV QV
h ADD0
h ADD1
l ADD2
s 50
print CHECK tag=T1_reverse add=1011 exp=01000001
assert QV 01000001
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=1010 exp=01010000
assert QV 01010000
d AV QV
h ADD0
l ADD1
s 50
print CHECK tag=T1_reverse add=1001 exp=01100011
assert QV 01100011
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=1000 exp=01110010
assert QV 01110010
d AV QV
h ADD0
h ADD1
h ADD2
l ADD3
s 50
print CHECK tag=T1_reverse add=0111 exp=10001101
assert QV 10001101
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=0110 exp=10011100
assert QV 10011100
d AV QV
h ADD0
l ADD1
s 50
print CHECK tag=T1_reverse add=0101 exp=10101111
assert QV 10101111
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=0100 exp=10111110
assert QV 10111110
d AV QV
h ADD0
h ADD1
l ADD2
s 50
print CHECK tag=T1_reverse add=0011 exp=11001001
assert QV 11001001
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=0010 exp=11011000
assert QV 11011000
d AV QV
h ADD0
l ADD1
s 50
print CHECK tag=T1_reverse add=0001 exp=11101011
assert QV 11101011
d AV QV
l ADD0
s 50
print CHECK tag=T1_reverse add=0000 exp=11111010
assert QV 11111010
d AV QV

| ================================================================
| T2  ウォーキング 1 / 0（4 本のビット線が独立か）
| ================================================================
l D2
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0000 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0000 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0001 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0001 exp=01111111
assert QV 01111111
d AV QV
l ADD0
h ADD1
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0010 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0010 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0011 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0011 exp=01111111
assert QV 01111111
d AV QV
l ADD0
l ADD1
h ADD2
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0100 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0100 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0101 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0101 exp=01111111
assert QV 01111111
d AV QV
l ADD0
h ADD1
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0110 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0110 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=0111 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=0111 exp=01111111
assert QV 01111111
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1000 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1000 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1001 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1001 exp=01111111
assert QV 01111111
d AV QV
l ADD0
h ADD1
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1010 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1010 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1011 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1011 exp=01111111
assert QV 01111111
d AV QV
l ADD0
l ADD1
h ADD2
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1100 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1100 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1101 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1101 exp=01111111
assert QV 01111111
d AV QV
l ADD0
h ADD1
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1110 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1110 exp=01111111
assert QV 01111111
d AV QV
h ADD0
l D1
l D2
l D3
l D4
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00000001
assert QV 00000001
d AV QV
l D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11111110
assert QV 11111110
d AV QV
l D2
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00000010
assert QV 00000010
d AV QV
h D0
l D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11111101
assert QV 11111101
d AV QV
l D0
l D3
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00000100
assert QV 00000100
d AV QV
h D0
h D1
l D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11111011
assert QV 11111011
d AV QV
l D0
l D1
l D4
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00001000
assert QV 00001000
d AV QV
h D0
h D1
h D2
l D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11110111
assert QV 11110111
d AV QV
l D0
l D1
l D2
l D5
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00010000
assert QV 00010000
d AV QV
h D0
h D1
h D2
h D3
l D4
h D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11101111
assert QV 11101111
d AV QV
l D0
l D1
l D2
l D3
l D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=00100000
assert QV 00100000
d AV QV
h D0
h D1
h D2
h D3
h D4
l D5
h D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=11011111
assert QV 11011111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=01000000
assert QV 01000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=10111111
assert QV 10111111
d AV QV
l D0
l D1
l D2
l D3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk1 add=1111 exp=10000000
assert QV 10000000
d AV QV
h D0
h D1
h D2
h D3
h D4
h D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T2_walk0 add=1111 exp=01111111
assert QV 01111111
d AV QV

| ================================================================
| T3  デコーダ一意性（全語 0101… -> 1 語だけ 1010…、他 15 語が不変か）
| ================================================================
l ADD0
l ADD1
l ADD2
l ADD3
l D1
l D3
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
s 50
print CHECK tag=T3_unique add=0000 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD2
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=10101010
assert QV 10101010
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD2
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD1
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD2
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=10101010
assert QV 10101010
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD2
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD2
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=10101010
assert QV 10101010
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD2
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD3
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=10101010
assert QV 10101010
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD2
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=10101010
assert QV 10101010
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD2
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD2
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=10101010
assert QV 10101010
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD2
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD2
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=10101010
assert QV 10101010
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=10101010
assert QV 10101010
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
l ADD3
h D0
l D1
h D2
l D3
h D4
l D5
h D6
l D7
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l D0
h D1
l D2
h D3
l D4
h D5
l D6
h D7
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T3_unique add=0000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=0100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=0110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=0111 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T3_unique add=1000 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1001 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1010 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1011 exp=01010101
assert QV 01010101
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T3_unique add=1100 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1101 exp=01010101
assert QV 01010101
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T3_unique add=1110 exp=01010101
assert QV 01010101
d AV QV
h ADD0
s 50
print CHECK tag=T3_unique add=1111 exp=10101010
assert QV 10101010
d AV QV

| ================================================================
| T4  WEB 極性（WEB=1 では書けない / 落とせば書ける）
| ================================================================
l ADD0
l ADD1
l ADD2
l ADD3
l D1
h D2
l D5
h D6
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
| WEB を落とさずにアドレスとデータだけ動かす -> 何も書かれないはず
l ADD0
l ADD1
l ADD2
l ADD3
h D0
h D1
l D2
l D3
h D4
h D5
l D6
l D7
s 150
h ADD0
s 150
l ADD0
h ADD1
s 150
h ADD0
s 150
l ADD0
l ADD1
h ADD2
s 150
h ADD0
s 150
l ADD0
h ADD1
s 150
h ADD0
s 150
l ADD0
l ADD1
l ADD2
h ADD3
s 150
h ADD0
s 150
l ADD0
h ADD1
s 150
h ADD0
s 150
l ADD0
l ADD1
h ADD2
s 150
h ADD0
s 150
l ADD0
h ADD1
s 150
h ADD0
s 150
l D0
l D1
l D4
l D5
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T4_no-write add=0000 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=0001 exp=11001100
assert QV 11001100
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_no-write add=0010 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=0011 exp=11001100
assert QV 11001100
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T4_no-write add=0100 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=0101 exp=11001100
assert QV 11001100
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_no-write add=0110 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=0111 exp=11001100
assert QV 11001100
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T4_no-write add=1000 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=1001 exp=11001100
assert QV 11001100
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_no-write add=1010 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=1011 exp=11001100
assert QV 11001100
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T4_no-write add=1100 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=1101 exp=11001100
assert QV 11001100
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_no-write add=1110 exp=11001100
assert QV 11001100
d AV QV
h ADD0
s 50
print CHECK tag=T4_no-write add=1111 exp=11001100
assert QV 11001100
d AV QV
| WEB を落とせば書ける（そもそも書けていない、のではないことの証明）
l ADD0
l ADD1
l ADD2
l ADD3
h D0
h D1
h D4
h D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T4_write-ok add=0000 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=0001 exp=00110011
assert QV 00110011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_write-ok add=0010 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=0011 exp=00110011
assert QV 00110011
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T4_write-ok add=0100 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=0101 exp=00110011
assert QV 00110011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_write-ok add=0110 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=0111 exp=00110011
assert QV 00110011
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T4_write-ok add=1000 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=1001 exp=00110011
assert QV 00110011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_write-ok add=1010 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=1011 exp=00110011
assert QV 00110011
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T4_write-ok add=1100 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=1101 exp=00110011
assert QV 00110011
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=T4_write-ok add=1110 exp=00110011
assert QV 00110011
d AV QV
h ADD0
s 50
print CHECK tag=T4_write-ok add=1111 exp=00110011
assert QV 00110011
d AV QV

| ================================================================
| T5  保持（全書込後にアドレス順でない順序で読み直す）
| ================================================================
l ADD0
l ADD1
l ADD2
l ADD3
l D4
l D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
h D3
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
h D0
l D1
l D3
h D4
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
h D3
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
h D0
h D1
h D2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
l D3
l D4
h D5
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
h D0
l D1
h D3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
l D3
h D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
h D0
h D1
l D2
h D3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
l D3
l D4
l D5
h D6
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
h D0
l D1
h D3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
l D3
h D4
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
h D0
h D1
h D2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
h D3
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
h D0
l D1
l D3
l D4
h D5
s 50
l WEB
s 50
h WEB
s 50
h ADD0
l D0
h D3
s 50
l WEB
s 50
h WEB
s 50
l ADD2
s 50
print CHECK tag=T5_hold add=1011 exp=01010000
assert QV 01010000
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0010 exp=00010001
assert QV 00010001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=0101 exp=00100110
assert QV 00100110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0100 exp=00011111
assert QV 00011111
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1111 exp=01101100
assert QV 01101100
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0110 exp=00101101
assert QV 00101101
d AV QV
h ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T5_hold add=1001 exp=01000010
assert QV 01000010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1000 exp=00111011
assert QV 00111011
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0011 exp=00011000
assert QV 00011000
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1010 exp=01001001
assert QV 01001001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=1101 exp=01011110
assert QV 01011110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1100 exp=01010111
assert QV 01010111
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0111 exp=00110100
assert QV 00110100
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1110 exp=01100101
assert QV 01100101
d AV QV
h ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T5_hold add=0001 exp=00001010
assert QV 00001010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0000 exp=00000011
assert QV 00000011
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1011 exp=01010000
assert QV 01010000
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0010 exp=00010001
assert QV 00010001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=0101 exp=00100110
assert QV 00100110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0100 exp=00011111
assert QV 00011111
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1111 exp=01101100
assert QV 01101100
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0110 exp=00101101
assert QV 00101101
d AV QV
h ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T5_hold add=1001 exp=01000010
assert QV 01000010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1000 exp=00111011
assert QV 00111011
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0011 exp=00011000
assert QV 00011000
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1010 exp=01001001
assert QV 01001001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=1101 exp=01011110
assert QV 01011110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1100 exp=01010111
assert QV 01010111
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0111 exp=00110100
assert QV 00110100
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1110 exp=01100101
assert QV 01100101
d AV QV
h ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T5_hold add=0001 exp=00001010
assert QV 00001010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0000 exp=00000011
assert QV 00000011
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1011 exp=01010000
assert QV 01010000
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0010 exp=00010001
assert QV 00010001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=0101 exp=00100110
assert QV 00100110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0100 exp=00011111
assert QV 00011111
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1111 exp=01101100
assert QV 01101100
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0110 exp=00101101
assert QV 00101101
d AV QV
h ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T5_hold add=1001 exp=01000010
assert QV 01000010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1000 exp=00111011
assert QV 00111011
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0011 exp=00011000
assert QV 00011000
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1010 exp=01001001
assert QV 01001001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=1101 exp=01011110
assert QV 01011110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1100 exp=01010111
assert QV 01010111
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0111 exp=00110100
assert QV 00110100
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1110 exp=01100101
assert QV 01100101
d AV QV
h ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T5_hold add=0001 exp=00001010
assert QV 00001010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0000 exp=00000011
assert QV 00000011
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1011 exp=01010000
assert QV 01010000
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0010 exp=00010001
assert QV 00010001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=0101 exp=00100110
assert QV 00100110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0100 exp=00011111
assert QV 00011111
d AV QV
h ADD0
h ADD1
h ADD3
s 50
print CHECK tag=T5_hold add=1111 exp=01101100
assert QV 01101100
d AV QV
l ADD0
l ADD3
s 50
print CHECK tag=T5_hold add=0110 exp=00101101
assert QV 00101101
d AV QV
h ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=T5_hold add=1001 exp=01000010
assert QV 01000010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1000 exp=00111011
assert QV 00111011
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0011 exp=00011000
assert QV 00011000
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1010 exp=01001001
assert QV 01001001
d AV QV
h ADD0
l ADD1
h ADD2
s 50
print CHECK tag=T5_hold add=1101 exp=01011110
assert QV 01011110
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=1100 exp=01010111
assert QV 01010111
d AV QV
h ADD0
h ADD1
l ADD3
s 50
print CHECK tag=T5_hold add=0111 exp=00110100
assert QV 00110100
d AV QV
l ADD0
h ADD3
s 50
print CHECK tag=T5_hold add=1110 exp=01100101
assert QV 01100101
d AV QV
h ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=T5_hold add=0001 exp=00001010
assert QV 00001010
d AV QV
l ADD0
s 50
print CHECK tag=T5_hold add=0000 exp=00000011
assert QV 00000011
d AV QV

| ================================================================
| I1  [参考] アドレスと WEB のタイミング（合否には数えない）
| ================================================================
| (a) アドレスと WEB を同時に動かす
l D2
l D3
l D5
l D6
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
h D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
| ここでアドレス変更と WEB 立下げを同じ時刻に置く
h ADD0
h ADD1
h ADD2
h ADD3
l WEB
s 50
h WEB
s 50
l D0
l D1
l D2
l D3
l D4
l D5
l D6
l D7
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=I1a_timing add=0000 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=0001 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1a_timing add=0010 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=0011 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=I1a_timing add=0100 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=0101 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1a_timing add=0110 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=0111 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=I1a_timing add=1000 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=1001 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1a_timing add=1010 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=1011 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=I1a_timing add=1100 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=1101 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1a_timing add=1110 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1a_timing add=1111 exp=11111111
assert QV 11111111
d AV QV
|
| (b) WEB=0 のままアドレスを動かす（違反した使い方）
l ADD0
l ADD1
l ADD2
l ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
h ADD3
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
h ADD2
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
h ADD1
s 50
l WEB
s 50
h WEB
s 50
h ADD0
s 50
l WEB
s 50
h WEB
s 50
l ADD0
l ADD1
l ADD2
l ADD3
h D0
h D1
h D2
h D3
h D4
h D5
h D6
h D7
s 50
l WEB
s 50
| 書込を開いたままアドレスを動かす
h ADD0
h ADD1
h ADD2
h ADD3
s 50
h WEB
s 50
l D0
l D1
l D2
l D3
l D4
l D5
l D6
l D7
l ADD0
l ADD1
l ADD2
l ADD3
s 50
print CHECK tag=I1b_timing add=0000 exp=11111111
assert QV 11111111
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=0001 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1b_timing add=0010 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=0011 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=I1b_timing add=0100 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=0101 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1b_timing add=0110 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=0111 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
l ADD2
h ADD3
s 50
print CHECK tag=I1b_timing add=1000 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=1001 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1b_timing add=1010 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=1011 exp=00000000
assert QV 00000000
d AV QV
l ADD0
l ADD1
h ADD2
s 50
print CHECK tag=I1b_timing add=1100 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=1101 exp=00000000
assert QV 00000000
d AV QV
l ADD0
h ADD1
s 50
print CHECK tag=I1b_timing add=1110 exp=00000000
assert QV 00000000
d AV QV
h ADD0
s 50
print CHECK tag=I1b_timing add=1111 exp=11111111
assert QV 11111111
d AV QV

| end of reg8x16.cmd

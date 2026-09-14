# char/ — 標準セルの ngspice 検証と Liberty 生成

TR-1um (IP62) の標準セルを **GDS から抽出 → ngspice で全数検証 → Liberty 生成**
まで通すための一式。PDK には .lib が無いので、ここで作る。

```sh
# 0) GDS から全セルの SPICE を起こす（36 セル）
for c in $(python3 -c "import cellspec;print(' '.join(cellspec.ALL_ROW_CELLS))"); do
  python3 gds_extract.py TR-1um_STDCELL.gds $c -o cells/$c.spi
done

# 1) 機能チェック
python3 check_comb.py      # 組合せ 26 種 / 真理値表 全網羅
python3 check_seq.py       # 順序 6 種 / クロック列シナリオ
python3 check_pass.py      # TAP・FILL / 短絡とレール導通と容量

# 2) 特性化（逐次で約 15 分 + 順序が約 30 分）
python3 char_comb.py       # NLDM 7x7
python3 char_seq.py        # CK->Q 7x7 と setup/hold 3x3

# 3) Liberty 生成と検算
python3 mklib.py -o tr1um_typ_5v0_25c.lib
python3 verify_lib.py
```

## 効いた落とし穴

### ngspice を並列に走らせてはいけない（このコンテナでは 50 倍遅くなる）

2 コアの環境で ngspice を 2 本同時に走らせると、**逐次 2.0 秒の仕事が並列 99 秒**
になった。`OMP_NUM_THREADS=1` を渡してもスレッド数は減らず効果なし。
スレッドがコア数を超えるとバリアのスピン待ちで焼き切れているものと見られる。
`charlib.NPROC = 1`（逐次）に固定してある。1 本 0.7 秒なので逐次で十分。

### 辺で接する図形は boolean 'or' で繋がらない

`gdstk.boolean(a, b, "or")` は**辺を共有するだけの図形を 1 枚にまとめないことがある**。
XOR2 で電源スタブ 2 本が同じ形でレールに接しているのに片方だけ別ネットに割れ、
PMOS プルアップの vdd が外れて「出力がフルレールに振れない」という**偽の不具合**に見えた。
KLayout の LVS は接触＝導通として扱うので、それに合わせて
`gds_extract.merge()` で **0.01 µm 膨らませてから結合**するようにした。
最小間隔は M1 で 1.4 µm あるので、この膨張で別ネットが繋がることはない。

ゲートと拡散の接触判定も同じ理由で `gdstk.offset` に変えた。
bbox を膨らませる方式だと **L 字のゲート**（FILL2/FILL3 のデキャップ）で
片側の拡散を取りこぼす。

### ラベルは層を合わせて拾う

(49,0) は M2 ラベル、(48,0) は M1 ラベル。層をまたいで拾うと、M2 のつもりで
置いたラベルが真下の M1 電源レールに付いて**電源ネットが信号名に化ける**。
REGBUF で実際に起きた（`DD` / `QQ` が vdd レールに付いていた）。
DRC デッキ `00_Layers.drc` の `M1_LBL = labels(48,0)` / `M2_LBL = labels(49,0)`
と同じ対応にしてある。

### チャネル長を 1.0 µm 決め打ちにしない

**DEL1 は遅延段の 4 個だけ L=2.0 µm**、FILL2/FILL3 のデキャップは L=3.2 / 8.6 µm。
決め打ちだと DEL1 の遅延も デキャップの容量も狂う。幾何から実測する。

### ソースとドレインが同じネットに落ちるのは異常ではない

FILL2/FILL3 のデキャップは拡散の両側とも同じレールに繋ぐ MOS 容量なので、
区別できるネットが 1 本しかない。`?` を出さずにそのネットを両端に使う。

### ngspice では `vss` は節点 0 の別名

`Vgnd vss 0 0` と書くと「shorted VSRC」で止まる。電源は vdd だけ置けばよい。

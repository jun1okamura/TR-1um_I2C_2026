# scripts/sta/ — OpenSTA

`.lib` は実測（ngspice）なので、STA が当てられる。ここはその足回り。

```sh
sh scripts/sta/sta.sh out/td4_soc_arr.v td4_soc_arr 100                    # まとめ
sh scripts/sta/sta.sh out/td4_soc_arr.v td4_soc_arr 100 scripts/sta/path.tcl   # クリティカルパス詳細
```

| ファイル | 中身 |
|---|---|
| `sta.sh` | ドライバ。`NET` / `TOP` / `PER` を先頭に置いて `setup.tcl` + レポート tcl を連結して流す |
| `setup.tcl` | 読み込みと SDC 相当の制約（クロック・駆動セル・負荷・入出力遅延） |
| `report.tcl` | reg→reg / in→reg / reg→out / hold の最悪 slack と Fmax |
| `path.tcl` | reg→reg のクリティカルパス詳細 |

## OpenSTA のビルド

このリポジトリには入れていない。Ubuntu 24.04 での手順:

```sh
apt-get install -y cmake swig bison flex tcl-dev libeigen3-dev zlib1g-dev
# CUDD が要る（apt に無いので自前ビルド）
git clone --depth 1 https://github.com/ivmai/cudd.git
cd cudd && ./configure --prefix=/usr/local --enable-shared --enable-obj && make -j && make install
cd ..
git clone --depth 1 https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA && cmake -B build -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR=/usr/local && make -C build -j
# build/sta を PATH に置くか STA=... で指定する
```

## いま入っていない前提

- **配線容量ゼロ。** P&R 前なのでネット容量は駆動セルの負荷だけ。
  TR-1um の M2 は幅 3.4 um と太いので、実配線が乗ると悪化する。
- **クロックツリー無し。** `set_ideal_network` で skew 0。
- **`REG8x16` のタイミングが `.lib` に無い。** P&R の本命 `td4_soc_arr_bb` は
  これが入るまで STA にかけられない。
- `RSTB` の `recovery` / `removal` と `min_pulse_width` を特性化していない。

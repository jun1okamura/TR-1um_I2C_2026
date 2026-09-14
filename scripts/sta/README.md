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

このリポジトリには入れていない。`sta` が PATH にあれば `scripts/syn.sh` の段 9 と
`scripts/sta/sta.sh` が自動で使う。別の場所に置くなら `STA=/path/to/sta` で渡せる。

### macOS（Apple Silicon / Homebrew）

**Xcode 付属の Tcl / Flex / Bison では通らない**（上流 README が明記）。
Homebrew のものを PATH の先に置くのが要点。

```sh
git clone https://github.com/parallaxsw/OpenSTA.git
cd OpenSTA

# 依存。上流の Brewfile がそのまま使える。
# 中身は bison / cmake / eigen / flex / swig / tcl-tk@8 / mht208/formal/cudd。
# **CUDD は Homebrew 本体に無く、mht208/formal というタップから入る。**
# 自前ビルドしなくてよいのはこれのおかげ。
brew bundle install

# Apple 版を押しのける。**これを忘れると Apple の bison 2.3 が使われ、parser 生成で落ちる。**
export PATH="$(brew --prefix bison)/bin:$(brew --prefix flex)/bin:$PATH"
export CMAKE_INCLUDE_PATH="$(brew --prefix flex)/include"
export CMAKE_LIBRARY_PATH="$(brew --prefix flex)/lib;$(brew --prefix bison)/lib"

cmake -B build -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR="$(brew --prefix cudd)"
cmake --build build -j"$(sysctl -n hw.physicalcpu)"
build/sta -version
```

つまずきどころ:

| 症状 | 原因と手当て |
|---|---|
| `bison: ... version 2.3` / `syntax error` が parser 生成で出る | export が効いていない。`which bison` が `/opt/homebrew/...` を指しているか確認 |
| Tcl が見つからない | `tcl-tk@8` は keg-only。`-DCMAKE_PREFIX_PATH="$(brew --prefix tcl-tk@8)"` を足す |
| `CUDD not found` | `brew --prefix cudd` が空。`brew install mht208/formal/cudd` を単体で叩く |
| タップが使えない | CUDD を自前で建てる: `git clone https://github.com/cuddorg/cudd.git && cd cudd && git checkout 3.0.0 && ./configure --prefix=/usr/local --enable-shared --enable-obj && make -j && make install`、その `--prefix` を `-DCUDD_DIR` に渡す |

`tclreadline` は Homebrew に無い（上流 README）。対話シェルの補完が無いだけで、
`sta.sh` のように `-exit` で流す使い方には関係しない。

置き場所はどちらでもよい:

```sh
sudo cp build/sta /usr/local/bin/     # PATH に置く
export STA="$PWD/build/sta"           # か、sta.sh / syn.sh に環境変数で渡す
```

動作確認:

```sh
cd ~/Dropbox/98_LSI_Design/TR-1um_I2C_2026
sh scripts/sta/sta.sh out/i2c_slave_async_pnr.v i2c_slave_async 2500
```

### Ubuntu 24.04

```sh
apt-get install -y cmake swig bison flex tcl-dev libeigen3-dev zlib1g-dev
# CUDD は apt に無いので自前ビルド
git clone --depth 1 https://github.com/cuddorg/cudd.git
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

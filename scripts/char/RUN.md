# 特性化を手元の Mac で流す手順

`.lib` を作るには ngspice を **14,179 本**流す必要があります。
クラウド側は 2 コアなので逐次で 2 時間近くかかりますが、18 コアの Mac なら
並列で **10〜20 分**で終わります。そのため

  **生成（デッキを全部書き出す） → 実行（並列） → 回収（JSON 化）**

の 3 段に分けてあります。往復するのは `results.txt` 1 本だけです。

---

## 0. 前提

```sh
cd scripts/char
which ngspice          # 見つからなければ brew install ngspice
python3 -V             # 3.9 以上
```

`models/` に PDK の BSIM3 モデル（`ip62_models` ほか 4 本）を置いてあります。
別の場所の PDK を使いたい場合は手順 2 で `-m` で指定してください。

---

## 1. 抽出ネットリストを取り込む

KLayout の `lef/extracted/*.extracted` を ngspice が読める形に直します。
ネット名の `\$6` や素子名の `XM$1` は `$` が ngspice のコメント文字なので、
ここで `n6` / `XM1` に置き換えています。

```sh
python3 loadext.py ../../lef/extracted -o cells_ext
```

→ `cells_ext/` に 30 セル。以降のスクリプトはすべてこれを見ます。

## 2. デッキを生成する

```sh
export TR1UM_CELLDIR=$PWD/cells_ext
export TR1UM_CELLEXT=.spi
python3 genjobs.py -o pack
```

→ `pack/decks/` に 14,179 本（約 70 MB）、`pack/jobs.json` に対応表。

内訳:

| 種類 | 本数 | 何を測るか |
|---|---:|---|
| delay | 686 | 組合せセルの cell_rise/fall・出力遷移（7×7） |
| cap | 49 | 入力に流れ込む電荷から出した入力容量 |
| calib | 124 | INV_X1 で N 個駆動して求める**遅延計算用の等価容量** |
| ckq | 56 | 順序セルの CK→Q（7×7） |
| setup / hold | 6,624 ×2 | 制約（3×3 × 立上下 × dt 掃引 92 点） |
| verify | 12+4 | 格子の**外**での検算と、実負荷ファンアウトの検算 |

setup/hold は二分探索をやめて**掃引**にしてあります。二分探索は前の結果に
依存するので並列にできません。掃引なら全点が独立で、しかも境界付近を
0.25 ns 刻みにしてあるので分解能は二分探索より良くなります。

## 3. 流す

```sh
./runjobs.sh -j 18
```

- 途中で Ctrl-C しても構いません。**もう一度叩けば続きから走ります**
  （結果のあるデッキは飛ばします）。
- 20 秒ごとに `本/秒` と残り時間が出ます。**1 本/秒 を大きく下回るようなら
  並列数を下げてください**（`-j 9` など）。ngspice は 1 プロセスで複数
  スレッドを使おうとし、コア数を超えると桁違いに遅くなります。
  対策として `pack/.spiceinit` に `set num_threads=1` を置いていますが、
  ビルドによっては効かないことがあります。
- モデルを別の場所から読ませたいとき: `./runjobs.sh -j 18 -m /path/to/pdk/models`

→ `pack/results.txt`（1 行が `タグ 測定名 値`、数 MB）

## 4. 回収して `.lib` を作る

```sh
python3 collect.py -p pack      # results.txt -> char/*.json
python3 mklib.py -o ../../lef/tr1um_typ_5v0_25c.lib
python3 verify_lib.py ../../lef/tr1um_typ_5v0_25c.lib
```

`verify_lib.py` は `char/_verify.json`（collect.py が置きます）があれば
ngspice を回さず、**手順 3 と同じ実行の実測値**で検算します。

---

## 何が出れば成功か

`verify_lib.py` の 4 段がすべて「逸脱なし」なら `.lib` は使えます。

1. **表の健全性** — 欠損なし、負荷を増やすと必ず遅くなる（単調）
2. **格子の外での照合** — 入力遷移 1.0 ns / 負荷 150 fF（どちらも格子点では
   ない）での ngspice 実測と、`.lib` を線形補間した値のずれが 15% 未満
3. **入力容量の妥当性** — INV_X1 が INV_X1 を N 個駆動したときの実測遅延と、
   `.lib` を「負荷 = N × capacitance」で引いた値のずれが 20% 未満
4. **`.lib` の構文** — 括弧の対応と必須項目

動作確認では 2 が 0.2〜1.0%、3 が 0.2〜2.5% で一致しています。

`collect.py` が出す注記のうち、

- `掃引の下端でも取り込めた` — その条件では setup/hold に余裕があり、
  境界が掃引範囲（−20 ns）より下にあるという意味。値は −20 で頭打ちになります。
- `単調でない` — dt を大きくしたのに取り込めない点があるということなので、
  刺激かセルを疑ってください。

---

## ファイルの役割

| ファイル | 役割 |
|---|---|
| `loadext.py` | `lef/extracted/*.extracted` → `cells_ext/*.spi` |
| `cellspec.py` | セルの真理値表・Liberty 関数・FF の定義（**唯一の出典**） |
| `charlib.py` | 格子（SLEWS/LOADS）・しきい値・アーク列挙 |
| `char_comb.py` / `char_seq.py` | デッキの組み立て（測定条件はここ） |
| `calib_cap.py` | 入力容量の較正（表の逆引き） |
| `genjobs.py` | 上記を使ってデッキを全部書き出す |
| `runjobs.sh` | 並列実行して `.meas` の行だけ集める |
| `collect.py` | `results.txt` → `char/*.json` |
| `mklib.py` | `char/*.json` → Liberty |
| `verify_lib.py` | `.lib` の検算 |
| `check_comb.py` / `check_seq.py` / `check_pass.py` | 論理の確認（`.lib` とは独立） |

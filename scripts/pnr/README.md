# `scripts/pnr/` — この設計を実際に作った配置配線

**提出した GDS を作ったのはここ。** `TR-1um_Async_I2C/script/` のフローを
この世代へ持ち込んだもので、設計固有の値は **`i2c_config.py` 1 本**に集めてある。
触るのはそのファイルだけ。

> ★ **2026-09-16 まで、ここには TD4 の README がバイト単位でそのまま置かれていた。**
> この repo に無い `td4_config.py` を 13 箇所で参照し、TD4 にしか無いマクロ
> （`REG8x16`）の側帯の話をしていた。同じ経緯で TD4 の TB 生成器
> （`gen_chip_tb.py` / `check_chip_sim.py`、LED フラッシャの期待値入り）も
> 紛れ込んでいたので、両方消した。**コピーしてきた文書は、中身を読むまで
> 「それらしく」見える**（U64）。

## いまの立ち位置 — 2 つの流し方がある

| | 何のため | 入口 |
|---|---|---|
| `scripts/pnr/` | **提出物を作った当時のフロー**。記録として動く形で残してある | `i2c_config.py` |
| APRtools | 4 世代を 1 本に集約した正本。**新しい作業はこちら** | リポジトリ直下の `config.py` |

APRtools で回すときは直下の `config.py` を使う（そちらの docstring に手順がある）。
**両者は同じ GDS を作る**ことを確認済み — APRtools で作り直したチップ段が
**当時の提出 GDS の正規化 md5 `bc73b16d` と一致**する
（このフローは `lef/` の凍結コピーを読むので、**古い `MUXDFFRB` のまま**。
2026-09-17 に `MUXDFFRB` を直したので、**いまの正本で作ると `b86d4c89`** になる）
（`<APRtools>/docs/90_improvement_notes.md` の U62。突き合わせは `apr/cmp_gds.py`
で行う。**生バイトはタイムスタンプで毎回変わる**ので `cmp` では判定できない）。

```sh
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um
export APRTOOLS=<PDK と道具を置いた場所>/TR-1um_APRtools
export PYTHONHASHSEED=0                    # ★ ルータが非決定的
python3 $APRTOOLS/apr/place.py             # 新しい作業はこちら
python3 $APRTOOLS/apr/route.py
```

## `spi_config.py` という薄皮

移植してきたスクリプトは `import spi_config as _cfg` と書いてある。
**原本を書き換えると移植の監査証跡が切れる**ので、名前だけ合わせて
`i2c_config.py` へ流す薄皮を置いてある。設定を触るのは `i2c_config.py`。

## チップの ngspice テストベンチ

この設計の TB は **2 本**。どちらも `layout/chip/simulation/` に出る。

```sh
python3 scripts/pnr/gen_chip_tb_batch14.py    # V10 の 14 項目回帰を今のチップへ
python3 scripts/pnr/gen_chip_tb_ringosc.py    # RING_OSC の発振

cd layout/chip/simulation
ngspice -b tb_batch14.spice > batch14.log 2>&1
python3 ../../../scripts/pnr/check_batch14.py batch14.log
```

★ **`.include` に機械のパスを書かない**。PDK の場所は TB の隣に生成する
`models.spice` 1 行に閉じ込めてあり、TB からは相対名で読む（U24）。
`models.spice` は `.gitignore`。

## セルの特性化はここには無い

`scripts/char/` は **APRtools の `char/` 1 本**に寄せた（U65）。
この repo にあった複製は消してある。

```sh
cd $APRTOOLS/char        # 手順は $APRTOOLS/char/RUN.md
```

## アルゴリズムの説明

段ごとの中身（FM 風分割・バリセンタ反復・チャネル配線の 5 パス・
リップアップ・圧縮）は **`<APRtools>/docs/21_flow_place.md` /
`22_flow_route.md` / `23_flow_chip.md`** にまとめてある。
移植の方式そのものは `<APRtools>/legacy/sclk_spi/PORTING.md`。

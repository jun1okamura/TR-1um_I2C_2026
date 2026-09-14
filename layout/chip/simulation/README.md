# `layout/chip/simulation/` — LVS 用ネットリスト

PDK の LVS デッキ（`TR-1um/libs.tech/klayout/tech/lvs/05_Compare.lvs` 21 行目）は

```ruby
Sch_file = "simulation/" + source.cell_name + ".spice"
```

つまり **GDS を置いたディレクトリの `simulation/<トップセル名>.spice`** を探す。
`layout/chip/*.gds` に対する参照ネットリストなので、ここに置いてある。

## 3 階層

| トップ | ソース（設計意図） | 出どころ |
|---|---|---|
| `i2c_slave_async_nrow_fm` | `.spice` | `out/i2c_slave_async_pnr.v` + `lef/simulation/*.spice` + 配置 JSON の物理セル |
| `RING_OSC` | `.spice` | xschem の回路図 `TR-1um_Async_I2C/ring_osc/RING_OSC.sch` / `INV3D.sch` |
| `tr_1um_jun1okamura_i2c` | `.spice` | 上の 2 つ + `lef/simulation/OSS_FRAME_GIO_nocombine.spice` + `layout/chip/gio_connections.json` |

`*.extracted` は**レイアウトから抽出した方**（`lvs_pnr.py -o` の出力）。
`*.lvsdb` は PDK デッキのレポートで、KLayout で開くと不一致箇所を色付きで
見られる。どちらも再生成できるので git には入れていない。

**どれもレイアウトを見ずに組み立てたソース**なので、突き合わせが同語反復に
ならない。唯一の例外は

* `FILL2`（デキャップ。回路図が無いのでレイアウト抽出を golden として凍結
  してある。`lef/simulation/FILL2.spice` の注記を参照）
* RING_OSC の `FILL2` の**個数**だけ GDS から数えている（論理に効かない
  詰め物なので、回路図の 206 個と一致することを確かめたうえで使う）

## 作り方

```sh
export TR1UM_PDK=$HOME/Dropbox/91_OpenPDK/TR-1um     # 環境に合わせて

# 1. コア
python3 scripts/pnr/mklvsnet.py    -o layout/chip/simulation/i2c_slave_async_nrow_fm.spice
# 2. RING_OSC（回路図から。FILL2 の数は GDS と照合する）
python3 scripts/pnr/mkringoscnet.py
# 3. チップ（1 と 2 とフレームを接続表で束ねる）
python3 scripts/pnr/mkchipnet.py
# 4. レイアウト側に 16 本のボンドパッドのピンを打つ
python3 scripts/pnr/add_top_pins.py
```

## 流し方

### 自前の照合（速い。素子とネットのグラフ同型だけ）

```sh
python3 scripts/pnr/lvs_pnr.py layout/step10/route_step_6_squeezed.gds i2c_slave_async_nrow_fm \
        layout/chip/simulation/i2c_slave_async_nrow_fm.spice \
        -o layout/chip/simulation/i2c_slave_async_nrow_fm.extracted
python3 scripts/pnr/lvs_pnr.py lef/RING_OSC.gds RING_OSC \
        layout/chip/simulation/RING_OSC.spice \
        -o layout/chip/simulation/RING_OSC.extracted
python3 scripts/pnr/lvs_pnr.py layout/chip/step3_top_pins.gds tr_1um_jun1okamura_i2c \
        layout/chip/simulation/tr_1um_jun1okamura_i2c.spice \
        -o layout/chip/simulation/tr_1um_jun1okamura_i2c.extracted
```

### PDK の本物のデッキ（最終判断はこちら）

```sh
python3 scripts/pnr/lvs_pdk.py layout/chip/step3_top_pins.gds \
        -r layout/chip/simulation/tr_1um_jun1okamura_i2c.lvsdb
python3 scripts/pnr/lvs_pdk.py lef/RING_OSC.gds RING_OSC \
        --sch layout/chip/simulation/RING_OSC.spice \
        -r layout/chip/simulation/RING_OSC.lvsdb
python3 scripts/pnr/lvs_pdk.py layout/step10/route_step_6_squeezed.gds i2c_slave_async_nrow_fm \
        --sch layout/chip/simulation/i2c_slave_async_nrow_fm.spice \
        -r layout/chip/simulation/i2c_slave_async_nrow_fm.lvsdb
```

### KLayout のバージョンについて

デッキは **0.29 以上**が要る。

* `02_Device.drc` の `size_inside`（0.29 で入った）
* `05_Compare.lvs` の `flag_missing_ports`（strict port モード）

0.28 で流すには `--allow-old-klayout` を付ける。`size_inside` を使う 4 行を
外した写しを作り、strict port モードを切って流す。**その分だけ検査は緩い**
ので、テープアウト前の最終判断は新しい KLayout で取り直すこと。トップピンの
本数と名前は `lvs_pnr.py` が別途照合している（16 本、`P1`-`P7` / `VSS` /
`P9`-`P15` / `VDD`）。

## 2026-09-14 時点の結果

| | 自前の照合 | PDK デッキ |
|---|---|---|
| `i2c_slave_async_nrow_fm` | 一致（素子 1852 / ネット 737 / ピン 26） | Netlists match |
| `RING_OSC` | 一致（素子 808 / ネット 201 / ピン 5） | Netlists match |
| `tr_1um_jun1okamura_i2c` | 一致（素子 3288 / ネット 1050 / ピン 16） | Netlists match |

PDK デッキは KLayout 0.28.16 + `--allow-old-klayout` で流したもの。

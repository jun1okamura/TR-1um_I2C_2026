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
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um     # 環境に合わせて

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

---

# 検証用 spice（抽出から）

LVS の次に、**同じ抽出ネットリスト**を ngspice で動かして機能を確かめる。
V10 の 14 項目回帰（`reference/v10/`）の刺激をそのまま当てている。

## ファイル

| | 中身 |
|---|---|
| `<top>_extracted.spice` | KLayout の素の抽出（`klayout_extract.py`。階層とラベルを残す） |
| `<top>_sim.spice` | それを ngspice 用に直したもの。**RING_OSC 入り** |
| `<top>_noosc_sim.spice` | 同上、**RING_OSC を外したもの**（長い回帰用） |
| `tb_batch14.spice` | I2C の 14 項目回帰（544 µs、SCL=100 kHz） |
| `spice_batch14_expected.json` | 14 項目の判定条件 |
| `tb_ringosc.spice` | RING_OSC の発振を見る短い TB |

LVS に使う `<top>.extracted` は**別物**。あちらは比較のために平坦化して
あるので網が `1` `2` `3` …の番号になっていて、中を覗けない。

## 作り方

```sh
export TR1UM_PDK=<PDK と道具を置いた場所>/TR-1um

python3 scripts/pnr/gen_chip_sim_ready.py                  # RING_OSC 入り
python3 scripts/pnr/gen_chip_sim_ready.py --no-ringosc     # 回帰用
python3 scripts/pnr/gen_chip_tb_batch14.py                 # 14 項目の TB
python3 scripts/pnr/gen_chip_tb_ringosc.py --until 12u --tmax 500p
```

## 流し方

```sh
cd layout/chip/simulation
ngspice -b tb_batch14.spice > batch14.log 2>&1      # 手元で約 5 分
python3 ../../../scripts/pnr/check_batch14.py batch14.log

ngspice -b tb_ringosc.spice > ringosc.log 2>&1      # 約 10 分
```

## ngspice 用に直しているところ（5 点）

KLayout の書き出しをそのまま ngspice に食わせると通らない。
`gen_chip_sim_ready.py` が直しているのは次の 5 点だけで、回路は触らない。

1. `\$123` のエスケープ名 -> `n123`（`via_1$6` のようなセル名も）
2. 角括弧のベクタ名 `tx_data[4]` -> `tx_data_4`（衝突したら止める）
3. ダイオードの `A=` / `P=` -> `AREA=` / `PJ=`（フレームの ESD）
4. モデル名 `NMOSE` -> `MNE`（PDK にあるのはこちら）
5. 素子を持たずポートも 0〜1 本のセルを落とす

W/L も AS/AD/PS/PD も**抽出した実物の寸法**なので、拡散容量は設計値では
なくレイアウトの実測値。

## RING_OSC を外す理由

`ENB` = `P15` = `rst_n` なので、リセットを解いた瞬間から 190 段が発振し
続ける。544 µs の回帰に入れたままだと刻みが潰れて終わらない。V10 も同じ
理由で分けている。外すと `P9` / `P10` が浮くので TB 側で 1 GΩ に落とす。

## 2026-09-14 時点の結果

`tb_batch14.spice`（`.tran 50n 544u 0 10n`、約 5 分）:

```
[t=9500ns]   OK: busy asserted after START                      (5.000V)
[t=99500ns]  OK: slave ACKed matching address (write)           (0.044V)
[t=101800ns] OK: addr_match asserted                            (5.000V)
[t=101800ns] OK: rw indicates WRITE                             (-0.000V)
[t=189500ns] OK: slave ACKed data byte                          (0.044V)
[t=194000ns] OK: rx_data == 0xA5                     (got 0xA5, expected 0xA5)
[t=209000ns] OK: busy cleared after STOP                        (0.000V)
[t=309500ns] OK: slave ACKed matching address (read)            (0.044V)
[t=311800ns] OK: rw indicates READ                              (5.000V)
[t=319500ns] OK: read byte == 0x3C                   (got 0x3C, expected 0x3C)
[t=419000ns] OK: busy cleared after final STOP                  (0.000V)
[t=519500ns] OK: unmatched address -> NACK (no slave ack)       (4.950V)
[t=521800ns] OK: addr_match not asserted for foreign address    (0.000V)
[t=539000ns] OK: busy cleared after STOP following NACK         (0.000V)

---- RESULT ----
All 14 checks PASSED
```

IRSIM / Verilog / V10 の SPICE と**同じ 14 項目**で、すべて 14/14。

`tb_ringosc.spice`（`.tran 100p 12u 0 500p uic`、約 15 分）:

| | 周期 | 周波数 | 振幅 | 1 段あたり |
|---|---|---|---|---|
| `OUT` (P10) 速い方 INV_X1 x95 | 155.04 ns | **6.450 MHz** | −0.046 … 5.047 V | 0.808 ns |
| `OUTD` (P9) 遅い方 INV3D x95 | 558.60 ns | **1.790 MHz** | −0.046 … 5.047 V | 2.910 ns |

どちらも 10 pF 負荷でレール to レール。比は **3.60 倍**。

この差が出るのが**抽出から流している意味**そのもの。`INV3D` は `INV_X1` と
**W/L が同じ**（PMOS 10.2/1.0、NMOS 3.4/1.0）で、違うのはレイアウトだけ。
抽出した拡散の面積が `AS=539.5p`（INV3D）対 `14.6p`（INV_X1）と桁違いなので、
接合容量で 3.6 倍遅くなる。回路図から作ったネットリストでは両者は同じ回路に
なるので、この差は出てこない。

## RING_OSC 入りは `uic` が要る

リング発振器を抱えたチップは動作点が求まらない
（`Transient op failed, timestep too small`）。`.tran … uic` で全節点 0 V から
始めて、`ENB` を上げるまでの 0.5 µs で落ち着かせる。14 項目の回帰の方は
RING_OSC を外してあるので `uic` は要らない。

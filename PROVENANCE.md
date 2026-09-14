# Provenance

このリポジトリは **2026 MPW の提出リポジトリであり、同時に設計環境そのもの**。
RTL・スクリプト・レイアウト・検証データがここに揃っていて、`src/` の 2 つの
ファイルはこのリポジトリの中で作られる。

| `src/` | どこから | 作るコマンド |
|---|---|---|
| `tr_1um_jun1okamura_i2c.gds` | `layout/chip/step3_top_pins.gds` | `scripts/pnr/export_mpw.py` |
| `tr_1um_jun1okamura_i2c.cir` | `layout/chip/simulation/tr_1um_jun1okamura_i2c.spice` | 同上 |

`.spice` -> `.cir` の改名は `info.yaml` の `lvs.extension` に合わせるため。

## 2025 年の V10 からの関係

設計の出自は
[jun1okamura/TR-1um_Async_I2C](https://github.com/jun1okamura/TR-1um_Async_I2C)
（RTL 設計、MyHDL/iverilog 検証、Yosys 合成、独自ルータ、DRC/LVS、IRSIM、
RING_OSC 統合までの全履歴と `design_notes.md`）。**同じ RTL・同じプロトコル**
だが、2026 版は物理設計を全部やり直している。

- **合成から作り直し**。`RSLATCH` を ngspice で特性化して `.lib` に入れ
  （NLDM 7x7、`scripts/char/`）、RTL から直接インスタンス化して
  `blackbox` で守る形にした。V10 は NOR2 のたすき掛けで書いていたが、
  `synth -flatten` の後で ABC が NOR3/NAND3 の生ループに吸収してしまい、
  組合せループが 4 個できていた。
- **配置・配線を作り直し**。4 行構成、コア 1611.0 x 963.2 µm。
  行割り当ての FM 分割にパッド近接の項を追加。
- **`RING_OSC` を現行 STDCELL 世代で描き直し**（セル高 64.8 -> 59.4、
  帯の高さ 244.8 -> 223.2 µm）。ネットリストは xschem の回路図から起こし、
  レイアウトとの LVS が通ることを確認している。
- **チップ配線を作り直し**。`DIS` を幹 1 本 + 端点ごとの足にまとめ、
  電源は V10 と同じ 10 µm x 5 本のストリップで PAD へ。コアと `RING_OSC` の
  両脇の M2 電源を M1 に落として `RING_OSC` の上下に M1 バスバーを足した
  （V10 の構成では `RING_OSC` にチップ電源が来ていなかった）。
- **検証をレイアウト抽出から**。LVS の照合に加えて、同じ抽出から ngspice 用の
  ネットリストを起こして 14 項目回帰を流している。刺激（PWL）は V10 の
  テストベンチをそのまま借りていて、`reference/v10/` に置いてある。

ピン配置（どのパッドがどのビットか）は **V10 の Option2 と同じ**
（物理パッド番号の昇順と bit 番号が単調対応、`P3`..`P6` = bit0-3、
`P11`..`P14` = bit4-7）。V9 以前のピン表は使わないこと。現行の表は
`README.md` の 1 節。

## フレームについて

実フレームのセルは元リポジトリでは `OSS_FRAME_GIO` という名前だが、この
リポジトリでは `OSS_FRAME` に改名して取り込んでいる（テンプレートの
`scripts/pre_check.py` の名前チェックに合わせるため）。

## `reference/v10/`

V10 の成果物のうち、2026 版の検証で**参照として使っているもの**だけを
置いてある。

| | 使い道 |
|---|---|
| `tb_chip_i2c_batch14_v10.spice` | 14 項目回帰の**刺激**（PWL）を借りる |
| `spice_batch14_v10_expected.json` | 14 項目の判定条件 |
| `check_batch14_v10.py` | 判定スクリプトの元（`scripts/pnr/check_batch14.py`） |
| `i2c_slave_async_net_v10_final.v` | セル数の比較用（`scripts/cmp_cells.py`） |
| `tr_1um_i2c_slave_async.cir` | V10 のチップネットリスト（参照） |

`RING_OSC` の回路図（`RING_OSC.sch` / `INV3D.sch`）は元リポジトリの
`ring_osc/` にあり、`scripts/pnr/mkringoscnet.py` がそれを読み下して
LVS ソースを作る。

## 検証の結果（2026-09-14）

| | |
|---|---|
| DRC（PDK デッキ、チップ） | 0 件 |
| DRC（MDP 後の IP62 マスク） | 0 件 |
| LVS（コア / RING_OSC / チップ） | いずれも Netlists match |
| ngspice 14 項目（抽出から） | 14/14 PASS |
| STA（OpenSTA、2 点法） | 49.104 ns = 20.36 MHz |
| RING_OSC 発振（抽出から） | OUT 6.450 MHz / OUTD 1.790 MHz |

手元では KLayout 0.28.16 に `size_inside` / `steps` を使う行を書き換えた
デッキで流している（`scripts/pnr/drc_pdk.py` / `lvs_pdk.py` の
`--allow-old-klayout`）。**その分だけ検査は緩い**ので、最終判断は CI
（KLayout 0.30.9）の結果で取ること。

# TR-1um I2C Asynchronous Slave

[![check](https://github.com/jun1okamura/TR-1um_I2C_2026/actions/workflows/check.yml/badge.svg)](../../actions)

Clockless (no `clk` port — every state transition is driven purely by
SCL/SDA bus edges) I2C slave core implemented on the OpenSUSI TR-1um
process, together with an on-die ring-oscillator (`RING_OSC`) test
structure sharing the chip's reset pin.

**This repository is the 2026 MPW submission.** The core was
re-synthesized from RTL with a characterized `RSLATCH`, re-placed and
re-routed from scratch, and `RING_OSC` was redrawn on the current
standard-cell generation. Chip DRC 0 / LVS match / MDP mask DRC 0, and
the 14-check WRITE/READ/NACK regression passes 14/14 **on the netlist
extracted from the layout**. See §2 for what changed.

Design source, full history and design notes:
[jun1okamura/TR-1um_Async_I2C](https://github.com/jun1okamura/TR-1um_Async_I2C)
(see that repo's `design_notes.md` and this repo's [`PROVENANCE.md`](PROVENANCE.md)
for exactly what was exported here and how).

Also see below series of design note in Japanese.
- [Completing a new chip design with Claude (1)](https://qiita.com/jun1okamura/items/898248762a03492cdc33)
- [Completing a new chip design with Claude (2)](https://qiita.com/jun1okamura/items/ca2fed5c46a105ac371c)
- [Completing a new chip design with Claude (3)](https://qiita.com/jun1okamura/items/928e6e1464e75a68b394)
- [Completing a new chip design with Claude (4)](https://qiita.com/jun1okamura/items/cb8f252360014d35043a)
- [Completing a new chip design with Claude (5)](https://qiita.com/jun1okamura/items/177e9ea388ee900ca6bb)

---

## 1. チップ概要（ピン説明）

チップ本体は非同期（クロックレス）I2Cスレーブコア
（`i2c_slave_async_nrow_fm`）と、テスト用リング発振器
（`RING_OSC`）を1チップに統合したもの。16本の実ボンドパッド
（P1〜P7、VSS, P9〜P15、VDD）で構成。

| ピン | 信号 | 方向 | 説明 |
|---|---|---|---|
| P1 | `SCL` | 入力 | I2Cクロック |
| P2 | `SDA` | 双方向（オープンドレイン） | I2Cデータ。ドライバは常にLowにしか駆動しない（`sda_oe`でゲート、Highはチップ外部プルアップ任せ）。入力パスは`sda_in`。 |
| P3 | `tx_data[0]` / `rx_data[0]` | 双方向 | 汎用データピン、ビット0 |
| P4 | `tx_data[1]` / `rx_data[1]` | 双方向 | 汎用データピン、ビット1 |
| P5 | `tx_data[2]` / `rx_data[2]` | 双方向 | 汎用データピン、ビット2 |
| P6 | `tx_data[3]` / `rx_data[3]` | 双方向 | 汎用データピン、ビット3 |
| P7 | `DIS` | 入力 | P3/P4/P5/P6/P11/P12/P13/P14の8本共有の方向制御。動作中はダイナミックに切り替わる——WRITE中はLow（チップ自身の出力ドライバが有効化され、各ピンは`rx_data`を出力）、READ中・アイドル中はHigh（Hi-Z、各ピンは`tx_data`入力として動作）。 |
| VSS | `VSS` | 接地 | 0V |
| P9 | `RING_OSC.OUTD` | 出力（常時駆動） | RING_OSC 低速リング出力（INV3Dベース、2026 版の実測 1.790 MHz） |
| P10 | `RING_OSC.OUT` | 出力（常時駆動） | RING_OSC 高速リング出力（INV_X1ベース、2026 版の実測 6.450 MHz） |
| P11 | `tx_data[4]` / `rx_data[4]` | 双方向 | 汎用データピン、ビット4 |
| P12 | `tx_data[5]` / `rx_data[5]` | 双方向 | 汎用データピン、ビット5 |
| P13 | `tx_data[6]` / `rx_data[6]` | 双方向 | 汎用データピン、ビット6 |
| P14 | `tx_data[7]` / `rx_data[7]` | 双方向 | 汎用データピン、ビット7 |
| P15 | `RSTN` | 入力（負論理） | チップリセット。`RING_OSC.ENB`と共有——リセット解除でコア動作開始と同時にRING_OSCも発振開始する。 |
| VDD | `VDD` | 電源 | 5.0V系 |

P3/P4/P5/P6/P11/P12/P13/P14の8本は、各ビットのtx（コアへの書き込み）と
rx（コアからの読み出し）が同一物理パッドを共有し、`DIS`（P7）で方向を
一括制御する構成——物理パッド番号の昇順とbit番号が単調対応する
（P3..P6=bit0-3、P11..P14=bit4-7）。P1/P2（SCL/SDA）は隣接パッドに
まとめて配置。WRITE中は`tx_data_i = rx_data_i`という自己ループバックが
構造的に生じる（意図した設計であり、テストベンチもこの経路を検証する
構成になっている）。

## 2. チップ概要

![Chip Image](docs/Chip_Image.png)

- プロセス: OpenSUSI TR-1um
- チップサイズ: 2.5mm × 2.5mm
- 構成: 非同期I2Cスレーブコア＋RING_OSCテスト構造＋OpenSUSIロゴ
  （コアとRING_OSCの間の空きスペースに、M2の3um角ドットでデジタイズ配置）
- 実機KLayoutでチップ全体の**DRC/LVSクリーン**を確認済み

**2026 MPW 改訂**（`src/` にあるのはこの版）: V10 から次を作り直した。

- **RSLATCH を特性化してセルとして使う**。V10 は NOR2 のたすき掛けで
  ラッチを作っていたが、`synth -flatten` の後で ABC が NOR3/NAND3 の
  生ループに吸収してしまい組合せループが 4 個できていた。ngspice で
  `RSLATCH` を特性化して `.lib` に入れ（NLDM 7x7、`<APRtools>/char/`）、
  RTL から直接インスタンス化して `blackbox` で守る形に変えた。
- **合成・配置・配線をゼロからやり直し**。4 行構成、コア 1611.0 x 963.2 µm、
  コア単体で DRC 0 / 短絡 0。
- **`RING_OSC` を現行の STDCELL 世代で描き直し**（セル高 64.8 -> 59.4、
  帯の高さ 244.8 -> 223.2 µm）。旧世代のセルが同名でコア側のセルを
  上書きして DRC が 8,449 件になる事故があり、取り込み方も直した。
- **チップ配線を作り直し**。`DIS` は P7 から 8 個のデータパッドへ配る
  1 ネットなので、幹 1 本 + 端点ごとの足にまとめた（32 本 -> 23 群、
  レーン 14 -> 10、総長 58,626 -> 47,511 µm）。電源バー <-> 電源 PAD は
  V10 と同じ幅 10 µm x 5 本。コアと `RING_OSC` の両脇の M2 電源を M1 に
  落として、`RING_OSC` の上下に M1 バスバーを足した（V10 の構成では
  `RING_OSC` にチップ電源が来ていなかった）。
- **検証を抽出ネットリストで**。LVS の照合に加えて、同じ抽出から
  ngspice 用のネットリストを起こして 14 項目を流している（5〜7 節）。

## 3. 回路設計

以下3〜7節は、設計元リポジトリ
[`TR-1um_Async_I2C`](https://github.com/jun1okamura/TR-1um_Async_I2C)
（RTL設計から配置配線・DRC/LVS・IRSIM検証・RING_OSC統合までの全設計
データ・スクリプト・`design_notes.md`による詳細記録一式）の内容を
要約した概要であり、詳細な経緯・実装・検証結果はすべて元リポジトリを
参照。

仕様書（NXP `UM10204` *I2C-bus specification and user manual* Rev. 5.0J）
準拠でRTLを設計し、機能検証→論理合成→ゲートレベルNETでの再検証、
という2段階の検証フローを踏んでいる。

- **RTL**: `i2c_slave_async.v`。`clk`ポートを持たない非同期設計——
  SCL立上りでビットサンプル、SCL立下りで出力更新、SDAエッジ
  （SCL=High中）でSTART/STOP検出する、バス信号のエッジのみで駆動される
  ステートマシン。
- **RTL検証（1段目）**: (a) MyHDLによるイベント駆動シミュレーションで
  バス機能モデル（マスタ）を使いwrite/read/誤アドレスNACKの3シナリオを
  検証。(b) iverilog/vvpによるVerilogテストベンチ（同3シナリオ）でも
  独立に検証。
- **論理合成**: Yosysで`TR1um_5_stdcell.lib`（プレースホルダLiberty）
  へのゲートマッピングを実施し、ゲートレベルネットリスト（NET）を生成。
  現行最終NETは`i2c_slave_async_net_v9_rowbuf.v`（137インスタンス）。
- **NET検証（2段目）**: 合成後のゲートレベルNETに対して、RTLと**同一の
  Verilogテストベンチ**を再実行し、RTLシミュレーション結果と一致する
  ことを確認（ゲートレベル等価性検証）。開発過程でこの段階を通じて
  実バグ2件（READアドレスバイト取り込み時の`bit_cnt`自己リセットと
  `rw`/`addr_match`取り込みの同一エッジレース、`sda_oe`⇔SDAパッド間の
  極性不一致）を発見し、RTLレベルで根本修正済み。

## 4. AP&R

`TR-1um_5_stdcell`（AND/OR/NAND/NOR/MUX/INV/BUF等）＋本プロジェクト
専用セル（`DFFR`: 非同期リセット付きDFF、`BUFTH`: しきい値バッファ、
SCL/SDA_INの行またぎ分配用）によるスタンダードセルベースの配置配線。

- **配置**: nrow（複数行）構成、行間に配線チャネルを設ける方式。
  行内セルのクロス行ネット数を最小化するFiduccia-Mattheysesハイパー
  グラフ分割で行割り当てを最適化。
- **配線**: 独自Pythonルータ（4パス方式: TAP電源メッシュ→行内ローカル
  配線→高FO/隣接ペア配線→複数行またぎ配線→強制ジョグ処理）＋汎用
  リップアップ&リルート後処理。**DRC違反0・短絡0件**を達成。
- **後処理**: 配線済みレイアウトを再配線せず、真に未使用な配線
  トラックのみを幾何学的に除去してチャネル高さを圧縮（コア高さを
  最大45.5%削減）。全トップレベルポートをコアBBOX端までM1/M2で
  引き出し、GIOフレーム側との結線に備える。
- **トップレベル統合**: GIO（I/Oパッドリング）⇔コアの結線・電源メッシュ
  構築も同じ独自ルータ体系で実施。パッド割り当ての変更（SCL/SDAの
  隣接パッド化等）にも同じ枠組みで対応済み。

### 4.1 2026 版で変えたところ

- **合成**: yosys。`RSLATCH` は `blackbox` で守り、`dfflibmap` +
  `abc -liberty -constr` でマッピング。`RSLATCH` の Liberty は ngspice
  特性化で作った（NLDM 7x7、SLEW 0.1〜16 ns / LOAD 10〜800 fF、
  area 1603.8、S->Q 2.676 ns、R->Q 1.242 ns、最小パルス幅 1.8501 ns）。
- **配置**: 4 行。行割り当ての FM 分割に**パッド近接の項**を足した
  （重み 16 / seed 4）。
- **配線**: コア 1611.0 x 963.2 µm、DRC 0 / 短絡 0。途中で見つけた
  ルータの実バグ 3 件（step10 の圧縮が step7/8 の配線を知らずに
  トラックを潰す / ch0 の高さが 5.4 グリッドに乗っていない / トップ
  ピンの左右振り分けが行単位）を直している。
- **チップ**: パッドリングのレーンは 10 本（`DIS` を幹 1 本にまとめる前は
  14 本）、リングは GND 884 / VDD 902。フレームの金属は四辺とも実測
  きっかり 920.0 までしか来ていない。

## 5. DRC/LVS

PDK の本物のデッキ（`TR-1um/libs.tech/klayout/tech/`）を当てている。
自前の軽いチェッカ（`drc_check_nrow_fm.py`、M1/M2/V1 の幅と間隔だけ）は
ルータの検算用で、最終判断には使わない——旧世代 STDCELL の混入で
DRC が 8,449 件になったとき、自前チェッカは 0 件のまま素通りした。

**DRC**（`run.drc` = 00_Layers + 01_Basics + 02_Device + 03_Electrical）

| | 違反 |
|---|---|
| コア単体 `i2c_slave_async_nrow_fm` | 0 |
| `RING_OSC` 単体 | 0 |
| チップ `tr_1um_jun1okamura_i2c` | **0** |
| MDP 後のマスク（`run_mdp.drc` -> `run_IP62.drc`） | **0** |

**LVS**（`run.lvs`）。ソース側は 3 階層とも**レイアウトを見ずに**
組み立てている（`layout/chip/simulation/README.md` に手順）。

| トップ | 素子 / ネット / ピン | 結果 |
|---|---|---|
| `i2c_slave_async_nrow_fm` | 1852 / 737 / 26 | Netlists match |
| `RING_OSC` | 808 / 201 / 5 | Netlists match |
| `tr_1um_jun1okamura_i2c` | 3288 / 1050 / 16 | Netlists match |

- コアのソースは合成後ネットリスト + セル単体の `.spice` + 配置 JSON の
  物理セル（FILL/TAP）から機械的に組み立てる。
- `RING_OSC` のソースは **xschem の回路図から**起こす（RTL が無いため）。
  1 リング 95 段 + AND 1 段が 2 本。レイアウトの実体数（INV_X1 97 /
  INV3D 95 / AND2_X1 2 / FILL2 206）が回路図とぴったり一致する。
- チップのソースは上の 2 つ + フレームの素子レベル `.spice` +
  `layout/chip/gio_connections.json` の接続表。

## 6. IRSIM

DRC/LVSクリーン確認済みのチップ全体netlistを、`OSS_ESD_5V_DIO`等の
ESDダイオードを除きトランジスタレベルまで再帰的にフラット化し
（BUFTHのみ、IRSIMのternaryスイッチレベルソルバでは正しく解けない
恒久的制限があるため、シミュレーション用にピン互換の`BUF_X1`へ機械的
置換）、スイッチレベルシミュレータ**IRSIM**上で実チップ相当の動作
検証を実施。

RTL/ゲートレベルのVerilogテストベンチ（`i2c_slave_async_tb.v`）と
1対1対応する自己検証型テストベンチを構築し、同じ3シナリオ・14項目の
チェックを実行:

1. アドレス`0x50`へのWRITEトランザクション（START〜ADDR+W〜ACK〜
   データ`0xA5`書き込み〜ACK〜STOP、書き込んだ`rx_data`が0xA5になる
   ことを含む）
2. 同アドレスからのREADトランザクション（START〜ADDR+R〜ACK〜
   `tx_data`=0x3Cとして読み出し〜マスタNACK〜STOP）
3. 誤アドレス（0x11）へのアクセスがNACKし、正しくidleへ戻ること

実機IRSIM（実キャリブレーション済み`TR-1um.prm`下）で実行した結果、
Verilog版と完全一致する**`All 14 checks PASSED`**を確認済み。DFFRB
（本設計の全フリップフロップセル）の内部記憶ノード（マスタ/スレーブ
両ラッチ）を非同期リセット時にクロックHIGH側で強制する実行時手法を
確立し、READトランザクション側で当初見つかった不具合も解消済み。

### 6.1 ngspice（2026 版、**レイアウト抽出から**）

IRSIM と**同じ 3 シナリオ・14 項目**を、レイアウト抽出ネットリストに
対して ngspice で流す。LVS に使う `.extracted` は比較のために平坦化して
あってネットが番号になるので、`klayout_extract.py` で階層とラベルを残した
まま抽出し直し、ngspice 用に 5 点だけ直している（`\$123` のエスケープ名、
角括弧、ダイオードの `A=`/`P=`、モデル名 `NMOSE`->`MNE`、素子を持たない
セル）。**W/L も AS/AD/PS/PD も抽出した実物の寸法**なので、拡散容量は
設計値ではなくレイアウトの実測。

`.tran 50n 544u 0 10n`、SCL=100 kHz、約 5 分:

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
---- RESULT ----  All 14 checks PASSED
```

刺激は V10 のテストベンチ（`reference/v10/`）をそのまま借りている。
パッド割り当てが同じなので `.measure` の時刻も流用できる。差し替えたのは
ネットの名前だけ。`RING_OSC` は外して流す（`ENB` = `RSTN` なので入れたままだと
544 µs のあいだ発振し続けて刻みが潰れる）。

### 6.2 STA（OpenSTA）

このコアにクロックは無く、最悪パスは `scl_n` <-> `scl_gated` の**半サイクル
パス**なので、`周期 - slack` では正しく出ない（最初その式で「Fmax 0.78 MHz」
という値が出た）。周期を 2 点振って `slack(T) = a*T + b` を解く方法に変えた。

| | |
|---|---|
| 周期係数 a | 0.50（= 半サイクルパス） |
| reg->reg が要求する最小周期 | **49.104 ns（20.36 MHz）** |
| パス遅延 | 24.552 ns |

I2C は Fast-mode+ でも 1 MHz なので 20 倍以上の余裕がある。

## 7. RING_OSCの説明

チップ上のテスト構造として、コア横に独立したリング発振器
`RING_OSC`を1個統合。97段（素数段——AND2_X1によるENBゲートと出力
バッファも含めた実段数）の2本のリング（共通のENB/VDD/VSSを共有）で
構成:

- `OUT`（→P10）: `INV_X1`（無装飾の素のインバータ）95段のチェーン＋
  `AND2_X1`（ENBゲート）＋出力バッファの計97段によるリング
- `OUTD`（→P9）: `INV3D`（出力ノード側にアンテナダイオード拡散を
  追加したインバータ）95段のチェーン＋`AND2_X1`（ENBゲート）＋
  出力バッファの計97段によるリング

`ENB`はチップの`RSTN`（P15）と共有——リセット解除（RSTN=High）と
同時にRING_OSCのループが閉じ発振を開始する。

**ngspice 実測**（2026 版。LVS クリーンのレイアウト抽出 netlist、
`.tran 100p 12u 0 500p uic`、VDD=5.0 V、RSTN は 0.5 µs で立ち上げ、
出力パッドに 10 pF）:

| リング | 周期 | 周波数 | 振幅 | 1 段あたり |
|---|---|---|---|---|
| `OUT`（P10） | 155.04 ns | **6.450 MHz** | −0.046 … 5.047 V | 0.808 ns |
| `OUTD`（P9） | 558.60 ns | **1.790 MHz** | −0.046 … 5.047 V | 2.910 ns |

（V10 は 6.508 / 1.558 MHz。RING_OSC を現行 STDCELL 世代で描き直した
ぶん少し変わっている。）

`INV3D` は `INV_X1` と **W/L が同じ**（PMOS 10.2/1.0、NMOS 3.4/1.0）で、
違うのはレイアウトだけ。抽出した拡散面積が `AS=539.5p` 対 `14.6p` と
桁違いなので、接合容量で 3.60 倍遅くなる。**回路図から作ったネットリスト
では両者は同じ回路になるので、この差は出てこない**——抽出から流している
意味がここに出る。

`OUTD`が`OUT`よりおよそ4.2倍遅いのは、`INV3D`のアンテナダイオード
拡散が出力（スイッチング）ノード側に直接ロードとして乗るため
（電源レール側ではなく出力ノード側の寄生容量が段遅延に効くため、
無装飾の`INV_X1`との差が段遅延に直接反映される）。両リングとも
RISE1→2とRISE3→4の周期がそれぞれ完全一致しており、定常発振である
ことを確認済み。

テストベンチ: `ring_osc/TB/tb_ring_osc.spice`（自己検証用ngspice
テストベンチ、OUT/OUTD波形・周期・電源電流の測定とASCII raw波形出力
を含む、設計元リポジトリの`ring_osc/TB/`配下）。

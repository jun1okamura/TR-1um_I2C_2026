# irsim/ — スイッチレベルシミュレーション

## REG4x16 / REG8x16（Nbit x 16word レジスタファイル）

**LVS がクリーンになったソースネットリスト `spice/REG4x16_src.spi` をそのまま
IRSIM に持ち込んで、実 R/C モデルで全レジスタアクセスを検証する。**

```sh
sh irsim/run_regx16.sh      # 4bit 全レジスタアクセス検証（合否まで表示）
sh irsim/run_regx16.sh 8    # 8bit
sh irsim/run_timing.sh      # 読出アクセス時間 / 書込レイテンシ / 最小 WEB パルス幅（4bit）
```

| ファイル | 内容 |
|---|---|
| `TR-1um.prm` | TR-1um 実モデルから校正したパラメータ（TR-1um_Async_I2C と共通） |
| `reg4x16.sim` / `reg8x16.sim` | `$APRTOOLS/apr/spi2sim.py` が LVS ソースから生成（1,076 Tr / 426 ノード、1,876 Tr / 705 ノード） |
| `reg4x16.cmd` / `reg8x16.cmd` | `$APRTOOLS/apr/gen_irsim_cmd.py --bits N` が生成。**`hdl/tb/tb_regx16.v` と同じベクタ・同じ期待値** |
| `reg4x16_timing.cmd` | `scripts/gen_irsim_timing.py` が生成。タイミング測定用 |
| `run_regx16.sh` / `run_timing.sh` | 実行 → 判定まで一発 |

### 時間分解能

```
stepsize 1     -> 1ns。以降の `s <n>` の n はすべて ns
settle 10      -> TLAT の帰還ノード(n2/n3)が背中合わせインバータなので、
                  一瞬の競合で X 判定されないよう落ち着く時間を与える
```

### 合否の出し方

IRSIM の `.cmd` 言語には条件分岐も算術も無いので、テストベンチのように
自前で pass/fail を数えられない。読出のたびに

```
print CHECK tag=T3_unique add=0101 exp=1010   ← 何を期待しているか
assert QV 1010                                 ← IRSIM 自身の判定（外れたらログに出る）
d AV QV                                        ← 実際の番地と値
```

の 3 行を出すので、**ログだけで完結して集計できる**（期待値ファイルは不要）。
`$APRTOOLS/apr/check_irsim_log.py` がタグ別に集計する。

### 結果

```
  T1_readback     PASS   16   FAIL    0     全ワード書込/読出
  T1_reverse      PASS   16   FAIL    0     逆順読出
  T2_walk1        PASS   64   FAIL    0     ウォーキング1
  T2_walk0        PASS   64   FAIL    0     ウォーキング0
  T3_unique       PASS  256   FAIL    0     デコーダ一意性（16通り全部）
  T4_no-write     PASS   16   FAIL    0     WEB=1 では書けない
  T4_write-ok     PASS   16   FAIL    0     WEB=0 なら書ける
  T5_hold         PASS   64   FAIL    0     保持
  合計  PASS 512 / FAIL 0    assertion failed 0 件
```

REG8x16（`sh irsim/run_regx16.sh 8`）は T2 が倍になるので **PASS 640 / FAIL 0**。

**どちらも Verilog 版（`hdl/run_regx16.sh [4|8]`）と完全に一致。** 読出に X は 1 回も出ていない。

### タイミング実測（TR-1um.prm, 1ns 分解能）

| | 値 |
|---|---:|
| 読出アクセス時間 `ADD` 変化 → `Q` 確定（0→1） | **14 ns** |
| 同（1→0） | 12 ns |
| 書込レイテンシ `WEB`↓ → `Q` 反映 | **12 ns** |
| 最小 `WEB` パルス幅 | 3 ns |

> **この数字は配線容量を含まない。** `.sim` に配線形状を持たせていないので、
> ビット線（M2 878 µm）やワードラインの容量は入っていない。実物はこれより遅い。
> ここで見ているのは「素子の R/C での論理と接続」であって、最終的な速度は
> レイアウト抽出（寄生込み）か SPICE で確認すること。
> TD4 は CPI=1 でクロックも遅いので、14 ns 程度なら余裕は十分ある。

### 分かったこと（タイミング制約）

- **アドレスと `WEB` を同時に動かしても安全。** WE バッファが INV 2 段、
  アドレス補が INV 1 段なので、`WEB` が効く頃にはアドレスが確定している。
- **`WEB`=0 のままアドレスを動かすと、通過したワードが全部書き換わる。**
  レベル書込なので当然。**アドレス確定 → `WEB` 立下げ → `WEB` 立上げ → 次のアドレス**
  の順を守ること。Verilog 版と IRSIM 版で同じ結果になった。

### 既知の警告

```
There are too many transistors in parallel (> 30)
      XT14_0.n3 / XT14_0.n2
```

IRSIM の `MAX_PARALLEL`（`base/globals.h`、既定 30）にぶつかっている。
**電源投入直後、ワードラインがまだ X で全 16 行のパスゲートが「導通かもしれない」
状態のときに、ビット線経由でアレイ全体が 1 つのステージになるため。**
アドレスが確定すれば 1 行しか導通しないので実害は無く、実際 512 項目すべてが
Verilog 版と一致している。気になる場合は `MAX_PARALLEL` を 64 にして
IRSIM をビルドし直せば消える。

---

## TD4 コア（これから）

```
irsim/
├── *.sim   ext2sim / 抽出結果から生成した .sim ネットリスト
├── *.prm   パラメータファイル（TR-1um 5V 用）
└── *.cmd   IRSIM コマンドスクリプト（ベクタ）
```

### 手順（Magic 系フロー）

```sh
magic -dnull -noconsole <<'EOT'
load td4_soc_rom
extract all
ext2sim labels on
ext2sim
quit
EOT
irsim TR-1um.prm td4_soc_rom.sim < td4_soc_rom.cmd
```

> REG4x16 は LVS ソースから `$APRTOOLS/apr/spi2sim.py` で直接 `.sim` を作った。
> レイアウトの寄生を入れたい場合は Magic の `ext2sim` 経由にする。

### 用途

- 全12命令の実行トレース（`hdl/tb/tb_td4_core.v` と同じベクタをそのまま移植する）
- 命令メモリ（RFCELL アレイ版）の読み書きマージン確認
- CPI=1 なので **1クロック内で「セレクタ→加算器→レジスタ」が閉じているか**の確認が主眼。
  C4004 と違って2相クロックのレース検証は不要。
- SPICE より桁違いに速いので、16命令のプログラムを丸ごと流せる。

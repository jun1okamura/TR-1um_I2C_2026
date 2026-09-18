# lef/ — 抽象化ライブラリ（LEF / Liberty）

TR-1um PDK には LEF も Liberty (.lib) も含まれていないので、ここで整備する。

| ファイル | 内容 |
|---|---|
| `TR-1um_STDCELL.gds` | セルライブラリ本体（レイアウト）。**これが唯一の正**  |
| `TR-1um_tech.lef` | LAYER / VIA / SITE 定義 — `$APRTOOLS/apr/mklef.py` で生成 |
| `TR-1um_cells.lef` | 全 48 MACRO（標準セル + アレイセル + `REG4x16` / `REG8x16`）— 同上 |
| `../scripts/tr1um.genlib` | Yosys/ABC 用の簡易 genlib — `$APRTOOLS/apr/cellinfo.py` で生成 |
| `../scripts/cell_area.json` | 全セルの実測寸法・面積・Tr 数 — 同上。面積見積りスクリプトが読む |

## GDS を直したら流すもの（この 3 つで全部追従する）

```sh
python3 $APRTOOLS/apr/pin_grid_check.py lef/TR-1um_STDCELL.gds          # 配置グリッド確認
python3 $APRTOOLS/apr/cellinfo.py       lef/TR-1um_STDCELL.gds \
        --genlib scripts/tr1um.genlib --areas scripts/cell_area.json --check
python3 $APRTOOLS/apr/mklef.py          lef/TR-1um_STDCELL.gds -o lef   # LEF 生成
```

面積の数値を**スクリプトに直接書かない**。`scripts/cell_area.json` を経由させる。
行高を 64.8 → 59.4 に変えたとき `area_estimate.py` の手書き表だけが取り残され、
組合せセルの面積を 8.3% 過大に見積もっていたため。

---

## 配置グリッド（2026-09-11 セル高さ変更後）— **判定 OK**

セル高さを **64.8 → 59.4 µm** に揃えた後の確認。`prBoundary` = (235,0) が BBOX。

**トラック = prBoundary 左端から 2.7 + n × 5.4 µm**（オフセットは半ピッチ）。
M2 ピン図形は全数が幅 3.4 µm で揃っており、3.4 + 2.0（スペース）= 5.4 と
ピッチがぴったり閉じている。**標準セル行に置くセル 39 個すべてがトラック上**。

### 直したもの

| セル | 指摘 | 現状 |
|---|---|---|
| `MUX2` | 高さ 64.8 のまま / 幅 35.0 が 5.4 の倍数でない（6.481×） | **32.4 × 59.4（6.000 サイト）** ピン 4 本とも 2.7/18.9/24.3/29.7 |
| `DFF` の `CK` | ピン中心が 8.00（`DFFRB`/`DFFS` は 8.10 で正しかった） | **8.10** に揃った |

### 設計意図どおりで、合否には数えないもの

- `DEC0` / `DEC2` / `DEC16` — 幅 114.0 は 5.4 の倍数でないが、**DEC2 は 90° 回転して使う**ので
  トラック方向になるのは高さ 86.4（= 16 × 5.4）の方。`DEC0` の prBoundary x0 = −2.4 も
  ミラー抱き合わせで電源ピンをセル境界上に置いているため
- `TLAT4B` / `TLAT8B` / `TLAT64` / `TLAT128` / `REG4x16` / `REG8x16` の高さ —
  行ピッチ 54.6（= 59.4 − 4.8 オーバーラップ）で積むので 5.4 の倍数にならない。
  縦方向の話なので、M2（縦配線）のトラックには影響しない

`$APRTOOLS/apr/pin_grid_check.py` は**高さが行高と一致するセルだけ**を合否に数え、
それ以外はマクロ／アレイとして情報表示に回す。

---

## LEF

```sh
python3 $APRTOOLS/apr/mklef.py lef/TR-1um_STDCELL.gds -o lef
```

セル高さ変更に合わせて更新した内容:

| | 変更前 | 変更後 | 根拠 |
|---|---|---|---|
| `SITE TR1UM` | 5.4 BY 64.8 | **5.4 BY 59.4** | 標準セル 39 個の実測値 |
| `METAL2 PITCH` | 5.0 | **5.4** | ピン中心の実測間隔 |
| `METAL2 OFFSET` | （無し） | **2.7** | prBoundary 左端からの最初のトラック |
| `METAL2 WIDTH` | 3.0 | **3.4** | M2 ピン図形すべて 3.4 |

`SPACING 2.0` はそのまま。**3.4 + 2.0 = 5.4** でピッチと閉じている。

### 結果: 48 MACRO / うち `SITE TR1UM` 付き 31 個

| MACRO | CLASS | SIZE | ピン |
|---|---|---|---|
| `REG8x16` | BLOCK | 399.600 × 933.000 | 23 |
| `REG4x16` | BLOCK | 248.400 × 933.000 | 15 |
| `DEC16` | BLOCK | 878.400 × 86.400 | 0 |
| `TLAT128` | BLOCK | 313.200 × 878.400 | 0 |
| `MUX2` | CORE | 32.400 × 59.400 | 4（SITE 付き） |
| `FILL1` | CORE SPACER | 5.400 × 59.400 | — （純フィラー、0 Tr） |
| `FILL2`/`FILL3` | CORE SPACER | 10.8 / 16.2 × 59.400 | — （**デキャップ**、下記） |
| `TAP2`/`TAP3` | CORE WELLTAP | 10.8 / 16.2 × 59.400 | — |

### `FILL2` / `FILL3` は空セルではなくデキャップ

名前はフィラーだが中身は **MOS 容量**。NMOS / PMOS とも L を伸ばした 1 個の
ゲートで、ゲートを反対側のレールに、拡散（両側）と基板を同じ側のレールに落としてある
（NMOS: ゲート→vdd / 拡散→vss、PMOS: ゲート→vss / 拡散→vdd。どちらも強反転で容量最大）。

| セル | W × L (P / N) | ゲート面積 | 容量 @ Cox 1.77 fF/µm² | セル面積比 |
|---|---|---:|---:|---:|
| `FILL2` (10.8 µm 幅) | 15.8×3.2 / 13.1×3.2 | 92.5 µm² | **164 fF** | 14% |
| `FILL3` (16.2 µm 幅) | 15.8×8.6 / 13.1×8.6 | 248.5 µm² | **440 fF** | 26% |
| `FILL1` (5.4 µm 幅) | — | 0 | 0（純フィラー） | — |

**行の隙間を `FILL2`/`FILL3` で埋めれば、それがそのまま電源デキャップになる。**
`FILL1` だけは幅 5.4 に容量が入らないので素の埋め物。
`cellinfo.py` がこの表を毎回出す。

`BLOCKS`（`CLASS BLOCK` 扱い）: `TLAT` `TAP2S` `REGBUF` `DEC0` `DEC2` `DEC16` `ADDBUF`
`TLAT4`〜`TLAT128` `REGBUF4` `REGBUF8` `REG4x16` `REG8x16`。アレイ内部で abut して使う
セルなので、P&R の行には流さない。

ピンがまだ入っていない MACRO（アレイ中間階層。上位から直接叩かないので実害なし）:
`DEC2` `DEC16` `REGBUF4` `REGBUF8` `TLAT4` `TLAT4B` `TLAT8` `TLAT8B` `TLAT64` `TLAT128`

---

## レイヤ / 規約（GDS 実測）

| GDS | 意味 | LEF |
|---|---|---|
| (13,0) | M1（横配線・電源レール） | `METAL1` W 1.8 / S 1.4 / pitch 3.2 |
| (19,0) | V1 | `VIA1` |
| (20,0) | M2（縦配線・ピンパッド） | `METAL2` W **3.4** / S 2.0 / pitch **5.4** / offset **2.7** |
| (48,0) | M1 ラベル | LVS が読むのはここ |
| (48,1) | 電源レール / 貫通ワードラインの内部ラベル | `USE POWER/GROUND SHAPE ABUTMENT` |
| (49,0) | M2 ラベル | LVS が読むのはここ |
| (49,1) | 信号ピン形状 | `PIN ... PORT` |
| (235,0) | セル境界（prBoundary = BBOX） | `SIZE` |
| (140,0) | N-well（境界を ±6.3 / +4.0 はみ出す） | — |

> **DRC/LVS のラベルは (48,0) と (49,0) だけ**。`drc/00_Layers.drc` は (48,1)/(49,1) を
> 読まないので、そこに書いたラベルは LVS に一切効かない（一度これで半日溶かした）。

- **SITE `TR1UM` = 5.4 × 59.4 µm**（ポリピッチ × 標準セル行高）。
  標準セルの幅はすべて `5.4 × n` なのでこのサイトに乗る。
- `REG4x16` / `REG8x16` はハードマクロなので `OBS` で M1/M2 とも全面をふさいである。

## 現状と TODO

- [x] 標準セル 39 種の MACRO（ピン・OBS 付き）、全数がグリッド上
- [x] `REG4x16`（15 ピン）/ `REG8x16`（23 ピン）の外形・ピン・OBS
- [x] `MUX2` の寸法、`DFF` の `CK` ピン位置
- [x] `FILL1` / `INV_X2` / `BUF_X2` を追加、genlib にも反映
- [ ] `TIEHI` / `TIELO` — 合成で定数を引くのに要る
- [x] `DECAP` — `FILL2` / `FILL3` が実体。フィラーと兼用
- [ ] アンテナダイオード、`ENDCAP`
- [ ] `TLAT` の `WR/WRB/RD/RDB` を (48,1) → (49,1) へ（現在は貫通 M1 として拾っている）
- [ ] `DEC0` / `ADDBUF` の信号ラベル（(49,1) の形状はあるがテキストが無い）
- [ ] Liberty (`.lib`) — タイミングは SPICE 特性化が要るので後回し
- [ ] `syn.sh` を `abc -g simple` から `scripts/tr1um.genlib` での実マッピングに切り替え

## Liberty を作るかどうか

`td4_soc_rom`（マスクROM版）は 76 セル / 3 行なので**手配置で十分**で、
LEF/Liberty は「TD4 を作るため」ではなく **C4004 に向けた投資**という位置づけ。
`td4_soc_arr` の論理部（FF 17 / 組合せ 66、約 83 セル）で P&R フローを通しておくと、
そのまま C4004（2,000 ゲート超）に使える。

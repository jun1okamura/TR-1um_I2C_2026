# scripts/

| スクリプト | 用途 |
|---|---|
| `pre_check.py` | (PDKテンプレート付属) GDS トップセル名 / dbu / bbox / フレーム検査 |
| `read_info.py` | (PDKテンプレート付属) `info.yaml` 読み出し |
| `syn.sh` | Yosys 合成 → 面積見積りを3構成まとめて実行 |
| `area_estimate.py` | Yosys の `stat` 出力を TR-1um 実セル面積に換算（C4004 版と共通、パーサのみ修正） |
| `area_custom.py` | 上記に C4004 のカスタムセル（RFCELL / TG-DFFE / 最小サイズ化）を適用した再見積り |
| `mem_array_estimate.py` | **命令メモリ 128bit を FF実装 / カスタムRFCELLアレイで作った場合の面積比較**（`07_memory_array.md` の数値の出どころ） |
| `tr1um.genlib` | Yosys/ABC 用 genlib（TR-1um STDLIB の実測面積入り） |
| `stat_td4_*.txt` | 2026-09-08 時点の合成結果（再現用の記録） |

## `area_estimate.py` の C4004 版との差分

新しい Yosys は `stat` を `<個数> <セル名>` の順で出力するため、
`<セル名> <個数>` しか受けていなかったパーサを **両方の順序を受ける**ように修正した。
面積テーブルと計算ロジックは C4004 版と同一。

## 依存

```sh
pip install yowasp-yosys --break-system-packages   # yowasp-yosys コマンドが入る
apt-get install -y iverilog
```

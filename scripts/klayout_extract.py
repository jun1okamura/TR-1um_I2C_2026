# copy: ok 薄皮。中身は $APRTOOLS/apr/klayout_extract.py を**ファイルで**読み込むだけ。
#          `scripts/pnr/lvs_pnr.py` が名前で import するので名前だけ残してある。
"""klayout_extract.py -- 薄皮。中身は `$APRTOOLS/apr/klayout_extract.py`。

`scripts/pnr/lvs_pnr.py` が `import klayout_extract` と**名前で**書いてあるので、
名前だけ残して**正本へ流す**（U94 / U99）。

★ **写しを置かない。** ここには 2026-09-18 まで**移行前の版**が置いてあった。
  正本は `--no-combine` を持つが、こちらは `combine_devices()` を常に掛ける
  古い版で、**U96（並列をまとめたネットリストで特性化していた）と同じ形の
  事故**をいつでも起こせる状態だった。U89 / U14 で 2 度踏んだのは、まさに
  「APRtools で直したのに設計側の古い写しを呼んだ」という形。

★ **名前ではなくファイルで読む**（U98）。`sys.path` 任せにすると、`config`
  のときのように**別物を掴む**。`$APRTOOLS` は `apr_path` と同じ探し方
  （`APRTOOLS` 環境変数 → リポジトリの隣）で決める。
"""
from __future__ import annotations

import importlib.util
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_apr = os.environ.get("APRTOOLS") or os.path.join(
    os.path.dirname(os.path.dirname(_here)), "TR-1um_APRtools")
_src = os.path.join(_apr, "apr", "klayout_extract.py")
if not os.path.exists(_src):
    raise SystemExit(
        f"** 正本が見つからない: {_src}\n"
        "   `export APRTOOLS=<APRtools を置いた場所>` してから回すこと\n"
        "   （このファイルは薄皮で、中身は APRtools 側にある。U94）")

_spec = importlib.util.spec_from_file_location("_apr_klayout_extract", _src)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_apr_klayout_extract"] = _mod
_spec.loader.exec_module(_mod)

# 正本の名前をそのまま生やす（`klayout_extract.build(...)` が動くように）
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_mod.main())

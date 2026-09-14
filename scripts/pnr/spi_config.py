"""spi_config.py -- 薄皮。中身は td4_config.py。

`TR-1um_Async_I2C` → `TR-1um_SCLK_SPI` と渡ってきた配線スクリプトは
`import spi_config as _cfg` と書いてある。**原本を書き換えると移植の監査証跡が
切れる**ので、名前だけ合わせてこちらへ流す。設定を触るときは td4_config.py を
直すこと。
"""
from td4_config import *          # noqa: F401,F403

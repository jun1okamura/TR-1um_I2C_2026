"""spi_config.py -- 薄皮。中身は i2c_config.py。

`TR-1um_Async_I2C` → `TR-1um_SCLK_SPI` → `TR-1um_TD4` と渡ってきた配線
スクリプトは `import spi_config as _cfg` と書いてある。**原本を書き換えると
移植の監査証跡が切れる**ので、名前だけ合わせてこちらへ流す。
設定を触るときは i2c_config.py を直すこと。
"""
from i2c_config import *          # noqa: F401,F403

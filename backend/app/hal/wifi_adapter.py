"""WiFi 适配器：仅占位，接口签名齐全，未来接入时再实现。

预留方案（写入注释供接手人参考）：
- ESP32 通过串口先广播自身 IP，或由用户手填 -> config 增加
  CHIPNEST_ESP_URL=http://192.168.x.x，经 HTTP 下发 LED 指令；
- 或使用 ESP-NOW / MQTT 云转发。二者都只需在下方三个方法里
  把串口写换成 HTTP POST /led {index,r,g,b} 即可，契约不变。
"""

from app.hal.base import BaseAdapter


class WifiAdapter(BaseAdapter):
    """占位实现：抛 NotImplementedError，禁止在生产路径误用。"""

    async def start(self) -> None:
        raise NotImplementedError("WiFiAdapter 尚未接入，请先用 SerialAdapter")

    async def stop(self) -> None:
        raise NotImplementedError("WiFiAdapter 尚未接入，请先用 SerialAdapter")

    async def send_led(self, index: int, r: int, g: int, b: int) -> bool:
        raise NotImplementedError("WiFiAdapter 尚未接入，请先用 SerialAdapter")

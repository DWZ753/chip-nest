// ChipNest LED Server —— ESP32/Arduino 灯带固件（与 backend HAL 协议一致）
// 协议：115200 8N1，行协议
//   PC→ESP  PING            → ESP→PC PONG
//   PC→ESP  LED:<idx>,<R>,<G>,<B>  （如 LED:25,255,165,0 = 橙色）
// 接线建议：NeoPixel DIN → 开发板 PIN（见下方宏），GND 共地，5V 供电。
// 依赖：Adafruit NeoPixel 库（库管理器搜索 "Adafruit NeoPixel" 安装）。

#include <Adafruit_NeoPixel.h>

// ---------- 按你的板子改这两行 ----------
#define LED_PIN 8          // NeoPixel 数据脚（可换 4/5/13 等）
#define NUMPIXELS 60       // 灯带灯珠总数（须 >= 最大 led_index + 1）

Adafruit_NeoPixel strip(NUMPIXELS, LED_PIN, NEO_GRB + NEO_KHZ800);

void setup() {
  Serial.begin(115200);          // 与电脑 HAL 的 PING/PONG 握手速率一致
  Serial.setTimeout(5000);
  strip.begin();
  strip.clear();
  strip.show();                  // 上电全灭
  // 上电即打印一行，方便上位机/串口监视器确认固件活着
  Serial.println("CHIPNEST-LED-SERVER READY");
}

void loop() {
  if (!Serial.available()) {
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();                   // 去掉 \r\n，兼容各平台
  if (line.length() == 0) {
    return;
  }

  if (line == "PING") {
    Serial.println("PONG");      // 握手：3 秒窗口内回应即被上位机接管
    return;
  }

  if (line.startsWith("LED:")) {
    int idx = -1, r = -1, g = -1, b = -1;
    if (sscanf(line.c_str(), "LED:%d,%d,%d,%d", &idx, &r, &g, &b) == 4) {
      setLed(idx, r, g, b);
    }
  }
  // 未知命令忽略（协议向后兼容）
}

void setLed(int idx, int r, int g, int b) {
  if (idx < 0 || idx >= NUMPIXELS) {
    return;                       // 越界灯号直接丢弃
  }
  // 输入限制在 0..255，防上位机脏数据
  r = constrain(r, 0, 255);
  g = constrain(g, 0, 255);
  b = constrain(b, 0, 255);
  strip.setPixelColor((uint16_t)idx, strip.Color((uint8_t)r, (uint8_t)g, (uint8_t)b));
  strip.show();
}

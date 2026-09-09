// 深浅主题 + 界面字号缩放：都持久化到 localStorage。
// light=true ⇔ html.light（日光浅色）；默认深色科技风。
// dark 是导出给组件用的反向计算量，语义就是“当前为深色”。
import { computed, ref } from 'vue'

const KEY = 'chipnest-theme'
const FONT_KEY = 'chipnest-font-scale'

function apply(light: boolean) {
  document.documentElement.classList.toggle('light', light)
}

const light = ref(document.documentElement.classList.contains('light'))
const dark = computed(() => !light.value)

const FONT_STEPS = [0.9, 1, 1.15, 1.3]
function readScale(): number {
  const v = Number.parseFloat(localStorage.getItem(FONT_KEY) ?? '')
  return FONT_STEPS.includes(v) ? v : 1
}
const fontScale = ref(readScale())
function applyFont(v: number) {
  document.documentElement.style.setProperty('--ui-zoom', String(v))
  localStorage.setItem(FONT_KEY, String(v))
}
applyFont(fontScale.value)

export function useTheme() {
  function setLight(wantLight: boolean) {
    light.value = wantLight
    apply(wantLight)
    localStorage.setItem(KEY, wantLight ? 'light' : 'dark')
  }
  function toggle() {
    setLight(!light.value)
  }
  function setFontScale(v: number) {
    if (!FONT_STEPS.includes(v)) return
    fontScale.value = v
    applyFont(v)
  }
  return { light, dark, setLight, toggle, fontScale, setFontScale, FONT_STEPS }
}

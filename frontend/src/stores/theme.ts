// 深浅主题 + 界面字号缩放：都持久化到 localStorage。
// 深色为默认科技风；html.light = 日光终端；字号用 CSS zoom 整体缩放。
import { ref } from 'vue'

const KEY = 'chipnest-theme'
const FONT_KEY = 'chipnest-font-scale'

function apply(light: boolean) {
  document.documentElement.classList.toggle('light', light)
}

const light = ref(document.documentElement.classList.contains('light'))

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
  function toggle() {
    light.value = !light.value
    apply(light.value)
    localStorage.setItem(KEY, light.value ? 'light' : 'dark')
  }
  function setFontScale(v: number) {
    if (!FONT_STEPS.includes(v)) return
    fontScale.value = v
    applyFont(v)
  }
  return { dark: light, toggle, fontScale, setFontScale, FONT_STEPS }
}

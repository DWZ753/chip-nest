<script setup lang="ts">
import { Boxes, ClipboardList, LayoutGrid, Moon, Search, Settings, Sun } from '@lucide/vue'

import { useBinsStore } from '../stores/bins'
import { useTheme } from '../stores/theme'
import ConnectionDot from './ConnectionDot.vue'

const emit = defineEmits<{
  openBom: []
  openLayout: []
  openSettings: []
}>()

const bins = useBinsStore()
const { dark, toggle } = useTheme()
// dark=true ⇔ 当前深色（默认）
</script>

<template>
  <header
    class="glass-panel sticky top-3 z-40 mx-auto flex w-[min(1400px,calc(100%-24px))] items-center gap-3 rounded-2xl px-4 py-2.5"
  >
    <!-- Logo -->
    <div class="flex items-center gap-2.5 pr-1">
      <div
        class="grid h-9 w-9 place-items-center rounded-xl text-white shadow-lg"
        style="background: linear-gradient(135deg, var(--accent-strong), var(--warm))"
      >
        <Boxes :size="19" stroke-width="2.2" />
      </div>
      <div class="hidden leading-tight md:block">
        <div class="title-gradient text-[15px] font-extrabold tracking-wide">
          ChipNest
        </div>
        <div class="text-[10px] font-medium tracking-[0.18em]" style="color: var(--text-faint)">
          智能元件管家
        </div>
      </div>
    </div>

    <!-- 中央巨大圆润搜索框 -->
    <div class="relative mx-auto w-full max-w-2xl flex-1">
      <Search
        :size="18"
        class="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2"
        style="color: var(--text-faint)"
      />
      <input
        v-model="bins.query"
        class="input !rounded-full !py-2.5 !pl-11 !pr-4 text-[15px]"
        placeholder="搜索元件：名称 / 阻值 / 封装 / 拼音首字母，如 10k、0603、dz…"
        type="search"
        @input="bins.setQuery(($event.target as HTMLInputElement).value)"
      />
    </div>

    <!-- 右侧操作 -->
    <div class="flex items-center gap-1">
      <button
        class="icon-btn"
        :title="dark ? '切换为浅色' : '切换为深色'"
        @click="toggle"
      >
        <Sun v-if="dark" :size="18" />
        <Moon v-else :size="18" />
      </button>
      <button
        class="icon-btn"
        title="BOM 导入"
        @click="emit('openBom')"
      >
        <ClipboardList :size="18" />
      </button>
      <button
        class="icon-btn"
        title="仓库布局"
        @click="emit('openLayout')"
      >
        <LayoutGrid :size="18" />
      </button>
      <button
        class="icon-btn"
        title="设置"
        @click="emit('openSettings')"
      >
        <Settings :size="18" />
      </button>
      <div class="mx-1 h-5 w-px" style="background: var(--line-strong)" />
      <ConnectionDot />
    </div>
  </header>
</template>
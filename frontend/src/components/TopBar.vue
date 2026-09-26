<script setup lang="ts">
import {
  Boxes, ChevronDown, ChevronUp, ClipboardList, LayoutGrid, Moon, Search,
  Settings, Sun,
} from '@lucide/vue'

import { useBinsStore } from '../stores/bins'
import { useTheme } from '../stores/theme'
import { useConnectionStore } from '../stores/connection'
import ConnectionDot from './ConnectionDot.vue'

const emit = defineEmits<{
  openBom: []
  openLayout: []
  openSettings: []
}>()

const bins = useBinsStore()
const connection = useConnectionStore()
const { dark, toggle } = useTheme()
// dark=true ⇔ 当前深色（默认）

function onSearchEnter(event: KeyboardEvent) {
  event.preventDefault()
  bins.navigateSearch(event.shiftKey ? -1 : 1)
}
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
          <span v-if="connection.version" class="mono ml-1 align-middle text-[9.5px] font-bold"
                style="color: var(--text-faint)">v{{ connection.version }}</span>
        </div>
        <div class="text-[10px] font-medium tracking-[0.18em]" style="color: var(--text-faint)">
          智能元件管家
        </div>
      </div>
    </div>

    <!-- 搜索框与匹配选项 -->
    <div class="relative mx-auto w-full max-w-2xl flex-1">
      <Search
        :size="18"
        class="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2"
        style="color: var(--text-faint)"
      />
      <input
        v-model="bins.query"
        class="input !rounded-full !py-2.5 !pl-11 !pr-36 text-[15px]"
        placeholder="搜索元件"
        type="search"
        :aria-invalid="!!bins.searchError"
        @input="bins.setQuery(($event.target as HTMLInputElement).value)"
        @keydown.enter="onSearchEnter"
      />
      <div class="absolute right-8 top-1/2 flex -translate-y-1/2 items-center gap-0.5">
        <button
          type="button"
          class="icon-btn !h-7 !w-7 !rounded-lg text-xs font-bold"
          :class="{ 'search-option-active': bins.searchOptions.matchCase }"
          title="区分大小写"
          aria-label="区分大小写"
          :aria-pressed="bins.searchOptions.matchCase"
          @click="bins.toggleSearchOption('matchCase')"
        >Aa</button>
        <button
          type="button"
          class="icon-btn !h-7 !w-7 !rounded-lg text-xs font-bold underline"
          :class="{ 'search-option-active': bins.searchOptions.wholeWord }"
          title="全字匹配"
          aria-label="全字匹配"
          :aria-pressed="bins.searchOptions.wholeWord"
          @click="bins.toggleSearchOption('wholeWord')"
        >ab</button>
        <button
          type="button"
          class="icon-btn !h-7 !w-7 !rounded-lg text-xs font-bold"
          :class="{ 'search-option-active': bins.searchOptions.useRegex }"
          title="使用正则表达式"
          aria-label="使用正则表达式"
          :aria-pressed="bins.searchOptions.useRegex"
          @click="bins.toggleSearchOption('useRegex')"
        >.*</button>
      </div>
      <div v-if="bins.searchError" class="absolute left-4 top-full mt-1 rounded-lg px-2 py-1 text-xs"
           style="color: var(--danger); background: var(--panel); border: 1px solid var(--danger)"
           role="status">{{ bins.searchError }}</div>
      <div v-if="bins.matchedIds !== null"
           class="absolute right-0 top-full mt-1 flex items-center gap-1 rounded-xl px-2 py-1 shadow-lg"
           style="background: var(--panel); border: 1px solid var(--line-strong)">
        <span class="mono mr-1 text-[11px]" style="color: var(--text-dim)" aria-live="polite">
          {{ bins.searchHitIds.length }} 个匹配
          <template v-if="bins.currentSearchIndex >= 0">
            · {{ bins.currentSearchIndex + 1 }}/{{ bins.searchHitIds.length }}
          </template>
        </span>
        <button type="button" class="icon-btn !h-6 !w-6 !rounded-md disabled:opacity-40"
                title="上一个匹配" aria-label="上一个匹配"
                :disabled="bins.searchHitIds.length === 0"
                @click="bins.navigateSearch(-1)"><ChevronUp :size="15" /></button>
        <button type="button" class="icon-btn !h-6 !w-6 !rounded-md disabled:opacity-40"
                title="下一个匹配" aria-label="下一个匹配"
                :disabled="bins.searchHitIds.length === 0"
                @click="bins.navigateSearch(1)"><ChevronDown :size="15" /></button>
      </div>
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

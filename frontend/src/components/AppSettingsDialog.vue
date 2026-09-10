<script setup lang="ts">
import {} from 'vue'
import {
  Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot,
} from '@headlessui/vue'
import { MonitorCog, Moon, Palette, Sun, X } from '@lucide/vue'

import { useConnectionStore } from '../stores/connection'
import { useTheme } from '../stores/theme'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const connection = useConnectionStore()
const { dark, setLight, fontScale, setFontScale, FONT_STEPS } = useTheme()
const SCALE_LABELS = ['小', '中', '大', '特大']

const MODE_TEXT = {
  serial: '串口模式',
  mock: '模拟模式',
} as Record<string, string>
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog as="div" class="relative z-50" @close="emit('close')">
      <TransitionChild as="template" enter="duration-200 ease-out" enter-from="opacity-0"
                       leave="duration-150 ease-in" leave-to="opacity-0">
        <div class="fixed inset-0 bg-black/60 backdrop-blur-[6px]" />
      </TransitionChild>
      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4">
          <TransitionChild as="template" enter="duration-200 ease-out"
                           enter-from="opacity-0 translate-y-3 scale-95"
                           enter-to="opacity-100 translate-y-0 scale-100"
                           leave="duration-150 ease-in" leave-to="opacity-0 translate-y-3 scale-95">
            <DialogPanel class="glass-strong flex max-h-[88vh] w-full max-w-md flex-col rounded-2xl p-5">
              <div class="mb-4 flex items-center gap-2.5">
                <Palette :size="17" style="color: var(--accent)" />
                <DialogTitle class="text-base font-extrabold">设置</DialogTitle>
                <button class="icon-btn ml-auto !h-8 !w-8" @click="emit('close')"><X :size="16" /></button>
              </div>

              <div class="flex flex-col gap-4">
                <!-- 外观 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 flex items-center gap-2 text-[13px] font-extrabold">外观</div>
                  <div class="flex flex-wrap items-center gap-3">
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="dark ? 'opacity-55' : ''"
                      :style="!dark ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setLight(true)"
                    ><Sun :size="12" class="mr-1 inline" />浅色</button>
                    <button
                      class="chip !cursor-pointer !px-3 !py-1.5"
                      :class="dark ? '' : 'opacity-55'"
                      :style="dark ? 'color: var(--accent); border-color: var(--accent)' : ''"
                      @click="setLight(false)"
                    ><Moon :size="12" class="mr-1 inline" />深色</button>
                  </div>
                </section>

                <!-- 字号 -->
                <section class="rounded-2xl p-4" style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-3 text-[13px] font-extrabold">字号</div>
                  <div class="flex flex-wrap items-center gap-1.5">
                    <button v-for="(s, i) in FONT_STEPS" :key="s"
                            class="chip !cursor-pointer !px-3 !py-1.5"
                            :class="fontScale === s ? '' : 'opacity-55 hover:opacity-90'"
                            :style="fontScale === s ? 'color: var(--accent); border-color: var(--accent)' : ''"
                            @click="setFontScale(s)">
                      {{ SCALE_LABELS[i] }}
                    </button>
                  </div>
                </section>

                <!-- 版本 -->
                <section class="flex items-center justify-between rounded-2xl px-4 py-3 text-[12.5px]"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <span class="font-bold">版本</span>
                  <span class="mono font-bold" style="color: var(--accent)">
                    {{ connection.version ? 'v' + connection.version : '—' }}
                  </span>
                </section>

                <!-- 硬件状态 -->
                <section class="rounded-2xl px-4 py-3 text-[12.5px]"
                         style="background: var(--panel); border: 1px solid var(--line)">
                  <div class="mb-1.5 flex items-center gap-2 text-[13px] font-extrabold">
                    <MonitorCog :size="15" style="color: var(--accent-strong)" /> 硬件
                  </div>
                  <div class="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                    <span class="chip"
                          :style="connection.status.mode === 'serial' ? 'color: var(--success)' : 'color: var(--warn)'">
                      {{ MODE_TEXT[connection.status.mode] ?? connection.status.mode }}
                    </span>
                    <span style="color: var(--text-dim)">设备：{{ connection.status.device ?? '—' }}</span>
                    <span style="color: var(--text-faint)">{{ connection.status.error ?? '' }}</span>
                  </div>
                </section>
              </div>

              <div class="mt-5 flex justify-end">
                <button class="btn btn-ghost" @click="emit('close')">关闭</button>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
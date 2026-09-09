<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, CircleCheck, PackageOpen, X } from '@lucide/vue'

import { api, ApiError } from '../api/client'
import type { BomStep } from '../api/types'
import { useBinsStore, zoneName } from '../stores/bins'

const props = defineProps<{ open: boolean; steps: BomStep[] }>()
const emit = defineEmits<{ close: []; finished: [] }>()

const bins = useBinsStore()

const index = ref(0)
const direction = ref<'right' | 'left'>('right')
const picking = ref(false)
const phase = ref<'go' | 'done' | 'abort'>('go')
const message = ref<string | null>(null)

const step = computed<BomStep | null>(
  () => props.steps[index.value] ?? null,
)

watch(
  () => [props.open, props.steps] as const,
  ([open]) => {
    if (!open) return
    index.value = 0
    direction.value = 'right'
    phase.value = 'go'
    message.value = null
    picking.value = false
    syncGuide()
  },
)

watch(step, () => syncGuide())

function syncGuide() {
  const s = step.value
  if (s && phase.value === 'go') {
    bins.setGuidePosition({
      zone: s.component.zone,
      layer: s.component.layer,
      slot: s.component.slot,
    })
  } else {
    bins.setGuidePosition(null)
  }
}

async function pickNext() {
  const s = step.value
  if (!s || phase.value !== 'go') return
  picking.value = true
  message.value = null
  try {
    const updated = await api.pickBom(s.component.id, s.quantity)
    bins.upsert(updated)          // 即时刷新卡片数量
    bins.setGuidePosition(null)   // 短暂离开高亮再跳到下一步
    if (index.value + 1 >= props.steps.length) {
      phase.value = 'done'
      return
    }
    direction.value = 'right'
    index.value += 1
  } catch (e) {
    phase.value = 'abort'
    message.value = e instanceof ApiError
      ? `${e.message}（余量 ${e.available ?? '?'}）—— 请先补货再继续引导`
      : e instanceof Error ? e.message : String(e)
    bins.setGuidePosition(null)
  } finally {
    picking.value = false
  }
}

function abort() {
  bins.setGuidePosition(null)
  phase.value = 'abort'
  message.value = null
  emit('close')
}

function done() {
  bins.setGuidePosition(null)
  emit('finished')
  emit('close')
}
</script>

<template>
  <Teleport to="body">
      <div
        v-if="open"
        class="fixed inset-0 z-[60] flex items-center justify-center overflow-hidden"
        style="background: radial-gradient(circle at 50% 40%, rgba(20, 18, 15, 0.42), rgba(16, 14, 12, 0.66))"
      >
        <!-- 巨幕步数 -->
        <div class="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div class="step-number num text-[26vh] font-black leading-none opacity-[0.16]" style="color: #fff">
            {{ index + 1 }}<span class="text-[12vh]">/{{ steps.length }}</span>
          </div>
        </div>

        <!-- 当前步卡片 -->
        <div class="relative mx-4 w-[min(560px,100%)]">
          <template v-if="phase === 'go' && step">
            <div
              :key="step.component.id + ':' + index"
              class="glass-strong rounded-[28px] p-7 text-center"
              :class="direction === 'right' ? 'step-in-right' : 'step-in-left'"
              style="box-shadow: 0 30px 80px -20px rgba(0,0,0,0.55)"
            >
              <div class="mb-1 text-[11px] font-bold tracking-[0.3em]" style="color: rgba(255,255,255,0.65)">
                {{ index + 1 }} / {{ steps.length }} · {{ zoneName(bins.layout, step.component.zone) }}/{{ step.component.layer }}层/{{ step.component.slot }}格
              </div>
              <div class="text-3xl font-black text-white">{{ step.component.name }}</div>
              <div class="mt-2 flex items-center justify-center gap-2">
                <span v-if="step.component.value" class="chip !text-white/85 !bg-white/10 !border-white/15 mono text-[15px]">
                  {{ step.component.value }}
                </span>
                <span v-if="step.component.package" class="chip !text-white/70 !bg-white/10 !border-white/15 mono">
                  {{ step.component.package }}
                </span>
                <span v-if="step.component.led_index !== null" class="chip !text-amber-200 !bg-amber-400/15 !border-amber-300/25 mono">
                  ● 灯 {{ step.component.led_index }}
                </span>
              </div>

              <div class="my-5 text-2xl font-black text-amber-300">请取走 × {{ step.quantity }}</div>

              <div class="flex items-center justify-center gap-3">
                <button class="btn !rounded-full !px-6 !py-3 text-base font-extrabold" :disabled="picking"
                        style="background: rgba(255,255,255,.1); border-color: rgba(255,255,255,.25); color: #fff"
                        @click="abort">
                  <X :size="17" /> 中止
                </button>
                <button class="btn !rounded-full !px-8 !py-3 text-base font-extrabold text-white" :disabled="picking"
                        style="background: linear-gradient(120deg, #d98f3e, #e8b45c); box-shadow: 0 14px 30px -10px rgba(220, 140, 50, 0.6)"
                        @click="pickNext">
                  <PackageOpen :size="18" /> 已取走，下一步
                </button>
              </div>
            </div>
          </template>

          <!-- 完成 -->
          <div v-else-if="phase === 'done'" class="glass-strong fade-up rounded-[28px] p-9 text-center">
            <CircleCheck :size="52" class="mx-auto mb-3" style="color: #8fce9c" />
            <div class="text-2xl font-black text-white">引导完成 🎉</div>
            <div class="mt-1 text-sm" style="color: rgba(255,255,255,0.65)">
              共 {{ steps.length }} 步已全部出库
            </div>
            <button class="btn btn-primary mt-6" @click="done"><Check :size="16" /> 完成</button>
          </div>

          <!-- 中断 -->
          <div v-else class="glass-strong fade-up rounded-[28px] p-7 text-center"
               style="border-color: rgba(255,120,100,0.5)">
            <div class="text-lg font-extrabold" style="color: #ffb4a8">引导中断</div>
            <div class="mt-2 text-[13px] leading-relaxed" style="color: rgba(255,255,255,0.75)">
              {{ message ?? '已中止引导' }}
            </div>
            <button class="btn mt-5" style="background: rgba(255,255,255,0.12)" @click="abort">关闭</button>
          </div>
        </div>
      </div>
  </Teleport>
</template>
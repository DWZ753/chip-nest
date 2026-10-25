import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'

import type { ComponentItem } from '../api/types'
import { positionKey, useBinsStore, zoneGrid } from '../stores/bins'
import type { BinPosition } from '../stores/bins'
import { create_motion } from '../utils/motion'
import { classify_drop } from '../utils/grid_drag_state'
import type { DragCell } from '../utils/grid_drag_state'

interface DragState {
  component: ComponentItem
  from: BinPosition
  shared: boolean
  phase: 'dragging' | 'saving' | 'settling'
  target: DragCell | null
  other: ComponentItem | null
  committed: boolean
  grab_x: number
  grab_y: number
}

interface PendingPointer {
  id: number
  element: HTMLElement
  cell: DragCell
  x: number
  y: number
}

/** @brief Own card pickup, direct manipulation and transactional placement. */
export function use_grid_drag(
  root: Ref<HTMLElement | null>, enabled: Readonly<Ref<boolean>>,
  notify: (message: string) => void,
) {
  const bins = useBinsStore()
  const state = ref<DragState | null>(null)
  const hover = ref<{ key: string; valid: boolean } | null>(null)
  const pose = ref({ x: 0, y: 0, width: 1, height: 1, scale: 1,
    other_x: 0, other_y: 0, other_width: 1, other_height: 1 })
  const busy = computed(() => state.value?.phase === 'saving')
  let pending: PendingPointer | null = null
  let pointer_x = 0
  let pointer_y = 0
  let scroll_frame = 0
  let suppress_until = 0
  let message = ''
  let success = false
  let resolve_drop: ((placed: boolean) => void) | null = null
  let hovered_cell: DragCell | null = null

  const motion = create_motion(pose.value, values => { pose.value = values },
    () => {
      if (state.value?.phase !== 'settling') return

      state.value = null
      hover.value = null
      if (message) notify(message)
      resolve_drop?.(success)
      resolve_drop = null
    })

  /** @brief Convert viewport pixels into the body's zoomed layout units. */
  function bounds(element: HTMLElement) {
    const rect = element.getBoundingClientRect()
    const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1

    return { x: rect.x / zoom, y: rect.y / zoom,
      width: rect.width / zoom, height: rect.height / zoom }
  }

  /** @brief Bind physical slot identity to card and empty-slot roots. */
  function attributes(cell: DragCell) {
    return {
      'data-grid-slot': positionKey(cell.pos),
      'data-grid-kind': cell.kind,
      'data-grid-row': cell.row,
      'data-grid-col': cell.col,
      'data-grid-columns': cell.colSpan,
      'data-grid-rows': cell.rowSpan,
    }
  }

  /** @brief Read the rendered cell beneath the pointer, ignoring the ghost. */
  function cell_from_element(element: HTMLElement): DragCell {
    const [zone, layer, slot] = element.dataset.gridSlot!.split(':').map(Number)

    return {
      pos: { zone: zone!, layer: layer!, slot: slot! },
      kind: element.dataset.gridKind as DragCell['kind'],
      comp: bins.components.find(item =>
        item.id === Number(element.dataset.componentId)),
      row: Number(element.dataset.gridRow),
      col: Number(element.dataset.gridCol),
      colSpan: Number(element.dataset.gridColumns),
      rowSpan: Number(element.dataset.gridRows),
    }
  }

  /** @brief Merged cards can contain a landing position beyond their anchor. */
  function contains(cell: DragCell, pos: BinPosition) {
    const columns = zoneGrid(bins.layout, pos.zone)[1]
    const row = Math.floor(pos.slot / columns)
    const col = pos.slot % columns

    return cell.pos.zone === pos.zone && cell.pos.layer === pos.layer &&
      row >= cell.row && row < cell.row + cell.rowSpan &&
      col >= cell.col && col < cell.col + cell.colSpan
  }

  /** @brief Find the current rendering after API or viewport changes. */
  function find_element(pos: BinPosition, component_id?: number) {
    return Array.from(root.value?.querySelectorAll<HTMLElement>(
      '[data-grid-slot]',
    ) ?? []).find(element => {
      const cell = cell_from_element(element)

      return (component_id === undefined || cell.comp?.id === component_id) &&
        contains(cell, pos)
    })
  }

  /** @brief Show a valid landing surface without changing grid geometry. */
  function hit_test() {
    const element = document.elementFromPoint(pointer_x, pointer_y)
      ?.closest<HTMLElement>('[data-grid-slot]')
    const current = state.value

    hovered_cell = element && root.value?.contains(element)
      ? cell_from_element(element) : null

    const key = hovered_cell ? positionKey(hovered_cell.pos) : ''
    const valid = !!current && classify_drop(current.component,
      current.from, hovered_cell) !== 'invalid'

    if (hover.value?.key !== key || hover.value?.valid !== valid) {
      hover.value = { key, valid }
    }
  }

  /** @brief Keep long shelves reachable while the cursor stays near an edge. */
  function auto_scroll() {
    const main = root.value?.closest('main')
    const scroller = document.elementFromPoint(pointer_x, pointer_y)
      ?.closest<HTMLElement>('.overflow-x-auto')
    const main_rect = main?.getBoundingClientRect()
    const row_rect = scroller?.getBoundingClientRect()

    if (state.value?.phase !== 'dragging') return

    if (main && main_rect) {
      main.scrollTop += edge_speed(pointer_y, main_rect.top, main_rect.bottom)
    }
    if (scroller && row_rect && root.value?.contains(scroller)) {
      scroller.scrollLeft += edge_speed(
        pointer_x, row_rect.left, row_rect.right)
    }
    hit_test()
    scroll_frame = requestAnimationFrame(auto_scroll)
  }

  /** @brief Scale edge scrolling continuously up to fourteen pixels/frame. */
  function edge_speed(pointer: number, start: number, end: number) {
    if (pointer < start + 42) return -Math.min(14, (start + 42 - pointer) / 3)
    if (pointer > end - 42) return Math.min(14, (pointer - end + 42) / 3)
    return 0
  }

  /** @brief Detach pointer work before capture loss or a store update. */
  function release_pointer() {
    const held = pending

    pending = null
    cancelAnimationFrame(scroll_frame)
    window.removeEventListener('pointermove', pointer_move)
    window.removeEventListener('pointerup', pointer_up)
    window.removeEventListener('pointercancel', cancel)
    window.removeEventListener('lostpointercapture', cancel)
    if (held?.element.hasPointerCapture(held.id)) {
      held.element.releasePointerCapture(held.id)
    }
  }

  /** @brief Lift the existing card without inserting space into its grid. */
  function prepare(element: HTMLElement, cell: DragCell, x: number, y: number) {
    const rect = bounds(element)
    const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1
    const component = { ...cell.comp! }

    message = ''
    success = false
    state.value = {
      component, from: { ...cell.pos },
      shared: positionKey(cell.pos) !== positionKey(component),
      phase: 'dragging', target: null, other: null, committed: false,
      grab_x: x / zoom - rect.x, grab_y: y / zoom - rect.y,
    }
    motion.jump({ ...rect, scale: 1, other_x: rect.x, other_y: rect.y,
      other_width: rect.width, other_height: rect.height })
    motion.set({ scale: 1.035 })
  }

  /** @brief A short press retains the existing click/keyboard pickup path. */
  function start(event: PointerEvent, cell: DragCell) {
    if (!enabled.value || event.button !== 0 || state.value || !cell.comp ||
      (event.target as HTMLElement).closest('button,a,input')) return

    const element = event.currentTarget as HTMLElement

    pending = { id: event.pointerId, element, cell,
      x: event.clientX, y: event.clientY }
    element.setPointerCapture(event.pointerId)
    window.addEventListener('pointermove', pointer_move)
    window.addEventListener('pointerup', pointer_up)
    window.addEventListener('pointercancel', cancel)
    window.addEventListener('lostpointercapture', cancel)
  }

  /** @brief Follow the pointer directly; only lift and landing use springs. */
  function pointer_move(event: PointerEvent) {
    const held = pending

    if (!held || event.pointerId !== held.id) return

    pointer_x = event.clientX
    pointer_y = event.clientY
    if (!state.value) {
      if (Math.hypot(pointer_x - held.x, pointer_y - held.y) < 5) return
      prepare(held.element, held.cell, held.x, held.y)
      scroll_frame = requestAnimationFrame(auto_scroll)
    }

    const current = state.value!
    const zoom = Number.parseFloat(getComputedStyle(document.body).zoom) || 1

    event.preventDefault()
    motion.jump({ x: pointer_x / zoom - current.grab_x,
      y: pointer_y / zoom - current.grab_y })
    hit_test()
  }

  /** @brief Commit at release, never while merely hovering over a slot. */
  function pointer_up(event: PointerEvent) {
    if (!pending || event.pointerId !== pending.id) return

    if (state.value) {
      pointer_x = event.clientX
      pointer_y = event.clientY
      hit_test()
      suppress_until = performance.now() + 250
      void drop(hovered_cell)
    }
    release_pointer()
  }

  /** @brief Land on the updated card, including merged sizes. */
  function landing_pose(current: DragState) {
    const destination = current.committed && current.target
      ? current.target.pos : current.from
    const element = find_element(destination, current.component.id)
    const other_element = current.other
      ? find_element(current.from, current.other.id) : null
    const rect = element ? bounds(element) : pose.value
    const other = other_element ? bounds(other_element) : null

    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height,
      scale: 1, ...(other ? { other_x: other.x, other_y: other.y,
        other_width: other.width, other_height: other.height } : {}) }
  }

  /** @brief Save one move or one atomic swap, then land both identities. */
  async function commit(target: DragCell) {
    const current = state.value!
    const kind = classify_drop(current.component, current.from, target)
    const target_element = find_element(target.pos, target.comp?.id)

    current.target = target
    current.phase = 'saving'
    if (kind === 'swap' && target.comp && target_element) {
      const rect = bounds(target_element)

      current.other = { ...target.comp }
      motion.jump({ other_x: rect.x, other_y: rect.y,
        other_width: rect.width, other_height: rect.height })
    }
    try {
      if (kind === 'swap') {
        await bins.swapComponents(current.component.id, target.comp!.id)
        message = `已把「${current.component.name}」与「${target.comp!.name}」互换`
      } else if (current.shared) {
        await bins.moveSlot(current.component.id, current.from, target.pos)
        message = '共用格已移动'
      } else {
        await bins.moveComponent(current.component.id, target.pos)
        message = `已移动「${current.component.name}」`
      }
      current.committed = true
      success = true
    } catch (error) {
      message = `移动失败：${error instanceof Error ? error.message : String(error)}`
      current.other = null
      await bins.refreshAll().catch(() => undefined)
      current.committed = bins.compsByKey[positionKey(target.pos)]?.id ===
        current.component.id
    }
    await nextTick()
    if (state.value !== current) return

    current.phase = 'settling'
    motion.set(landing_pose(current))
  }

  /** @brief Start release handling, including cancellation outside the grid. */
  function drop(target: DragCell | null): Promise<boolean> {
    const current = state.value

    if (!current) return Promise.resolve(false)

    const kind = classify_drop(current.component, current.from, target)

    return new Promise(resolve => {
      resolve_drop = resolve
      if (kind === 'origin' || kind === 'invalid') {
        message = kind === 'invalid' ? '未选择可用格子' : ''
        current.phase = 'settling'
        motion.set(landing_pose(current))
      } else {
        void commit(target!)
      }
    })
  }

  /** @brief Reuse visible placement for clicks and keyboard controls. */
  async function place(component: ComponentItem, from: BinPosition,
    destination: BinPosition) {
    const element = find_element(from, component.id)
    const target = find_element(destination)

    if (state.value || !element || !target) return false

    const rect = element.getBoundingClientRect()

    prepare(element, { ...cell_from_element(element), pos: from },
      rect.x + rect.width / 2, rect.y + rect.height / 2)
    return drop(cell_from_element(target))
  }

  /** @brief Return an unsaved card on Escape, blur or cancellation. */
  function cancel() {
    release_pointer()
    if (state.value?.phase !== 'dragging') return
    state.value.phase = 'settling'
    message = ''
    motion.set(landing_pose(state.value))
  }

  function key_down(event: KeyboardEvent) {
    if (event.key !== 'Escape' || (!state.value && !pending)) return
    if (state.value?.phase === 'settling') return
    event.preventDefault()
    event.stopImmediatePropagation()
    cancel()
  }

  function resize() {
    if (state.value?.phase === 'settling') {
      motion.set(landing_pose(state.value))
    } else {
      cancel()
    }
  }

  /** @brief A dragged release must not also select the underlying slot. */
  function capture_click(event: MouseEvent) {
    if ((state.value || performance.now() < suppress_until) &&
      (event.target as HTMLElement).closest('[data-grid-slot]')) {
      event.preventDefault()
      event.stopImmediatePropagation()
    }
  }

  /** @brief Dim origins, mark targets, and keep landing ghosts single-owned. */
  function classes(cell: DragCell) {
    const current = state.value
    const key = positionKey(cell.pos)
    const source = !!current && cell.comp?.id === current.component.id &&
      contains(cell, current.from)
    const covered = !!current && !!current.target &&
      ((current.committed && cell.comp?.id === current.component.id &&
        contains(cell, current.target.pos)) ||
      (!!current.other && cell.comp?.id === current.other.id &&
        contains(cell, current.committed ? current.from : current.target.pos)))

    return {
      'grid-drag-enabled': enabled.value && !!cell.comp,
      'grid-drag-source': source && !covered,
      'grid-drag-covered': covered,
      'grid-drop-target': hover.value?.key === key && hover.value.valid,
      'grid-drop-invalid': hover.value?.key === key && !hover.value.valid,
    }
  }

  watch(enabled, active => { if (!active) cancel() })

  onMounted(() => {
    window.addEventListener('keydown', key_down, true)
    window.addEventListener('blur', cancel)
    window.addEventListener('resize', resize)
  })
  onBeforeUnmount(() => {
    release_pointer()
    motion.stop()
    state.value = null
    resolve_drop?.(false)
    window.removeEventListener('keydown', key_down, true)
    window.removeEventListener('blur', cancel)
    window.removeEventListener('resize', resize)
  })

  return { state, pose, busy, attributes, classes, start, place, cancel,
    capture_click }
}

export type GridDragController = ReturnType<typeof use_grid_drag>

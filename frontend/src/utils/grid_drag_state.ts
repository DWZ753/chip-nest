import type { ComponentItem } from '../api/types'
import type { BinPosition } from '../stores/bins'

/** A rendered physical card or slot, including merged card geometry. */
export interface DragCell {
  pos: BinPosition
  kind: 'card' | 'shared' | 'empty' | 'blocked'
  comp?: ComponentItem
  row: number
  col: number
  colSpan: number
  rowSpan: number
}

/** @brief Resolve a drop without changing inventory or UI state. */
export function classify_drop(
  component: ComponentItem, from: BinPosition, target: DragCell | null,
): 'origin' | 'move' | 'swap' | 'invalid' {
  if (!target || target.kind === 'blocked') return 'invalid'
  if (from.zone === target.pos.zone && from.layer === target.pos.layer &&
    from.slot === target.pos.slot) return 'origin'
  if (target.kind === 'empty') return 'move'

  const shared = from.zone !== component.zone ||
    from.layer !== component.layer || from.slot !== component.slot
  const other = target.comp

  if (shared || !other || other.id === component.id ||
    other.zone !== target.pos.zone || other.layer !== target.pos.layer ||
    other.slot !== target.pos.slot) return 'invalid'

  return 'swap'
}

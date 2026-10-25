import assert from 'node:assert/strict'
import test from 'node:test'

import { classify_drop } from '../src/utils/grid_drag_state.ts'

const component = { id: 1, zone: 1, layer: 1, slot: 0 }
const other = { id: 2, zone: 1, layer: 1, slot: 2 }
const cell = (slot, kind = 'empty', comp) => ({
  pos: { zone: 1, layer: 1, slot }, kind, comp,
  row: 0, col: slot, colSpan: 1, rowSpan: 1,
})

test('empty cells accept a primary or a shared position', () => {
  assert.equal(classify_drop(component, component, cell(3)), 'move')
  assert.equal(classify_drop(component, cell(1).pos, cell(3)), 'move')
})

test('blocked cells and drops outside the shelf are rejected', () => {
  assert.equal(classify_drop(component, component, null), 'invalid')
  assert.equal(classify_drop(component, component, cell(3, 'blocked')),
    'invalid')
})

test('primary exchange preserves stock', () => {
  assert.equal(classify_drop(component, component, cell(2, 'card', other)),
    'swap')
})

test('shared and same-component targets reject primary moves', () => {
  assert.equal(classify_drop(component, component,
    cell(1, 'shared', component)),
    'invalid')
  assert.equal(classify_drop(component, cell(1).pos, cell(2, 'card', other)),
    'invalid')
  assert.equal(classify_drop(component, component, cell(3, 'shared', other)),
    'invalid')
})

test('returning to the pickup position is cancellation without a write', () => {
  assert.equal(classify_drop(component, component, cell(0, 'card', component)),
    'origin')
})

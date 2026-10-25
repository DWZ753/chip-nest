import assert from 'node:assert/strict'
import test from 'node:test'

import { MotionStrip, spring_step } from '../src/utils/motion_state.ts'

const order = ['appearance', 'hardware', 'backup', 'cleanup', 'about']

test('reversal reuses the visible source instead of relocating it', () => {
  const strip = new MotionStrip('appearance')

  assert.equal(strip.select('hardware', 0, order), 1)
  assert.equal(strip.select('appearance', .45, order), 0)
  assert.equal(strip.offset('hardware'), 1)
})

test('a third target preserves visible page positions', () => {
  const strip = new MotionStrip('appearance')

  strip.select('hardware', 0, order)
  assert.equal(strip.select('backup', .4, order), 2)
  assert.equal(strip.offset('appearance'), 0)
  assert.equal(strip.offset('hardware'), 1)
  assert.equal(strip.select('appearance', .7, order), 0)
})

test('long-distance requests enter beside the viewport', () => {
  const strip = new MotionStrip('appearance')

  assert.equal(strip.select('about', 0, order), 1)
  assert.equal(strip.select('hardware', .6, order), -1)
  assert.equal(strip.offset('appearance'), 0)
  assert.equal(strip.offset('about'), 1)
})

test('rapid targets never overwrite either visible page', () => {
  const strip = new MotionStrip(order[0])
  let position = 0
  let velocity = 0
  let target = 0
  let index = 0
  let key = ''
  let visible = []
  let offsets = []

  for (index = 0; index < 1800; index += 1) {
    visible = order.map(page => [page, strip.offset(page)]).filter(
      ([, offset]) => offset !== undefined && Math.abs(offset - position) < 1,
    )
    key = order[(index * 7 + Math.floor(index / 11)) % order.length]
    target = strip.select(key, position, order)
    visible.forEach(([page, offset]) =>
      assert.equal(strip.offset(page), offset))
    offsets = order.map(page => strip.offset(page)).filter(
      offset => offset !== undefined,
    )
    assert.equal(new Set(offsets).size, offsets.length)
    ;[position, velocity] = spring_step(position, velocity, target, .016)
  }
})

test('redirected spring decelerates, reverses and settles', () => {
  let position = .3
  let velocity = 4
  let iteration = 0

  ;[position, velocity] = spring_step(position, velocity, 0, .008)
  assert.ok(position > .3)
  assert.ok(velocity > 0 && velocity < 4)

  for (iteration = 0; iteration < 160; iteration += 1) {
    ;[position, velocity] = spring_step(position, velocity, 0, .016)
  }

  assert.ok(Math.abs(position) < .00001)
  assert.ok(Math.abs(velocity) < .0001)
})

import assert from 'node:assert/strict'
import { registerHooks } from 'node:module'
import test from 'node:test'

registerHooks({
  resolve(specifier, context, next) {
    return next(specifier === './motion_state'
      ? './motion_state.ts' : specifier, context)
  },
})

const { create_motion } = await import('../src/utils/motion.ts')

/** @brief Supply deterministic browser frames and accessibility preferences. */
function browser_driver(t, reduced = false) {
  const names = ['matchMedia', 'requestAnimationFrame', 'cancelAnimationFrame']
  const originals = names.map(name =>
    [name, Object.getOwnPropertyDescriptor(globalThis, name)])
  const frames = new Map()
  const listeners = new Set()
  const media = {
    matches: reduced,
    addEventListener: (_, callback) => listeners.add(callback),
    removeEventListener: (_, callback) => listeners.delete(callback),
  }
  let identifier = 0
  let timestamp = 0

  Object.assign(globalThis, {
    matchMedia: () => media,
    requestAnimationFrame: callback => {
      identifier += 1
      frames.set(identifier, callback)
      return identifier
    },
    cancelAnimationFrame: id => frames.delete(id),
  })
  t.after(() => originals.forEach(([name, descriptor]) => {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor)
    else delete globalThis[name]
  }))

  return {
    pending: () => frames.size,
    subscriptions: () => listeners.size,
    reduce: () => {
      media.matches = true
      listeners.forEach(callback => callback())
    },
    step: count => {
      let index = 0
      let callbacks = []

      for (index = 0; index < count; index += 1) {
        callbacks = [...frames.values()]
        frames.clear()
        timestamp += 16
        callbacks.forEach(callback => callback(timestamp))
      }
    },
  }
}

test('retargeting keeps current values and owns only one pending frame', t => {
  const driver = browser_driver(t)
  let completed = 0
  const motion = create_motion({ position: 0, height: 300 }, () => {},
    () => { completed += 1 })

  motion.set({ position: 1, height: 40 })
  driver.step(8)

  const current = motion.read()

  motion.set({ position: 0, height: 280 })
  assert.deepEqual(motion.read(), current)
  assert.equal(driver.pending(), 1)
  driver.step(120)
  assert.deepEqual(motion.read(), { position: 0, height: 280 })
  assert.equal(completed, 1)
  motion.stop()
  assert.equal(driver.pending(), 0)
  assert.equal(driver.subscriptions(), 0)
})

test('reduced motion selects the endpoint immediately', t => {
  const driver = browser_driver(t, true)
  const motion = create_motion({ position: 0, height: 300 }, () => {})

  motion.set({ position: 1, height: 60 })
  assert.deepEqual(motion.read(), { position: 1, height: 60 })
  assert.equal(driver.pending(), 0)
  motion.stop()
})

test('changing the motion preference finishes and removes pending work', t => {
  const driver = browser_driver(t)
  const motion = create_motion({ position: 0 }, () => {})

  motion.set({ position: 1 })
  driver.step(3)
  assert.ok(motion.read().position > 0 && motion.read().position < 1)
  driver.reduce()
  assert.deepEqual(motion.read(), { position: 1 })
  assert.equal(driver.pending(), 0)
  motion.stop()
  assert.equal(driver.subscriptions(), 0)
})

test('visual endpoints finish within 352ms', t => {
  const driver = browser_driver(t)
  const motion = create_motion({ position: 0, height: 0 }, () => {})

  motion.set({ position: 1, height: 300 })
  driver.step(22)
  assert.deepEqual(motion.read(), { position: 1, height: 300 })
  assert.equal(driver.pending(), 0)
  motion.stop()
})

test('direct pointer updates do not snap the concurrent lift animation', t => {
  const driver = browser_driver(t)
  const motion = create_motion({ x: 0, scale: 1 }, () => {})

  motion.set({ scale: 1.035 })
  driver.step(2)

  const scale = motion.read().scale

  motion.jump({ x: 120 })
  assert.equal(motion.read().x, 120)
  assert.equal(motion.read().scale, scale)
  assert.equal(driver.pending(), 1)
  driver.step(60)
  assert.equal(motion.read().scale, 1.035)
  motion.stop()
})

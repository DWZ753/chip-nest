import { spring_step } from './motion_state'

/** @brief Own the frame, position and velocity of a UI surface. */
export function create_motion<T extends Record<string, number>>(
  initial: T, render: (values: T) => void, rest?: () => void,
) {
  const values = { ...initial }
  const target = { ...initial }
  const velocity = Object.fromEntries(
    Object.keys(initial).map(key => [key, 0]),
  ) as T
  const keys = Object.keys(initial) as (keyof T)[]
  const reduced = matchMedia('(prefers-reduced-motion: reduce)')
  let frame = 0
  let previous = 0

  /** @brief Finish immediately when reduced motion is enabled. */
  function finish() {
    cancelAnimationFrame(frame)
    frame = 0
    Object.assign(values, target)
    keys.forEach(key => { velocity[key] = 0 as T[keyof T] })
    render({ ...values })
  }

  /** @brief Integrate every property on the same animation frame. */
  function tick(timestamp: number) {
    const delta = previous ? (timestamp - previous) / 1000 : .016
    let settled = true

    previous = timestamp
    keys.forEach(key => {
      const [position, speed] = spring_step(
        values[key], velocity[key], target[key], delta,
      )
      values[key] = position as T[keyof T]
      velocity[key] = speed as T[keyof T]
      // Page offsets and scales are unitless; other values are pixels.
      const epsilon = key === 'position' ? .002 : key === 'scale' ? .001 : .35
      const speed_limit = key === 'position' ? .05 : key === 'scale' ? .03 : 8

      settled &&= Math.abs(position - target[key]) < epsilon &&
        Math.abs(speed) < speed_limit
    })

    render({ ...values })

    if (settled || reduced.matches) {
      finish()
      rest?.()
    } else {
      frame = requestAnimationFrame(tick)
    }
  }

  /** @brief Changing the target retains current positions and velocities. */
  function set(next: Partial<T>, immediate = false) {
    Object.assign(target, next)

    if (immediate || reduced.matches) {
      finish()
      rest?.()
    } else if (!frame) {
      previous = 0
      frame = requestAnimationFrame(tick)
    }
  }

  /** @brief Apply a changed accessibility preference during an animation. */
  function change_preference() {
    if (reduced.matches) {
      finish()
      rest?.()
    }
  }

  reduced.addEventListener('change', change_preference)

  return {
    set,
    read: () => ({ ...values }),
    // Direct manipulation updates only the grabbed coordinates.
    jump: (next: Partial<T>) => {
      ;(Object.keys(next) as (keyof T)[]).forEach(key => {
        values[key] = next[key] as T[keyof T]
        target[key] = values[key]
        velocity[key] = 0 as T[keyof T]
      })
      render({ ...values })
    },
    stop: () => {
      cancelAnimationFrame(frame)
      reduced.removeEventListener('change', change_preference)
    },
  }
}

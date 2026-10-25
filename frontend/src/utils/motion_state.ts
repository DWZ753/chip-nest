/** Continuous positions for adjacent, cached content pages. */
export class MotionStrip {
  private positions = new Map<string, number>()
  private selected: string

  constructor(key: string) {
    this.selected = key
    this.positions.set(key, 0)
  }

  /** @brief Reuse visible pages; place new targets beyond the edge. */
  select(key: string, position: number, order: string[]): number {
    const existing = this.positions.get(key)
    const previous = this.selected
    const direction = order.indexOf(key) >= order.indexOf(previous) ? 1 : -1
    const target = existing !== undefined && Math.abs(existing - position) <= 1
      ? existing
      : direction > 0 ? Math.ceil(position - .00001) + 1
        : Math.floor(position + .00001) - 1

    this.selected = key

    this.positions.forEach((offset, page_key) => {
      if (offset === target && page_key !== key) {
        this.positions.delete(page_key)
      }
    })
    this.positions.set(key, target)

    return target
  }

  /** @brief Return the location of a visited page, if still on the strip. */
  offset(key: string): number | undefined {
    return this.positions.get(key)
  }
}

/** @brief Advance a damped spring without discarding its velocity. */
export function spring_step(
  position: number, velocity: number, target: number, delta: number,
): [number, number] {
  const step = Math.min(delta, .032) / 4
  let iteration = 0

  for (iteration = 0; iteration < 4; iteration += 1) {
    velocity += ((target - position) * 900 - velocity * 60) * step
    position += velocity * step
  }

  return [position, velocity]
}

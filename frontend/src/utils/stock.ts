/** 库存策略：按入库量推导一个省心的补货阈值。 */

/**
 * 入库 100 → 阈值 20（20%），入库 3 → 1，入库 0 → 5（维持老默认）。
 * 目的：初次入库填了数量后，阈值自动跟着定，不用每次手动改；
 * 想自定义时直接在界面上改，改过之后就不再自动覆盖。
 */
export function suggestThreshold(quantity: number): number {
  const qty = Math.max(0, Math.floor(quantity || 0))
  if (qty <= 0) return 5
  return Math.max(1, Math.min(9999, Math.round(qty * 0.2)))
}

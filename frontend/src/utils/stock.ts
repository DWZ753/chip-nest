/** 库存策略：按入库量推导一个省心的补货阈值。 */

/**
 * 入库 100 → 阈值 20（20%），入库 5 → 阈值 2，入库 0 → 5（维持老默认）。
 * 目的：初次入库填了数量后阈值自动跟着定，不用每次手动改；填完仍可手动微调，
 * 之后再改入库数量会按新数量重算一次。只对"新建元件"生效，改已有元件不动它的阈值。
 */
export function suggestThreshold(quantity: number): number {
  const qty = Math.max(0, Math.floor(quantity || 0))
  if (qty <= 0) return 5
  return Math.min(9999, Math.max(2, Math.round(qty * 0.2)))
}

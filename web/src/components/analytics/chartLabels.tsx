// Recharts Line label renderers: direct labels at the right end of each series.
// Labels are stacked so series ending at similar values do not overlap; each label only
// yields to series earlier in `order`, so placement is stable across re-renders (e.g. hover).
export const createEndLabelStack = (order: string[], minGap = 12) => {
  const placed = new Map<string, number>()
  return (seriesKey: string, text: string, lastIndex: number) => (props: any) => {
    const { x, y, index } = props
    if (index !== lastIndex || x == null || y == null) return null
    const earlier = order
      .slice(0, Math.max(0, order.indexOf(seriesKey)))
      .map((k) => placed.get(k))
      .filter((v): v is number => v != null)
    let target = y
    let moved = true
    while (moved) {
      moved = false
      for (const e of earlier) {
        if (Math.abs(target - e) < minGap) {
          target = e + minGap
          moved = true
        }
      }
    }
    placed.set(seriesKey, target)
    return (
      <text key={seriesKey} x={x + 6} y={target} dy={4} fontSize={10} fontWeight={600} fill="#475569">
        {text}
      </text>
    )
  }
}

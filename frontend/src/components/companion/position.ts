export type Position = { x: number; y: number }
export const companionSize = { width: 76, height: 132 }
export type Obstacle = { left: number; top: number; right: number; bottom: number }
export function overlaps(position: Position, box: Obstacle) {
  return position.x < box.right + 4 && position.x + companionSize.width > box.left - 4 &&
    position.y < box.bottom + 4 && position.y + companionSize.height > box.top - 4
}
export function safePosition(position: Position, width: number, height: number, obstacles: Obstacle[]): Position | null {
  if (width < 180 || height < 340) return null
  const docked = dockPosition(position, width, height)
  const candidates = [docked]
  for (let y = 88; y <= height - companionSize.height - 104; y += 16) {
    candidates.push({ x: 4, y }, { x: width - companionSize.width - 4, y })
  }
  return candidates.sort((a, b) => Math.hypot(a.x - docked.x, a.y - docked.y) - Math.hypot(b.x - docked.x, b.y - docked.y))
    .find(candidate => !obstacles.some(box => overlaps(candidate, box))) || null
}
export function clampPosition(position: Position, width: number, height: number): Position {
  return { x: Math.max(0, Math.min(width - companionSize.width, position.x)),
    y: Math.max(70, Math.min(Math.max(70, height - companionSize.height - 104), position.y)) }
}
export function dockPosition(position: Position, width: number, height: number): Position {
  return clampPosition({ x: position.x < width / 2 ? 4 : width - companionSize.width - 4, y: position.y }, width, height)
}

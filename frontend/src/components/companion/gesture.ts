export class Gesture {
  private active = false
  private held = false
  private dragged = false
  private x = 0
  private y = 0
  private at = 0
  start(x: number, y: number, now: number) { this.active = true; this.held = false; this.dragged = false; this.x = x; this.y = y; this.at = now }
  move(x: number, y: number) { if (this.active && Math.hypot(x - this.x, y - this.y) >= 8) this.dragged = true; return this.dragged }
  hold(now: number, random = Math.random): 'invite' | 'react' | null {
    if (!this.active || this.dragged || this.held || now - this.at < 600) return null
    this.held = true
    return random() < 0.3 ? 'invite' : 'react'
  }
  end(x: number, y: number, _now: number): 'tap' | 'drag' | 'held' | null {
    if (!this.active) return null
    this.move(x, y); this.active = false
    return this.dragged ? 'drag' : this.held ? 'held' : 'tap'
  }
  cancel() { this.active = false }
}

import test from 'node:test'
import assert from 'node:assert/strict'
import { clampPosition, dockPosition, safePosition, overlaps } from '../src/components/companion/position'
import { Gesture } from '../src/components/companion/gesture'

test('safe interior positions do not snap to an edge', () => {
  assert.deepEqual(safePosition({ x: 430, y: 220 }, 1440, 1000, []), { x: 430, y: 220 })
})

test('corrupt persisted coordinates recover to finite viewport bounds', () => {
  const next = clampPosition({ x: Number.NaN, y: Number.POSITIVE_INFINITY }, 390, 844)
  assert.ok(Number.isFinite(next.x) && Number.isFinite(next.y))
})

test('tap, drag and long press are distinct; probability has an exact boundary', () => {
  const gesture = new Gesture()
  gesture.start(20, 30, 0)
  assert.equal(gesture.end(20, 30, 200), 'tap')
  gesture.start(20, 30, 0); gesture.move(100, 30)
  assert.equal(gesture.hold(800, () => 0), null)
  assert.equal(gesture.end(20, 30, 900), 'drag')
  gesture.start(20, 30, 0)
  assert.equal(gesture.hold(599, () => 0), null)
  assert.equal(gesture.hold(600, () => 0.2999), 'invite')
  assert.equal(gesture.hold(700, () => 0), null)
  assert.equal(gesture.end(20, 30, 800), 'held')
  gesture.start(20, 30, 0)
  assert.equal(gesture.hold(600, () => 0.3), 'react')
  gesture.cancel()
  assert.equal(gesture.end(20, 30, 1000), null)
})

test('dragging and resizing keep the companion inside phone and desktop bounds', () => {
  for (const [width,height] of [[320,568],[390,844],[800,600],[1440,900]]) {
    for (const position of [{x:-100,y:-100},{x:9999,y:9999},{x:150,y:240}]) {
      const clamped = clampPosition(position,width,height)
      assert.ok(clamped.x>=0 && clamped.x+76<=width)
      assert.ok(clamped.y>=70 && clamped.y+132+104<=height)
      const docked = dockPosition(position,width,height)
      assert.ok(docked.x===4 || docked.x===width-80)
    }
  }
})

test('docking avoids controls and hides when no safe space remains', () => {
  const obstacles = [{ left: 0, top: 110, right: 390, bottom: 300 }]
  const position = safePosition({ x: 310, y: 120 }, 390, 844, obstacles)
  assert.ok(position)
  assert.equal(overlaps(position, obstacles[0]), false)
  assert.equal(safePosition({ x: 310, y: 120 }, 390, 844, [{ left: 0, top: 0, right: 390, bottom: 844 }]), null)
  assert.equal(safePosition({ x: 0, y: 0 }, 100, 200, []), null)
})

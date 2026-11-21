import { useEffect, useRef } from 'react'

/** KYMPS-inspired directional scene reveal, rendered as soft cloud puffs. */
export default function FogTransition({ sequence }: { sequence: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas || !sequence || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const bounds = canvas.getBoundingClientRect()
    const width = bounds.width, height = bounds.height
    const scale = Math.min(window.devicePixelRatio || 1, 1.5)
    canvas.width = width * scale; canvas.height = height * scale
    ctx.setTransform(scale, 0, 0, scale, 0, 0)
    const sprite = document.createElement('canvas'); sprite.width = sprite.height = 128
    const brush = sprite.getContext('2d')!
    const gradient = brush.createRadialGradient(64, 64, 0, 64, 64, 64)
    gradient.addColorStop(0, 'rgba(244,250,255,.72)')
    gradient.addColorStop(.35, 'rgba(222,238,245,.45)')
    gradient.addColorStop(1, 'rgba(210,230,243,0)')
    brush.fillStyle = gradient; brush.fillRect(0, 0, 128, 128)
    const clouds = Array.from({ length: width < 600 ? 45 : 90 }, () => ({
      born: Math.random() * .45, lane: Math.random(), speed: .8 + Math.random() * .4,
      radius: 80 + Math.random() * 160, phase: Math.random() * Math.PI * 2,
    }))
    let frame = 0
    const started = performance.now()
    function draw(now: number) {
      if (!ctx) return
      const time = (now - started) / 1000
      ctx.clearRect(0, 0, width, height)
      if (document.hidden || time > 2.2) return
      for (const cloud of clouds) {
        const age = time - cloud.born
        if (age <= 0) continue
        const travel = age * cloud.speed / 1.35
        const x = width * (1.2 - travel * 1.6) + Math.sin(age * 2 + cloud.phase) * 45
        const y = height * (cloud.lane * .65 + travel * .4 - .15)
        const size = cloud.radius * (1 + age * .65)
        ctx.globalAlpha = Math.max(0, Math.min(1, age * 4, (1.7 - age) * 1.8)) * .6
        ctx.drawImage(sprite, x - size, y - size, size * 2, size * 2)
      }
      ctx.globalAlpha = 1
      frame = requestAnimationFrame(draw)
    }
    frame = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(frame); ctx.clearRect(0, 0, width, height) }
  }, [sequence])
  return <canvas ref={ref} className="grow-fog" aria-hidden="true" />
}

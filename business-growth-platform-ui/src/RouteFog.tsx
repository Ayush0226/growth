import { useEffect, useState } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'
import './route-fog.css'

/** Visual-only reveal; navigation, auth and browser history are never delayed. */
export default function RouteFog() {
  const { pathname } = useLocation()
  const navigationType = useNavigationType()
  const [disabled, setDisabled] = useState(false)
  useEffect(() => { if (navigationType !== 'POP') window.scrollTo(0, 0) }, [pathname, navigationType])
  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => {
      try { setDisabled(media.matches || localStorage.getItem('growboard.motion') === 'off') } catch { setDisabled(media.matches) }
    }
    update()
    media.addEventListener('change', update)
    window.addEventListener('growboard-motion-change', update)
    return () => { media.removeEventListener('change', update); window.removeEventListener('growboard-motion-change', update) }
  }, [])
  if (disabled) return null
  return <div key={pathname} className="gb-route-fog" aria-hidden="true"><i/><i/><i/><i/><i/><i/></div>
}

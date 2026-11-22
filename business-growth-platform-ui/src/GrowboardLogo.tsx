/** An open G built from a rising ribbon, from favicon to billboard. */
export default function GrowboardLogo({ className = '', wordmark = true }: { className?: string; wordmark?: boolean }) {
  return <span className={`gb-logo ${className}`}><svg viewBox="0 0 64 64" fill="none" aria-hidden="true"><path d="M53 18A25 25 0 1 0 56 40H33V29h23v11" stroke="currentColor" strokeWidth="11" strokeLinejoin="round"/><path d="M44 5h15v15" stroke="currentColor" strokeWidth="7" strokeLinejoin="round"/></svg>{wordmark && <span>growboard<span className="gb-logo-period">.</span></span>}</span>
}

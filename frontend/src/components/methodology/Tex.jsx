import 'katex/dist/katex.min.css'
import { renderTex } from './renderTex'

// Inline math:  <Tex>{String.raw`a_i`}</Tex>
export function Tex({ children }) {
  return <span className="tex" dangerouslySetInnerHTML={{ __html: renderTex(children) }} />
}

// Inline math as a tagged template, so backslashes need no escaping:  {T`\hat\beta`}
export const T = (strings, ...values) => <Tex>{String.raw(strings, ...values)}</Tex>

// A display equation with an optional number on the right, e.g.
//   <Eq tag={3}>{String.raw`r_i = o_i + d_i`}</Eq>
// The number is also the element id, so <Ref n={3} /> can scroll to it.
export function Eq({ tag, children }) {
  return (
    <div className="eq" id={tag ? `eq-${tag}` : undefined}>
      <div className="eq-body" dangerouslySetInnerHTML={{ __html: renderTex(children, true) }} />
      {tag ? <span className="eq-tag">({tag})</span> : <span />}
    </div>
  )
}

function scrollToId(id) {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  document.getElementById(id)?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
}

// A reference to a numbered equation. A <button> and not an <a href="#...">:
// the app uses HashRouter, so a bare hash link would be read as a route.
export function Ref({ n }) {
  return (
    <button type="button" className="ref" onClick={() => scrollToId(`eq-${n}`)}>
      ({n})
    </button>
  )
}

// A boxed statement: Proposition, Remark, Example, Algorithm.
export function Callout({ kind, label, n, title, children }) {
  return (
    <div className={`callout callout-${kind}`}>
      <p className="callout-head">
        <strong>
          {label}
          {n ? ` ${n}` : ''}.
        </strong>
        {title ? <span className="callout-title"> {title}.</span> : null}
      </p>
      {children}
    </div>
  )
}

// "Proof." ... ∎  (the square is added by CSS after the last paragraph)
export function Proof({ children }) {
  return (
    <div className="proof">
      <span className="proof-label">Proof.</span> {children}
    </div>
  )
}

// Which file implements the section, as small monospace chips.
export function Source({ files }) {
  return (
    <p className="source">
      <span>Implemented in</span>
      {files.map((file) => (
        <code key={file}>{file}</code>
      ))}
    </p>
  )
}

export function Figure({ n, caption, children }) {
  return (
    <figure className="method-figure">
      {children}
      <figcaption>
        <strong>Figure {n}.</strong> {caption}
      </figcaption>
    </figure>
  )
}

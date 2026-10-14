import katex from 'katex'

// Shorthands used throughout the methodology page. \Pr, \ker, \argmax-style
// operators and the like come with KaTeX; these are the few it doesn't have.
const MACROS = {
  '\\R': '\\mathbb{R}',
  '\\E': '\\mathbb{E}',
  '\\T': '^{\\top}',
  '\\pinv': '^{+}',
  '\\ind': '\\mathbf{1}',
  '\\argmin': '\\operatorname*{arg\\,min}',
  '\\argmax': '\\operatorname*{arg\\,max}',
}

const cache = new Map()

// LaTeX in, HTML (plus hidden MathML for screen readers) out. Every string
// passed in is written in this repo -- never user input -- so injecting the
// result as HTML is safe. throwOnError is off so a typo shows up as red source
// text on that one formula instead of taking the whole page down.
export function renderTex(source, display = false) {
  const key = `${display ? 'd' : 'i'}:${source}`
  if (!cache.has(key)) {
    cache.set(
      key,
      katex.renderToString(source, {
        displayMode: display,
        throwOnError: false,
        macros: { ...MACROS }, // KaTeX may write into this object, so give it a copy
      }),
    )
  }
  return cache.get(key)
}

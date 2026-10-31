import { useEffect, useState } from 'react'

/**
 * Run an async `fetcher` and track its result: { data, error, isLoading }.
 *
 * `fetcher` is a function that takes no arguments and returns a promise, such as
 * `fetchRankings` from api.js. The request runs on mount and again whenever the
 * `fetcher` function itself changes, so a fetch that depends on a value needs a
 * stable function per value:
 *
 *   const load = useCallback(() => fetchTeamDetail(teamId), [teamId])
 *   const { data, error, isLoading } = useFetch(load)
 *
 * Pass `null` to skip fetching (for example, until an id is known). Nothing runs,
 * isLoading is false, and `data` from an earlier fetch is left as it was.
 *
 * - `error` is the failure's message (a string), or null.
 * - While a new fetcher's request is in flight, isLoading is true, `error` is null
 *   and the previous `data` is kept, so check `isLoading` before trusting `data`.
 * - A response that arrives after the fetcher changed or the component unmounted
 *   is ignored.
 */
export function useFetch(fetcher) {
  // The result remembers which fetcher produced it. A result that came from a
  // different fetcher than the current one means the current request hasn't
  // finished, which is how isLoading and error are derived below.
  const [result, setResult] = useState({ fetcher: null, data: null, error: null })

  useEffect(() => {
    if (!fetcher) return undefined

    let cancelled = false

    fetcher()
      .then((data) => {
        if (!cancelled) setResult({ fetcher, data, error: null })
      })
      .catch((err) => {
        if (!cancelled) setResult((previous) => ({ fetcher, data: previous.data, error: err.message }))
      })

    return () => {
      cancelled = true
    }
  }, [fetcher])

  const isCurrent = fetcher != null && result.fetcher === fetcher

  return {
    data: result.data,
    error: isCurrent ? result.error : null,
    isLoading: fetcher != null && !isCurrent,
  }
}

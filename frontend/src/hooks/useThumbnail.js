/**
 * Server-rendered schematic SVG as an object URL.
 *
 * <img src> can't carry the JWT, so the SVG is fetched via axios (auth
 * interceptor applies) as a blob and cached in a module-level Map keyed by
 * the caller's cacheKey.
 *
 * The version (updated_at) MUST live in the `path` itself (e.g. `?v=<updated_at>`),
 * not only in cacheKey. The server sends `Cache-Control: max-age=3600`, so a
 * versionless URL would be served stale from the *browser's* HTTP cache for an
 * hour even when our Map cache misses — the URL must change for the edit to show.
 * cacheKey therefore defaults to path (they can't drift out of sync).
 *
 * Works for any thumbnail endpoint: /designs/{id}/thumbnail.svg and
 * /estimates/{id}/frames/{fid}/thumbnail.svg.
 */
import { useEffect, useState } from 'react'
import api from '../api/client'

const cache = new Map() // cacheKey → object URL

export default function useThumbnail(path, cacheKey = path) {
  const [url, setUrl] = useState(() => cache.get(cacheKey) || null)

  useEffect(() => {
    if (!path) return undefined
    if (cache.has(cacheKey)) { setUrl(cache.get(cacheKey)); return undefined }
    let cancelled = false
    api.get(path, { responseType: 'blob' })
      .then(({ data }) => {
        const objectUrl = URL.createObjectURL(data)
        cache.set(cacheKey, objectUrl)
        if (!cancelled) setUrl(objectUrl)
      })
      .catch(() => { /* keep the placeholder on failure */ })
    return () => { cancelled = true }
  }, [path, cacheKey])

  return url
}

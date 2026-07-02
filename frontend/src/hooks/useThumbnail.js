/**
 * Design thumbnail as an object URL.
 *
 * <img src> can't carry the JWT, so the SVG is fetched via axios (auth
 * interceptor applies) as a blob and cached in a module-level Map keyed by
 * `id:updated_at` — a design edit changes updated_at and naturally busts
 * the cached entry.
 */
import { useEffect, useState } from 'react'
import api from '../api/client'

const cache = new Map() // `${id}:${updatedAt}` → object URL

export default function useThumbnail(id, updatedAt) {
  const key = `${id}:${updatedAt}`
  const [url, setUrl] = useState(() => cache.get(key) || null)

  useEffect(() => {
    if (!id) return undefined
    if (cache.has(key)) { setUrl(cache.get(key)); return undefined }
    let cancelled = false
    api.get(`/designs/${id}/thumbnail.svg`, { responseType: 'blob' })
      .then(({ data }) => {
        const objectUrl = URL.createObjectURL(data)
        cache.set(key, objectUrl)
        if (!cancelled) setUrl(objectUrl)
      })
      .catch(() => { /* keep the placeholder on failure */ })
    return () => { cancelled = true }
  }, [id, key])

  return url
}

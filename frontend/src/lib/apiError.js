/**
 * Turn an axios error into a toast-safe message string.
 *
 * FastAPI's `detail` is a string for HTTPExceptions but an array of
 * `{loc, msg, type}` objects for 422 request-validation errors. Passing that
 * array straight to `toast.error` makes React throw ("Objects are not valid as
 * a React child") and takes the whole page down — so never hand `detail` to
 * the UI without going through here.
 */
export function apiError(err, fallback) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    const { loc, msg } = detail[0] || {}
    if (typeof msg === 'string' && msg) {
      const field = Array.isArray(loc) ? loc[loc.length - 1] : null
      return typeof field === 'string' && field !== 'body' ? `${field}: ${msg}` : msg
    }
  }
  return fallback
}

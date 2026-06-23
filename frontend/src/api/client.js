/**
 * SteelCAD API Client
 * Axios instance with JWT interceptors — auto-attaches access token,
 * auto-refreshes on 401, and redirects to /login on total failure.
 */
import axios from 'axios'

const api = axios.create({
  baseURL: '/',
  headers: { 'Content-Type': 'application/json' },
})

// Attach access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Refresh on 401, redirect on second failure
let isRefreshing = false
let refreshQueue = []

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject })
        }).then(() => api(original))
      }
      original._retry = true
      isRefreshing = true
      try {
        const refresh = localStorage.getItem('refresh_token')
        if (!refresh) throw new Error('No refresh token')
        const { data } = await axios.post('/auth/refresh', { refresh_token: refresh })
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        refreshQueue.forEach((p) => p.resolve())
        refreshQueue = []
        return api(original)
      } catch {
        refreshQueue.forEach((p) => p.reject())
        refreshQueue = []
        localStorage.clear()
        window.location.href = '/login'
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(err)
  }
)

export default api

// ─── Auth ─────────────────────────────────────────────────────────
export const authApi = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
}

// ─── Designs ──────────────────────────────────────────────────────
export const designsApi = {
  list: (params) => api.get('/designs', { params }),
  get: (id) => api.get(`/designs/${id}`),
  create: (data) => api.post('/designs', data),
  update: (id, data) => api.put(`/designs/${id}`, data),
  delete: (id) => api.delete(`/designs/${id}`),
}

// ─── Stateless price preview (live canvas pricing) ───────────────────
export const pricePreview = (tree_json) => api.post('/price', { tree_json })

// ─── Customers ────────────────────────────────────────────────────
export const customersApi = {
  list: (params) => api.get('/customers', { params }),
  get: (id) => api.get(`/customers/${id}`),
  create: (data) => api.post('/customers', data),
  update: (id, data) => api.put(`/customers/${id}`, data),
  delete: (id) => api.delete(`/customers/${id}`),
}

// ─── Estimates (customer-scoped, multi-frame) ─────────────────────
export const estimatesApi = {
  listForCustomer: (customerId) => api.get(`/customers/${customerId}/estimates`),
  create: (customerId, data) => api.post(`/customers/${customerId}/estimates`, data),
  get: (id) => api.get(`/estimates/${id}`),
  update: (id, data) => api.put(`/estimates/${id}`, data),
  delete: (id) => api.delete(`/estimates/${id}`),
  addFrame: (id, data) => api.post(`/estimates/${id}/frames`, data),
  updateFrame: (id, frameId, data) => api.put(`/estimates/${id}/frames/${frameId}`, data),
  deleteFrame: (id, frameId) => api.delete(`/estimates/${id}/frames/${frameId}`),
  downloadPdf: (id) => api.get(`/estimates/${id}/pdf`, { responseType: 'blob' }),
}

// ─── Rates ────────────────────────────────────────────────────────
export const ratesApi = {
  list: () => api.get('/rates'),
  update: (itemCode, data) => api.put(`/rates/${itemCode}`, data),
  seed: () => api.post('/rates/seed'),
}

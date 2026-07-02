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
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),
}

// ─── Users (invite-only management) ──────────────────────────────
export const usersApi = {
  list: () => api.get('/users'),
  create: (data) => api.post('/users', data),
  updateRole: (id, role) => api.patch(`/users/${id}/role`, { role }),
  resetPassword: (id, newPassword) => api.patch(`/users/${id}/password`, { new_password: newPassword }),
  delete: (id) => api.delete(`/users/${id}`),
}

// ─── Designs ──────────────────────────────────────────────────────
export const designsApi = {
  list: (params) => api.get('/designs', { params }),
  get: (id) => api.get(`/designs/${id}`),
  create: (data) => api.post('/designs', data),
  update: (id, data) => api.put(`/designs/${id}`, data),
  delete: (id) => api.delete(`/designs/${id}`),
  restore: (id) => api.post(`/designs/${id}/restore`),
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
  restore: (id) => api.post(`/customers/${id}/restore`),
}

// ─── Estimates (customer-scoped, multi-frame) ─────────────────────
export const estimatesApi = {
  listForCustomer: (customerId, params) => api.get(`/customers/${customerId}/estimates`, { params }),
  create: (customerId, data) => api.post(`/customers/${customerId}/estimates`, data),
  get: (id) => api.get(`/estimates/${id}`),
  update: (id, data) => api.put(`/estimates/${id}`, data),
  setStatus: (id, status) => api.patch(`/estimates/${id}/status`, { status }),
  duplicate: (id) => api.post(`/estimates/${id}/duplicate`),
  revise: (id) => api.post(`/estimates/${id}/revise`),
  restore: (id) => api.post(`/estimates/${id}/restore`),
  delete: (id) => api.delete(`/estimates/${id}`),
  addFrame: (id, data) => api.post(`/estimates/${id}/frames`, data),
  updateFrame: (id, frameId, data) => api.put(`/estimates/${id}/frames/${frameId}`, data),
  duplicateFrame: (id, frameId) => api.post(`/estimates/${id}/frames/${frameId}/duplicate`),
  deleteFrame: (id, frameId) => api.delete(`/estimates/${id}/frames/${frameId}`),
  downloadPdf: (id) => api.get(`/estimates/${id}/pdf`, { responseType: 'blob' }),
}

// ─── Rates ────────────────────────────────────────────────────────
export const ratesApi = {
  list: () => api.get('/rates'),
  update: (itemCode, data) => api.put(`/rates/${itemCode}`, data),
  seed: () => api.post('/rates/seed'),
}

// ─── Company settings (PDF branding) ──────────────────────────────
export const settingsApi = {
  getCompany: () => api.get('/settings/company'),
  updateCompany: (data) => api.put('/settings/company', data),
}

// ─── Audit / activity trail (admin/owner) ─────────────────────────
export const auditApi = {
  list: (params) => api.get('/audit', { params }),
}

// ─── Trash (soft-deleted records, admin/owner) ────────────────────
export const trashApi = {
  list: () => api.get('/trash'),
}

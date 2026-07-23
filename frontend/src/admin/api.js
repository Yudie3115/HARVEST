const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const TOKEN_KEY = 'admin_token'

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY)
}

function authHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request(method, path, body, isFormData = false) {
  const headers = { ...authHeaders() }
  if (!isFormData) headers['Content-Type'] = 'application/json'

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: isFormData ? body : body ? JSON.stringify(body) : undefined,
  })

  if (res.status === 401) {
    sessionStorage.removeItem(TOKEN_KEY)
    window.location.href = '/admin/login'
    return
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }

  return res.json()
}

export const adminApi = {
  async login(username, password) {
    const res = await fetch(`${BASE}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Login failed' }))
      throw new Error(err.detail || 'Login failed')
    }
    const data = await res.json()
    sessionStorage.setItem(TOKEN_KEY, data.access_token)
    return data
  },

  logout() {
    sessionStorage.removeItem(TOKEN_KEY)
  },

  isAuthenticated() {
    return Boolean(getToken())
  },

  getStats: () => request('GET', '/admin/stats'),

  getDocuments: (params = {}) => {
    const q = new URLSearchParams()
    if (params.site) q.set('site', params.site)
    if (params.status) q.set('status', params.status)
    if (params.sort) q.set('sort', params.sort)
    if (params.offset != null) q.set('offset', params.offset)
    if (params.limit != null) q.set('limit', params.limit)
    return request('GET', `/admin/documents?${q}`)
  },

  updateDocumentPublication: (id, body) =>
    request('PATCH', `/admin/documents/${id}/publication`, body),

  updateDocumentTitle: (id, title) =>
    request('PATCH', `/admin/documents/${id}/title`, { title }),

  getHealth: () => request('GET', '/admin/health'),

  getConfig: () => request('GET', '/admin/config'),

  triggerCrawl: (type) =>
    request('POST', type === 'full' ? '/admin/crawl/full' : '/admin/crawl/incremental'),

  async ingestFile(file, title, siteName) {
    const fd = new FormData()
    fd.append('file', file)
    if (title) fd.append('title', title)
    fd.append('site_name', siteName || 'manual')
    return request('POST', '/admin/documents/ingest', fd, true)
  },

  search: (query, topK = 10) =>
    request('POST', '/admin/search', { query, top_k: topK }),

  qa: (question, topK = 8, scoreThreshold = 0.4) =>
    request('POST', '/admin/qa', { question, top_k: topK, score_threshold: scoreThreshold }),

  async ingestUrl(url, title, siteName) {
    const fd = new FormData()
    fd.append('url', url)
    if (title) fd.append('title', title)
    fd.append('site_name', siteName || 'manual')
    return request('POST', '/admin/documents/ingest', fd, true)
  },

  getChatQualityStats: () => request('GET', '/admin/chat-quality/stats'),

  getChatQuality: (params = {}) => {
    const q = new URLSearchParams()
    if (params.offset != null) q.set('offset', params.offset)
    if (params.limit  != null) q.set('limit',  params.limit)
    if (params.min_f1 != null) q.set('min_f1', params.min_f1)
    if (params.max_f1 != null) q.set('max_f1', params.max_f1)
    return request('GET', `/admin/chat-quality?${q}`)
  },

  getCataloguePending: () => request('GET', '/admin/catalogue/pending'),
  getCatalogueApproved: () => request('GET', '/admin/catalogue/approved'),
  approveCatalogue: (id) => request('POST', `/admin/catalogue/${id}/approve`),
  rejectCatalogue: (id) => request('POST', `/admin/catalogue/${id}/reject`),
  retractCatalogue: (id) => request('POST', `/admin/catalogue/${id}/retract`),
  retryCatalogue: (id) => request('POST', `/admin/catalogue/${id}/retry-publish`),
}

import { useNavigate } from 'react-router-dom'
import { adminApi } from './api'

export function useAdminAuth() {
  const navigate = useNavigate()

  function logout() {
    adminApi.logout()
    navigate('/admin/login')
  }

  return { logout, isAuthenticated: adminApi.isAuthenticated() }
}

import { Routes, Route, Navigate } from 'react-router-dom'
import ChatApp from './ChatApp'
import LoginPage from './admin/LoginPage'
import AdminLayout from './admin/AdminLayout'
import Overview from './admin/pages/Overview'
import Documents from './admin/pages/Documents'
import SearchPage from './admin/pages/Search'
import QAPage from './admin/pages/QA'
import ConfigPage from './admin/pages/Config'
import AddDocumentPage from './admin/pages/AddDocument'
import { adminApi } from './admin/api'

function ProtectedAdmin({ children }) {
  if (!adminApi.isAuthenticated()) {
    return <Navigate to="/admin/login" replace />
  }
  return children
}

export default function App() {
  return (
    <Routes>
      {/* Chat interface */}
      <Route path="/" element={<ChatApp />} />

      {/* Admin login */}
      <Route path="/admin/login" element={<LoginPage />} />

      {/* Protected admin shell */}
      <Route
        path="/admin"
        element={
          <ProtectedAdmin>
            <AdminLayout />
          </ProtectedAdmin>
        }
      >
        <Route index element={<Navigate to="/admin/overview" replace />} />
        <Route path="overview" element={<Overview />} />
        <Route path="documents" element={<Documents />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="qa" element={<QAPage />} />
        <Route path="config" element={<ConfigPage />} />
        <Route path="add-document" element={<AddDocumentPage />} />
      </Route>
    </Routes>
  )
}

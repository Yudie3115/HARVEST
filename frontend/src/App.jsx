import { Routes, Route, Navigate } from 'react-router-dom'
import ChatApp from './ChatApp'
import AskPage from './ask/AskPage'
import DocumentsPage from './library/pages/DocumentsPage'
import DocumentDetailPage from './library/pages/DocumentDetailPage'
import CataloguePage from './catalogue/pages/CataloguePage'
import CatalogueDetailPage from './catalogue/pages/CatalogueDetailPage'
import LoginPage from './admin/LoginPage'
import AdminLayout from './admin/AdminLayout'
import Overview from './admin/pages/Overview'
import Documents from './admin/pages/Documents'
import SearchPage from './admin/pages/Search'
import QAPage from './admin/pages/QA'
import ConfigPage from './admin/pages/Config'
import AddDocumentPage from './admin/pages/AddDocument'
import ChatQualityPage from './admin/pages/ChatQuality'
import CatalogueAdminPage from './admin/pages/Catalogue'
import AccessCodesPage from './admin/pages/AccessCodes'
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
      {/* Browse-first ask gate and internal live chat */}
      <Route path="/" element={<AskPage />} />
      <Route path="/chat" element={<ChatApp />} />

      {/* Public documents library */}
      <Route path="/documents" element={<DocumentsPage />} />
      <Route path="/documents/:id" element={<DocumentDetailPage />} />
      <Route path="/catalogue" element={<CataloguePage />} />
      <Route path="/catalogue/:id" element={<CatalogueDetailPage />} />

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
        <Route path="chat-quality" element={<ChatQualityPage />} />
        <Route path="catalogue" element={<CatalogueAdminPage />} />
        <Route path="access-codes" element={<AccessCodesPage />} />
      </Route>
    </Routes>
  )
}

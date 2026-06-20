import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import AppLayout from './components/Layout/AppLayout';
import AuthGuard from './components/AuthGuard';
import LoginPage from './pages/Login/LoginPage';
import RegisterPage from './pages/Register/RegisterPage';
import DashboardPage from './pages/Dashboard/DashboardPage';
import PostListPage from './pages/PostList/PostListPage';
import PostDetailPage from './pages/PostDetail/PostDetailPage';
import PostCreatePage from './pages/PostCreate/PostCreatePage';
import AgentConsolePage from './pages/AgentConsole/AgentConsolePage';
import SourcesPage from './pages/Sources/SourcesPage';
import FetchRunsPage from './pages/FetchRuns/FetchRunsPage';
import ContentQueuePage from './pages/ContentQueue/ContentQueuePage';
import ReviewQueuePage from './pages/ReviewQueue/ReviewQueuePage';
import DigestPage from './pages/Digests/DigestPage';

export default function App() {
  const token = useAuthStore((s) => s.token);

  return (
    <Routes>
      {/* 公开路由 */}
      <Route
        path="/login"
        element={!token ? <LoginPage /> : <Navigate to="/" replace />}
      />
      <Route
        path="/register"
        element={!token ? <RegisterPage /> : <Navigate to="/" replace />}
      />

      {/* 受保护路由 */}
      <Route
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route path="/" element={<DashboardPage />} />
        <Route path="/sources" element={<SourcesPage />} />
        <Route path="/fetch-runs" element={<FetchRunsPage />} />
        <Route path="/content-queue" element={<ContentQueuePage />} />
        <Route path="/review-queue" element={<ReviewQueuePage />} />
        <Route path="/digests" element={<DigestPage />} />
        <Route path="/posts" element={<PostListPage />} />
        <Route path="/posts/:id" element={<PostDetailPage />} />
        <Route path="/posts/new" element={<PostCreatePage />} />
        <Route path="/agent" element={<AgentConsolePage />} />
      </Route>

      {/* 兜底 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

import { lazy, Suspense } from 'react';
import { Spin } from 'antd';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './stores/authStore';
import './styles/console-polish.css';
import AuthGuard from './components/AuthGuard';
const PolishedAppLayout = lazy(() => import('./components/Layout/PolishedAppLayout'));
const LoginPage = lazy(() => import('./pages/Login/LoginPage'));
const RegisterPage = lazy(() => import('./pages/Register/RegisterPage'));
const PolishedDashboardPage = lazy(() => import('./pages/Dashboard/PolishedDashboardPage'));
const PostListPage = lazy(() => import('./pages/PostList/PostListPage'));
const PostDetailPage = lazy(() => import('./pages/PostDetail/PostDetailPage'));
const PostCreatePage = lazy(() => import('./pages/PostCreate/PostCreatePage'));
const PolishedAgentConsolePage = lazy(() => import('./pages/AgentConsole/PolishedAgentConsolePage'));
const PolishedSourcesPage = lazy(() => import('./pages/Sources/PolishedSourcesPage'));
const PolishedFetchRunsPage = lazy(() => import('./pages/FetchRuns/PolishedFetchRunsPage'));
const PolishedContentQueuePage = lazy(() => import('./pages/ContentQueue/PolishedContentQueuePage'));
const PolishedReviewQueuePage = lazy(() => import('./pages/ReviewQueue/PolishedReviewQueuePage'));
const PolishedDigestPage = lazy(() => import('./pages/Digests/PolishedDigestPage'));

function RouteFallback() {
  return (
    <div className="route-fallback">
      <Spin size="large" tip="加载中..." />
    </div>
  );
}

export default function App() {
  const token = useAuthStore((s) => s.token);

  return (
    <Suspense fallback={<RouteFallback />}>
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
            <PolishedAppLayout />
          </AuthGuard>
        }
      >
        <Route path="/" element={<PolishedDashboardPage />} />
        <Route path="/sources" element={<PolishedSourcesPage />} />
        <Route path="/fetch-runs" element={<PolishedFetchRunsPage />} />
        <Route path="/content-queue" element={<PolishedContentQueuePage />} />
        <Route path="/review-queue" element={<PolishedReviewQueuePage />} />
        <Route path="/digests" element={<PolishedDigestPage />} />
        <Route path="/posts" element={<PostListPage />} />
        <Route path="/posts/:id" element={<PostDetailPage />} />
        <Route path="/posts/new" element={<PostCreatePage />} />
        <Route path="/agent" element={<PolishedAgentConsolePage />} />
      </Route>

      {/* 兜底 */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}

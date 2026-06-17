import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../stores/authStore';
import type {
  Agent,
  ApiResponse,
  Comment,
  ContentItem,
  CreateCommentRequest,
  CreatePostRequest,
  DigestReport,
  FetchRun,
  LoginRequest,
  LoginResponse,
  OrchestrationRun,
  PaginatedResponse,
  Post,
  RegisterRequest,
  ReviewApprovePayload,
  ReviewItem,
  SchedulerTask,
  SourceConfig,
  SourceConfigPayload,
  SourceSubscription,
  SourceSubscriptionPayload,
  TriggerFetchPayload,
  User,
} from '../types';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

const internalApiClient = axios.create({
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

const internalApiToken = import.meta.env.VITE_INTERNAL_API_TOKEN;

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token;
  if (token !== null) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

internalApiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (internalApiToken) {
    config.headers['x-internal-token'] = internalApiToken;
  }
  return config;
});

function _isAuthUrl(url: string | undefined): boolean {
  if (!url) return false;
  return url.endsWith('/auth/login') || url.endsWith('/auth/register');
}

function _extractErrorMessage(err: AxiosError): string {
  const detail = err.response?.data;
  if (detail && typeof detail === 'object' && 'detail' in detail && typeof detail.detail === 'string') {
    return detail.detail;
  }
  return err instanceof Error ? err.message : 'Request failed';
}

apiClient.interceptors.response.use(
  (res) => {
    const body = res.data as ApiResponse<unknown>;
    if (
      body !== null &&
      typeof body === 'object' &&
      'code' in body &&
      body.code !== undefined &&
      body.code !== 0
    ) {
      if (!_isAuthUrl(res.config.url) && (body.code === 40101 || body.code === 40102 || body.code === 40103)) {
        useAuthStore.getState().logout();
        window.location.href = '/console/login';
      }
      return Promise.reject(new Error(body.message || 'Request failed'));
    }
    return res;
  },
  (err: AxiosError) => {
    if (!_isAuthUrl(err.config?.url) && err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/console/login';
    }
    return Promise.reject(new Error(_extractErrorMessage(err)));
  }
);

internalApiClient.interceptors.response.use(
  (res) => {
    const body = res.data as ApiResponse<unknown>;
    if (body && typeof body === 'object' && 'code' in body && body.code !== 0) {
      return Promise.reject(new Error(body.message || 'Request failed'));
    }
    return res;
  },
  (err: AxiosError) => Promise.reject(new Error(_extractErrorMessage(err)))
);

export async function login(data: LoginRequest): Promise<LoginResponse> {
  const res = await apiClient.post<ApiResponse<LoginResponse>>('/auth/login', data);
  return res.data.data;
}

export async function register(data: RegisterRequest): Promise<LoginResponse> {
  const res = await apiClient.post<ApiResponse<LoginResponse>>('/auth/register', data);
  return res.data.data;
}

export async function getMe(): Promise<User> {
  const res = await apiClient.get<ApiResponse<User>>('/auth/me');
  return res.data.data;
}

export async function refreshToken(): Promise<LoginResponse> {
  const res = await apiClient.post<ApiResponse<LoginResponse>>('/auth/refresh');
  return res.data.data;
}

export async function listPosts(
  page: number = 1,
  pageSize: number = 20,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<Post>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<Post>>>('/posts', {
    params: { page, page_size: pageSize, ...params },
  });
  return res.data.data;
}

export async function getPost(id: number): Promise<Post> {
  const res = await apiClient.get<ApiResponse<Post>>(`/posts/${id}`);
  return res.data.data;
}

export async function createPost(data: CreatePostRequest): Promise<Post> {
  const res = await apiClient.post<ApiResponse<Post>>('/posts', data);
  return res.data.data;
}

export async function updatePost(id: number, data: Partial<CreatePostRequest>): Promise<Post> {
  const res = await apiClient.put<ApiResponse<Post>>(`/posts/${id}`, data);
  return res.data.data;
}

export async function deletePost(id: number): Promise<void> {
  await apiClient.delete(`/posts/${id}`);
}

export async function likePost(id: number): Promise<void> {
  await apiClient.post(`/posts/${id}/like`);
}

export async function unlikePost(id: number): Promise<void> {
  await apiClient.delete(`/posts/${id}/like`);
}

export async function listComments(
  postId: number,
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<Comment>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<Comment>>>(`/posts/${postId}/comments`, {
    params: { page, page_size: pageSize },
  });
  return res.data.data;
}

export async function createComment(postId: number, data: CreateCommentRequest): Promise<Comment> {
  const res = await apiClient.post<ApiResponse<Comment>>(`/posts/${postId}/comments`, data);
  return res.data.data;
}

export async function deleteComment(postId: number, commentId: number): Promise<void> {
  await apiClient.delete(`/posts/${postId}/comments/${commentId}`);
}

export async function listAgents(): Promise<Agent[]> {
  const res = await apiClient.get<ApiResponse<Agent[]>>('/admin/agents');
  return res.data.data;
}

export async function getAgent(agentKey: string): Promise<Agent> {
  const res = await apiClient.get<ApiResponse<Agent>>(`/admin/agents/${agentKey}`);
  return res.data.data;
}

export async function listTasks(
  page: number = 1,
  pageSize: number = 20,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<SchedulerTask>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<SchedulerTask>>>('/admin/tasks', {
    params: { page, page_size: pageSize, ...params },
  });
  return res.data.data;
}

export async function getTask(taskId: string): Promise<SchedulerTask> {
  const res = await apiClient.get<ApiResponse<SchedulerTask>>(`/admin/tasks/${taskId}`);
  return res.data.data;
}

export async function listOrchestrationRuns(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<OrchestrationRun>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<OrchestrationRun>>>('/admin/orchestrations', {
    params: { page, page_size: pageSize },
  });
  return res.data.data;
}

export async function getOrchestrationRun(runId: string): Promise<OrchestrationRun> {
  const res = await apiClient.get<ApiResponse<OrchestrationRun>>(`/admin/orchestrations/${runId}`);
  return res.data.data;
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await apiClient.get<ApiResponse<{ status: string }>>('/admin/health');
  return res.data.data;
}

export async function systemStats(): Promise<Record<string, unknown>> {
  const res = await apiClient.get<ApiResponse<Record<string, unknown>>>('/admin/stats');
  return res.data.data;
}

export async function listSourceConfigs(): Promise<SourceConfig[]> {
  const res = await apiClient.get<ApiResponse<SourceConfig[]>>('/console/sources');
  return res.data.data;
}

export async function createSourceConfig(data: SourceConfigPayload): Promise<SourceConfig> {
  const res = await apiClient.post<ApiResponse<SourceConfig>>('/console/sources', data);
  return res.data.data;
}

export async function updateSourceConfig(id: number, data: Partial<SourceConfigPayload>): Promise<SourceConfig> {
  const res = await apiClient.put<ApiResponse<SourceConfig>>(`/console/sources/${id}`, data);
  return res.data.data;
}

export async function triggerSourceRun(
  id: number,
  data: TriggerFetchPayload
): Promise<{ fetch_run_id: number; task_id?: string; trace_id?: string; status: string }> {
  const res = await apiClient.post<
    ApiResponse<{ fetch_run_id: number; task_id?: string; trace_id?: string; status: string }>
  >(`/console/sources/${id}/run`, data);
  return res.data.data;
}

export async function listFetchRuns(
  page: number = 1,
  pageSize: number = 20,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<FetchRun>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<FetchRun>>>('/console/fetch-runs', {
    params: { page, page_size: pageSize, ...params },
  });
  return res.data.data;
}

export async function listConsoleContentItems(
  page: number = 1,
  pageSize: number = 20,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ContentItem>> {
  const res = await apiClient.get<ApiResponse<PaginatedResponse<ContentItem>>>('/console/content-items', {
    params: { page, page_size: pageSize, ...params },
  });
  return res.data.data;
}

export async function getConsoleContentItem(id: number): Promise<ContentItem> {
  const res = await apiClient.get<ApiResponse<ContentItem>>(`/console/content-items/${id}`);
  return res.data.data;
}

export async function approveConsoleContentItem(id: number, reason?: string): Promise<ContentItem> {
  const res = await apiClient.post<ApiResponse<ContentItem>>(`/console/content-items/${id}/approve`, { reason });
  return res.data.data;
}

export async function rejectConsoleContentItem(id: number, reason?: string): Promise<ContentItem> {
  const res = await apiClient.post<ApiResponse<ContentItem>>(`/console/content-items/${id}/reject`, { reason });
  return res.data.data;
}

export async function publishConsoleContentItem(
  id: number,
  data?: { title?: string; content?: string; tech_tags?: string }
): Promise<{ content_item: ContentItem; post_id: number }> {
  const res = await apiClient.post<ApiResponse<{ content_item: ContentItem; post_id: number }>>(
    `/console/content-items/${id}/publish-to-post`,
    data || {}
  );
  return res.data.data;
}

export async function getSources(): Promise<SourceSubscription[]> {
  const res = await internalApiClient.get<ApiResponse<SourceSubscription[]>>('/api/internal/content/sources/');
  return res.data.data;
}

export async function createSource(data: SourceSubscriptionPayload): Promise<SourceSubscription> {
  const res = await internalApiClient.post<ApiResponse<SourceSubscription>>('/api/internal/content/sources/', data);
  return res.data.data;
}

export async function updateSource(id: number, data: Partial<SourceSubscriptionPayload>): Promise<SourceSubscription> {
  const res = await internalApiClient.patch<ApiResponse<SourceSubscription>>(`/api/internal/content/sources/${id}`, data);
  return res.data.data;
}

export async function toggleSource(id: number, enabled: boolean): Promise<void> {
  await internalApiClient.post(`/api/internal/content/sources/${id}/${enabled ? 'enable' : 'disable'}`);
}

export async function triggerFetch(sourceId: number): Promise<void> {
  if (!internalApiToken) {
    throw new Error('VITE_INTERNAL_API_TOKEN is not configured');
  }
  await internalApiClient.post('/api/internal/tasks/content-pipeline/radar/run', {
    limit: 20,
    filter_config: { source_subscription_ids: [sourceId] },
  });
}

export async function getReviews(
  params?: Record<string, unknown>
): Promise<PaginatedResponse<ReviewItem>> {
  const res = await internalApiClient.get<ApiResponse<PaginatedResponse<ReviewItem>>>('/api/internal/content/reviews/', {
    params,
  });
  return res.data.data;
}

export async function getReview(id: number): Promise<ReviewItem> {
  const res = await internalApiClient.get<ApiResponse<ReviewItem>>(`/api/internal/content/reviews/${id}`);
  return res.data.data;
}

export async function approveReview(id: number, data?: ReviewApprovePayload): Promise<void> {
  await internalApiClient.post(`/api/internal/content/reviews/${id}/approve`, {
    reviewer: data?.reviewer || 'admin',
    edited_title: data?.edited_title,
    edited_content: data?.edited_content,
  });
}

export async function rejectReview(id: number, note?: string): Promise<void> {
  await internalApiClient.post(`/api/internal/content/reviews/${id}/reject`, {
    reviewer: 'admin',
    note: note || '',
  });
}

export async function archiveReview(id: number): Promise<void> {
  await internalApiClient.post(`/api/internal/content/reviews/${id}/archive`, null, {
    params: { reviewer: 'admin' },
  });
}

export async function getDigests(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<DigestReport>> {
  const res = await internalApiClient.get<ApiResponse<PaginatedResponse<DigestReport>>>('/api/internal/content/digests/', {
    params: { page, page_size: pageSize },
  });
  return res.data.data;
}

export async function getDigest(id: number): Promise<DigestReport> {
  const res = await internalApiClient.get<ApiResponse<DigestReport>>(`/api/internal/content/digests/${id}`);
  return res.data.data;
}

export async function generateDigest(): Promise<DigestReport> {
  const res = await internalApiClient.post<ApiResponse<DigestReport>>('/api/internal/content/digests/generate', {
    lookback_hours: 24,
  });
  return res.data.data;
}

export async function triggerDailyDigest(): Promise<void> {
  if (!internalApiToken) {
    throw new Error('VITE_INTERNAL_API_TOKEN is not configured');
  }
  await internalApiClient.post('/api/internal/tasks/content-pipeline/daily-digest/run', {
    lookback_hours: 24,
  });
}

export async function downloadDigest(id: number): Promise<Blob> {
  const res = await internalApiClient.get(`/api/internal/content/digests/${id}/download`, {
    responseType: 'blob',
  });
  return res.data as Blob;
}

export default apiClient;

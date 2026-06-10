import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../stores/authStore';
import type {
  Agent,
  ApiResponse,
  Comment,
  ContentItem,
  CreateCommentRequest,
  CreatePostRequest,
  FetchRun,
  LoginRequest,
  LoginResponse,
  OrchestrationRun,
  PaginatedResponse,
  Post,
  RegisterRequest,
  SchedulerTask,
  SourceConfig,
  SourceConfigPayload,
  TriggerFetchPayload,
  User,
} from '../types';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token;
  if (token !== null) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** 请求是否是登录/注册（不触发 401 自动跳转） */
function _isAuthUrl(url: string | undefined): boolean {
  if (!url) return false;
  return url.endsWith('/auth/login') || url.endsWith('/auth/register');
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
      return Promise.reject(new Error(body.message || '请求失败'));
    }
    return res;
  },
  (err: AxiosError) => {
    if (!_isAuthUrl(err.config?.url) && err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/console/login';
    }
    const message = err instanceof Error ? err.message : '网络请求失败';
    return Promise.reject(new Error(message));
  }
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

export default apiClient;

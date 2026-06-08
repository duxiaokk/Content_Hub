import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../stores/authStore';
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  Post,
  CreatePostRequest,
  Comment,
  CreateCommentRequest,
  User,
  Agent,
  SchedulerTask,
  OrchestrationRun,
  PaginatedResponse,
  ApiResponse,
} from '../types';

// ============ 创建 axios 实例 ============
const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ============ 请求拦截器 ============
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token;
  if (token !== null) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ============ 响应拦截器 ============
apiClient.interceptors.response.use(
  (res) => {
    const body = res.data as ApiResponse<unknown>;
    if (body !== null && typeof body === 'object' && 'code' in body && (body as ApiResponse<unknown>).code !== undefined && (body as ApiResponse<unknown>).code !== 0) {
      if (body.code === 40101 || body.code === 40102 || body.code === 40103) {
        useAuthStore.getState().logout();
        window.location.href = '/login';
      }
      return Promise.reject(new Error(body.message || '请求失败'));
    }
    return res;
  },
  (err: AxiosError) => {
    if (err.response?.status === 401) {
      useAuthStore.getState().logout();
      window.location.href = '/login';
    }
    const message = err instanceof Error ? err.message : '网络请求失败';
    return Promise.reject(new Error(message));
  }
);

// ============ 调度器 API 实例 ============
const schedulerClient = axios.create({
  baseURL: '/scheduler/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

schedulerClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().token;
  if (token !== null) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

schedulerClient.interceptors.response.use(
  (res) => {
    const body = res.data as ApiResponse<unknown>;
    if (body !== null && typeof body === 'object' && 'code' in body && (body as ApiResponse<unknown>).code !== undefined && (body as ApiResponse<unknown>).code !== 0) {
      return Promise.reject(new Error(body.message || '请求失败'));
    }
    return res;
  },
  (err: AxiosError) => {
    const message = err instanceof Error ? err.message : '网络请求失败';
    return Promise.reject(new Error(message));
  }
);

// ============ 认证 API ============
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

// ============ 文章 API ============
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

// ============ 评论 API ============
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

// ============ Agent API ============
export async function listAgents(): Promise<Agent[]> {
  const res = await schedulerClient.get<ApiResponse<Agent[]>>('/agents');
  return res.data.data;
}

export async function getAgent(agentKey: string): Promise<Agent> {
  const res = await schedulerClient.get<ApiResponse<Agent>>(`/agents/${agentKey}`);
  return res.data.data;
}

// ============ 调度任务 API ============
export async function listTasks(
  page: number = 1,
  pageSize: number = 20,
  params?: Record<string, unknown>
): Promise<PaginatedResponse<SchedulerTask>> {
  const res = await schedulerClient.get<ApiResponse<PaginatedResponse<SchedulerTask>>>('/tasks', {
    params: { page, page_size: pageSize, ...params },
  });
  return res.data.data;
}

export async function getTask(taskId: string): Promise<SchedulerTask> {
  const res = await schedulerClient.get<ApiResponse<SchedulerTask>>(`/tasks/${taskId}`);
  return res.data.data;
}

// ============ 编排运行 API ============
export async function listOrchestrationRuns(
  page: number = 1,
  pageSize: number = 20
): Promise<PaginatedResponse<OrchestrationRun>> {
  const res = await schedulerClient.get<ApiResponse<PaginatedResponse<OrchestrationRun>>>('/orchestrations', {
    params: { page, page_size: pageSize },
  });
  return res.data.data;
}

export async function getOrchestrationRun(runId: string): Promise<OrchestrationRun> {
  const res = await schedulerClient.get<ApiResponse<OrchestrationRun>>(`/orchestrations/${runId}`);
  return res.data.data;
}

// ============ 健康检查 API ============
export async function healthCheck(): Promise<{ status: string }> {
  const res = await schedulerClient.get<ApiResponse<{ status: string }>>('/health');
  return res.data.data;
}

export async function systemStats(): Promise<Record<string, unknown>> {
  const res = await apiClient.get<ApiResponse<Record<string, unknown>>>('/admin/stats');
  return res.data.data;
}

export default apiClient;

// ============ 用户 ============
export interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  avatar_path?: string;
  created_at: string;
  updated_at: string;
}

// ============ 文章 ============
export interface Post {
  id: number;
  title: string;
  content: string;
  summary?: string;
  tech_tags?: string;
  like_count: number;
  view_count: number;
  author_id: number;
  author_name?: string;
  author_avatar?: string;
  status: 'draft' | 'published';
  liked?: boolean;
  created_at: string;
  updated_at: string;
}

// ============ 评论 ============
export interface Comment {
  id: number;
  post_id: number;
  user_id: number;
  username: string;
  content: string;
  created_at: string;
}

// ============ Agent ============
export type AgentStatus = 'online' | 'offline' | 'busy';

export interface Agent {
  agent_key: string;
  agent_name: string;
  agent_type: string;
  status: AgentStatus;
  host: string;
  port: number;
  load_score: number;
  last_heartbeat: string;
}

// ============ 调度任务 ============
export type TaskStatus = 'pending' | 'running' | 'success' | 'failure' | 'retrying';

export interface SchedulerTask {
  task_id: string;
  trace_id: string;
  task_type: string;
  status: TaskStatus;
  input_payload: Record<string, unknown>;
  output_payload?: Record<string, unknown>;
  error_message?: string;
  retry_count: number;
  max_retries: number;
  created_at: string;
  updated_at: string;
}

// ============ 编排运行 ============
export interface OrchestrationRun {
  id: string;
  status: string;
  dag_definition: Record<string, unknown>;
  tasks: SchedulerTask[];
  created_at: string;
  updated_at: string;
}

// ============ 分页响应 ============
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ============ API 请求/响应 ============
export interface LoginRequest {
  username: string;
  password: string;
  remember?: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface CreatePostRequest {
  title: string;
  content: string;
  tech_tags?: string;
  status?: 'draft' | 'published';
}

export interface CreateCommentRequest {
  content: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

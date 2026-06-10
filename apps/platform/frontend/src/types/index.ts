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

export interface SourceConfig {
  id: number;
  name: string;
  source_type: string;
  enabled: boolean;
  channels: string[];
  keywords: string[];
  lookback_hours: number;
  item_limit: number;
  dedup_window_hours: number;
  // 前端表单会把 config 当作“任意 JSON 对象”编辑；用 any 避免与 antd Form 的递归 Partial 类型冲突
  config: Record<string, any>;
  last_cursor?: Record<string, unknown> | string | null;
  last_run_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface FetchRun {
  id: number;
  source_config_id: number;
  source_name: string;
  source_type: string;
  trigger_mode: string;
  status: string;
  task_id?: string | null;
  trace_id?: string | null;
  requested_by?: string | null;
  request_payload: Record<string, unknown>;
  fetched_count: number;
  inserted_count: number;
  deduped_count: number;
  duration_ms?: number | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ContentItem {
  id: number;
  source_config_id?: number | null;
  fetch_run_id?: number | null;
  source_type: string;
  source_id: string;
  source_url?: string | null;
  title: string;
  raw_content?: string | null;
  processed_content?: string | null;
  pipeline_status: string;
  review_status: string;
  publish_status: string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  draft_post_id?: number | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
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

export interface SourceConfigPayload {
  name: string;
  source_type: string;
  enabled: boolean;
  channels: string[];
  keywords: string[];
  lookback_hours: number;
  item_limit: number;
  dedup_window_hours: number;
  // 同上：config 允许任意 JSON，避免 TS2345/TS2322（unknown 无法赋值给 {}）
  config: Record<string, any>;
}

export interface TriggerFetchPayload {
  lookback_hours?: number;
  item_limit?: number;
  dry_run?: boolean;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

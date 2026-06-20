export interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  avatar_path?: string;
  created_at: string;
  updated_at: string;
}

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
  image_path?: string | null;
  media_json?: string | null;
  status: 'draft' | 'published';
  liked?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: number;
  post_id: number;
  user_id: number;
  username: string;
  content: string;
  created_at: string;
}

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
  config: Record<string, any>;
  last_cursor?: Record<string, unknown> | string | null;
  last_run_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SourceSubscription {
  id: number;
  source_type: string;
  source_name: string;
  account_identifier?: string;
  feed_url?: string;
  enabled: boolean;
  category?: string;
  default_tags?: string;
  last_cursor?: string;
  created_at?: string;
  updated_at?: string;
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
  summary?: string | null;
  rewritten_title?: string | null;
  rewritten_content?: string | null;
  score?: number | null;
  tags?: string[];
  category?: string | null;
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

export type ReviewStatus = 'pending' | 'approved' | 'rejected' | 'archived';

export interface ReviewItem {
  id: number;
  content_item_id: number;
  candidate_title?: string;
  candidate_content?: string;
  original_title: string;
  original_content: string;
  summary?: string;
  source_url?: string;
  score: number;
  tags: string[];
  category?: string;
  status: ReviewStatus;
  reviewer?: string;
  review_note?: string;
  reviewed_at?: string;
  created_at?: string;
}

export interface DigestReport {
  id: number;
  title: string;
  content_markdown: string;
  included_count: number;
  generated_at: string;
  run_id?: string;
  created_at?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

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
  config: Record<string, any>;
}

export interface TriggerFetchPayload {
  lookback_hours?: number;
  item_limit?: number;
  dry_run?: boolean;
}

export interface ConsoleSourceRunResult {
  fetch_run_id: number;
  task_id?: string;
  trace_id?: string;
  status: string;
}

export interface ProcessFetchRunPayload {
  limit?: number;
  source_type?: string;
  filter_config?: Record<string, unknown>;
  process_options?: Record<string, unknown>;
}

export interface ProcessFetchRunResult {
  fetch_run_id: number;
  task_id?: string;
  trace_id?: string;
  status: string;
  review_status: string;
  review_queue_path: string;
  next_action: string;
}

export interface SourceSubscriptionPayload {
  source_type: string;
  source_name: string;
  account_identifier?: string;
  feed_url?: string;
  schedule_expression?: string;
  category?: string;
  default_tags?: string;
}

export interface ReviewApprovePayload {
  reviewer?: string;
  edited_title?: string;
  edited_content?: string;
}

export interface ReviewApproveResult extends ReviewItem {
  publish_status?: string;
  publish_path?: string;
  next_action?: string;
}

export interface ConsolePublishResult {
  content_item: ContentItem;
  post_id: number;
  post_path: string;
  publish_status: string;
  next_action: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

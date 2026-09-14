/**
 * API 类型定义 — 与后端 Pydantic 模型对齐 / API type definitions — aligned with backend Pydantic models
 */

// ─── 任务 / Task ───

export type TaskStatus =
  | 'recording'
  | 'paused'
  | 'pending'
  | 'processing'
  | 'transcribing'
  | 'awaiting_mapping'
  | 'summarizing'
  | 'completed'
  | 'failed'

export interface Chapter {
  id: number
  title: string
  start_ms: number
  end_ms: number
  summary: string
  key_points: string[]
}

export interface Sentence {
  begin_time: number
  end_time: number
  text: string
  sentence_id: number
  speaker_id: number
}

export interface DialogueLine {
  speaker_id: number
  text: string
  sentences: Sentence[]
}

/** 扁平化后的转写行（从 dialogue.sentences 展开） / Flattened transcript line (expanded from dialogue.sentences) */
export interface FlatTranscriptLine {
  begin_time: number
  end_time: number
  text: string
  speaker_id: number
  sentence_id: number
}

export interface TodoItem {
  id: string
  text: string
  done: boolean
  assignee?: string
  source?: 'ai' | 'manual'
}

export interface Task {
  task_id: string
  status: TaskStatus
  progress: number
  message: string
  audio_name: string
  audio_path: string
  audio_duration: number | null
  speaker_count: number | null
  summary: string | null
  output_path: string | null
  created_at: string
  meeting_date: string | null
  error: string | null
  error_category: string | null
  error_suggestion: string | null
  failed_stage: string | null
  retry_count: number
  speaker_mapping: Record<string, string>
  dialogue: DialogueLine[]
  normalized_path: string | null
  voiceprint_match: unknown[]
  voiceprint_auto_mapping: Record<string, string>
  speaker_uuid_mapping: Record<string, string>
  title: string | null
  todos: TodoItem[]
  chapters: Chapter[]
  project_id: string | null
  source?: 'record' | 'upload'
  archived_at: string | null
}

// ─── 用户 / User ───

export interface User {
  id: string
  name: string
  avatar_url: string
  email: string
  role: string
  provider: string
  prefs: Record<string, unknown>
  privacy_consent_at?: string | null
}

// ─── 状态配置（与后端 STATUS_CONFIG 对齐） / Status config (aligned with backend STATUS_CONFIG) ───

export interface StatusConfig {
  label: string
  dotColor: string
  pulse: boolean
}

export const STATUS_CONFIG: Record<TaskStatus, StatusConfig> = {
  recording:        { label: '录音中',   dotColor: 'var(--rec)',    pulse: true },
  paused:           { label: '已暂停',   dotColor: 'var(--warn)',   pulse: false },
  pending:          { label: '等待处理', dotColor: 'var(--warn)',   pulse: false },
  processing:       { label: '处理中',   dotColor: 'var(--accent)', pulse: true },
  transcribing:     { label: '识别中',   dotColor: 'var(--accent)', pulse: true },
  awaiting_mapping: { label: '待关联身份', dotColor: 'var(--warn)', pulse: false },
  summarizing:      { label: '生成纪要', dotColor: 'var(--accent)', pulse: true },
  completed:        { label: '已完成',   dotColor: 'var(--ok)',     pulse: false },
  failed:           { label: '处理失败', dotColor: 'var(--rec)',    pulse: false },
}

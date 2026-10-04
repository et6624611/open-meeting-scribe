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
  /** 本地口语清理版（响应级富化，仅变化时挂键）/ Local cleaned text (response-enriched, only when changed) */
  clean_text?: string
  clean_ops?: import('@/composables/useWebSocket').CleanOp[]
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
  /** 本地口语清理版（响应级富化，仅变化时挂键）/ Local cleaned text (response-enriched, only when changed) */
  clean_text?: string
  clean_ops?: import('@/composables/useWebSocket').CleanOp[]
}

/** 书面版单句（WP-2 sidecar item）/ One formal-rewritten sentence */
export interface FormalItem {
  sentence_id: number
  begin_time?: number
  text: string
  /** 弱化/勉强语气标记，前端强制警示 / Weakened-tone marker (mandatory warning) */
  tone_flag: 'weakened' | null
}

/** 书面版 sidecar（GET /api/tasks/{id}/formal）/ Formal version sidecar */
export interface FormalVersion {
  version: number
  /** running|done|error|stale（stale 为读取时比对签名派生，不落盘） */
  status: 'running' | 'done' | 'error' | 'stale' | string
  scope: 'full' | 'selection' | string
  auto: boolean
  source_sig: { count: number; hash: string }
  model: string
  source: string
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
  created_at: string
  finished_at: string
  error: string
  progress?: { done: number; total: number }
  items: FormalItem[]
}

// 决策流状态：DC-R2-c 后为状态字典 id（不再是封闭枚举）
// Decision-flow status: a status-dictionary id since DC-R2-c (open set, user-maintainable)
export type DecisionStatus = string
// 等待谁推进(展示用标签) / Who is driving (display-only label)
export type OwnerType = 'self' | 'agent' | 'colleague' | 'enterprise'

/** 决策「已被替代」关系快照：标题/会议名冗余存储，目标被删后仍可展示（死链退化为纯文本） */
export interface SupersededBy {
  task_id: string
  todo_id: string
  title: string
  meeting_title: string
  prev_status: string
  marked_at: string
}

export interface TodoItem {
  id: string
  text: string          // 决策正文(沿用旧字段) / Decision body (legacy field)
  done: boolean         // 兼容字段：等价于状态属于闭档态 / Compat: status is a closing one
  assignee?: string
  source?: 'auto' | 'ai' | 'manual' | 'injection'
  deadline?: string
  // ── 决策链字段（人工编辑） / Decision-chain fields (human-edited) ──
  why?: string          // 为什么做这个决定 / Why this decision
  how?: string[]        // 如何完成：执行步骤，缺省视为 [text] / How: steps, defaults to [text]
  outcome?: string      // 完成后带来什么 / What it brings
  status?: DecisionStatus  // 缺省时由 done 推导 / Derived from done when absent
  owner_type?: OwnerType   // 等待谁推进(展示用) / Who drives (display-only)
  // ── DC-UNIFY-01：承接原 decision 对象的能力 / Absorbed from the retired decision record ──
  title?: string           // 决策短标题（auto/存量可为空）
  owner_id?: string | null // 执行人说话人档案 id
  pending_confirmation?: boolean
  /** 演变链：已被另一决策替代时的关系快照（手动标记；null/缺省=未标记） */
  superseded_by?: SupersededBy | null
  // 后端随行下发的状态字典元信息（读侧只用于展示，不回写）
  status_name?: string
  status_name_en?: string
  status_color?: string
  status_closing?: boolean
}

/** 声纹自动识别单项结果 / Single voiceprint auto-match result */
export interface VoiceprintMatchItem {
  speaker_id: number
  matched_uuid: string | null
  matched_name: string | null
  /** 最佳候选相似度（0~1，未命中也记录真实值） / Best-candidate similarity */
  similarity: number
  /** matched / unmatched / insufficient_audio */
  status: 'matched' | 'unmatched' | 'insufficient_audio'
  /** 未命中时的最佳候选姓名（仅供人工参考） / Best candidate name when unmatched */
  best_candidate: string | null
  /** 最佳与次优的差距 / Gap between best and second-best */
  margin: number
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
  /** AC-4（QA-R1 DEF-04）：本地引擎失败时后端落盘的错误码与云端回退标志；
   *  旧任务 JSON 无此字段，故为可选 / Local-engine failure error code & cloud-fallback flag (absent in legacy task JSON) */
  error_code?: string | null
  can_fallback_cloud?: boolean | null
  retry_count: number
  speaker_mapping: Record<string, string>
  dialogue: DialogueLine[]
  normalized_path: string | null
  voiceprint_match: VoiceprintMatchItem[] | null
  voiceprint_auto_mapping: Record<string, string> | null
  /** 已忽略声纹建议的 speaker_id（重跑识别自动清空） / Speaker ids with dismissed suggestions */
  voiceprint_dismissed?: number[] | null
  speaker_uuid_mapping: Record<string, string>
  roster: string[]
  title: string | null
  todos: TodoItem[]
  chapters: Chapter[]
  project_id: string | null
  source?: 'record' | 'upload' | 'import_transcript' | 'import_summary'
  archived_at: string | null
  /** 一页纸系数（会议级，纪要/洞察各自一页）；旧任务 JSON 无此字段，读取侧按 1 兜底
   *  Per-meeting one-page factors; absent in legacy task JSON (defaults to 1) */
  one_page?: { summary?: number; insights?: number } | null
  /** 转写分层信封（响应级，不入任务文件）：cleanup=true 表示 dialogue 已按当前设置富化 clean_text
   *  Transcript-layers envelope (response-level): cleanup=true means dialogue carries clean_text */
  transcript_layers?: { cleanup: boolean } | null
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
  subscription?: { tier: string; started_at?: string; expires_at?: string | null }
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

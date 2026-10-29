/**
 * OriginRegistry — 双 origin 平面注册器（档位②，契约 §1.8 / 设计 §二）
 *
 * 企业形态两个后端：
 *  - server plane：浏览器所在 origin（公司服务器）＝ /api/v1/* 账号面 + 上下文数据面；
 *  - local plane：本机录音助手（默认 http://127.0.0.1:8000）＝ /api/record/*、/ws/transcript/*、
 *    /api/engine/* 等设备控制面，首连 GET /api/local/handshake 换取 X-OMS-Local-Token。
 * 个人版形态：local plane 即 same-origin，零行为变化（契约 §4：两平面路由集合零交集）。
 *
 * local_token 为会话级机密：仅存内存，不落 localStorage/sessionStorage（W1-04 纪律）。
 */
import axios, { type AxiosInstance } from 'axios'
import { isEnterprise } from '@/edition'
import { getLocale } from '@/i18n'
import { scopedGet, scopedSet, scopedKey } from '@/utils/scopedStorage'

export type Plane = 'server' | 'local'

/** 录音助手默认探测地址（desktop.py/cli.py server 默认 127.0.0.1:8000） */
const DEFAULT_LOCAL_CANDIDATES = ['http://127.0.0.1:8000', 'http://localhost:8000']

interface LocalHandshake {
  local_token: string
  paired_user_id: string
}

interface LocalState {
  /** 已解析的 local origin；'' = same-origin（个人版形态） */
  origin: string
  handshake: LocalHandshake | null
  /** 握手建立时的 active user（W4-01：用户切换必须重新握手，防同机串号） */
  handshakeUid: string | null
  /** 握手失败原因（企业形态 UI 呈现"未连接录音助手"态） */
  error: string | null
  probing: Promise<LocalState> | null
  /** 进行中的探测所属 uid（跨用户不共享探测结果） */
  probingUid?: string | null
}

const local: LocalState = { origin: '', handshake: null, handshakeUid: null, error: null, probing: null }

/**
 * 当前登录用户（W4-02：助手地址覆盖按 uid 读取的前置）。
 * 由 user store 在登录/checkAuth 成功时写入、登出/过期时清空——
 * origins 不反向 import store，避免循环依赖。
 */
let activeUserId: string | null = null
export function setActiveUser(uid: string | null): void {
  if (uid !== activeUserId) {
    activeUserId = uid
    // 用户即上下文：切换用户时内存握手一律作废（W4-01 结构性防串号）
    invalidateLocalPlane()
  }
}

/** 服务端 origin（企业版即当前页面 origin） */
export function serverOrigin(): string {
  return window.location.origin
}

/** 用户（按命名空间）配置的助手地址覆盖；档位⑦设置页写入 */
export function setLocalOriginOverride(userId: string | null, url: string | null): void {
  if (!userId) return
  if (url) scopedSet(userId, 'local_origin_override', url.replace(/\/+$/, ''))
  else { try { localStorage.removeItem(scopedKey(userId, 'local_origin_override')) } catch { /* */ } }
}

function readLocalOriginOverride(userId: string | null): string | null {
  if (!userId) return null
  return scopedGet(userId, 'local_origin_override')
}

/** 当前 paired user（handshake 返回），供设备态 UI 展示 */
export function pairedUserId(): string | null {
  return local.handshake?.paired_user_id ?? null
}

export function localPlaneError(): string | null {
  return local.error
}

async function probeHandshake(origin: string): Promise<LocalHandshake | null> {
  try {
    const { data } = await axios.get<LocalHandshake>(`${origin}/api/local/handshake`, { timeout: 3000 })
    if (typeof data?.local_token === 'string' && data.local_token) return data
    return null
  } catch {
    return null
  }
}

/**
 * 确保 local plane 可用（幂等；并发共享同一次探测）。
 * 个人版直接返回 same-origin 态，不产生任何网络行为。
 */
export function ensureLocalPlane(userId?: string | null): Promise<LocalState> {
  if (!isEnterprise) {
    local.origin = ''
    return Promise.resolve(local)
  }
  const uid = userId ?? activeUserId
  // W4-01/02：握手归属用户与当前用户不一致 → 视为失效，重新探测（覆盖也按当前 uid 读）
  if (local.handshake && local.origin && local.handshakeUid === uid) return Promise.resolve(local)
  if (local.handshake && local.handshakeUid !== uid) invalidateLocalPlane()
  if (local.probing && local.probingUid === uid) return local.probing
  local.probingUid = uid
  local.probing = (async () => {
    const override = readLocalOriginOverride(uid)
    const candidates = [...new Set([
      ...(override ? [override] : []),
      ...DEFAULT_LOCAL_CANDIDATES,
    ])]
    for (const origin of candidates) {
      const hs = await probeHandshake(origin)
      if (hs) {
        local.origin = origin
        local.handshake = hs
        local.handshakeUid = uid
        local.error = null
        return local
      }
    }
    local.error = 'assistant_unreachable'
    return local
  })().finally(() => { local.probing = null; local.probingUid = null })
  return local.probing
}

/** 握手失效（token 轮换/助手重启/用户切换）时重置，下次调用重新探测 */
export function invalidateLocalPlane(): void {
  local.origin = ''
  local.handshake = null
  local.handshakeUid = null
  local.error = null
}

/**
 * local plane axios 实例（企业形态带 X-OMS-Local-Token；个人形态等价 same-origin 请求）。
 * record/engine 等设备面模块一律用它替代 client，保证个人版零变化。
 */
const localClient: AxiosInstance = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

localClient.interceptors.request.use(async (config) => {
  config.headers['Accept-Language'] = getLocale().replace('_', '-')
  if (isEnterprise) {
    await ensureLocalPlane()
    // origin 留空 = 助手不可达；请求将 404，由调用方按"未连接助手"处理
    config.baseURL = local.origin
    if (local.handshake) config.headers['X-OMS-Local-Token'] = local.handshake.local_token
  }
  return config
})

localClient.interceptors.response.use(
  (res) => res,
  (err) => {
    if (axios.isAxiosError(err)) {
      if (err.response?.status === 401 && isEnterprise) {
        // token 过期/助手重启 → 下请求重新握手（本次仍报错，由 UI 呈现重试）
        invalidateLocalPlane()
      }
      // 与 client.ts 同口径的错误日志格式（保持个人版排障体验零变化）
      if (err.response?.status !== 401) {
        const status = err.response?.status
        const detail = err.response?.data?.detail || err.message
        console.error(`[API] ${status ?? 'NETWORK'}: ${detail}`)
      }
    }
    return Promise.reject(err)
  },
)

/** 按平面取 axios 实例：'server'→既有 client；'local'→设备控制面实例 */
export function planeClient(plane: Plane): AxiosInstance {
  if (plane === 'local') return localClient
  return serverClientRef
}

// 延迟 import 避免循环依赖（client.ts 反向引用 edition/stores）
import client from './client'
const serverClientRef: AxiosInstance = client

/**
 * 实时转写 WS 地址（契约 §1.8：企业形态连本机助手并携本地 token）。
 * 浏览器 WebSocket 无法自定义请求头，token 经查询参数下发——已同步后端确认该承载方式（W4 前定稿）。
 * 个人版返回值与旧实现逐字节一致（same-origin，无 token 参数）。
 */
export async function transcriptWsUrl(taskId: string, locale: string): Promise<string> {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  let base = `${protocol}//${location.host}`
  if (isEnterprise) {
    await ensureLocalPlane()
    if (local.origin) {
      const wsHost = local.origin.replace(/^http/, 'ws')
      base = `${wsHost}`
    }
  }
  const token = isEnterprise && local.handshake ? local.handshake.local_token : null
  const q = token ? `locale=${locale}&oms_local_token=${encodeURIComponent(token)}` : `locale=${locale}`
  return `${base}/ws/transcript/${taskId}?${q}`
}

/**
 * 计算引擎状态 API / Compute engine status API
 *
 * R6（PRD-LOCAL-ENGINE）：徽章判定为双因子——本地引擎目录存在性 + settings.engine.mode。
 * R6 (PRD-LOCAL-ENGINE): badge state is two-factor — local engine directory presence + settings.engine.mode.
 *
 * TODO(WP-B 联调 / integration): 后端 `GET /api/engine/status` 尚未实现。
 * 实现后应返回 { mode, local: { ready, model_dir } }，本文件回退分支可删除。
 * Backend `GET /api/engine/status` is not implemented yet. Once available it should
 * return { mode, local: { ready, model_dir } } and the settings fallback below can be removed.
 */
import client from './client'
import { fetchSettings } from './settings'

/** 引擎模式（settings.engine.mode 契约，PRD §9） / Engine mode (settings.engine.mode contract, PRD §9) */
export type EngineMode = 'cloud' | 'proxy' | 'direct' | 'local'

export interface EngineStatus {
  /** 当前引擎模式 / Current engine mode */
  mode: EngineMode
  /** 本地引擎目录存在且模型就绪（双因子之一） / Local engine directory exists and models ready (factor 1 of 2) */
  local_ready: boolean
  /** 数据来源：api=后端状态接口 / settings=占位回退 / Data source: api=status endpoint / settings=placeholder fallback */
  source: 'api' | 'settings'
}

interface EngineStatusResponse {
  mode?: EngineMode
  local?: { ready?: boolean; model_dir?: string }
}

/**
 * 获取引擎状态：优先 /api/engine/status，接口不存在时回退 settings 占位字段。
 * Fetch engine status: prefer /api/engine/status, fall back to settings placeholder fields.
 */
export async function fetchEngineStatus(): Promise<EngineStatus> {
  try {
    const { data } = await client.get<EngineStatusResponse>('/api/engine/status')
    if (data && typeof data.mode === 'string') {
      return {
        mode: data.mode,
        local_ready: !!data.local?.ready,
        source: 'api',
      }
    }
  } catch {
    // 接口未就绪，落入 settings 回退 / Endpoint unavailable, fall through to settings fallback
  }

  // TODO(WP-B 联调 / integration): settings.engine 为占位契约，后端落地后由 /api/engine/status 取代。
  // settings.engine is a placeholder contract until the backend endpoint lands.
  const settings = await fetchSettings()
  const engine = settings.engine as { mode?: EngineMode; local?: { ready?: boolean } } | undefined
  const mode: EngineMode = engine?.mode
    ?? (settings.asr?.mode === 'direct' ? 'direct' : 'proxy')
  return {
    mode,
    local_ready: !!engine?.local?.ready,
    source: 'settings',
  }
}

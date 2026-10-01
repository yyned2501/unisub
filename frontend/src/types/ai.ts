/** AI 辅助识别配置。 */
export interface AiConfig {
  ai_assist_enabled: boolean
  ai_api_base: string
  ai_api_key: string
  ai_model: string
  ai_enable_search: boolean
  /** JEV 采纳闸门总开关（默认关；仅对阶段 4/5 的兜底候选生效） */
  jev_decision_enabled: boolean
  /** 影子模式：只记录 JEV 判定与实际采纳的差异，不影响下单 */
  jev_decision_shadow: boolean
  /** JEV API 地址 */
  jev_api_base: string
  /** JEV API Key（留空则用后端 .env 的 UNISUB_JEV_API_KEY） */
  jev_api_key: string
  /** JEV 模型（必须 pin 到具体版本，禁用 jev-latest 别名） */
  jev_model: string
  /** same_work 阈值：低于该值拦截（Phase 4A 推荐 0.5） */
  jev_same_work_threshold: number
}

/** AI 配置响应。 */
export interface AiConfigResponse {
  config: AiConfig
}

/** AI 配置更新请求。 */
export interface AiConfigUpdate {
  config: Partial<AiConfig>
}

/** AI 模型列表请求。 */
export interface AiModelListRequest {
  api_base: string
  api_key: string
}

/** 单个 AI 模型信息。 */
export interface AiModelItem {
  id: string
  object: string
}

/** AI 模型列表响应。 */
export interface AiModelListResponse {
  models: AiModelItem[]
}

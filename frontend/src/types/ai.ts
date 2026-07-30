/** AI 辅助识别配置。 */
export interface AiConfig {
  ai_assist_enabled: boolean
  ai_api_base: string
  ai_api_key: string
  ai_model: string
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

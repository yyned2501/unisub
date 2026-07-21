/**
 * 认证相关类型。
 */

/** 登录响应（OAuth2 token） */
export interface LoginResponse {
  access_token: string
  token_type: string
}

/** 认证信息 */
export interface AuthInfo {
  username: string
  [key: string]: unknown
}

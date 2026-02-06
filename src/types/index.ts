/**
 * 类型定义：项目全局类型
 */

/**
 * 任务步骤
 */
export interface TaskStep {
  type: string;
  action: string;
  params: Record<string, any>;
  description: string;
}

/**
 * 步骤执行结果
 */
export interface StepResult {
  success: boolean;
  message: string;
  data: any;
  /** 生成的图片路径 */
  images?: string[];
  /** 自动安装的包 */
  installed_packages?: string[];
}

/**
 * 任务执行结果
 */
export interface TaskResult {
  success: boolean;
  message: string;
  steps: Array<{
    step: TaskStep;
    result: StepResult;
  }>;
  user_instruction: string;
}

/**
 * 聊天消息
 */
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
  taskResult?: TaskResult;
  /** 图片附件（用于截图预览等） */
  images?: string[]; // base64 或文件路径
}

/**
 * AI提供商类型
 */
export type AIProvider = "claude" | "openai" | "deepseek" | "grok" | "anthropic";

/**
 * 应用配置
 */
export interface AppConfig {
  provider: AIProvider;
  api_key: string;
  model: string;
  sandbox_path: string;
  auto_confirm: boolean;
  log_level: string;
}

/**
 * 任务状态
 */
export type TaskStatus = "idle" | "planning" | "executing" | "completed" | "error" | "reflecting" | "multi_agent";

/**
 * 日志条目
 */
export interface LogEntry {
  timestamp: Date;
  level: "info" | "warning" | "error" | "success";
  message: string;
  /** 来源 Agent（多代理模式） */
  agent?: string;
}

/**
 * 右侧面板的“实时提示”（类似 ChatGPT/Grok 的思考提示）。
 * - 不进入聊天气泡
 * - 自动淡出/消失（由前端控制）
 */
export interface LiveNotice {
  id: string;
  timestamp: Date;
  message: string;
  phase?: string;
}

/**
 * Agent 类型（多代理协作）
 */
export type AgentType = "Planner" | "Executor" | "Reflector" | "Reviser" | "Summarizer" | "System" | "Crew";

/**
 * Agent 进度事件
 */
export interface AgentProgress {
  agent: AgentType;
  message: string;
  data?: Record<string, any>;
}

/**
 * 多代理执行模式
 */
export type ExecutionMode = "single-agent" | "multi-agent";

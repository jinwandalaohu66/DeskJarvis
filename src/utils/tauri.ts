/**
 * Tauri工具函数：调用Tauri命令
 * 
 * 支持浏览器环境降级（使用localStorage）
 */

// 检测是否在Tauri环境中
export function isTauriEnvironment(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in window || "__TAURI__" in window;
}

// 安全调用Tauri API
async function safeInvoke(command: string, args?: any): Promise<any> {
  if (!isTauriEnvironment()) {
    throw new Error("Tauri环境不可用");
  }
  
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return await invoke(command, args);
  } catch (e) {
    console.error(`调用Tauri命令失败 [${command}]:`, e);
    throw e;
  }
}

/**
 * 使用localStorage的配置管理（浏览器环境降级方案）
 */
const CONFIG_STORAGE_KEY = "deskjarvis_config";

function getConfigFromStorage(): any {
  try {
    const stored = localStorage.getItem(CONFIG_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch (e) {
    console.error("读取localStorage配置失败:", e);
  }
  // 返回默认配置
  return {
    provider: "claude",
    api_key: "",
    model: "claude-3-5-sonnet-20241022",
    sandbox_path: "",
    auto_confirm: false,
    log_level: "INFO",
  };
}

function saveConfigToStorage(config: any): void {
  try {
    localStorage.setItem(CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch (e) {
    console.error("保存localStorage配置失败:", e);
    throw new Error("保存配置失败: " + (e instanceof Error ? e.message : "未知错误"));
  }
}

/**
 * 执行用户指令
 * 
 * @param instruction 用户自然语言指令
 * @param context 上下文信息（可选），包含之前创建的文件等
 * @returns 任务执行结果
 */
export async function executeTask(instruction: string, context?: any): Promise<any> {
  if (isTauriEnvironment()) {
    try {
      return await safeInvoke("execute_task", { instruction, context: context || null });
    } catch (error) {
      console.error("执行任务失败:", error);
      throw error;
    }
  } else {
    // 浏览器环境：返回提示
    throw new Error("执行任务需要在Tauri桌面应用中运行。请使用 'npm run tauri:dev' 启动完整应用。");
  }
}

/**
 * 停止当前正在执行的任务
 */
export async function stopTask(): Promise<void> {
  if (isTauriEnvironment()) {
    try {
      await safeInvoke("stop_task");
    } catch (error) {
      console.error("停止任务失败:", error);
      throw error;
    }
  } else {
    console.warn("停止任务需要在Tauri桌面应用中运行");
  }
}

/**
 * 获取配置
 * 
 * @returns 应用配置
 */
export async function getConfig(): Promise<any> {
  if (isTauriEnvironment()) {
    try {
      return await safeInvoke("get_config");
    } catch (error) {
      console.warn("从Tauri获取配置失败，使用localStorage:", error);
      // 降级到localStorage
      return getConfigFromStorage();
    }
  } else {
    // 浏览器环境：使用localStorage
    return getConfigFromStorage();
  }
}

/**
 * 保存配置
 * 
 * @param config 配置对象
 */
export async function saveConfig(config: any): Promise<void> {
  // 总是先保存到localStorage（作为备份和浏览器环境支持）
  saveConfigToStorage(config);
  
  if (isTauriEnvironment()) {
    try {
      await safeInvoke("save_config", { config });
    } catch (error) {
      console.warn("保存配置到Tauri失败，已保存到localStorage:", error);
      // localStorage已经保存了，所以不抛出错误
    }
  }
  // 浏览器环境：已经在上面保存到localStorage了
}

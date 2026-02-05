/**
 * App组件：应用主入口
 * 
 * 遵循 docs/ARCHITECTURE.md 中的UI组件规范
 */

import React, { useState, useEffect } from "react";
import { ChatInterface } from "./components/ChatInterface";
import { Settings } from "./components/Settings";
import { ProgressPanel } from "./components/ProgressPanel";
import { AppConfig, TaskStatus, LogEntry, AgentType, ExecutionMode } from "./types";
import { getConfig } from "./utils/tauri";

type Page = "chat" | "settings";

/**
 * App主组件
 */
export const App: React.FC = () => {
  console.log("[App] 组件渲染");
  const [currentPage, setCurrentPage] = useState<Page>("chat");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [loading, setLoading] = useState(true);
  
  // 进度面板状态
  const [progressCollapsed, setProgressCollapsed] = useState(false);
  const [taskStatus, setTaskStatus] = useState<TaskStatus>("idle");
  const [taskSteps, setTaskSteps] = useState<Array<{ step: any; result?: any }>>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [taskLogs, setTaskLogs] = useState<LogEntry[]>([]);
  
  // 多代理协作状态
  const [executionMode, setExecutionMode] = useState<ExecutionMode>("single-agent");
  const [activeAgent, setActiveAgent] = useState<AgentType | undefined>(undefined);

  useEffect(() => {
    // 加载配置
    loadConfig();
    
    // 监听侧边栏设置按钮的点击事件
    const handleNavigateToSettings = () => {
      setCurrentPage("settings");
    };
    
    window.addEventListener("navigate-to-settings", handleNavigateToSettings);
    
    return () => {
      window.removeEventListener("navigate-to-settings", handleNavigateToSettings);
    };
  }, []);

  const loadConfig = async () => {
    try {
      console.log("[App] 开始加载配置...");
      const cfg = await getConfig();
      console.log("[App] 配置加载成功:", cfg);
      setConfig(cfg);
    } catch (error) {
      console.error("[App] 加载配置失败:", error);
      // 如果加载失败，使用默认配置
      const defaultConfig: AppConfig = {
        provider: "claude" as const,
        api_key: "",
        model: "claude-3-5-sonnet-20241022",
        sandbox_path: "",
        auto_confirm: false,
        log_level: "INFO",
      };
      console.log("[App] 使用默认配置:", defaultConfig);
      setConfig(defaultConfig);
    } finally {
      console.log("[App] 设置 loading = false");
      setLoading(false);
    }
  };

  console.log("[App] 渲染状态:", { loading, config, currentPage });

  if (loading) {
    console.log("[App] 显示加载界面");
    return (
      <div className="flex items-center justify-center h-screen bg-gray-100 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto border-t-transparent"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">加载中...</p>
        </div>
      </div>
    );
  }

  console.log("[App] 显示主界面");
  return (
    <div className="h-screen flex flex-col bg-white dark:bg-[#0a0a0a]">
      {/* 主内容区 */}
      <main className="flex-1 overflow-hidden flex">
        {/* 左侧：聊天或设置 */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {/* 使用 CSS 隐藏而不是卸载，保持聊天状态 */}
          <div className={`flex-1 overflow-hidden ${currentPage === "chat" ? "block" : "hidden"}`}>
            <ChatInterface
              config={config}
              onStepsChange={setTaskSteps}
              onCurrentStepChange={setCurrentStepIndex}
              onLogsChange={setTaskLogs}
              onStatusChange={setTaskStatus}
              onProgressPanelToggle={() => setProgressCollapsed(!progressCollapsed)}
              onExecutionModeChange={setExecutionMode}
              onActiveAgentChange={setActiveAgent}
            />
          </div>
          {currentPage === "settings" && (
            <Settings 
              config={config} 
              onConfigChange={loadConfig}
              onBack={() => setCurrentPage("chat")}
            />
          )}
        </div>

        {/* 右侧：进度面板（仅在聊天页面显示） */}
        {currentPage === "chat" && (
          <ProgressPanel
            collapsed={progressCollapsed}
            onToggleCollapse={() => setProgressCollapsed(!progressCollapsed)}
            status={taskStatus}
            steps={taskSteps}
            currentStepIndex={currentStepIndex}
            logs={taskLogs}
            activeAgent={activeAgent}
            executionMode={executionMode}
          />
        )}
      </main>
    </div>
  );
};

export default App;

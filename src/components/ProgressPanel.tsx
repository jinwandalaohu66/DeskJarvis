/**
 * 进度面板组件
 */

import React, { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TaskStep, StepResult, TaskStatus, AgentType, ExecutionMode } from "../types";

interface ProgressPanelProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  status: TaskStatus;
  steps: Array<{
    step: TaskStep;
    result?: StepResult;
  }>;
  currentStepIndex: number;
  logs: Array<{
    timestamp: Date;
    level: "info" | "warning" | "error" | "success";
    message: string;
    agent?: string;
  }>;
  /** 当前活动的 Agent（多代理模式） */
  activeAgent?: AgentType;
  /** 执行模式 */
  executionMode?: ExecutionMode;
}

/**
 * Agent 图标颜色映射
 */
const AGENT_COLORS: Record<AgentType, string> = {
  Planner: "bg-purple-500",
  Executor: "bg-blue-500",
  Reflector: "bg-yellow-500",
  Reviser: "bg-orange-500",
  Summarizer: "bg-green-500",
  System: "bg-gray-500",
  Crew: "bg-indigo-500",
};

/**
 * Agent 图标
 */
const AgentIcon: React.FC<{ agent: AgentType; size?: "sm" | "md" }> = ({ agent, size = "sm" }) => {
  const sizeClass = size === "sm" ? "w-4 h-4 text-[8px]" : "w-6 h-6 text-[10px]";
  return (
    <div className={`${sizeClass} ${AGENT_COLORS[agent]} rounded-full flex items-center justify-center text-white font-bold`}>
      {agent[0]}
    </div>
  );
};

type StepStatus = "pending" | "running" | "success" | "error";

function getStepStatus(
  index: number,
  currentIndex: number,
  result?: StepResult,
  taskStatus?: TaskStatus
): StepStatus {
  if (result?.success === false) return "error";
  if (result?.success === true) return "success";
  if (index === currentIndex && taskStatus === "executing") return "running";
  if (index < currentIndex) return "success";
  return "pending";
}

/**
 * 简洁的步骤项组件
 */
const StepItem: React.FC<{
  step: TaskStep;
  result?: StepResult;
  status: StepStatus;
  index: number;
  total: number;
}> = ({ step, result, status, index, total }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 5 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.15 }}
      className="flex items-start gap-3 py-2"
    >
      {/* 左侧：状态图标 */}
      <div className="flex-shrink-0 mt-0.5">
        {status === "success" && (
          <div className="w-5 h-5 rounded-full bg-green-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}
        {status === "error" && (
          <div className="w-5 h-5 rounded-full bg-red-500 flex items-center justify-center">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </div>
        )}
        {status === "running" && (
          <div className="w-5 h-5 rounded-full border-2 border-blue-500 border-t-transparent animate-spin" />
        )}
        {status === "pending" && (
          <div className="w-5 h-5 rounded-full bg-gray-200 dark:bg-gray-700 flex items-center justify-center">
            <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium">{index + 1}</span>
          </div>
        )}
      </div>

      {/* 右侧：内容 */}
      <div className="flex-1 min-w-0">
        <div className={`text-sm leading-tight ${
          status === "success" 
            ? "text-gray-900 dark:text-gray-100" 
            : status === "error"
            ? "text-red-600 dark:text-red-400"
            : status === "running"
            ? "text-blue-600 dark:text-blue-400"
            : "text-gray-500 dark:text-gray-400"
        }`}>
          {step.action || step.description || `步骤 ${index + 1}`}
        </div>
        
        {/* 结果消息 - 只显示简洁的结果 */}
        {result?.message && (
          <div className={`text-xs mt-1 break-words line-clamp-2 ${
            result.success 
              ? "text-green-600 dark:text-green-400" 
              : "text-red-500 dark:text-red-400"
          }`} title={result.message}>
            {result.message.length > 80 ? result.message.substring(0, 80) + "..." : result.message}
          </div>
        )}
        
        {/* 显示生成的图表 */}
        {result?.images && Array.isArray(result.images) && result.images.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              生成的图表:
            </div>
            {result.images.map((imagePath: string, idx: number) => (
              <div 
                key={idx} 
                className="relative group rounded-lg overflow-hidden border-2 border-dashed border-gray-200 dark:border-gray-600 hover:border-green-400 dark:hover:border-green-500 transition-colors cursor-pointer bg-gray-50 dark:bg-gray-800/50"
                onClick={async () => {
                  try {
                    // 使用 Tauri 打开文件
                    const { invoke } = await import('@tauri-apps/api/core');
                    await invoke('open_file', { path: imagePath });
                  } catch (e) {
                    console.error('打开文件失败:', e);
                    // 备选方案：复制路径到剪贴板
                    navigator.clipboard.writeText(imagePath);
                    alert(`图表路径已复制: ${imagePath}`);
                  }
                }}
              >
                <div className="p-3 flex items-center gap-3">
                  {/* 图表图标 */}
                  <div className="w-12 h-12 rounded-lg bg-gradient-to-br from-green-400 to-emerald-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                    <svg className="w-6 h-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  {/* 文件信息 */}
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">
                      {imagePath.split('/').pop()}
                    </div>
                    <div className="text-xs text-gray-400 dark:text-gray-500">
                      已保存到桌面
                    </div>
                  </div>
                  {/* 打开图标 */}
                  <div className="text-gray-400 group-hover:text-green-500 transition-colors">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* 显示自动安装的包 */}
        {result?.installed_packages && Array.isArray(result.installed_packages) && result.installed_packages.length > 0 && (
          <div className="mt-2 flex items-center gap-1.5 text-xs">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              自动安装
            </span>
            <span className="text-gray-500 dark:text-gray-400">
              {result.installed_packages.join(", ")}
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

const panelTransition = {
  type: "tween" as const,
  duration: 0.2,
  ease: [0.4, 0, 0.2, 1] as const,
};

export const ProgressPanel: React.FC<ProgressPanelProps> = ({
  collapsed,
  onToggleCollapse,
  status,
  steps,
  currentStepIndex,
  logs,
  activeAgent,
  executionMode = "single-agent"
}) => {
  const logsEndRef = useRef<HTMLDivElement>(null);
  const expandedWidth = 300;
  const collapsedWidth = 64;

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const completedCount = steps.filter(s => s.result?.success === true).length;

  return (
    <motion.div
      initial={false}
      animate={{ width: collapsed ? collapsedWidth : expandedWidth }}
      transition={panelTransition}
      className="bg-white dark:bg-[#0a0a0a] flex flex-col h-full overflow-hidden"
      style={{ flexShrink: 0 }}
    >
      {/* 头部 */}
      <div className="flex-shrink-0 relative" style={{ minHeight: '56px' }}>
        {/* 收起状态 */}
        <div 
          className="absolute inset-0 flex flex-col items-center justify-center px-3 py-3"
          style={{
            opacity: collapsed ? 1 : 0,
            visibility: collapsed ? 'visible' : 'hidden',
            pointerEvents: collapsed ? 'auto' : 'none',
          }}
        >
          <button
            onClick={onToggleCollapse}
            className="w-10 h-10 rounded-2xl bg-black dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 flex items-center justify-center active:scale-95 transition-transform"
            title="展开进度面板"
          >
            <svg className="w-4 h-4 text-white dark:text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </button>
        </div>

        {/* 展开状态 */}
        <div 
          className="absolute inset-0 flex items-center justify-between px-4 py-3"
          style={{
            opacity: collapsed ? 0 : 1,
            visibility: collapsed ? 'hidden' : 'visible',
            pointerEvents: collapsed ? 'none' : 'auto',
          }}
        >
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">任务进度</h3>
          <button
            onClick={onToggleCollapse}
            className="w-9 h-9 rounded-2xl bg-black dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 flex items-center justify-center active:scale-95 transition-transform"
            title="折叠进度面板"
          >
            <svg className="w-4 h-4 text-white dark:text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </button>
        </div>
      </div>

      {/* 折叠时的进度指示器 */}
      <div 
        className="flex-shrink-0 flex flex-col items-center px-2 py-4"
        style={{
          opacity: collapsed && status !== "idle" ? 1 : 0,
          visibility: collapsed && status !== "idle" ? 'visible' : 'hidden',
          height: collapsed && status !== "idle" ? 'auto' : 0,
        }}
      >
        <div className="w-8 h-8 rounded-full border-2 border-blue-500 border-t-transparent animate-spin"></div>
        <div className="mt-2 text-xs text-gray-600 dark:text-gray-400 text-center font-medium">
          {completedCount}/{steps.length}
        </div>
      </div>

      {/* 展开时的内容 */}
      <div 
        className="flex-1 flex flex-col overflow-hidden"
        style={{ 
          opacity: collapsed ? 0 : 1,
          visibility: collapsed ? 'hidden' : 'visible',
        }}
      >
        {/* 多代理模式指示器 - 简洁样式 */}
        {executionMode === "multi-agent" && activeAgent && (
          <div className="flex-shrink-0 mx-4 mt-2 mb-3">
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
                {activeAgent}
              </span>
              <span className="text-xs text-gray-400 dark:text-gray-500">
                协作中
              </span>
            </div>
          </div>
        )}

        {/* 状态和进度 */}
        {status !== "idle" && (
          <div className="flex-shrink-0 px-4 pb-3">
            <div className="flex items-center justify-between mb-2">
              <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                status === "planning" 
                  ? "bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400"
                  : status === "executing"
                  ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                  : status === "reflecting"
                  ? "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-600 dark:text-yellow-400"
                  : status === "completed"
                  ? "bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400"
                  : status === "multi_agent"
                  ? "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                  : "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
              }`}>
                {status === "planning" && "规划中"}
                {status === "executing" && "执行中"}
                {status === "multi_agent" && "团队协作中"}
                {status === "reflecting" && "反思中"}
                {status === "completed" && "已完成"}
                {status === "error" && "失败"}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {completedCount}/{steps.length}
              </span>
            </div>
          </div>
        )}

        {/* 步骤列表 */}
        <div className="flex-1 overflow-y-auto px-4 pb-3 scrollbar-auto-hide">
          {steps.length === 0 ? (
            <div className="text-center text-gray-400 dark:text-gray-500 py-8">
              <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
              <p className="text-sm">暂无任务步骤</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-800">
              <AnimatePresence>
                {steps.map((item, index) => {
                  const stepStatus = getStepStatus(index, currentStepIndex, item.result, status);
                  return (
                    <StepItem
                      key={index}
                      step={item.step}
                      result={item.result}
                      status={stepStatus}
                      index={index}
                      total={steps.length}
                    />
                  );
                })}
              </AnimatePresence>
            </div>
          )}
        </div>

        {/* 日志区域 */}
        {logs.length > 0 && (
          <div className="flex-shrink-0 bg-gray-100 dark:bg-gray-800/50">
            <details className="px-4 py-3">
              <summary className="text-sm font-semibold text-gray-700 dark:text-gray-300 cursor-pointer">
                执行日志 ({logs.length})
              </summary>
              <div className="mt-2 max-h-32 overflow-y-auto space-y-1 font-mono text-xs">
                {logs.slice(-10).map((log, index) => (
                  <div
                    key={index}
                    className={`py-1 px-2 rounded ${
                      log.level === "error"
                        ? "text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20"
                        : log.level === "warning"
                        ? "text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20"
                        : log.level === "success"
                        ? "text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20"
                        : "text-gray-600 dark:text-gray-400"
                    }`}
                  >
                    <span className="text-gray-400 dark:text-gray-500">
                      {log.timestamp.toLocaleTimeString()}
                    </span>{" "}
                    <span className="font-semibold">[{log.level.toUpperCase()}]</span> {log.message}
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </details>
          </div>
        )}
      </div>
    </motion.div>
  );
};

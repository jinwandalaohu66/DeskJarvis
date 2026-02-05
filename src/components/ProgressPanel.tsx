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
  activeAgent?: AgentType;
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
      className="flex items-start gap-3 py-2.5"
    >
      {/* 左侧：状态图标 */}
      <div className="flex-shrink-0 mt-0.5">
        {status === "success" && (
          <div className="w-5 h-5 rounded-full bg-emerald-500 flex items-center justify-center shadow-sm">
            <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          </div>
        )}
        {status === "error" && (
          <div className="w-5 h-5 rounded-full bg-red-500 flex items-center justify-center shadow-sm">
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
        
        {/* 结果消息 */}
        {result?.message && (
          <div className={`text-xs mt-1 break-words line-clamp-2 ${
            result.success 
              ? "text-emerald-600 dark:text-emerald-400" 
              : "text-red-500 dark:text-red-400"
          }`} title={result.message}>
            {result.message.length > 80 ? result.message.substring(0, 80) + "..." : result.message}
          </div>
        )}
        
        {/* 显示生成的图表 */}
        {result?.images && Array.isArray(result.images) && result.images.length > 0 && (
          <div className="mt-3 space-y-2">
            {result.images.map((imagePath: string, idx: number) => (
              <div 
                key={idx} 
                className="group rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 hover:border-emerald-400 dark:hover:border-emerald-500 transition-all cursor-pointer bg-gradient-to-r from-gray-50 to-white dark:from-gray-800/50 dark:to-gray-800 hover:shadow-md"
                onClick={async () => {
                  try {
                    const { invoke } = await import('@tauri-apps/api/core');
                    await invoke('open_file', { path: imagePath });
                  } catch (e) {
                    navigator.clipboard.writeText(imagePath);
                  }
                }}
              >
                <div className="p-3 flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center flex-shrink-0 shadow-sm">
                    <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-700 dark:text-gray-200 truncate">
                      {imagePath.split('/').pop()}
                    </div>
                    <div className="text-xs text-gray-400">点击打开</div>
                  </div>
                  <svg className="w-4 h-4 text-gray-400 group-hover:text-emerald-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                  </svg>
                </div>
              </div>
            ))}
          </div>
        )}
        
        {/* 显示自动安装的包 */}
        {result?.installed_packages && Array.isArray(result.installed_packages) && result.installed_packages.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {result.installed_packages.map((pkg: string, idx: number) => (
              <span key={idx} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400">
                {pkg}
              </span>
            ))}
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

// 收起状态的按钮样式
const collapsedButtonStyle: React.CSSProperties = {
  width: '40px',
  height: '40px',
  borderRadius: '16px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  flexShrink: 0,
  padding: 0,
  border: 'none',
  cursor: 'pointer',
};

const iconStyle: React.CSSProperties = {
  width: '16px',
  height: '16px',
  flexShrink: 0,
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
  const errorCount = steps.filter(s => s.result?.success === false).length;
  const totalSteps = steps.length;

  return (
    <motion.div
      initial={false}
      animate={{ width: collapsed ? collapsedWidth : expandedWidth }}
      transition={panelTransition}
      className="bg-white dark:bg-[#0a0a0a] border-l border-gray-200 dark:border-gray-800 flex flex-col h-full overflow-hidden"
      style={{ flexShrink: 0 }}
    >
      {/* 顶部按钮区域 - 使用条件渲染 */}
      <div className="flex-shrink-0 pt-4 pb-2">
        {collapsed ? (
          // 收起状态：垂直居中排列
          <div style={{ width: '64px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
            <button 
              onClick={onToggleCollapse} 
              className="bg-black dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 active:scale-95 transition-transform"
              style={collapsedButtonStyle} 
              title="展开进度面板"
            >
              <svg style={iconStyle} className="text-white dark:text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </button>
            
            {/* 收起时的步骤进度指示器 - 使用数字圆环 */}
            {status !== "idle" && totalSteps > 0 && (
              <div className="flex flex-col items-center gap-1">
                {/* 进度圆环 */}
                <div className="relative w-10 h-10">
                  {/* 背景圆环 */}
                  <svg className="w-10 h-10 transform -rotate-90" viewBox="0 0 36 36">
                    <circle
                      cx="18" cy="18" r="15"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      className="text-gray-200 dark:text-gray-700"
                    />
                    {/* 进度圆环 */}
                    <circle
                      cx="18" cy="18" r="15"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeDasharray={`${(completedCount / totalSteps) * 94.2} 94.2`}
                      strokeLinecap="round"
                      className={errorCount > 0 ? "text-red-500" : completedCount === totalSteps ? "text-emerald-500" : "text-blue-500"}
                    />
                  </svg>
                  {/* 中心数字 */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className={`text-xs font-bold ${
                      errorCount > 0 ? "text-red-500" : completedCount === totalSteps ? "text-emerald-500" : "text-blue-500"
                    }`}>
                      {completedCount}
                    </span>
                  </div>
                </div>
                {/* 总数 */}
                <span className="text-[10px] text-gray-400 dark:text-gray-500">/{totalSteps}</span>
              </div>
            )}
          </div>
        ) : (
          // 展开状态：水平排列
          <div className="flex items-center justify-between px-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">任务进度</h3>
            <button
              onClick={onToggleCollapse}
              className="w-9 h-9 rounded-xl bg-black dark:bg-white hover:bg-gray-800 dark:hover:bg-gray-200 flex items-center justify-center flex-shrink-0 active:scale-95 transition-transform"
              title="折叠进度面板"
            >
              <svg className="w-4 h-4 text-white dark:text-black" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </button>
          </div>
        )}
      </div>

      {/* 展开时的内容 */}
      {!collapsed && (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* 多代理模式指示器 */}
          {executionMode === "multi-agent" && activeAgent && (
            <div className="flex-shrink-0 mx-4 mb-3">
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 border border-indigo-100 dark:border-indigo-800/50">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400">
                  {activeAgent}
                </span>
                <span className="text-xs text-gray-400">协作中</span>
              </div>
            </div>
          )}

          {/* 状态和进度 */}
          {status !== "idle" && (
            <div className="flex-shrink-0 px-4 pb-3">
              <div className="flex items-center justify-between">
                <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                  status === "planning" 
                    ? "bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400"
                    : status === "executing"
                    ? "bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400"
                    : status === "reflecting"
                    ? "bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400"
                    : status === "completed"
                    ? "bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400"
                    : status === "multi_agent"
                    ? "bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                    : "bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400"
                }`}>
                  {status === "planning" && "规划中"}
                  {status === "executing" && "执行中"}
                  {status === "multi_agent" && "协作中"}
                  {status === "reflecting" && "反思中"}
                  {status === "completed" && "已完成"}
                  {status === "error" && "失败"}
                </span>
                <div className="flex items-center gap-1.5">
                  {errorCount > 0 && (
                    <span className="text-xs text-red-500 font-medium">{errorCount} 失败</span>
                  )}
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                    {completedCount}/{totalSteps}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* 步骤列表 */}
          <div className="flex-1 overflow-y-auto px-4 pb-3 scrollbar-auto-hide">
            {steps.length === 0 ? (
              <div className="text-center text-gray-400 dark:text-gray-500 py-12">
                <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gray-100 dark:bg-gray-800 flex items-center justify-center">
                  <svg className="w-8 h-8 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                </div>
                <p className="text-sm">发送指令开始任务</p>
              </div>
            ) : (
              <div className="space-y-0.5">
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

          {/* 日志区域 - 美化版 */}
          {logs.length > 0 && (
            <div className="flex-shrink-0 border-t border-gray-100 dark:border-gray-800">
              <details className="group">
                <summary className="px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-gray-400 group-open:text-blue-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                    </svg>
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">执行日志</span>
                    <span className="text-xs px-1.5 py-0.5 rounded-full bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                      {logs.length}
                    </span>
                  </div>
                  <svg className="w-4 h-4 text-gray-400 transition-transform group-open:rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </summary>
                <div className="px-4 pb-4">
                  <div className="max-h-40 overflow-y-auto rounded-xl bg-gray-900 dark:bg-black p-3 space-y-1 scrollbar-auto-hide">
                    {logs.slice(-15).map((log, index) => (
                      <div
                        key={index}
                        className="flex items-start gap-2 text-xs font-mono"
                      >
                        {/* 时间戳 */}
                        <span className="text-gray-500 flex-shrink-0">
                          {log.timestamp.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                        </span>
                        {/* 级别图标 */}
                        <span className={`flex-shrink-0 w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold ${
                          log.level === "error"
                            ? "bg-red-500/20 text-red-400"
                            : log.level === "warning"
                            ? "bg-amber-500/20 text-amber-400"
                            : log.level === "success"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : "bg-blue-500/20 text-blue-400"
                        }`}>
                          {log.level === "error" ? "E" : log.level === "warning" ? "W" : log.level === "success" ? "✓" : "I"}
                        </span>
                        {/* 消息 */}
                        <span className={`flex-1 break-words ${
                          log.level === "error"
                            ? "text-red-400"
                            : log.level === "warning"
                            ? "text-amber-400"
                            : log.level === "success"
                            ? "text-emerald-400"
                            : "text-gray-300"
                        }`}>
                          {log.message}
                        </span>
                      </div>
                    ))}
                    <div ref={logsEndRef} />
                  </div>
                </div>
              </details>
            </div>
          )}
        </div>
      )}
    </motion.div>
  );
};

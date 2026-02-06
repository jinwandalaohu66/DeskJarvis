/**
 * 聊天界面组件：ChatGPT 风格的消息界面
 * 
 * 功能：
 * - ChatGPT 风格泡泡消息（用户右蓝、AI 左白）
 * - 支持 Markdown 渲染
 * - 图片预览
 * - 与现有代码兼容
 * 
 * 遵循 docs/ARCHITECTURE.md 中的UI组件规范
 */

import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage, TaskStatus, AppConfig, LogEntry, TaskResult, AgentType, LiveNotice } from "../types";
import { executeTask, isTauriEnvironment } from "../utils/tauri";
import { ChatSidebar, ChatSession } from "./ChatSidebar";
import { UserInputDialog, InputRequest } from "./UserInputDialog";
import { 
  toastVariants, 
  messageVariants, 
  imagePreviewVariants,
  transitionFast
} from "../utils/animations";
import { createLogger } from "../utils/logger";

const log = createLogger('Chat');

// 导入Tauri事件API
let listenProgress: any = null;
let tauriInvoke: any = null;
if (isTauriEnvironment()) {
  import("@tauri-apps/api/event").then((module) => {
    listenProgress = module.listen;
  });
  import("@tauri-apps/api/core").then((module) => {
    tauriInvoke = module.invoke;
  });
}

interface ChatInterfaceProps {
  config: AppConfig | null;
  /** 任务步骤变化回调 */
  onStepsChange?: (steps: Array<{ step: any; result?: any }>) => void;
  /** 当前步骤索引变化回调 */
  onCurrentStepChange?: (index: number) => void;
  /** 日志变化回调 */
  onLogsChange?: (logs: LogEntry[]) => void;
  /** 任务状态变化回调 */
  onStatusChange?: (status: TaskStatus) => void;
  /** 右侧实时提示变化回调（类似 ChatGPT/Grok 的思考提示） */
  onLiveNoticesChange?: (notices: LiveNotice[]) => void;
  /** 进度面板切换回调 */
  onProgressPanelToggle?: () => void;
  /** 执行模式变化回调 */
  onExecutionModeChange?: (mode: "single-agent" | "multi-agent") => void;
  /** 活动 Agent 变化回调 */
  onActiveAgentChange?: React.Dispatch<React.SetStateAction<AgentType | undefined>>;
}

/**
 * 聊天界面组件
 */
export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  config,
  onStepsChange,
  onCurrentStepChange,
  onLogsChange,
  onStatusChange,
  onLiveNoticesChange,
  onProgressPanelToggle,
  onExecutionModeChange,
  onActiveAgentChange,
}) => {
  // 聊天会话管理
  const [chats, setChats] = useState<ChatSession[]>([]);
  const [currentChatId, setCurrentChatId] = useState<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    // 从 localStorage 加载折叠状态
    const saved = localStorage.getItem("deskjarvis_sidebar_collapsed");
    return saved === "true";
  });
  // 当前聊天的消息
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<TaskStatus>("idle");
  const statusRef = useRef<TaskStatus>("idle"); // 用于在定时器中访问最新状态
  const [currentSteps, setCurrentSteps] = useState<Array<{ step: any; result?: any }>>([]);
  const [currentStepIndex, setCurrentStepIndex] = useState(-1);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [liveNotices, setLiveNotices] = useState<LiveNotice[]>([]);
  const [lastTaskContext, setLastTaskContext] = useState<any>(null); // 保存上次任务上下文
  const [isDragging, setIsDragging] = useState(false);
  const [attachedPath, setAttachedPath] = useState<string | null>(null);
  
  // 用户输入请求（登录、验证码等）
  const [userInputRequest, setUserInputRequest] = useState<InputRequest | null>(null);
  
  // 多代理协作状态
  const [executionMode, setExecutionMode] = useState<"single-agent" | "multi-agent">("single-agent");
  const [activeAgent, setActiveAgent] = useState<AgentType | undefined>(undefined);
  const [copyToast, setCopyToast] = useState<{ show: boolean; message: string }>({ show: false, message: "" });
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null); // 追踪已复制的消息ID
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentAssistantMessageIdRef = useRef<string | null>(null); // 跟踪当前正在更新的AI消息ID
  const prevMessagesLengthRef = useRef<number>(0); // 用于优化滚动性能
  const isTaskCancelledRef = useRef<boolean>(false); // 任务是否被取消
  const unlistenProgressRef = useRef<(() => void) | null>(null); // 进度事件监听器的清理函数

  // 组件加载时输出日志，确认控制台正常工作
  useEffect(() => {
    log.debug("[ChatInterface] 组件已加载");
    log.debug("[ChatInterface] Tauri环境:", isTauriEnvironment());
    
    // 监听 Tauri 原生拖拽事件（获取完整文件路径）
    let unlistenDrop: (() => void) | null = null;
    
    if (isTauriEnvironment()) {
      import("@tauri-apps/api/event").then(({ listen }) => {
        listen<{ paths: string[] }>("tauri://drag-drop", (event) => {
          log.debug("[拖拽] 收到文件:", event.payload.paths);
          if (event.payload.paths && event.payload.paths.length > 0) {
            const path = event.payload.paths[0];
            setAttachedPath(path);
            setInput((prev) => {
              const trimmed = prev.trim();
              return trimmed ? `${trimmed}` : "";
            });
          }
        }).then((unlisten) => {
          unlistenDrop = unlisten;
        });
      });
    }
    
    return () => {
      if (unlistenDrop) unlistenDrop();
    };
  }, []);

  // 从 localStorage 加载聊天历史
  useEffect(() => {
    const savedChats = localStorage.getItem("deskjarvis_chats");
    if (savedChats) {
      try {
        const parsedChats = JSON.parse(savedChats).map((chat: any) => ({
          ...chat,
          createdAt: new Date(chat.createdAt),
          updatedAt: new Date(chat.updatedAt),
        }));
        setChats(parsedChats);
        
        // 如果有聊天记录，默认选中第一个
        if (parsedChats.length > 0) {
          setCurrentChatId(parsedChats[0].id);
          loadChatMessages(parsedChats[0].id);
        }
      } catch (e) {
        log.error("加载聊天历史失败:", e);
      }
    }
  }, []);

  // 当 currentChatId 变化时，保存上一个聊天的消息（作为额外保护）
  const prevChatIdRef = useRef<string | null>(null);
  const prevMessagesRef = useRef<ChatMessage[]>([]);
  useEffect(() => {
    // 如果之前有聊天ID且有消息，保存它
    if (prevChatIdRef.current && prevChatIdRef.current !== currentChatId && prevMessagesRef.current.length > 0) {
      saveChatMessages(prevChatIdRef.current, prevMessagesRef.current);
    }
    // 更新 ref
    prevChatIdRef.current = currentChatId;
    prevMessagesRef.current = messages;
  }, [currentChatId, messages]);

  // 组件卸载时保存当前聊天的消息
  useEffect(() => {
    return () => {
      if (currentChatId && messages.length > 0) {
        saveChatMessages(currentChatId, messages);
      }
    };
  }, []);

  // 保存聊天历史到 localStorage
  const saveChats = (updatedChats: ChatSession[]) => {
    localStorage.setItem("deskjarvis_chats", JSON.stringify(updatedChats));
    setChats(updatedChats);
  };

  // 加载指定聊天的消息
  const loadChatMessages = (chatId: string) => {
    const savedMessages = localStorage.getItem(`deskjarvis_messages_${chatId}`);
    if (savedMessages) {
      try {
        const parsedMessages = JSON.parse(savedMessages).map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }));
        setMessages(parsedMessages);
      } catch (e) {
        log.error("加载消息失败:", e);
        setMessages([]);
      }
    } else {
      setMessages([]);
    }
  };

  // 保存当前聊天的消息
  const saveChatMessages = (chatId: string, msgs: ChatMessage[]) => {
    localStorage.setItem(`deskjarvis_messages_${chatId}`, JSON.stringify(msgs));
  };

  // 新建聊天
  const handleNewChat = () => {
    // 先保存当前聊天的消息（如果存在）
    if (currentChatId && messages.length > 0) {
      saveChatMessages(currentChatId, messages);
    }
    
    const newChatId = `chat_${Date.now()}`;
    const newChat: ChatSession = {
      id: newChatId,
      title: "新聊天",
      createdAt: new Date(),
      updatedAt: new Date(),
      messageCount: 0,
    };
    
    const updatedChats = [newChat, ...chats];
    saveChats(updatedChats);
    setCurrentChatId(newChatId);
    setMessages([]);
    setInput("");
    // 重置 textarea 高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = "56px";
    }
    // 重置任务进度相关状态
    setStatus("idle");
    setCurrentSteps([]);
    setCurrentStepIndex(-1);
    setLogs([]);
    setLastTaskContext(null);
    // 通知父组件重置进度面板
    onStepsChange?.([]);
    onCurrentStepChange?.(-1);
    onLogsChange?.([]);
    onStatusChange?.("idle");
  };

  // 切换聊天
  const handleSelectChat = (chatId: string) => {
    // 先保存当前聊天的消息（如果存在且不是同一个聊天）
    if (currentChatId && currentChatId !== chatId && messages.length > 0) {
      saveChatMessages(currentChatId, messages);
    }
    
    setCurrentChatId(chatId);
    loadChatMessages(chatId);
    setInput("");
    // 重置 textarea 高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = "56px";
    }
    // 重置任务进度相关状态
    setStatus("idle");
    setCurrentSteps([]);
    setCurrentStepIndex(-1);
    setLogs([]);
    setLastTaskContext(null);
    // 通知父组件重置进度面板
    onStepsChange?.([]);
    onCurrentStepChange?.(-1);
    onLogsChange?.([]);
    onStatusChange?.("idle");
  };

  // 删除聊天
  const handleDeleteChat = (chatId: string) => {
    const updatedChats = chats.filter((chat) => chat.id !== chatId);
    saveChats(updatedChats);
    
    // 删除消息记录
    localStorage.removeItem(`deskjarvis_messages_${chatId}`);
    
    // 如果删除的是当前聊天，切换到其他聊天或新建
    if (currentChatId === chatId) {
      if (updatedChats.length > 0) {
        setCurrentChatId(updatedChats[0].id);
        loadChatMessages(updatedChats[0].id);
      } else {
        setCurrentChatId(null);
        setMessages([]);
      }
    }
  };

  // 清空当前聊天消息
  const handleClearCurrentChat = () => {
    if (!currentChatId) return;
    
    if (window.confirm("确定要清空当前聊天的所有消息吗？")) {
      setMessages([]);
      setStatus("idle");
      setCurrentSteps([]);
      setCurrentStepIndex(-1);
      setLogs([]);
      setLastTaskContext(null);
      setAttachedPath(null);
      
      // 清空 localStorage 中的消息
      localStorage.removeItem(`deskjarvis_messages_${currentChatId}`);
      
      // 更新聊天标题
      const updatedChats = chats.map((chat) =>
        chat.id === currentChatId
          ? { ...chat, title: "新聊天", messageCount: 0, updatedAt: new Date() }
          : chat
      );
      saveChats(updatedChats);
    }
  };

  // 清空所有聊天
  const handleClearAllChats = () => {
    // 清空所有聊天记录
    chats.forEach((chat) => {
      localStorage.removeItem(`deskjarvis_messages_${chat.id}`);
    });
    
    // 重置状态
    setChats([]);
    setCurrentChatId(null);
    setMessages([]);
    setStatus("idle");
    setCurrentSteps([]);
    setCurrentStepIndex(-1);
    setLogs([]);
    setLastTaskContext(null);
    setAttachedPath(null);
    
    // 清空 localStorage
    localStorage.removeItem("deskjarvis_chats");
  };

  // 更新聊天标题（从第一条用户消息提取）
  const updateChatTitle = (chatId: string, firstMessage: string) => {
    const title = firstMessage.slice(0, 30) || "新聊天";
    const updatedChats = chats.map((chat) =>
      chat.id === chatId
        ? { ...chat, title, updatedAt: new Date(), messageCount: messages.length + 1 }
        : chat
    );
    saveChats(updatedChats);
  };

  // 更新状态并通知父组件
  const updateStatus = (newStatus: TaskStatus) => {
    setStatus(newStatus);
    statusRef.current = newStatus; // 同步更新 ref
    onStatusChange?.(newStatus);
  };

  const addLog = (level: LogEntry["level"], message: string) => {
    const newLog: LogEntry = {
      timestamp: new Date(),
      level,
      message,
    };
    setLogs((prev) => [...prev, newLog]);
  };

  // 添加带 Agent 标识的日志
  const addLogWithAgent = (level: LogEntry["level"], message: string, agent: string) => {
    const newLog: LogEntry = {
      timestamp: new Date(),
      level,
      message,
      agent,
    };
    setLogs((prev) => [...prev, newLog]);
  };
  
  // 使用 useEffect 同步状态到父组件，避免在渲染期间更新父组件状态
  useEffect(() => {
    onLogsChange?.(logs);
  }, [logs]);
  
  useEffect(() => {
    onStepsChange?.(currentSteps);
  }, [currentSteps]);
  
  useEffect(() => {
    onCurrentStepChange?.(currentStepIndex);
  }, [currentStepIndex]);
  
  useEffect(() => {
    onExecutionModeChange?.(executionMode);
  }, [executionMode]);
  
  useEffect(() => {
    onActiveAgentChange?.(activeAgent);
  }, [activeAgent]);

  // 同步右侧“实时提示”到父组件
  useEffect(() => {
    onLiveNoticesChange?.(liveNotices);
  }, [liveNotices, onLiveNoticesChange]);

  const pushLiveNotice = (message: string, phase?: string) => {
    const id = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const notice: LiveNotice = {
      id,
      timestamp: new Date(),
      message,
      phase,
    };
    setLiveNotices((prev) => [...prev, notice].slice(-3));
    // 8 秒后自动移除，形成“出现后消失”的效果
    window.setTimeout(() => {
      setLiveNotices((prev) => prev.filter((n) => n.id !== id));
    }, 8000);
  };

  // 自动滚动到底部（优化：只在消息数量变化时滚动，避免打字机效果时频繁滚动）
  useEffect(() => {
    // 只在消息数量变化时滚动，避免打字机效果时频繁滚动
    if (messages.length !== prevMessagesLengthRef.current) {
      prevMessagesLengthRef.current = messages.length;
      // 使用 requestAnimationFrame 确保滚动在下一帧执行，避免阻塞
      requestAnimationFrame(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
      });
    }
    // 打字机效果时的滚动由打字机效果内部处理，这里不再重复滚动
  }, [messages.length]); // 只依赖消息数量，不依赖整个 messages 数组，避免打字机效果时频繁触发

  // 处理消息中的图片：当消息加载后，检查并加载图片
  useEffect(() => {
    log.debug("🔄 [图片处理] useEffect 触发，消息数量:", messages.length);
    
    const processImagesForMessages = async () => {
      if (!isTauriEnvironment()) {
        log.debug("⚠️ [图片处理] 不在Tauri环境，跳过图片处理");
        return;
      }

      const messagesToUpdate: ChatMessage[] = [];
      let hasUpdates = false;

      for (const message of messages) {
        // 如果消息已经有图片数据，跳过
        if (message.images && message.images.length > 0) {
          log.debug(`✅ [图片处理] 消息 ${message.id} 已有图片数据`);
          continue;
        }

        // 检查是否有截图路径但还没有图片数据
        if (message.taskResult?.steps) {
          const screenshotPaths: string[] = [];
          for (const stepItem of message.taskResult.steps) {
            if (
              stepItem.step?.type === "screenshot_desktop" &&
              stepItem.result?.success &&
              stepItem.result?.data?.path
            ) {
              screenshotPaths.push(stepItem.result.data.path);
            }
          }

          if (screenshotPaths.length > 0) {
            log.debug(`🔄 [图片处理] 消息 ${message.id} 需要加载图片，路径:`, screenshotPaths);
            
            try {
              const fs = await import("@tauri-apps/plugin-fs");
              const imageDataUrls: string[] = [];

              for (const path of screenshotPaths) {
                try {
                  // 先检查文件是否存在
                  try {
                    const exists = await fs.exists(path);
                    if (!exists) {
                      log.warn(`⚠️ [图片处理] 文件不存在，跳过: ${path}`);
                      continue; // 跳过不存在的文件，不显示错误
                    }
                  } catch (checkError) {
                    // 如果检查文件存在性失败，尝试直接读取（某些情况下 exists 可能不可用）
                    log.debug(`ℹ️ [图片处理] 无法检查文件存在性，尝试直接读取: ${path}`);
                  }
                  
                  log.debug(`📖 [图片处理] 读取文件: ${path}`);
                  const imageBytes = await fs.readFile(path);
                  log.debug(`✅ [图片处理] 文件读取成功，大小: ${imageBytes.length} 字节`);

                  // 转换为 base64
                  let binaryString = '';
                  const len = imageBytes.length;
                  const chunkSize = 8192;
                  for (let i = 0; i < len; i += chunkSize) {
                    const chunk = imageBytes.slice(i, i + chunkSize);
                    binaryString += String.fromCharCode(...chunk);
                  }

                  const base64 = btoa(binaryString);
                  const dataUrl = `data:image/png;base64,${base64}`;
                  imageDataUrls.push(dataUrl);
                  log.debug(`✅ [图片处理] 图片转换成功，已添加到列表`);
                } catch (e: any) {
                  // 文件不存在或其他错误：静默处理，不显示错误日志
                  const errorMessage = e?.message || String(e);
                  if (errorMessage.includes("No such file") || errorMessage.includes("os error 2")) {
                    log.warn(`⚠️ [图片处理] 文件不存在，跳过: ${path}`);
                  } else {
                    // 其他错误（权限问题等）才显示警告
                    log.warn(`⚠️ [图片处理] 读取文件失败，跳过: ${path}`, errorMessage);
                  }
                }
              }

              if (imageDataUrls.length > 0) {
                const updatedMessage: ChatMessage = {
                  ...message,
                  images: imageDataUrls,
                };
                messagesToUpdate.push(updatedMessage);
                hasUpdates = true;
                log.debug(`✅ [图片处理] 消息 ${message.id} 图片加载完成`);
              }
            } catch (e: any) {
              log.error(`❌ [图片处理] 导入 fs 插件失败:`, e);
            }
          }
        }
      }

      if (hasUpdates) {
        log.debug(`🔄 [图片处理] 更新 ${messagesToUpdate.length} 条消息的图片数据`);
        setMessages((prev) => {
          const updated = prev.map((msg) => {
            const updatedMsg = messagesToUpdate.find((u) => u.id === msg.id);
            return updatedMsg || msg;
          });
          // 保存更新后的消息
          if (currentChatId) {
            saveChatMessages(currentChatId, updated);
          }
          return updated;
        });
      }
    };

    processImagesForMessages();
  }, [messages, currentChatId]);

  // 停止当前任务
  const handleStop = () => {
    log.debug("🛑 [handleStop] 用户请求停止任务");
    isTaskCancelledRef.current = true;
    
    // 清理进度事件监听器
    if (unlistenProgressRef.current) {
      unlistenProgressRef.current();
      unlistenProgressRef.current = null;
    }
    
    // 重置累积内容
    accumulatedContentRef.current = "";
    
    // 更新状态
    updateStatus("idle");
    addLog("warning", "任务已取消");
    
    // 更新AI消息，显示任务已取消
    const stopTargetId = currentAssistantMessageIdRef.current;
    currentAssistantMessageIdRef.current = null; // 提前清除
    if (stopTargetId) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === stopTargetId && msg.role === "assistant"
            ? { ...msg, content: "任务已取消" }
            : msg
        )
      );
    }
  };

  const handleSend = async () => {
    // 如果正在执行任务，点击发送按钮就是停止任务
    if (status !== "idle") {
      handleStop();
      return;
    }
    
    if (!input.trim()) return;

    // 如果没有当前聊天，先创建一个
    if (!currentChatId) {
      handleNewChat();
      // 等待状态更新
      await new Promise((resolve) => setTimeout(resolve, 100));
    }

    // 检查配置
    if (!config?.api_key) {
      addMessage({
        id: Date.now().toString(),
        role: "system",
        content: "请先在设置中配置API密钥",
        timestamp: new Date(),
      });
      return;
    }

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    // 如果是第一条消息，更新聊天标题
    if (messages.length === 0 && currentChatId) {
      updateChatTitle(currentChatId, input.trim());
    }

    setMessages((prev) => [...prev, userMessage]);
    const instruction = input.trim();
    setInput("");
    // 重置 textarea 高度
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = "56px";
    }
    // 重置取消标记
    isTaskCancelledRef.current = false;
    
    updateStatus("planning");
    setCurrentSteps([]);
    setCurrentStepIndex(-1);
    setLogs([]);
    setLiveNotices([]);
    // 通知父组件清空右侧进度面板
    onStepsChange?.([]);
    onCurrentStepChange?.(-1);
    onLogsChange?.([]);
    onLiveNoticesChange?.([]);
    addLog("info", "开始规划任务...");
    pushLiveNotice("收到指令，正在规划步骤…", "planning");

    // ✅ 先设置进度事件监听器（在消息创建之前，避免竞态条件）
    let unlistenProgress: (() => void) | null = null;
    if (isTauriEnvironment()) {
      try {
        const { listen } = await import("@tauri-apps/api/event");
        unlistenProgress = await listen("task-progress", (event: any) => {
          // 如果任务已被取消，忽略进度事件
          if (isTaskCancelledRef.current) {
            return;
          }
          const progressEvent = event.payload as any;
          handleProgressEvent(progressEvent);
        });
        unlistenProgressRef.current = unlistenProgress;
      } catch (e) {
        log.error("设置进度事件监听器失败:", e);
      }
    }

    // ✅ 创建 AI 回复消息（初始内容为"正在思考..."）
    const tempAssistantId = `temp-assistant-${Date.now()}`;
    currentAssistantMessageIdRef.current = tempAssistantId;
    const initialAssistantMessage: ChatMessage = {
      id: tempAssistantId,
      role: "assistant",
      content: "好的，让我来处理...",  // 初始内容
      timestamp: new Date(),
    };
    log.debug("✅ [handleSend] 创建AI消息，ID:", tempAssistantId);
    setMessages((prev) => [...prev, initialAssistantMessage]);

    try {
      log.debug("🚀 [handleSend] 进入 try 块，准备执行任务");
      // 构建上下文信息（包含之前创建的文件和附加的文件路径）
      const context: any = lastTaskContext ? {
        created_files: lastTaskContext.created_files || [],
        last_created_file: lastTaskContext.last_created_file || null,
      } : {};
      
      // 如果用户附加了文件/文件夹路径，添加到上下文中
      if (attachedPath) {
        context.attached_path = attachedPath;
        log.debug(`[上下文] 用户附加了路径: ${attachedPath}`);
      }
      
      // 添加聊天历史到上下文（只包含用户和AI的消息，排除系统消息）
      const chatHistory = messages
        .filter(msg => msg.role === "user" || msg.role === "assistant")
        .slice(-10) // 只保留最近10条消息，避免token过多
        .map(msg => ({
          role: msg.role === "user" ? "user" : "assistant",
          content: msg.content,
        }));
      
      if (chatHistory.length > 0) {
        context.chat_history = chatHistory;
        log.debug(`[上下文] 添加聊天历史: ${chatHistory.length} 条消息`);
      }
      
      // 调用Tauri命令执行任务（传递上下文）
      // 如果任务已被取消，不执行
      if (isTaskCancelledRef.current) {
        log.debug("🛑 [handleSend] 任务已被取消，跳过执行");
        return;
      }
      
      log.debug("🚀 [handleSend] 准备调用 executeTask");
      log.debug("🚀 [handleSend] 指令:", instruction);
      log.debug("🚀 [handleSend] 上下文:", context);
      log.debug("🚀 [handleSend] Tauri环境:", isTauriEnvironment());
      
      let result;
      try {
        result = await executeTask(instruction, Object.keys(context).length > 0 ? context : null);
        log.debug("✅ [handleSend] executeTask 调用成功，结果:", result);
      } catch (executeError: any) {
        log.error("❌ [handleSend] executeTask 调用失败:", executeError);
        log.error("❌ [handleSend] 错误详情:", {
          message: executeError?.message,
          stack: executeError?.stack,
          name: executeError?.name
        });
        throw executeError; // 重新抛出错误，让 catch 块处理
      }
      
      // 检查任务是否在执行过程中被取消
      if (isTaskCancelledRef.current) {
        log.debug("🛑 [handleSend] 任务在执行过程中被取消");
        return;
      }

      // 更新步骤列表（如果进度事件没有更新）
      if (result.steps && result.steps.length > 0) {
        // 只有在步骤列表为空时才更新（避免覆盖实时更新的数据）
        setCurrentSteps((prev) => {
          if (prev.length === 0) {
            return result.steps;
          }
          return prev;
        });
        // onStepsChange 由 useEffect 自动同步
      }

      // 检查是否有截图结果，提取图片路径
      log.debug("🔍 [图片预览] 开始检查任务结果...");
      log.debug("🔍 [图片预览] 任务结果:", JSON.stringify(result, null, 2));
      
      const screenshotPaths: string[] = [];
      if (result.steps && result.steps.length > 0) {
        log.debug(`🔍 [图片预览] 找到 ${result.steps.length} 个步骤`);
        for (const stepItem of result.steps) {
          const stepType = stepItem.step?.type;
          const stepResult = stepItem.result;
          const stepData = stepResult?.data;
          
          log.debug("🔍 [图片预览] 检查步骤:", { 
            stepType, 
            success: stepResult?.success, 
            path: stepData?.path,
            data: stepData
          });
          
          if (
            stepType === "screenshot_desktop" &&
            stepResult?.success &&
            stepData?.path
          ) {
            log.debug("✅ [图片预览] 找到截图路径:", stepData.path);
            screenshotPaths.push(stepData.path);
          }
        }
      } else {
        log.debug("⚠️ [图片预览] 没有找到步骤数据");
      }
      
      log.debug(`📊 [图片预览] 提取的截图路径数量: ${screenshotPaths.length}`);
      log.debug(`📊 [图片预览] 截图路径列表:`, screenshotPaths);

      // 如果有截图，读取图片文件并转换为base64
      const imageDataUrls: string[] = [];
      const isTauri = isTauriEnvironment();
      log.debug(`🔍 [图片预览] Tauri环境检测: ${isTauri}`);
      log.debug(`🔍 [图片预览] window对象:`, typeof window !== "undefined" ? "存在" : "不存在");
      log.debug(`🔍 [图片预览] __TAURI__:`, typeof window !== "undefined" && "__TAURI__" in window);
      log.debug(`🔍 [图片预览] __TAURI_INTERNALS__:`, typeof window !== "undefined" && "__TAURI_INTERNALS__" in window);
      
      if (screenshotPaths.length > 0) {
        if (isTauri) {
          log.debug("✅ [图片预览] 开始读取截图文件（Tauri环境）");
          try {
            const fs = await import("@tauri-apps/plugin-fs");
            log.debug("✅ [图片预览] fs 模块导入成功");
            log.debug("✅ [图片预览] fs 模块内容:", Object.keys(fs));
            
            for (const path of screenshotPaths) {
              try {
                log.debug(`📖 [图片预览] 开始读取文件: ${path}`);
                
                // 先检查文件是否存在
                try {
                  const exists = await fs.exists(path);
                  if (!exists) {
                    log.warn(`⚠️ [图片预览] 文件不存在，跳过: ${path}`);
                    continue; // 跳过不存在的文件，不显示错误
                  }
                } catch (checkError) {
                  // 如果检查文件存在性失败，尝试直接读取（某些情况下 exists 可能不可用）
                  log.debug(`ℹ️ [图片预览] 无法检查文件存在性，尝试直接读取: ${path}`);
                }
                
                // Tauri 2.0 fs 插件：readFile 支持绝对路径
                const imageBytes = await fs.readFile(path);
                log.debug(`✅ [图片预览] 文件读取成功，大小: ${imageBytes.length} 字节`);
                
                // 转换为 base64
                let binaryString = '';
                const len = imageBytes.length;
                
                // 使用更高效的方式转换（分批处理，避免栈溢出）
                const chunkSize = 8192;
                for (let i = 0; i < len; i += chunkSize) {
                  const chunk = imageBytes.slice(i, i + chunkSize);
                  binaryString += String.fromCharCode(...chunk);
                }
                
                const base64 = btoa(binaryString);
                const dataUrl = `data:image/png;base64,${base64}`;
                imageDataUrls.push(dataUrl);
                log.debug(`✅ [图片预览] 图片已添加到预览列表: ${path}`);
              } catch (e: any) {
                // 文件不存在或其他错误：静默处理，不显示错误日志
                // 只在开发模式下显示详细错误信息
                const errorMessage = e?.message || String(e);
                if (errorMessage.includes("No such file") || errorMessage.includes("os error 2")) {
                  log.warn(`⚠️ [图片预览] 文件不存在，跳过: ${path}`);
                } else {
                  // 其他错误（权限问题等）才显示警告
                  log.warn(`⚠️ [图片预览] 读取文件失败，跳过: ${path}`, errorMessage);
                }
              }
            }
          } catch (e: any) {
            log.error("❌ [图片预览] 导入 fs 插件失败:", e);
            log.error("❌ [图片预览] 错误详情:", {
              message: e?.message,
              stack: e?.stack,
              name: e?.name
            });
          }
        } else {
          log.warn("⚠️ [图片预览] 不在Tauri环境，无法读取文件");
        }
      } else {
        log.debug("⚠️ [图片预览] 没有找到截图路径");
      }
      
      log.debug(`📊 [图片预览] 最终图片数据URL数量: ${imageDataUrls.length}`);
      if (imageDataUrls.length > 0) {
        log.debug(`✅ [图片预览] 图片数据URL已准备就绪，将添加到消息中`);
      } else {
        log.warn(`⚠️ [图片预览] 没有成功加载任何图片`);
      }

      // 构建简洁的总结消息
      const successCount = result.steps?.filter((s: any) => s.result?.success).length || 0;
      const totalCount = result.steps?.length || 0;
      
      let messageContent = "";
      if (result.success) {
        messageContent = result.message || "任务执行完成";
      } else {
        messageContent = `执行失败: ${result.message || "未知错误"}`;
      }
      
      // 提取特定工具的详细结果
      if (result.steps && result.steps.length > 0) {
        for (const stepItem of result.steps) {
          const stepType = stepItem.step?.type;
          const stepResult = stepItem.result;
          
          if (!stepResult?.success) continue;
          
          // 文本处理结果
          if (stepType === "text_process" && stepResult.data?.result) {
            messageContent += "\n\n**结果：**\n" + stepResult.data.result;
          }
          // 系统信息
          else if (stepType === "get_system_info" && stepResult.data) {
            const info = stepResult.data;
            let infoText = "\n\n**系统信息：**";
            if (info.battery) {
              infoText += `\n- 电池: ${info.battery.percentage}% ${info.battery.charging ? "(充电中)" : ""}`;
            }
            if (info.disk) {
              infoText += `\n- 磁盘: 已用 ${info.disk.used} / 总共 ${info.disk.total} (${info.disk.use_percent})`;
            }
            if (info.running_apps) {
              infoText += `\n- 运行中应用: ${info.running_apps.slice(0, 10).join(", ")}${info.running_apps.length > 10 ? "..." : ""}`;
            }
            if (info.network?.local_ip) {
              infoText += `\n- 本机IP: ${info.network.local_ip}`;
            }
            messageContent += infoText;
          }
          // 图片处理结果
          else if (stepType === "image_process" && stepResult.data) {
            const imgData = stepResult.data;
            if (imgData.path) {
              messageContent += `\n\n已保存: ${imgData.path}`;
            }
            if (imgData.width && imgData.height) {
              messageContent += `\n尺寸: ${imgData.width}x${imgData.height}`;
            }
          }
          // 提醒列表
          else if (stepType === "list_reminders" && stepResult.data?.reminders) {
            const reminders = stepResult.data.reminders;
            if (reminders.length > 0) {
              messageContent += "\n\n**待处理提醒：**";
              for (const r of reminders.slice(0, 5)) {
                messageContent += `\n- ${r.message} (${r.remaining})`;
              }
            }
          }
          // 工作流列表
          else if (stepType === "list_workflows" && stepResult.data?.workflows) {
            const workflows = stepResult.data.workflows;
            if (workflows.length > 0) {
              messageContent += "\n\n**可用工作流：**";
              for (const w of workflows) {
                messageContent += `\n- **${w.name}**: ${w.description || w.commands_count + " 个命令"}`;
              }
            }
          }
          // 任务历史
          else if (stepType === "get_task_history" && stepResult.data?.tasks) {
            const tasks = stepResult.data.tasks;
            if (tasks.length > 0) {
              messageContent += "\n\n**最近任务：**";
              for (const t of tasks.slice(0, 5)) {
                const status = t.success ? "✓" : "✗";
                messageContent += `\n- ${status} ${t.instruction.slice(0, 30)}${t.instruction.length > 30 ? "..." : ""} (${t.time_display || ""})`;
              }
            }
          }
          // 收藏列表
          else if (stepType === "list_favorites" && stepResult.data?.favorites) {
            const favorites = stepResult.data.favorites;
            if (favorites.length > 0) {
              messageContent += "\n\n**我的收藏：**";
              for (const f of favorites) {
                messageContent += `\n- ${f.name}`;
              }
            } else {
              messageContent += "\n\n暂无收藏";
            }
          }
        }
      }
      
      // 如果有截图，简洁显示保存路径
      if (screenshotPaths.length > 0) {
        const paths = screenshotPaths.map(p => `\n已保存: ${p}`).join('');
        messageContent += paths;
      }

      log.debug("[handleSend] 最终消息:", messageContent);

      // ✅ 重置累积内容
      accumulatedContentRef.current = "";

      // ✅ 更新临时AI消息为最终消息（替换临时消息）
      const finalAssistantId = `assistant-${Date.now()}`;
      
      // 确保消息内容不为空
      const finalMessageContent = messageContent?.trim() || (result.success ? "任务执行完成" : "任务执行失败");
      log.debug("📝 [handleSend] 准备更新最终消息，内容长度:", finalMessageContent.length);
      
      // ⚠️ 关键：在调用 setMessages 之前捕获当前 ref 值。
      // React 18 自动批处理会延迟执行 setMessages 回调，
      // 如果在回调执行时 ref 已被置为 null，则无法匹配到目标消息。
      const targetMessageId = currentAssistantMessageIdRef.current;
      currentAssistantMessageIdRef.current = null; // 提前清除，避免后续误用
      
      setMessages((prev) => {
        // 确保能找到AI消息并更新
        const hasAssistantMessage = prev.some(
          (msg) => msg.id === targetMessageId && msg.role === "assistant"
        );
        
        if (!hasAssistantMessage && targetMessageId) {
          // 如果找不到临时消息，直接添加新消息
          log.warn("⚠️ [handleSend] 未找到临时AI消息，直接添加最终消息");
          return [
            ...prev,
            {
              id: finalAssistantId,
              role: "assistant" as const,
              content: finalMessageContent,
              timestamp: new Date(),
              taskResult: result,
              images: imageDataUrls.length > 0 ? imageDataUrls : undefined,
            },
          ];
        }
        
        const updated = prev.map((msg) => {
          if (msg.id === targetMessageId && msg.role === "assistant") {
            log.debug("✅ [handleSend] 找到并更新AI消息");
            return {
              ...msg,
              id: finalAssistantId,
              content: finalMessageContent, // 确保内容不为空
              taskResult: result,
              images: imageDataUrls.length > 0 ? imageDataUrls : undefined,
            };
          }
          return msg;
        });
        
        // 验证更新后的消息
        const finalMsg = updated.find(m => m.id === finalAssistantId);
        if (!finalMsg || !finalMsg.content || !finalMsg.content.trim()) {
          log.error("❌ [handleSend] 更新后的消息内容为空！");
        }
        
        return updated;
      });
      
      // 保存任务上下文（用于下次任务理解"这个文件"等引用）
      if (result.steps && result.steps.length > 0) {
        const contextFiles: string[] = [];
        let latestFile: string | null = null; // 最新的文件路径
        
        // 按步骤顺序处理，总是更新 latestFile 为最后一个成功的文件操作
        for (const stepItem of result.steps) {
          const stepType = stepItem.step?.type;
          const stepResult = stepItem.result;
          const stepData = stepResult?.data;
          
          if (!stepResult?.success) continue; // 跳过失败的操作
          
          // 收集创建的文件路径
          if (stepType === "file_create" && stepData?.path) {
            contextFiles.push(stepData.path);
            latestFile = stepData.path; // 总是更新为最新的文件
          }
          // 收集截图创建的文件路径
          if (stepType === "screenshot_desktop" && stepData?.path) {
            contextFiles.push(stepData.path);
            latestFile = stepData.path; // 总是更新为最新的截图
            log.debug(`✅ [上下文] 截图保存: ${stepData.path}，更新最新文件`);
          }
          // 收集重命名/移动操作的文件路径（优先使用新路径）
          if (stepType === "file_rename" || stepType === "file_move") {
            const newPath = stepData?.target || stepData?.new_path;
            const oldPath = stepData?.source || stepData?.path;
            
            if (newPath) {
              contextFiles.push(newPath);
              latestFile = newPath; // 重命名/移动后的新路径
              log.debug(`✅ [上下文] 重命名/移动: ${oldPath} → ${newPath}`);
            } else if (oldPath) {
              contextFiles.push(oldPath);
              latestFile = oldPath;
            }
          }
          // 收集下载的文件路径
          if (stepType === "download_file" && stepData?.path) {
            contextFiles.push(stepData.path);
            latestFile = stepData.path;
          }
          // 收集 Python 脚本操作的文件（如果返回了文件路径）
          if (stepType === "execute_python_script") {
            // 脚本可能返回 deleted_files、created_files、path 等
            if (stepData?.path) {
              contextFiles.push(stepData.path);
              latestFile = stepData.path;
            }
            if (stepData?.created_files && Array.isArray(stepData.created_files)) {
              for (const f of stepData.created_files) {
                contextFiles.push(f);
                latestFile = f;
              }
            }
            // 如果是删除操作，记录被删除的文件（但不设为 latestFile）
            if (stepData?.deleted_files && Array.isArray(stepData.deleted_files)) {
              for (const f of stepData.deleted_files) {
                contextFiles.push(f);
              }
            }
          }
        }
        
        if (contextFiles.length > 0 || latestFile) {
          const finalLatestFile = latestFile || contextFiles[contextFiles.length - 1];
          setLastTaskContext({
            created_files: contextFiles,
            last_created_file: finalLatestFile,
            timestamp: Date.now(),
          });
          log.debug(`✅ [上下文] 更新上下文: 最新文件 = ${finalLatestFile}, 所有文件 = [${contextFiles.join(", ")}]`);
        } else {
          // 如果没有收集到文件，但之前有上下文，保持之前的上下文（不要清空）
          log.debug(`⚠️ [上下文] 本次任务没有操作文件，保持之前的上下文`);
        }
      }
      
      if (result.success) {
        addLog("success", "任务执行完成");
        updateStatus("completed");
      } else {
        addLog("error", "任务执行失败");
        updateStatus("error");
      }
    } catch (error) {
      // 如果任务已被取消，不显示错误
      if (isTaskCancelledRef.current) {
        log.debug("🛑 [handleSend] 任务已取消，忽略错误");
        return;
      }
      
      const errorMsg = error instanceof Error ? error.message : "未知错误";
      addLog("error", `执行失败: ${errorMsg}`);
      
      // ✅ 更新AI消息为错误信息
      const errorTargetId = currentAssistantMessageIdRef.current;
      currentAssistantMessageIdRef.current = null; // 提前清除
      if (errorTargetId) {
        setMessages((prev) => {
          return prev.map((msg) => {
            if (msg.id === errorTargetId && msg.role === "assistant") {
              return {
                ...msg,
                content: `执行失败: ${errorMsg}`,
              };
            }
            return msg;
          });
        });
      } else {
        // 只有在没有现有消息可更新时才创建新消息
        const errorMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: `执行失败: ${errorMsg}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
      updateStatus("error");
    } finally {
      // 清理事件监听器
      if (unlistenProgress) {
        unlistenProgress();
        unlistenProgressRef.current = null;
      }
      
      // 重置累积内容
      accumulatedContentRef.current = "";
      
      // 检查任务是否被取消（在重置标记之前）
      const wasCancelled = isTaskCancelledRef.current;
      
      // 重置取消标记
      isTaskCancelledRef.current = false;
      
      // 如果任务没有被取消，延迟重置状态
      if (!wasCancelled) {
        setTimeout(() => {
          updateStatus("idle");
        }, 2000);
      } else {
        // 如果任务被取消，立即重置状态
        updateStatus("idle");
      }
    }
  };

  // 累积的消息内容 ref（避免打字机效果竞态）
  const accumulatedContentRef = useRef<string>("");

  // 简化的消息更新函数（不使用打字机效果，直接更新）
  const updateAssistantMessage = (content: string, append: boolean = false) => {
    const msgId = currentAssistantMessageIdRef.current;
    if (!msgId) return;
    
    if (append) {
      // 追加模式：在现有内容后追加
      accumulatedContentRef.current = accumulatedContentRef.current 
        ? `${accumulatedContentRef.current}\n${content}` 
        : content;
    } else {
      // 替换模式：直接替换
      accumulatedContentRef.current = content;
    }
    
    const newContent = accumulatedContentRef.current;
    
    setMessages((prev) => {
      return prev.map((msg) => {
            if (msg.id === msgId && msg.role === "assistant") {
              return { ...msg, content: newContent };
            }
            return msg;
          });
    });
  };

  // 处理进度事件 - 简洁显示，步骤详情只在右侧面板
  const handleProgressEvent = (event: any) => {
    const eventType = event.type;
    const eventData = event.data || {};

    log.debug("[进度事件]", eventType, eventData);

    switch (eventType) {
      // ========== 思考阶段 ==========
      case "thinking":
        const thinkingContent = eventData.content || "让我想想...";
        // 思考提示不进入聊天气泡，只在右侧“实时提示”短暂显示
        pushLiveNotice(thinkingContent, eventData.phase);
        if (eventData.phase === "reflecting" || eventData.phase === "preparing_reflection") {
          updateStatus("reflecting");
        } else if (eventData.phase === "multi_agent") {
          updateStatus("multi_agent");
        } else if (eventData.phase === "executing") {
          updateStatus("executing");
        } else {
          updateStatus("planning");
        }
        break;

      // ========== 计划就绪 ==========
      case "plan_ready":
        const steps = eventData.steps || [];
        log.debug("[plan_ready] 收到步骤:", steps.length, "个");
        pushLiveNotice(`计划已生成，共 ${steps.length} 步`, "planning");
        
        // 初始化步骤列表（右侧面板显示）
        if (steps.length > 0) {
          const initialSteps = steps.map((step: any) => ({
            step,
            result: undefined,
          }));
          log.debug("[plan_ready] 设置步骤到右侧面板:", initialSteps);
          setCurrentSteps(initialSteps);
          // onStepsChange 由 useEffect 自动同步
        }

        addLog("success", `规划完成，共 ${steps.length} 个步骤`);
        break;

      // ========== 执行开始 ==========
      case "execution_started":
        updateStatus("executing");
        addLog("info", `开始执行，共 ${eventData.step_count || 0} 个步骤`);
        pushLiveNotice(`开始执行，共 ${eventData.step_count || 0} 步`, "executing");
        break;

      // ========== 步骤开始 ==========
      case "step_started":
        const startedIndex = eventData.step_index || 0;
        const startedTotal = eventData.total_steps || 0;
        const startedAction = eventData.action || eventData.step?.action || "";
        
        setCurrentStepIndex(startedIndex);
        // onCurrentStepChange 由 useEffect 自动同步
        pushLiveNotice(`执行中：第 ${startedIndex + 1}/${startedTotal} 步`, "executing");
        addLog("info", `执行步骤 ${startedIndex + 1}/${startedTotal}: ${startedAction}`);
        break;

      // ========== 步骤完成 ==========
      case "step_completed":
        const completedIndex = eventData.step_index || 0;
        const completedStep = eventData.step || {};
        const stepResult = eventData.result || {};
        const totalSteps = eventData.total_steps || 0;
        
        // 更新步骤结果（右侧面板显示）
        setCurrentSteps((prev) => {
          const updated = [...prev];
          if (updated[completedIndex]) {
            updated[completedIndex] = {
              step: completedStep,
              result: stepResult,
            };
          }
          // onStepsChange 由 useEffect 自动同步
          return updated;
        });
        
        // 如果有生成的图表，添加到消息中
        if (stepResult.images && Array.isArray(stepResult.images) && stepResult.images.length > 0) {
          // 为每个图表添加图片块到消息
          stepResult.images.forEach((imagePath: string) => {
            addLog("info", `生成图表: ${imagePath}`);
          });
          pushLiveNotice(`已生成 ${stepResult.images.length} 个图表`, "executing");
        }
        
        // 如果自动安装了包，记录日志
        if (stepResult.installed_packages && Array.isArray(stepResult.installed_packages) && stepResult.installed_packages.length > 0) {
          addLog("info", `自动安装了依赖: ${stepResult.installed_packages.join(", ")}`);
        }
        
        addLog("success", `步骤 ${completedIndex + 1} 成功`);
        break;

      // ========== 步骤失败 ==========
      case "step_failed":
        const failedIndex = eventData.step_index || 0;
        const failedStep = eventData.step || {};
        const failedResult = eventData.result || {};
        const errorMsg = eventData.error || failedResult.message || "未知错误";
        
        // 更新步骤结果（右侧面板显示）
        setCurrentSteps((prev) => {
          const updated = [...prev];
          if (updated[failedIndex]) {
            updated[failedIndex] = {
              step: failedStep,
              result: { success: false, message: errorMsg },
            };
          }
          // onStepsChange 由 useEffect 自动同步
          return updated;
        });
        
        addLog("error", `步骤 ${failedIndex + 1} 失败: ${errorMsg}`);
        break;

      // ========== 反思开始 ==========
      case "reflection_started":
        updateStatus("reflecting");
        addLog("info", `正在反思失败原因...`);
        pushLiveNotice("执行失败，正在反思并尝试修复…", "reflecting");
        break;

      // ========== 反思完成 ==========
      case "reflection_completed":
        const newStepCount = eventData.new_step_count || 0;
        addLog("info", `反思完成，新方案有 ${newStepCount} 个步骤`);
        pushLiveNotice(`反思完成，新方案 ${newStepCount} 步`, "reflecting");
        break;

      // ========== 任务完成 ==========
      case "task_completed":
        // 不在这里更新消息，让 handleSend 处理最终结果
        const success = eventData.success || false;
        const successCount = eventData.success_count || 0;
        const totalCount = eventData.total_count || 0;
        const completedMessage = eventData.message || "";
        
        if (success) {
          addLog("success", completedMessage || `任务完成: ${successCount}/${totalCount} 个步骤成功`);
          pushLiveNotice("任务完成", "completed");
        } else {
          addLog("warning", completedMessage || `任务部分完成: ${successCount}/${totalCount} 个步骤成功`);
          pushLiveNotice("任务结束（部分成功）", "completed");
        }
        break;

      // ========== 错误 ==========
      case "error":
        const errorMessage = eventData.message || "未知错误";
        addLog("error", errorMessage);
        pushLiveNotice("发生错误：" + errorMessage, "error");
        updateStatus("idle");
        break;

      // ========== 其他事件 ==========
      case "browser_starting":
        addLog("info", "正在启动浏览器...");
        pushLiveNotice("正在启动浏览器…", "executing");
        break;

      case "browser_started":
        addLog("success", "浏览器已启动");
        pushLiveNotice("浏览器已启动", "executing");
        break;

      case "browser_stopping":
        addLog("info", "正在停止浏览器...");
        break;

      case "browser_stopped":
        addLog("success", "浏览器已停止");
        break;

      // ========== 请求用户输入（登录、验证码） ==========
      case "request_input":
        log.debug("[request_input] 收到用户输入请求:", eventData);
        setUserInputRequest(eventData as InputRequest);
        addLog("info", `等待用户输入: ${eventData.title || "请输入"}`);
        pushLiveNotice("需要你输入信息，等待中…", "executing");
        break;

      // ========== CodeInterpreter 进度事件 ==========
      case "installing_packages":
      case "installing":
      case "retrying":
      case "validating_script":
      case "validation_failed":
        if (eventData.message) {
          pushLiveNotice(String(eventData.message), "executing");
          addLog("info", String(eventData.message));
        }
        if (eventType === "validation_failed" && eventData.details) {
          addLog("error", "ruff: " + String(eventData.details));
        }
        break;

      // ========== 多代理协作事件 ==========
      case "crew_started":
        log.debug("[crew_started] 多代理协作开始:", eventData);
        updateStatus("multi_agent");
        setExecutionMode("multi-agent");
        const agents = eventData.agents || [];
        addLog("info", `多代理团队启动: ${agents.join(", ")}`);
        break;

      case "agent_progress":
        const agentName = eventData.agent || "Agent";
        const agentMessage = eventData.message || "";
        log.debug(`[agent_progress] ${agentName}: ${agentMessage}`);
        setActiveAgent(agentName);
        addLogWithAgent("info", agentMessage, agentName);
        // 更新 AI 消息
        accumulatedContentRef.current = `[${agentName}] ${agentMessage}`;
        updateAssistantMessage(accumulatedContentRef.current, false);
        break;

      case "crew_completed":
        log.debug("[crew_completed] 多代理协作完成:", eventData);
        const crewSuccess = eventData.success;
        const crewResult = eventData.result || "";
        const crewDuration = eventData.duration || 0;
        
        if (crewSuccess) {
          addLog("success", `团队协作完成 (${crewDuration.toFixed(1)}s)`);
          updateAssistantMessage(crewResult, true);
          updateStatus("completed");
        } else {
          addLog("error", `团队协作失败: ${eventData.error || "未知错误"}`);
          updateStatus("error");
        }
        setActiveAgent(undefined);
        break;

      default:
        log.debug("[未处理事件]", eventType, eventData);
    }
  };

  // 处理用户输入提交（登录、验证码）
  const handleUserInputSubmit = async (requestId: string, values: Record<string, string>) => {
    log.debug("[用户输入] 提交:", requestId, values);
    try {
      if (tauriInvoke) {
        await tauriInvoke("submit_user_input", { requestId, values });
      }
      setUserInputRequest(null);
      addLog("success", "已提交用户输入");
    } catch (error) {
      log.error("[用户输入] 提交失败:", error);
      addLog("error", `提交失败: ${error}`);
    }
  };

  // 处理用户输入取消
  const handleUserInputCancel = async (requestId: string) => {
    log.debug("[用户输入] 取消:", requestId);
    try {
      if (tauriInvoke) {
        await tauriInvoke("cancel_user_input", { requestId });
      }
      setUserInputRequest(null);
      addLog("info", "用户取消了输入");
    } catch (error) {
      log.error("[用户输入] 取消失败:", error);
    }
  };

  const addMessage = (message: ChatMessage) => {
    setMessages((prev) => {
      const updated = [...prev, message];
      // 保存到 localStorage
      if (currentChatId) {
        saveChatMessages(currentChatId, updated);
      }
      return updated;
    });
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 处理文件/文件夹选择
  const handleFileSelect = () => {
    // 使用文件输入来选择文件/文件夹
    fileInputRef.current?.click();
  };

  // 处理拖拽
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      // 尝试获取完整路径（Tauri 环境）
      const path = (file as any).path || file.name;
      
      if (path) {
        setAttachedPath(path);
        setInput((prev) => {
          const trimmed = prev.trim();
          return trimmed ? `${trimmed} ${path}` : path;
        });
      }
    }
  };

  // 移除附加的路径
  const handleRemoveAttachment = () => {
    setAttachedPath(null);
    if (attachedPath) {
      setInput((prev) => prev.replace(attachedPath, "").trim());
    }
  };

  // 复制消息内容
  const handleCopyMessage = async (content: string, messageId: string) => {
    const onCopySuccess = () => {
      // 设置已复制状态
      setCopiedMessageId(messageId);
      // 显示成功提示
      setCopyToast({ show: true, message: "已复制到剪贴板" });
      // 2秒后恢复按钮状态
      setTimeout(() => {
        setCopiedMessageId(null);
      }, 2000);
      // 3秒后自动隐藏 Toast
      setTimeout(() => {
        setCopyToast({ show: false, message: "" });
      }, 3000);
    };

    try {
      await navigator.clipboard.writeText(content);
      onCopySuccess();
    } catch (error) {
      log.error("复制失败:", error);
      // 降级方案：使用传统方法
      const textArea = document.createElement("textarea");
      textArea.value = content;
      textArea.style.position = "fixed";
      textArea.style.opacity = "0";
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand("copy");
        onCopySuccess();
      } catch (err) {
        log.error("复制失败（降级方案）:", err);
        // 显示失败提示
        setCopyToast({ show: true, message: "复制失败" });
        setTimeout(() => {
          setCopyToast({ show: false, message: "" });
        }, 3000);
      }
      document.body.removeChild(textArea);
    }
  };

  // 撤回操作
  const handleUndo = async (taskResult: TaskResult) => {
    try {
      if (!taskResult?.steps || taskResult.steps.length === 0) {
        log.warn("没有可撤回的操作");
        addMessage({
          id: Date.now().toString(),
          role: "system",
          content: "没有可撤回的操作",
          timestamp: new Date(),
        });
        return;
      }

      // 检查是否有可撤回的操作
      const undoableSteps = taskResult.steps.filter((stepItem: { step: any; result: any }) => {
      const stepType = stepItem.step?.type;
      const stepResult = stepItem.result;
      // 只撤回成功的操作
      if (!stepResult?.success) return false;
      
      // 可撤回的操作类型
      const undoableTypes = [
        "file_delete", "file_rename", "file_move", "file_create", 
        "file_write", "file_copy", "file_batch_rename", "file_batch_copy",
        "execute_python_script" // 可能包含删除操作
      ];
      
      // 对于execute_python_script，检查是否是删除操作
      if (stepType === "execute_python_script") {
        const stepParams = stepItem.step?.params || {};
        const script = stepParams.script || "";
        const action = stepParams.action || stepItem.step?.action || "";
        const description = stepItem.step?.description || "";
        const scriptLower = script.toLowerCase();
        const actionStr = typeof action === "string" ? action : String(action || "");
        const descriptionStr = typeof description === "string" ? description : String(description || "");
        
        // 检查是否是删除操作（使用 includes 而不是 in）
        return (
          actionStr.includes("删除") || descriptionStr.includes("删除") ||
          scriptLower.includes("os.remove") || scriptLower.includes("os.unlink") || 
          scriptLower.includes("path.unlink") || (scriptLower.includes("pathlib") && scriptLower.includes("unlink"))
        );
      }
      
        return undoableTypes.includes(stepType);
      });

      if (undoableSteps.length === 0) {
        addMessage({
          id: Date.now().toString(),
          role: "system",
          content: "没有可撤回的操作",
          timestamp: new Date(),
        });
        return;
      }

      // 构建撤回指令：反向执行所有操作
      const undoInstructions: string[] = [];
      
      // 反向处理步骤（从后往前）
      for (let i = undoableSteps.length - 1; i >= 0; i--) {
        const stepItem = undoableSteps[i];
        const stepType = stepItem.step?.type;
        const stepParams = stepItem.step?.params || {};
        const stepResult = stepItem.result;
        const stepData = stepResult?.data || {};

        if (stepType === "file_delete" || stepType === "execute_python_script") {
          // 检查是否是删除操作（通过execute_python_script执行os.remove）
          const scriptContent = stepParams.script || "";
          const action = stepParams.action || stepItem.step?.action || "";
          const description = stepItem.step?.description || "";
          const actionStr = typeof action === "string" ? action : String(action || "");
          const descriptionStr = typeof description === "string" ? description : String(description || "");
          const scriptContentStr = typeof scriptContent === "string" ? scriptContent : String(scriptContent || "");
          
          // 判断是否是删除操作（使用 includes 而不是 in）
          const isDeleteOperation = 
            stepType === "file_delete" ||
            (stepType === "execute_python_script" && (
              actionStr.includes("删除") || descriptionStr.includes("删除") ||
              (scriptContentStr.includes("os.remove") || scriptContentStr.includes("os.unlink") || scriptContentStr.includes("Path.unlink"))
            ));
          
          if (isDeleteOperation) {
            // 尝试从结果中提取文件路径
            let filePath = stepData.path || stepParams.file_path;
            
            // 如果是从脚本删除，尝试从脚本中提取路径
            if (!filePath && scriptContent) {
              // 尝试从脚本中提取文件路径（简化处理）
              const pathMatch = scriptContent.match(/['"]([^'"]+\.(txt|docx|pdf|png|jpg|jpeg|zip|dmg|pkg))['"]/);
              if (pathMatch) {
                filePath = pathMatch[1];
              }
            }
            
            // 如果从结果消息中提取路径
            if (!filePath && stepResult?.message) {
              const messageMatch = stepResult.message.match(/删除.*?([\/~][^\s]+)/);
              if (messageMatch) {
                filePath = messageMatch[1];
              }
            }
            
            if (filePath) {
              // macOS: 尝试从Trash恢复，如果不行则提示用户
              undoInstructions.push(`恢复文件 ${filePath}（从回收站）`);
            }
          }
        } else if (stepType === "file_rename") {
          // 重命名的反向：改回原名
          const target = stepData.target || stepParams.new_name;
          const source = stepData.source || stepParams.file_path;
          if (target && source && target !== source) {
            // 提取文件名（不包含路径）
            const targetName = target.split("/").pop() || target;
            const sourceName = source.split("/").pop() || source;
            undoInstructions.push(`将文件 ${targetName} 重命名为 ${sourceName}`);
          }
        } else if (stepType === "file_move") {
          // 移动的反向：移回原位置
          const newPath = stepData.new_path || stepData.target;
          const oldPath = stepData.path || stepParams.file_path;
          if (newPath && oldPath && newPath !== oldPath) {
            const newFileName = newPath.split("/").pop() || newPath;
            const oldDir = oldPath.split("/").slice(0, -1).join("/") || "原位置";
            undoInstructions.push(`将文件 ${newFileName} 移动回 ${oldDir}`);
          }
        } else if (stepType === "file_create") {
          // 创建文件的反向：删除文件
          const filePath = stepData.path || stepParams.file_path;
          if (filePath) {
            const fileName = filePath.split("/").pop() || filePath;
            undoInstructions.push(`删除文件 ${fileName}`);
          }
        } else if (stepType === "file_write") {
          // 写入文件的反向：恢复原内容（需要保存原内容，这里简化处理）
          const filePath = stepParams.file_path;
          if (filePath) {
            const fileName = filePath.split("/").pop() || filePath;
            undoInstructions.push(`恢复文件 ${fileName} 的原始内容`);
          }
        } else if (stepType === "file_copy") {
          // 复制的反向：删除副本
          const target = stepData.target || stepParams.target_path;
          if (target) {
            const fileName = target.split("/").pop() || target;
            undoInstructions.push(`删除复制的文件 ${fileName}`);
          }
        }
      }

      if (undoInstructions.length === 0) {
        addMessage({
          id: Date.now().toString(),
          role: "system",
          content: "无法生成撤回操作",
          timestamp: new Date(),
        });
        return;
      }

      // 构建撤回指令
      const undoInstruction = `撤回刚才的操作：${undoInstructions.join("，")}`;
      
      // 添加用户消息
      const undoUserMessage: ChatMessage = {
        id: Date.now().toString(),
        role: "user",
        content: undoInstruction,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, undoUserMessage]);

      // 执行撤回操作
      try {
        updateStatus("planning");
        addLog("info", "开始撤回操作...");

        // 构建上下文（使用原始任务的结果）
        const context: any = {};
        if (taskResult.steps && taskResult.steps.length > 0) {
          const contextFiles: string[] = [];
          for (const stepItem of taskResult.steps) {
            const stepData = stepItem.result?.data;
            if (stepData?.path) contextFiles.push(stepData.path);
            if (stepData?.target) contextFiles.push(stepData.target);
            if (stepData?.new_path) contextFiles.push(stepData.new_path);
          }
          if (contextFiles.length > 0) {
            context.created_files = contextFiles;
            context.last_created_file = contextFiles[contextFiles.length - 1];
          }
        }

        // 检查任务是否被取消
        if (isTaskCancelledRef.current) {
          log.debug("🛑 [handleUndo] 任务已被取消，跳过执行");
          return;
        }

        const result = await executeTask(undoInstruction, Object.keys(context).length > 0 ? context : null);

        // 检查任务是否在执行过程中被取消
        if (isTaskCancelledRef.current) {
          log.debug("🛑 [handleUndo] 任务在执行过程中被取消");
          return;
        }

        // 更新消息
        const undoAssistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: result.success ? `撤回成功：${result.message}` : `撤回失败：${result.message}`,
          timestamp: new Date(),
          taskResult: result,
        };
        setMessages((prev) => [...prev, undoAssistantMessage]);

        if (result.success) {
          addLog("success", "撤回操作完成");
          updateStatus("completed");
        } else {
          addLog("error", "撤回操作失败");
          updateStatus("error");
        }
      } catch (error: any) {
        // 如果任务已被取消，不显示错误
        if (isTaskCancelledRef.current) {
          log.debug("🛑 [handleUndo] 任务已取消，忽略错误");
          return;
        }

        log.error("撤回操作失败:", error);
        addLog("error", `撤回失败: ${error.message || error}`);
        updateStatus("error");
        
        const errorMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: `撤回失败: ${error.message || error}`,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMessage]);
      }
    } catch (outerError: any) {
      // 捕获所有未预期的错误，防止组件崩溃
      log.error("撤回操作发生未预期错误:", outerError);
      addLog("error", `撤回操作失败: ${outerError.message || outerError}`);
      updateStatus("idle");
      
      const errorMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: `撤回操作失败: ${outerError.message || "未知错误，请查看控制台"}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    }
  };

  return (
    <div className="h-full w-full flex flex-col bg-white dark:bg-[#0a0a0a] overflow-hidden relative">
      {/* 复制成功提示 Toast */}
      <AnimatePresence mode="wait">
        {copyToast.show && (
          <motion.div
            variants={toastVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="fixed top-4 left-1/2 transform -translate-x-1/2 z-50 pointer-events-none gpu-accelerated"
          >
            <div className="bg-gray-900 dark:bg-gray-800 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span className="text-sm font-medium">{copyToast.message}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      
      {/* 主内容区域 */}
      <div className="flex-1 flex overflow-hidden">
        {/* 左侧边栏 */}
        <ChatSidebar
        currentChatId={currentChatId}
        chats={chats}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
        onDeleteChat={handleDeleteChat}
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => {
          const newState = !sidebarCollapsed;
          setSidebarCollapsed(newState);
          localStorage.setItem("deskjarvis_sidebar_collapsed", String(newState));
        }}
        onClearAllChats={handleClearAllChats}
      />

      {/* 主聊天区域 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4 bg-white dark:bg-[#0a0a0a] scrollbar-auto-hide" style={{
          // 优化滚动性能，减少抖动
          scrollBehavior: "smooth",
          willChange: status === "planning" ? "scroll-position" : "auto",
        }}>
        {messages.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 mt-20">
            <p className="text-xl font-medium mb-3 text-gray-700 dark:text-gray-300">欢迎使用 DeskJarvis</p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              用自然语言告诉我你想做什么，我会帮你完成！
            </p>
            <div className="mt-10 text-left max-w-md mx-auto space-y-3 text-sm">
              <p className="font-semibold text-gray-700 dark:text-gray-300">示例指令：</p>
              <ul className="space-y-2 text-gray-600 dark:text-gray-400">
                <li className="flex items-start gap-2">
                  <span className="text-blue-500 dark:text-blue-400 mt-0.5">•</span>
                  <span>从Python官网下载最新安装包</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-500 dark:text-blue-400 mt-0.5">•</span>
                  <span>整理下载文件夹，按文件类型分类</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-blue-500 dark:text-blue-400 mt-0.5">•</span>
                  <span>帮我截图桌面</span>
                </li>
              </ul>
            </div>
          </div>
        )}

        <AnimatePresence mode="popLayout">
          {messages.map((message, index) => (
            <motion.div
              key={message.id}
              variants={messageVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
              layout
              className={`flex ${
                message.role === "user" ? "justify-end" : "justify-start"
              } gpu-accelerated`}
            >
              <div className={`flex items-start gap-3 max-w-[85%] ${
                message.role === "user" ? "flex-row-reverse" : "flex-row"
              }`}>
                {/* 头像 */}
                {message.role === "user" ? (
                  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-gray-900 dark:bg-white flex items-center justify-center">
                    <svg className="w-4 h-4 text-white dark:text-gray-900" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
                    </svg>
                  </div>
                ) : message.role === "system" ? (
                  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-amber-500 flex items-center justify-center">
                    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                ) : (
                  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm">
                    <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 2L9.19 8.63L2 9.24l5.46 4.73L5.82 21L12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2z"/>
                    </svg>
                  </div>
                )}

                {/* 消息气泡容器 */}
                <div className={`flex flex-col ${
                  message.role === "user" ? "items-end" : "items-start"
                }`}>
                  {/* 消息气泡 */}
                  <div className={`rounded-2xl px-4 py-3 ${
                    message.role === "user"
                      ? "bg-gray-900 dark:bg-white text-white dark:text-gray-900 shadow-md"
                      : message.role === "system"
                      ? "bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-800/50"
                      : "bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                  }`}>
                  {/* Markdown 内容 */}
                  {message.role === "user" ? (
                    <p className="whitespace-pre-wrap m-0 text-sm leading-relaxed">{message.content}</p>
                  ) : (
                    <div className="markdown-content prose prose-sm dark:prose-invert max-w-none text-sm font-mono">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          // 段落
                          p: ({ children }: any) => <p className="m-0 mb-2 last:mb-0 leading-relaxed text-sm">{children}</p>,
                          
                          // 标题
                          h1: ({ children }: any) => <h1 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h1>,
                          h2: ({ children }: any) => <h2 className="text-base font-bold mt-3 mb-2 first:mt-0">{children}</h2>,
                          h3: ({ children }: any) => <h3 className="text-sm font-semibold mt-2 mb-1 first:mt-0">{children}</h3>,
                          
                          // 代码块
                          code: ({ className, children, ...props }: any) => {
                            const match = /language-(\w+)/.exec(className || '');
                            const isInline = !match;
                            
                            if (isInline) {
                              return (
                                <code 
                                  className="bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded text-sm font-mono text-gray-800 dark:text-gray-200" 
                                  {...props}
                                >
                                  {children}
                                </code>
                              );
                            }
                            
                            return (
                              <pre className="bg-gray-900 dark:bg-gray-950 p-3 rounded-lg overflow-x-auto my-2 border border-gray-700">
                                <code className={`text-sm font-mono text-gray-100 ${className || ''}`} {...props}>
                                  {children}
                                </code>
                              </pre>
                            );
                          },
                          
                          // 列表
                          ul: ({ children }: any) => (
                            <ul className="list-disc list-inside my-2 space-y-1 ml-2">{children}</ul>
                          ),
                          ol: ({ children }: any) => (
                            <ol className="list-decimal list-inside my-2 space-y-1 ml-2">{children}</ol>
                          ),
                          li: ({ children }: any) => (
                            <li className="ml-2">{children}</li>
                          ),
                          
                          // 表格
                          table: ({ children }: any) => (
                            <div className="overflow-x-auto my-2">
                              <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600">
                                {children}
                              </table>
                            </div>
                          ),
                          thead: ({ children }: any) => (
                            <thead className="bg-gray-100 dark:bg-gray-800">{children}</thead>
                          ),
                          tbody: ({ children }: any) => <tbody>{children}</tbody>,
                          tr: ({ children }: any) => (
                            <tr className="border-b border-gray-200 dark:border-gray-700">{children}</tr>
                          ),
                          th: ({ children }: any) => (
                            <th className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-left font-semibold text-sm">
                              {children}
                            </th>
                          ),
                          td: ({ children }: any) => (
                            <td className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm">
                              {children}
                            </td>
                          ),
                          
                          // 引用
                          blockquote: ({ children }: any) => (
                            <blockquote className="border-l-4 border-blue-500 pl-4 my-2 italic text-gray-600 dark:text-gray-400">
                              {children}
                            </blockquote>
                          ),
                          
                          // 链接
                          a: ({ href, children }: any) => (
                            <a 
                              href={href} 
                              target="_blank" 
                              rel="noopener noreferrer"
                              className="text-blue-600 dark:text-blue-400 hover:underline"
                            >
                              {children}
                            </a>
                          ),
                          
                          // 粗体、斜体
                          strong: ({ children }: any) => (
                            <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>
                          ),
                          em: ({ children }: any) => (
                            <em className="italic">{children}</em>
                          ),
                          
                          // 水平线
                          hr: () => <hr className="my-4 border-gray-300 dark:border-gray-700" />,
                          
                          // 任务列表（GFM）
                          input: ({ checked, ...props }: any) => (
                            <input 
                              type="checkbox" 
                              checked={checked} 
                              readOnly 
                              className="mr-2"
                              {...props}
                            />
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )}

                  {/* 图片预览 */}
                  {message.images && message.images.length > 0 ? (
                    <motion.div
                      variants={imagePreviewVariants}
                      initial="hidden"
                      animate="visible"
                      className="mt-3 space-y-2 gpu-accelerated"
                    >
                      {message.images.map((imageDataUrl, idx) => {
                        log.debug(`🖼️ 渲染图片 ${idx + 1}, 数据URL长度: ${imageDataUrl.length}`);
                        return (
                          <div
                            key={idx}
                            className="rounded-lg overflow-hidden border-2 border-gray-200 dark:border-gray-700 shadow-md hover:shadow-lg transition-shadow cursor-pointer group"
                            onClick={() => {
                              // 点击图片在新窗口打开大图
                              const newWindow = window.open();
                              if (newWindow) {
                                newWindow.document.write(`
                                  <!DOCTYPE html>
                                  <html>
                                    <head>
                                      <title>图片预览</title>
                                      <style>
                                        body { margin: 0; padding: 20px; background: #1a1a1a; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
                                        img { max-width: 100%; max-height: 100vh; border-radius: 8px; box-shadow: 0 4px 20px rgba(0,0,0,0.3); }
                                      </style>
                                    </head>
                                    <body>
                                      <img src="${imageDataUrl}" alt="截图预览" />
                                    </body>
                                  </html>
                                `);
                              }
                            }}
                          >
                            <img
                              src={imageDataUrl}
                              alt={`截图 ${idx + 1}`}
                              className="max-w-full h-auto block group-hover:opacity-90 transition-opacity"
                              onError={(e) => {
                                log.error(`❌ 图片加载失败 ${idx + 1}:`, e);
                              }}
                              onLoad={() => {
                                log.debug(`✅ 图片加载成功 ${idx + 1}`);
                              }}
                            />
                            <div className="px-3 py-2 bg-gray-50 dark:bg-gray-900/50 text-xs text-gray-500 dark:text-gray-400 text-center">
                              点击查看大图
                            </div>
                          </div>
                        );
                      })}
                    </motion.div>
                  ) : (
                    // 如果有截图路径但图片未加载，显示提示
                    message.taskResult && message.taskResult.steps && (() => {
                      log.debug("🔍 [渲染] 检查是否有截图路径但图片未加载");
                      const paths: string[] = [];
                      for (const stepItem of message.taskResult.steps) {
                        if (
                          stepItem.step?.type === "screenshot_desktop" &&
                          stepItem.result?.success &&
                          stepItem.result?.data?.path
                        ) {
                          paths.push(stepItem.result.data.path);
                        }
                      }
                      log.debug(`🔍 [渲染] 找到 ${paths.length} 个截图路径，但图片未加载`);
                      return paths.length > 0 ? (
                        <motion.div
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          className="mt-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg"
                        >
                          <p className="text-sm text-yellow-800 dark:text-yellow-200 mb-1">
                            图片预览加载失败
                          </p>
                          <p className="text-xs text-yellow-600 dark:text-yellow-400">
                            文件已保存到: {paths[0]}
                          </p>
                          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                            请打开开发者工具（F12）查看控制台日志
                          </p>
                          <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">
                            Tauri环境: {isTauriEnvironment() ? "是" : "否"}
                          </p>
                        </motion.div>
                      ) : null;
                    })()
                  )}
                  </div>

                  {/* 操作按钮 - 在气泡下方 */}
                  <div className={`mt-1 flex items-center gap-2 ${
                    message.role === "user" ? "justify-end" : "justify-start"
                  }`}>
                    {/* 复制按钮 */}
                    <button
                      onClick={() => handleCopyMessage(message.content, message.id)}
                      className={`relative flex items-center justify-center w-6 h-6 rounded hover:bg-gray-100 dark:hover:bg-gray-800 active:scale-95 transition-transform ${
                        copiedMessageId === message.id
                          ? "text-green-500 dark:text-green-400"
                          : message.role === "user"
                          ? "text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300"
                          : "text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                      }`}
                      title={copiedMessageId === message.id ? "已复制" : "复制消息"}
                    >
                      {/* 复制图标 */}
                      <svg
                        className={`w-3.5 h-3.5 absolute transition-opacity duration-200 ${
                          copiedMessageId === message.id ? "opacity-0" : "opacity-100"
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                        />
                      </svg>
                      {/* 对勾图标 */}
                      <svg
                        className={`w-3.5 h-3.5 absolute transition-opacity duration-200 ${
                          copiedMessageId === message.id ? "opacity-100" : "opacity-0"
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    </button>

                    {/* 撤回按钮 - 仅AI消息且有任务结果时显示 */}
                    {message.role === "assistant" && message.taskResult && message.taskResult.steps && message.taskResult.steps.length > 0 && (
                      <button
                        onClick={() => handleUndo(message.taskResult!)}
                        className="flex items-center justify-center w-6 h-6 rounded transition-all hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
                        title="撤回操作"
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>


        <div ref={messagesEndRef} />
        </div>

        {/* 输入框 */}
        <div className="flex-shrink-0 bg-white dark:bg-[#0a0a0a] px-4 py-4">
          <div className="max-w-4xl mx-auto">
            {/* 已附加的路径显示 */}
            {attachedPath && (
              <div className="mb-3 flex items-center gap-2 px-4 py-2.5 bg-blue-50 dark:bg-blue-900/20 rounded-2xl">
                <svg className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                </svg>
                <span className="flex-1 text-sm text-blue-800 dark:text-blue-200 truncate" title={attachedPath}>
                  {attachedPath}
                </span>
                <button
                  onClick={handleRemoveAttachment}
                  className="flex-shrink-0 w-6 h-6 flex items-center justify-center rounded-lg hover:bg-blue-200 dark:hover:bg-blue-800/50 transition-colors"
                  title="移除"
                >
                  <svg className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}
            
            {/* 输入框容器：嵌入式按钮 */}
            <div 
              className={`relative ${isDragging ? "opacity-50" : ""}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value);
                  // 自动调整高度
                  const textarea = e.target as HTMLTextAreaElement;
                  textarea.style.height = "auto";
                  const scrollHeight = textarea.scrollHeight;
                  const minHeight = 56;
                  const maxHeight = 200;
                  
                  if (scrollHeight <= maxHeight) {
                    // 内容未超过最大高度，自动调整高度
                    textarea.style.height = `${Math.max(scrollHeight, minHeight)}px`;
                    textarea.style.overflowY = "hidden";
                  } else {
                    // 内容超过最大高度，固定高度并允许滚动
                    textarea.style.height = `${maxHeight}px`;
                    textarea.style.overflowY = "auto";
                  }
                }}
                onKeyPress={handleKeyPress}
                placeholder={isDragging ? "松开鼠标以附加文件..." : "输入你的指令或拖拽文件/文件夹到这里..."}
                disabled={status !== "idle"}
                className="w-full px-5 py-4 pr-32 rounded-[2rem] border border-gray-200 dark:border-gray-800 bg-white dark:bg-[#1a1a1a] text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-black dark:focus:ring-white focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed resize-none transition-all overflow-y-auto"
                rows={1}
                style={{ minHeight: "56px", maxHeight: "200px" }}
              />
              
              {/* 右侧嵌入式按钮组 */}
              <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1.5">
                {/* 文件选择按钮 */}
                <button
                  onClick={handleFileSelect}
                  disabled={status !== "idle"}
                  className="flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-2xl text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  title="选择文件或文件夹"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
                
                {/* 发送/停止按钮 */}
                <button
                  onClick={handleSend}
                  disabled={status === "idle" && !input.trim()}
                  className={`flex-shrink-0 w-10 h-10 flex items-center justify-center rounded-full bg-black dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-black dark:focus:ring-white disabled:opacity-50 disabled:cursor-not-allowed transition-all relative ${
                    status !== "idle" ? "hover:bg-red-600 dark:hover:bg-red-400" : "shadow-sm hover:shadow-md"
                  }`}
                  title={status !== "idle" ? "停止任务" : "发送"}
                >
                  <AnimatePresence initial={false}>
                    {status !== "idle" ? (
                      // 任务执行中显示停止图标（正方形方块）
                      <motion.div
                        key="stop"
                        initial={{ opacity: 0, scale: 0.5, rotate: -90 }}
                        animate={{ opacity: 1, scale: 1, rotate: 0 }}
                        exit={{ opacity: 0, scale: 0.5, rotate: 90 }}
                        transition={{ 
                          type: "spring",
                          stiffness: 600,
                          damping: 30,
                          duration: 0.2
                        }}
                        style={{ 
                          position: "absolute",
                          display: "flex", 
                          alignItems: "center", 
                          justifyContent: "center" 
                        }}
                      >
                        <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                          <rect x="4" y="4" width="16" height="16" rx="1.5" />
                        </svg>
                      </motion.div>
                    ) : (
                      // 正常状态显示箭头
                      <motion.div
                        key="send"
                        initial={{ opacity: 0, scale: 0.5, rotate: 90 }}
                        animate={{ opacity: 1, scale: 1, rotate: 0 }}
                        exit={{ opacity: 0, scale: 0.5, rotate: -90 }}
                        transition={{ 
                          type: "spring",
                          stiffness: 600,
                          damping: 30,
                          duration: 0.2
                        }}
                        style={{ 
                          position: "absolute",
                          display: "flex", 
                          alignItems: "center", 
                          justifyContent: "center" 
                        }}
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 15l7-7 7 7" />
                        </svg>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </button>
              </div>
            </div>
            
            {/* 隐藏的文件输入 */}
            <input
              ref={fileInputRef}
              type="file"
              style={{ display: "none" }}
              {...{ webkitdirectory: "" } as any}
              multiple={false}
              onChange={(e) => {
                const files = e.target.files;
                if (files && files.length > 0) {
                  const file = files[0];
                  // 尝试获取完整路径（Tauri 环境）
                  const path = (file as any).path || file.webkitRelativePath || file.name;
                  setAttachedPath(path);
                  setInput((prev) => {
                    const trimmed = prev.trim();
                    return trimmed ? `${trimmed} ${path}` : path;
                  });
                }
              }}
            />
          </div>
        </div>
      </div>
      </div>
      
      {/* 用户输入对话框（登录、验证码） */}
      <UserInputDialog
        request={userInputRequest}
        onSubmit={handleUserInputSubmit}
        onCancel={handleUserInputCancel}
      />
    </div>
  );
};

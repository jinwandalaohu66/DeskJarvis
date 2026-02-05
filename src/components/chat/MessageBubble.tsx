/**
 * 消息气泡组件
 * 
 * 功能：
 * - 显示单条消息（用户/AI/系统）
 * - 支持图片预览
 * - 支持 Markdown 渲染
 */

import React, { useState } from "react";
import { motion } from "framer-motion";
import { ChatMessage } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { messageVariants, imagePreviewVariants } from "../../utils/animations";

interface MessageBubbleProps {
  message: ChatMessage;
}

/**
 * 用户头像组件 - 简约人形图标
 */
const UserAvatar: React.FC = () => (
  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-gray-900 dark:bg-white flex items-center justify-center">
    <svg className="w-4 h-4 text-white dark:text-gray-900" fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
    </svg>
  </div>
);

/**
 * AI 头像组件 - 星星/火花图标
 */
const AIAvatar: React.FC = () => (
  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-sm">
    <svg className="w-4 h-4 text-white" fill="currentColor" viewBox="0 0 24 24">
      <path d="M12 2L9.19 8.63L2 9.24l5.46 4.73L5.82 21L12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2z"/>
    </svg>
  </div>
);

/**
 * 系统头像组件 - 感叹号
 */
const SystemAvatar: React.FC = () => (
  <div className="flex-shrink-0 w-8 h-8 rounded-xl bg-amber-500 flex items-center justify-center">
    <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  </div>
);

/**
 * 消息气泡组件
 */
export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedId(message.id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      // 复制失败时静默处理
    }
  };

  const handleImageClick = (imageDataUrl: string) => {
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
      newWindow.document.close();
    }
  };

  // 获取头像组件
  const Avatar = () => {
    if (message.role === "user") return <UserAvatar />;
    if (message.role === "system") return <SystemAvatar />;
    return <AIAvatar />;
  };

  return (
    <motion.div
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
        <Avatar />

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
            {/* 消息内容 */}
            {message.role === "user" ? (
              <p className="whitespace-pre-wrap m-0 text-sm leading-relaxed">
                {message.content}
              </p>
            ) : (
              <MarkdownRenderer content={message.content} />
            )}

            {/* 图片预览 */}
            {message.images && message.images.length > 0 && (
              <motion.div
                variants={imagePreviewVariants}
                initial="hidden"
                animate="visible"
                className="mt-3 space-y-2 gpu-accelerated"
              >
                {message.images.map((imageDataUrl, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 shadow-sm hover:shadow-md transition-shadow cursor-pointer group"
                    onClick={() => handleImageClick(imageDataUrl)}
                  >
                    <img
                      src={imageDataUrl}
                      alt={`截图 ${idx + 1}`}
                      className="max-w-full max-h-60 w-auto h-auto object-contain transition-transform group-hover:scale-[1.02]"
                      onError={(e) => {
                        const target = e.target as HTMLImageElement;
                        target.style.display = 'none';
                      }}
                    />
                    <div className="px-3 py-2 bg-gray-50 dark:bg-gray-900 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0zM10 7v3m0 0v3m0-3h3m-3 0H7" />
                      </svg>
                      <span>点击放大</span>
                    </div>
                  </div>
                ))}
              </motion.div>
            )}
          </div>

          {/* 复制按钮（仅 AI 消息） */}
          {message.role === "assistant" && (
            <div className="flex items-center gap-2 mt-1.5 px-1">
              <button
                onClick={handleCopy}
                className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex items-center gap-1.5 transition-colors"
                title="复制内容"
              >
                <div className="relative w-3.5 h-3.5">
                  <svg
                    className={`absolute inset-0 w-3.5 h-3.5 transition-opacity duration-200 ${
                      copiedId === message.id ? 'opacity-0' : 'opacity-100'
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
                  <svg
                    className={`absolute inset-0 w-3.5 h-3.5 text-emerald-500 transition-opacity duration-200 ${
                      copiedId === message.id ? 'opacity-100' : 'opacity-0'
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
                </div>
                <span>{copiedId === message.id ? '已复制' : '复制'}</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default MessageBubble;

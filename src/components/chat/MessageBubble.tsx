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
      <div className={`flex items-start gap-2 max-w-[85%] ${
        message.role === "user" ? "flex-row-reverse" : "flex-row"
      }`}>
        {/* 头像 */}
        <div className={`flex-shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium ${
          message.role === "user"
            ? "bg-blue-600 text-white"
            : message.role === "system"
            ? "bg-yellow-500 text-white"
            : "bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300"
        }`}>
          {message.role === "user" ? "你" : message.role === "system" ? "!" : "AI"}
        </div>

        {/* 消息气泡容器 */}
        <div className={`flex flex-col ${
          message.role === "user" ? "items-end" : "items-start"
        }`}>
          {/* 消息气泡 */}
          <div className={`rounded-2xl px-4 py-3 ${
            message.role === "user"
              ? "bg-blue-600 dark:bg-blue-500 text-white shadow-lg shadow-blue-500/20"
              : message.role === "system"
              ? "bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 rounded-2xl"
              : "bg-gray-50 dark:bg-[#1e1e1e] text-gray-900 dark:text-gray-100 shadow-sm border border-gray-100 dark:border-gray-800/50"
          }`}>
            {/* 消息内容 */}
            {message.role === "user" ? (
              <p className="text-white whitespace-pre-wrap m-0 text-sm leading-relaxed font-mono">
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
                    className="rounded-lg overflow-hidden border-2 border-gray-200 dark:border-gray-700 shadow-md hover:shadow-lg transition-shadow cursor-pointer group"
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
                    <div className="px-3 py-2 bg-gray-100 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      <span>点击查看大图</span>
                    </div>
                  </div>
                ))}
              </motion.div>
            )}
          </div>

          {/* 复制按钮（仅 AI 消息） */}
          {message.role === "assistant" && (
            <div className="flex items-center gap-2 mt-1 px-1">
              <button
                onClick={handleCopy}
                className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 flex items-center gap-1 transition-colors"
                title="复制内容"
              >
                <div className="relative w-3 h-3">
                  <svg
                    className={`absolute inset-0 w-3 h-3 transition-opacity duration-200 ${
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
                    className={`absolute inset-0 w-3 h-3 text-green-500 transition-opacity duration-200 ${
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

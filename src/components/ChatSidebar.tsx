/**
 * 聊天侧边栏组件：Ollama 风格的聊天历史列表
 */

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface ChatSession {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
  messageCount: number;
}

interface ChatSidebarProps {
  currentChatId: string | null;
  chats: ChatSession[];
  onNewChat: () => void;
  onSelectChat: (chatId: string) => void;
  onDeleteChat: (chatId: string) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onClearAllChats?: () => void;
}

const panelTransition = {
  type: "spring" as const,
  stiffness: 280,
  damping: 35,
  mass: 0.9,
};

export const ChatSidebar: React.FC<ChatSidebarProps> = ({
  currentChatId,
  chats,
  onNewChat,
  onSelectChat,
  onDeleteChat,
  collapsed = false,
  onToggleCollapse,
  onClearAllChats,
}) => {
  const [hoveredChatId, setHoveredChatId] = useState<string | null>(null);
  
  const expandedWidth = 220;
  const collapsedWidth = 64;

  const groupChatsByDate = () => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const todayChats: ChatSession[] = [];
    const olderChats: ChatSession[] = [];

    chats.forEach((chat) => {
      const chatDate = new Date(chat.updatedAt);
      chatDate.setHours(0, 0, 0, 0);
      
      if (chatDate.getTime() === today.getTime()) {
        todayChats.push(chat);
      } else {
        olderChats.push(chat);
      }
    });

    return { todayChats, olderChats };
  };

  const { todayChats, olderChats } = groupChatsByDate();

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
  
  // 图标样式 - 确保居中
  const iconStyle: React.CSSProperties = {
    width: '16px',
    height: '16px',
    flexShrink: 0,
  };
  
  const collapsedButtonClass = "bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 active:scale-95 transition-transform";

  return (
    <motion.div
      initial={false}
      animate={{ width: collapsed ? collapsedWidth : expandedWidth }}
      transition={panelTransition}
      layout
      className="h-full bg-black dark:bg-white flex flex-col overflow-hidden flex-shrink-0"
      style={{ 
        borderTopRightRadius: '1.5rem',
        borderBottomRightRadius: '1.5rem',
      }}
    >
      {/* 顶部按钮区域 */}
      <div className="flex-shrink-0 pt-4 pb-2 overflow-hidden">
        {collapsed ? (
          // 收起状态：垂直居中排列 - 使用固定宽度 64px 容器
          <div style={{ width: '64px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
            {onToggleCollapse && (
              <button onClick={onToggleCollapse} className={collapsedButtonClass} style={collapsedButtonStyle} title="展开侧边栏">
                <svg style={iconStyle} className="text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            )}
            <button onClick={onNewChat} className={collapsedButtonClass} style={collapsedButtonStyle} title="新建聊天">
              <svg style={iconStyle} className="text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        ) : (
          // 展开状态：水平排列
          <div className="flex items-center gap-2 px-3">
            {onToggleCollapse && (
              <button
                onClick={onToggleCollapse}
                className="w-9 h-9 rounded-xl bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 flex items-center justify-center flex-shrink-0 active:scale-95 transition-transform"
                title="折叠侧边栏"
              >
                <svg className="w-4 h-4 text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                </svg>
              </button>
            )}
            <button
              onClick={onNewChat}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-xl bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 active:scale-[0.98] transition-transform"
              title="新建聊天"
            >
              <svg className="w-4 h-4 text-black dark:text-white flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span className="text-sm font-medium text-black dark:text-white">New Chat</span>
            </button>
          </div>
        )}
      </div>

      {/* 聊天列表 */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {collapsed ? (
          // 收起状态：聊天图标居中 - 使用固定宽度 64px 容器
          <div style={{ width: '64px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', paddingTop: '8px', paddingBottom: '8px' }}>
            {chats.map((chat) => (
              <ChatItem
                key={chat.id}
                chat={chat}
                isSelected={currentChatId === chat.id}
                isHovered={hoveredChatId === chat.id}
                collapsed={true}
                onSelect={() => onSelectChat(chat.id)}
                onDelete={() => onDeleteChat(chat.id)}
                onMouseEnter={() => setHoveredChatId(chat.id)}
                onMouseLeave={() => setHoveredChatId(null)}
              />
            ))}
            {chats.length === 0 && (
              <div className="py-8 text-center">
                <svg className="w-6 h-6 mx-auto text-gray-400 dark:text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
            )}
          </div>
        ) : (
          // 展开状态：完整聊天列表
          <div className="px-3">
            {todayChats.length > 0 && (
              <div className="py-2">
                <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider mb-2 px-1">Today</h3>
                <div className="space-y-1">
                  {todayChats.map((chat) => (
                    <ChatItem
                      key={chat.id}
                      chat={chat}
                      isSelected={currentChatId === chat.id}
                      isHovered={hoveredChatId === chat.id}
                      collapsed={false}
                      onSelect={() => onSelectChat(chat.id)}
                      onDelete={() => onDeleteChat(chat.id)}
                      onMouseEnter={() => setHoveredChatId(chat.id)}
                      onMouseLeave={() => setHoveredChatId(null)}
                    />
                  ))}
                </div>
              </div>
            )}
            {olderChats.length > 0 && (
              <div className="py-2">
                <h3 className="text-xs font-semibold text-gray-400 dark:text-gray-600 uppercase tracking-wider mb-2 px-1">Older</h3>
                <div className="space-y-1">
                  {olderChats.map((chat) => (
                    <ChatItem
                      key={chat.id}
                      chat={chat}
                      isSelected={currentChatId === chat.id}
                      isHovered={hoveredChatId === chat.id}
                      collapsed={false}
                      onSelect={() => onSelectChat(chat.id)}
                      onDelete={() => onDeleteChat(chat.id)}
                      onMouseEnter={() => setHoveredChatId(chat.id)}
                      onMouseLeave={() => setHoveredChatId(null)}
                    />
                  ))}
                </div>
              </div>
            )}
            {chats.length === 0 && (
              <div className="py-8 text-center text-gray-400 dark:text-gray-600 text-sm">
                <p>还没有聊天记录</p>
                <p className="text-xs mt-2">点击 "New Chat" 开始对话</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部按钮区域 */}
      <div className="flex-shrink-0 pt-2 pb-4">
        {collapsed ? (
          // 收起状态：设置按钮居中 - 使用固定宽度 64px 容器
          <div style={{ width: '64px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <button
              onClick={() => window.dispatchEvent(new CustomEvent('navigate-to-settings'))}
              className={collapsedButtonClass}
              style={collapsedButtonStyle}
              title="设置"
            >
              <svg style={iconStyle} className="text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            </button>
          </div>
        ) : (
          // 展开状态：设置按钮 + 清空按钮
          <div className="flex items-center gap-2 px-3">
            <button
              onClick={() => window.dispatchEvent(new CustomEvent('navigate-to-settings'))}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900 active:scale-[0.98] transition-transform"
              title="设置"
            >
              <svg className="w-4 h-4 text-black dark:text-white flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              <span className="text-sm font-medium text-black dark:text-white">设置</span>
            </button>
            {chats.length > 0 && onClearAllChats && (
              <button
                onClick={() => {
                  if (window.confirm("确定要清空所有聊天记录吗？此操作不可恢复。")) {
                    onClearAllChats();
                  }
                }}
                className="w-9 h-9 rounded-full bg-red-600 hover:bg-red-700 flex items-center justify-center flex-shrink-0 active:scale-95 transition-transform"
                title="清空所有聊天"
              >
                <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

// 聊天项组件
interface ChatItemProps {
  chat: ChatSession;
  isSelected: boolean;
  isHovered: boolean;
  collapsed: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

const ChatItem: React.FC<ChatItemProps> = ({
  chat,
  isSelected,
  isHovered,
  collapsed,
  onSelect,
  onDelete,
  onMouseEnter,
  onMouseLeave,
}) => {
  const getChatTitle = (chat: ChatSession): string => {
    return chat.title || "新聊天";
  };

  if (collapsed) {
    return (
      <div
        style={{
          width: '40px',
          height: '40px',
          borderRadius: '16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          position: 'relative',
          flexShrink: 0,
        }}
        className={`group active:scale-95 transition-transform ${
          isSelected
            ? "bg-white dark:bg-black"
            : "bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900"
        }`}
        onClick={onSelect}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
        title={getChatTitle(chat)}
      >
        <svg style={{ width: '16px', height: '16px', flexShrink: 0 }} className="text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        {isHovered && (
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            className="absolute -top-1 -right-1 w-4 h-4 flex items-center justify-center rounded-full bg-red-500 text-white text-xs hover:bg-red-600 z-10 shadow-sm active:scale-90 transition-transform"
            title="删除"
          >
            ×
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={`group relative flex items-center gap-2 px-3 py-2 rounded-xl cursor-pointer active:scale-[0.98] transition-transform ${
        isSelected
          ? "bg-white dark:bg-black"
          : "bg-white dark:bg-black hover:bg-gray-100 dark:hover:bg-gray-900"
      }`}
      onClick={onSelect}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="flex-shrink-0 w-5 h-5 flex items-center justify-center">
        <svg className="w-4 h-4 text-black dark:text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <p className={`text-sm truncate ${isSelected ? "text-black dark:text-white font-medium" : "text-black dark:text-white"}`}>
          {getChatTitle(chat)}
        </p>
      </div>
      {(isHovered || isSelected) && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-red-100 dark:hover:bg-red-900/30 active:scale-90 transition-all"
          title="删除聊天"
        >
          <svg className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      )}
    </div>
  );
};

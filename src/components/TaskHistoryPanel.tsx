/**
 * 任务历史和收藏面板
 */

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { invoke } from "@tauri-apps/api/core";

interface Task {
  id: string;
  instruction: string;
  success: boolean;
  time_display?: string;
  duration?: number;
}

interface Favorite {
  id: string;
  name: string;
  instruction: string;
}

interface TaskHistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectTask: (instruction: string) => void;
}

export const TaskHistoryPanel: React.FC<TaskHistoryPanelProps> = ({
  isOpen,
  onClose,
  onSelectTask,
}) => {
  const [activeTab, setActiveTab] = useState<"history" | "favorites">("history");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [favorites, setFavorites] = useState<Favorite[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, activeTab]);

  const loadData = async () => {
    setLoading(true);
    try {
      if (activeTab === "history") {
        const result = await invoke<any>("execute_task", {
          instruction: "获取任务历史",
        });
        if (result?.steps?.[0]?.result?.data?.tasks) {
          setTasks(result.steps[0].result.data.tasks);
        }
      } else {
        const result = await invoke<any>("execute_task", {
          instruction: "列出收藏",
        });
        if (result?.steps?.[0]?.result?.data?.favorites) {
          setFavorites(result.steps[0].result.data.favorites);
        }
      }
    } catch (e) {
      console.error("加载数据失败:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleRemoveFavorite = async (id: string) => {
    try {
      await invoke<any>("execute_task", {
        instruction: `移除收藏 ${id}`,
      });
      setFavorites(favorites.filter(f => f.id !== id));
    } catch (e) {
      console.error("移除收藏失败:", e);
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
        >
          {/* 背景遮罩 */}
          <div 
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* 面板 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
          >
            {/* 头部 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex gap-4">
                <button
                  onClick={() => setActiveTab("history")}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    activeTab === "history"
                      ? "bg-black text-white dark:bg-white dark:text-black"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                  }`}
                >
                  历史记录
                </button>
                <button
                  onClick={() => setActiveTab("favorites")}
                  className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                    activeTab === "favorites"
                      ? "bg-black text-white dark:bg-white dark:text-black"
                      : "text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800"
                  }`}
                >
                  收藏
                </button>
              </div>
              <button
                onClick={onClose}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* 内容 */}
            <div className="flex-1 overflow-y-auto p-4 scrollbar-auto-hide">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="w-8 h-8 border-2 border-gray-300 border-t-black dark:border-gray-600 dark:border-t-white rounded-full animate-spin" />
                </div>
              ) : activeTab === "history" ? (
                tasks.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    暂无历史记录
                  </div>
                ) : (
                  <div className="space-y-2">
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        onClick={() => {
                          onSelectTask(task.instruction);
                          onClose();
                        }}
                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer transition-colors"
                      >
                        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                          task.success ? "bg-green-500" : "bg-red-500"
                        }`} />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-gray-900 dark:text-gray-100 truncate">
                            {task.instruction}
                          </div>
                          <div className="text-xs text-gray-500">
                            {task.time_display}
                            {task.duration && ` · ${task.duration}s`}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )
              ) : (
                favorites.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    暂无收藏
                  </div>
                ) : (
                  <div className="space-y-2">
                    {favorites.map((fav) => (
                      <div
                        key={fav.id}
                        className="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors group"
                      >
                        <svg className="w-5 h-5 text-yellow-500 flex-shrink-0" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                        </svg>
                        <div 
                          className="flex-1 min-w-0 cursor-pointer"
                          onClick={() => {
                            onSelectTask(fav.instruction);
                            onClose();
                          }}
                        >
                          <div className="text-sm text-gray-900 dark:text-gray-100 truncate">
                            {fav.name}
                          </div>
                          <div className="text-xs text-gray-500 truncate">
                            {fav.instruction}
                          </div>
                        </div>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveFavorite(fav.id);
                          }}
                          className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-100 dark:hover:bg-red-900/30 text-red-500 transition-all"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

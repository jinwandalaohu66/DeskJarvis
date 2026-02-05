/**
 * 工作流管理面板
 */

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { invoke } from "@tauri-apps/api/core";

interface Workflow {
  name: string;
  description: string;
  commands_count: number;
}

interface WorkflowPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectWorkflow: (name: string) => void;
}

export const WorkflowPanel: React.FC<WorkflowPanelProps> = ({
  isOpen,
  onClose,
  onSelectWorkflow,
}) => {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newCommands, setNewCommands] = useState("");
  const [newDescription, setNewDescription] = useState("");

  useEffect(() => {
    if (isOpen) {
      loadWorkflows();
    }
  }, [isOpen]);

  const loadWorkflows = async () => {
    setLoading(true);
    try {
      const result = await invoke<any>("execute_task", {
        instruction: "列出工作流",
      });
      if (result?.steps?.[0]?.result?.data?.workflows) {
        setWorkflows(result.steps[0].result.data.workflows);
      }
    } catch (e) {
      console.error("加载工作流失败:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!newName || !newCommands) return;
    
    try {
      const commands = newCommands.split("\n").filter(c => c.trim());
      await invoke<any>("execute_task", {
        instruction: `创建工作流 ${newName}: ${commands.join(", ")}`,
      });
      setShowCreate(false);
      setNewName("");
      setNewCommands("");
      setNewDescription("");
      loadWorkflows();
    } catch (e) {
      console.error("创建工作流失败:", e);
    }
  };

  const handleDelete = async (name: string) => {
    try {
      await invoke<any>("execute_task", {
        instruction: `删除工作流 ${name}`,
      });
      setWorkflows(workflows.filter(w => w.name !== name));
    } catch (e) {
      console.error("删除工作流失败:", e);
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
            className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] overflow-hidden flex flex-col"
          >
            {/* 头部 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                快捷工作流
              </h2>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowCreate(!showCreate)}
                  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* 创建表单 */}
            <AnimatePresence>
              {showCreate && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden border-b border-gray-200 dark:border-gray-700"
                >
                  <div className="p-4 space-y-3 bg-gray-50 dark:bg-gray-800/50">
                    <input
                      type="text"
                      placeholder="工作流名称（如：工作模式）"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm"
                    />
                    <textarea
                      placeholder="命令列表（每行一个）&#10;如：&#10;打开企业微信&#10;打开飞书&#10;静音"
                      value={newCommands}
                      onChange={(e) => setNewCommands(e.target.value)}
                      rows={4}
                      className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm resize-none"
                    />
                    <input
                      type="text"
                      placeholder="描述（可选）"
                      value={newDescription}
                      onChange={(e) => setNewDescription(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 text-sm"
                    />
                    <button
                      onClick={handleCreate}
                      disabled={!newName || !newCommands}
                      className="w-full py-2 rounded-lg bg-black text-white dark:bg-white dark:text-black font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      创建工作流
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* 内容 */}
            <div className="flex-1 overflow-y-auto p-4 scrollbar-auto-hide">
              {loading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="w-8 h-8 border-2 border-gray-300 border-t-black dark:border-gray-600 dark:border-t-white rounded-full animate-spin" />
                </div>
              ) : workflows.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  暂无工作流，点击 + 创建
                </div>
              ) : (
                <div className="space-y-2">
                  {workflows.map((workflow) => (
                    <div
                      key={workflow.name}
                      className="flex items-center gap-3 p-3 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors group"
                    >
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500 to-blue-500 flex items-center justify-center flex-shrink-0">
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                      </div>
                      <div 
                        className="flex-1 min-w-0 cursor-pointer"
                        onClick={() => {
                          onSelectWorkflow(workflow.name);
                          onClose();
                        }}
                      >
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100">
                          {workflow.name}
                        </div>
                        <div className="text-xs text-gray-500">
                          {workflow.description || `${workflow.commands_count} 个命令`}
                        </div>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(workflow.name);
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
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

/**
 * 用户输入对话框
 * 用于登录时输入账号密码、验证码等
 */

import React, { useState, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

export interface InputRequest {
  id: string;
  type: "login" | "captcha" | "custom";
  title: string;
  message?: string;
  fields: Array<{
    name: string;
    label: string;
    type: "text" | "password" | "captcha";
    placeholder?: string;
    required?: boolean;
  }>;
  captchaImage?: string; // base64 图片
}

interface UserInputDialogProps {
  request: InputRequest | null;
  onSubmit: (requestId: string, values: Record<string, string>) => void;
  onCancel: (requestId: string) => void;
}

export const UserInputDialog: React.FC<UserInputDialogProps> = ({
  request,
  onSubmit,
  onCancel,
}) => {
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const firstInputRef = useRef<HTMLInputElement>(null);

  // 重置表单
  useEffect(() => {
    if (request) {
      const initialValues: Record<string, string> = {};
      request.fields.forEach((field) => {
        initialValues[field.name] = "";
      });
      setValues(initialValues);
      setLoading(false);
      
      // 聚焦第一个输入框
      setTimeout(() => {
        firstInputRef.current?.focus();
      }, 100);
    }
  }, [request]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!request) return;
    
    // 检查必填字段
    for (const field of request.fields) {
      if (field.required && !values[field.name]?.trim()) {
        return;
      }
    }
    
    setLoading(true);
    onSubmit(request.id, values);
  };

  const handleCancel = () => {
    if (!request) return;
    onCancel(request.id);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      handleCancel();
    }
  };

  return (
    <AnimatePresence>
      {request && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-center justify-center p-4"
          onKeyDown={handleKeyDown}
        >
          {/* 背景遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={handleCancel}
          />

          {/* 对话框 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 20 }}
            transition={{ type: "spring", duration: 0.3 }}
            className="relative bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden"
          >
            {/* 头部 */}
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                  {request.type === "login" ? (
                    <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                  ) : (
                    <svg className="w-5 h-5 text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                    </svg>
                  )}
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                    {request.title}
                  </h3>
                  {request.message && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      {request.message}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* 表单 */}
            <form onSubmit={handleSubmit} className="p-6 space-y-4">
              {/* 验证码图片 */}
              {request.captchaImage && (
                <div className="flex flex-col items-center gap-3 p-4 bg-gray-50 dark:bg-gray-800 rounded-xl">
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    请输入下方验证码
                  </p>
                  <img
                    src={request.captchaImage}
                    alt="验证码"
                    className="max-w-full h-auto rounded-lg border border-gray-200 dark:border-gray-700"
                    style={{ maxHeight: "100px" }}
                  />
                </div>
              )}

              {/* 输入字段 */}
              {request.fields.map((field, index) => (
                <div key={field.name}>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">
                    {field.label}
                    {field.required && <span className="text-red-500 ml-1">*</span>}
                  </label>
                  <input
                    ref={index === 0 ? firstInputRef : undefined}
                    type={field.type === "password" ? "password" : "text"}
                    value={values[field.name] || ""}
                    onChange={(e) =>
                      setValues({ ...values, [field.name]: e.target.value })
                    }
                    placeholder={field.placeholder}
                    required={field.required}
                    autoComplete={field.type === "password" ? "current-password" : field.name === "username" ? "username" : "off"}
                    className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
                  />
                </div>
              ))}

              {/* 按钮 */}
              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={loading}
                  className="flex-1 px-4 py-3 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 font-medium hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-3 rounded-xl bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {loading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      提交中...
                    </>
                  ) : (
                    "确认提交"
                  )}
                </button>
              </div>
            </form>

            {/* 安全提示 */}
            <div className="px-6 py-3 bg-gray-50 dark:bg-gray-800/50 border-t border-gray-200 dark:border-gray-700">
              <p className="text-xs text-gray-500 dark:text-gray-400 text-center">
                🔒 您的信息仅用于当前操作，不会被保存
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

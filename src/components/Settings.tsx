/**
 * 设置页面组件：配置API密钥等设置
 * 
 * 遵循 docs/ARCHITECTURE.md 中的UI组件规范
 */

import React, { useState, useEffect } from "react";
import { AppConfig, AIProvider } from "../types";
import { getConfig, saveConfig } from "../utils/tauri";

interface SettingsProps {
  config: AppConfig | null;
  onConfigChange: () => void;
  onBack?: () => void;
}

/**
 * 设置页面组件
 */
export const Settings: React.FC<SettingsProps> = ({
  config,
  onConfigChange,
  onBack,
}) => {
  const [formData, setFormData] = useState<AppConfig>({
    provider: "claude",
    api_key: "",
    model: "claude-3-5-sonnet-20241022",
    sandbox_path: "",
    auto_confirm: false,
    log_level: "INFO",
  });
  
  // 各提供商的模型列表
  const providerModels: Record<AIProvider, string[]> = {
    claude: [
      "claude-3-5-sonnet-20241022",
      "claude-3-opus-20240229",
      "claude-3-sonnet-20240229",
      "claude-3-haiku-20240307",
    ],
    anthropic: [
      "claude-3-5-sonnet-20241022",
      "claude-3-opus-20240229",
      "claude-3-sonnet-20240229",
      "claude-3-haiku-20240307",
    ],
    openai: [
      "gpt-4-turbo-preview",
      "gpt-4",
      "gpt-3.5-turbo",
    ],
    deepseek: [
      "deepseek-chat",      // DeepSeek-V3，最强通用模型
      "deepseek-reasoner",  // DeepSeek-R1，推理专用
      "deepseek-coder",     // 代码专用模型
    ],
    grok: [
      "grok-beta",
    ],
  };
  
  // 当provider改变时，自动更新默认模型
  const handleProviderChange = (provider: AIProvider) => {
    const defaultModel = providerModels[provider][0];
    setFormData((prev) => ({
      ...prev,
      provider,
      model: defaultModel,
    }));
  };
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (config) {
      setFormData(config);
    }
  }, [config]);

  const handleSave = async () => {
    setSaving(true);
    setMessage(null);

    try {
      await saveConfig(formData);
      setMessage({ 
        type: "success", 
        text: "配置已保存" + (typeof window !== "undefined" && !("__TAURI_INTERNALS__" in window) ? "（已保存到浏览器本地存储）" : "")
      });
      onConfigChange();
    } catch (error) {
      setMessage({
        type: "error",
        text: `保存失败: ${error instanceof Error ? error.message : "未知错误"}`,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (
    field: keyof AppConfig,
    value: string | boolean
  ) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  return (
    <div className="h-full overflow-y-auto p-6 bg-white dark:bg-gray-900">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          {onBack && (
            <button
              onClick={onBack}
              className="flex items-center justify-center w-8 h-8 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-gray-600 dark:text-gray-400"
              title="返回"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
          )}
          <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
            设置
          </h2>
        </div>

        {/* 环境提示 */}
        {typeof window !== "undefined" && !("__TAURI_INTERNALS__" in window) && (
          <div className="mb-4 p-4 rounded-lg bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200">
            <p className="text-sm font-medium mb-1">⚠️ 浏览器模式</p>
            <p className="text-xs">
              当前在浏览器中运行，配置将保存到浏览器本地存储。
              要使用完整功能（执行任务），请使用 <code className="bg-yellow-200 dark:bg-yellow-800 px-1 rounded">npm run tauri:dev</code> 启动桌面应用。
            </p>
          </div>
        )}

        {message && (
          <div
            className={`mb-4 p-4 rounded-lg ${
              message.type === "success"
                ? "bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"
                : "bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200"
            }`}
          >
            {message.text}
          </div>
        )}

        <div className="space-y-6">
          {/* AI提供商选择 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              AI提供商 <span className="text-red-500">*</span>
            </label>
            <select
              value={formData.provider}
              onChange={(e) => handleProviderChange(e.target.value as AIProvider)}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="claude">Claude (Anthropic)</option>
              <option value="openai">ChatGPT (OpenAI)</option>
              <option value="deepseek">DeepSeek</option>
              <option value="grok">Grok (X.AI)</option>
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              选择要使用的AI模型提供商
            </p>
          </div>

          {/* API密钥 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {formData.provider === "claude" && "Claude"}
              {formData.provider === "openai" && "OpenAI"}
              {formData.provider === "deepseek" && "DeepSeek"}
              {formData.provider === "grok" && "Grok"}
              {" "}API密钥 <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={formData.api_key}
              onChange={(e) => handleChange("api_key", e.target.value)}
              placeholder="sk-ant-..."
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              获取API密钥：
              {formData.provider === "claude" && (
                <a
                  href="https://console.anthropic.com/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 dark:text-primary-400 hover:underline ml-1"
                >
                  Anthropic Console
                </a>
              )}
              {formData.provider === "openai" && (
                <a
                  href="https://platform.openai.com/api-keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 dark:text-primary-400 hover:underline ml-1"
                >
                  OpenAI Platform
                </a>
              )}
              {formData.provider === "deepseek" && (
                <a
                  href="https://platform.deepseek.com/api_keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 dark:text-primary-400 hover:underline ml-1"
                >
                  DeepSeek Platform
                </a>
              )}
              {formData.provider === "grok" && (
                <a
                  href="https://x.ai/api"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 dark:text-primary-400 hover:underline ml-1"
                >
                  X.AI API
                </a>
              )}
            </p>
          </div>

          {/* 模型选择 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              模型
            </label>
            <select
              value={formData.model}
              onChange={(e) => handleChange("model", e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {providerModels[formData.provider].map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              根据选择的提供商显示可用模型
            </p>
          </div>

          {/* 沙盒路径 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              沙盒目录
            </label>
            <input
              type="text"
              value={formData.sandbox_path}
              onChange={(e) => handleChange("sandbox_path", e.target.value)}
              placeholder="~/.deskjarvis/sandbox"
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              文件操作将限制在此目录内
            </p>
          </div>

          {/* 自动确认 */}
          <div className="flex items-center">
            <input
              type="checkbox"
              id="auto_confirm"
              checked={formData.auto_confirm}
              onChange={(e) => handleChange("auto_confirm", e.target.checked)}
              className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
            />
            <label
              htmlFor="auto_confirm"
              className="ml-2 text-sm text-gray-700 dark:text-gray-300"
            >
              自动确认操作（危险操作仍需确认）
            </label>
          </div>

          {/* 日志级别 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              日志级别
            </label>
            <select
              value={formData.log_level}
              onChange={(e) => handleChange("log_level", e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </select>
          </div>

          {/* 保存按钮 */}
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={saving || !formData.api_key}
              className="px-6 py-2 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "保存中..." : "保存配置"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

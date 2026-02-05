/**
 * Markdown 渲染组件
 * 
 * 功能：
 * - 渲染 Markdown 内容（标题、列表、代码块、表格等）
 * - 支持 GFM (GitHub Flavored Markdown)
 */

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Markdown 渲染器
 */
export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = "",
}) => {
  return (
    <div className={`markdown-content prose prose-sm dark:prose-invert max-w-none text-sm font-mono ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 段落
          p: ({ children }) => (
            <p className="m-0 mb-2 last:mb-0 leading-relaxed text-sm">{children}</p>
          ),
          
          // 标题
          h1: ({ children }) => (
            <h1 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-bold mt-3 mb-2 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold mt-2 mb-1 first:mt-0">{children}</h3>
          ),
          
          // 代码块
          code: ({ className: codeClassName, children, ...props }) => {
            const match = /language-(\w+)/.exec(codeClassName || '');
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
                <code className={`text-sm font-mono text-gray-100 ${codeClassName || ''}`} {...props}>
                  {children}
                </code>
              </pre>
            );
          },
          
          // 列表
          ul: ({ children }) => (
            <ul className="list-disc list-inside my-2 space-y-1 ml-2">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside my-2 space-y-1 ml-2">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="ml-2">{children}</li>
          ),
          
          // 表格
          table: ({ children }) => (
            <div className="overflow-x-auto my-2">
              <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-600">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-100 dark:bg-gray-800">{children}</thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => (
            <tr className="border-b border-gray-200 dark:border-gray-700">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-left font-semibold text-sm">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-sm">
              {children}
            </td>
          ),
          
          // 引用
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-blue-500 pl-4 my-2 italic text-gray-600 dark:text-gray-400">
              {children}
            </blockquote>
          ),
          
          // 链接
          a: ({ href, children }) => (
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
          strong: ({ children }) => (
            <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="italic">{children}</em>
          ),
          
          // 水平线
          hr: () => <hr className="my-4 border-gray-300 dark:border-gray-700" />,
          
          // 任务列表（GFM）
          input: ({ checked, ...props }) => (
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
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;

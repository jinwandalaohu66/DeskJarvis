/**
 * 统一日志工具
 * 
 * 生产环境自动禁用调试日志
 */

const isDev = import.meta.env.DEV;

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface Logger {
  debug: (...args: unknown[]) => void;
  info: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
}

/**
 * 创建模块专用的 logger
 * @param module 模块名称
 */
export function createLogger(module: string): Logger {
  const prefix = `[${module}]`;
  
  return {
    debug: (...args: unknown[]) => {
      if (isDev) {
        console.debug(prefix, ...args);
      }
    },
    info: (...args: unknown[]) => {
      if (isDev) {
        console.info(prefix, ...args);
      }
    },
    warn: (...args: unknown[]) => {
      console.warn(prefix, ...args);
    },
    error: (...args: unknown[]) => {
      console.error(prefix, ...args);
    },
  };
}

// 默认 logger
export const logger = createLogger('DeskJarvis');

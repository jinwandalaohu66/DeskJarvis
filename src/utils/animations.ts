/**
 * 统一的动画配置
 * 
 * 提供流畅、一致的动画体验
 */

import { Variants, Transition } from "framer-motion";

// ============================================
// 基础 Transition 配置
// ============================================

/** 快速动画 - 用于小元素、按钮反馈 */
export const transitionFast: Transition = {
  type: "spring",
  stiffness: 500,
  damping: 30,
  mass: 0.5,
};

/** 普通动画 - 用于卡片、面板 */
export const transitionNormal: Transition = {
  type: "spring",
  stiffness: 400,
  damping: 28,
  mass: 0.8,
};

/** 慢速动画 - 用于大型面板、页面切换 */
export const transitionSlow: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 30,
  mass: 1,
};

/** 平滑动画 - 用于进度条、数值变化 */
export const transitionSmooth: Transition = {
  type: "tween",
  duration: 0.4,
  ease: [0.16, 1, 0.3, 1], // ease-out-expo
};

/** 面板展开/折叠动画 */
export const transitionPanel: Transition = {
  type: "spring",
  stiffness: 350,
  damping: 35,
  mass: 0.8,
};

// ============================================
// 按钮动画
// ============================================

/** 按钮悬停效果 */
export const buttonHover = {
  scale: 1.02,
  transition: transitionFast,
};

/** 按钮点击效果 */
export const buttonTap = {
  scale: 0.96,
  transition: { type: "spring", stiffness: 600, damping: 20 },
};

// ============================================
// 消息动画 Variants
// ============================================

export const messageVariants: Variants = {
  hidden: {
    opacity: 0,
    y: 12,
    scale: 0.98,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: transitionNormal,
  },
  exit: {
    opacity: 0,
    scale: 0.98,
    transition: { duration: 0.15 },
  },
};

// ============================================
// Toast 动画 Variants
// ============================================

export const toastVariants: Variants = {
  hidden: {
    opacity: 0,
    y: -20,
    scale: 0.95,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: transitionFast,
  },
  exit: {
    opacity: 0,
    y: -10,
    scale: 0.95,
    transition: { duration: 0.15 },
  },
};

// ============================================
// 卡片动画 Variants
// ============================================

export const cardVariants: Variants = {
  hidden: {
    opacity: 0,
    y: 10,
    scale: 0.96,
  },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      ...transitionNormal,
      delay: i * 0.04, // 级联延迟
    },
  }),
  exit: {
    opacity: 0,
    scale: 0.96,
    transition: { duration: 0.12 },
  },
};

// ============================================
// 侧边栏/面板动画 Variants
// ============================================

export const panelVariants: Variants = {
  collapsed: (width: number) => ({
    width,
    transition: transitionPanel,
  }),
  expanded: (width: number) => ({
    width,
    transition: transitionPanel,
  }),
};

// ============================================
// 淡入淡出动画 Variants
// ============================================

export const fadeVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.2 },
  },
  exit: {
    opacity: 0,
    transition: { duration: 0.15 },
  },
};

// ============================================
// 滑入动画 Variants
// ============================================

export const slideInVariants: Variants = {
  hidden: { opacity: 0, x: -10 },
  visible: {
    opacity: 1,
    x: 0,
    transition: transitionNormal,
  },
  exit: {
    opacity: 0,
    x: -5,
    transition: { duration: 0.12 },
  },
};

// ============================================
// 思考块动画 Variants
// ============================================

export const thinkingVariants: Variants = {
  hidden: {
    opacity: 0,
    y: -8,
    scale: 0.98,
  },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: transitionNormal,
  },
};

// ============================================
// 进度条动画
// ============================================

export const progressTransition: Transition = {
  type: "spring",
  stiffness: 100,
  damping: 20,
  mass: 0.5,
};

// ============================================
// 脉冲动画（用于"执行中..."等提示）
// ============================================

export const pulseAnimation = {
  opacity: [1, 0.5, 1],
  transition: {
    duration: 1.2,
    repeat: Infinity,
    ease: "easeInOut",
  },
};

// ============================================
// 图片预览动画 Variants
// ============================================

export const imagePreviewVariants: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.9,
  },
  visible: {
    opacity: 1,
    scale: 1,
    transition: transitionNormal,
  },
};

// ============================================
// 删除按钮动画 Variants
// ============================================

export const deleteButtonVariants: Variants = {
  hidden: {
    opacity: 0,
    scale: 0.8,
  },
  visible: {
    opacity: 1,
    scale: 1,
    transition: transitionFast,
  },
};

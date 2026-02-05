"""
层3：高级记忆

功能：
- 情绪分析与感知
- 工作流自动发现
- 主动确认学习
- 用户画像构建
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)


class EmotionAnalyzer:
    """情绪分析器"""
    
    # 中文情绪关键词
    EMOTION_KEYWORDS = {
        "happy": ["开心", "高兴", "太好了", "棒", "完美", "感谢", "谢谢", "不错", "很好", "赞"],
        "frustrated": ["烦", "烦死了", "崩溃", "气死", "怎么回事", "又", "不行", "失败", "错误"],
        "anxious": ["着急", "紧急", "急", "快点", "赶紧", "马上", "立刻", "焦虑", "担心"],
        "tired": ["累", "疲惫", "困", "心情不好", "心情烂透了", "不想动", "无聊"],
        "neutral": []
    }
    
    # 情绪响应建议
    EMOTION_RESPONSES = {
        "happy": "用户心情不错，可以适当活泼一些。",
        "frustrated": "用户可能遇到困难，保持耐心，简洁高效地帮助。",
        "anxious": "用户比较着急，优先快速响应，减少不必要的解释。",
        "tired": "用户可能疲惫，保持温和，不要给太多选择。",
        "neutral": "用户情绪正常，正常响应即可。"
    }
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        分析文本情绪
        
        Args:
            text: 用户输入文本
        
        Returns:
            {
                "emotion": "happy/frustrated/anxious/tired/neutral",
                "confidence": 0.0-1.0,
                "keywords_found": [...],
                "suggestion": "..."
            }
        """
        text_lower = text.lower()
        
        emotion_scores = {}
        keywords_found = {}
        
        for emotion, keywords in self.EMOTION_KEYWORDS.items():
            found = []
            for kw in keywords:
                if kw in text:
                    found.append(kw)
            if found:
                emotion_scores[emotion] = len(found)
                keywords_found[emotion] = found
        
        if not emotion_scores:
            return {
                "emotion": "neutral",
                "confidence": 0.5,
                "keywords_found": [],
                "suggestion": self.EMOTION_RESPONSES["neutral"]
            }
        
        # 选择得分最高的情绪
        top_emotion = max(emotion_scores, key=emotion_scores.get)
        max_score = emotion_scores[top_emotion]
        confidence = min(0.5 + max_score * 0.15, 1.0)
        
        return {
            "emotion": top_emotion,
            "confidence": confidence,
            "keywords_found": keywords_found.get(top_emotion, []),
            "suggestion": self.EMOTION_RESPONSES.get(top_emotion, "")
        }
    
    def get_emotion_pattern(self, emotions_history: List[Dict]) -> Dict[str, Any]:
        """
        分析情绪模式
        
        Args:
            emotions_history: 历史情绪记录列表
        
        Returns:
            情绪模式分析结果
        """
        if not emotions_history:
            return {"pattern": "unknown", "dominant_emotion": "neutral"}
        
        # 统计情绪分布
        emotion_counts = Counter(e.get("emotion", "neutral") for e in emotions_history)
        
        # 分析时间模式
        time_emotions = defaultdict(list)
        for e in emotions_history:
            timestamp = e.get("timestamp", "")
            if timestamp:
                try:
                    hour = datetime.fromisoformat(timestamp).hour
                    time_emotions[hour].append(e.get("emotion", "neutral"))
                except:
                    pass
        
        # 找出高峰时段
        peak_times = {}
        for hour, emotions in time_emotions.items():
            dominant = Counter(emotions).most_common(1)
            if dominant:
                peak_times[hour] = dominant[0][0]
        
        return {
            "emotion_distribution": dict(emotion_counts),
            "dominant_emotion": emotion_counts.most_common(1)[0][0] if emotion_counts else "neutral",
            "peak_times": peak_times,
            "total_records": len(emotions_history)
        }


class WorkflowDiscovery:
    """工作流自动发现"""
    
    def __init__(self, min_occurrences: int = 3, similarity_threshold: float = 0.6):
        """
        初始化工作流发现器
        
        Args:
            min_occurrences: 最小出现次数（达到此次数才被识别为工作流）
            similarity_threshold: 相似度阈值
        """
        self.min_occurrences = min_occurrences
        self.similarity_threshold = similarity_threshold
    
    def _normalize_instruction(self, instruction: str) -> str:
        """标准化指令"""
        # 移除数字、路径、文件名等变化部分
        normalized = re.sub(r'\d+', '#NUM#', instruction)
        normalized = re.sub(r'["\'].*?["\']', '#STR#', normalized)
        normalized = re.sub(r'/[\w\./]+', '#PATH#', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
        return normalized
    
    def _extract_action_sequence(self, steps: List[Dict]) -> List[str]:
        """从步骤中提取动作序列"""
        actions = []
        for step in steps:
            step_type = step.get("type", "unknown")
            actions.append(step_type)
        return actions
    
    def find_patterns(self, instruction_history: List[Dict]) -> List[Dict]:
        """
        发现指令模式
        
        Args:
            instruction_history: 指令历史列表
                [{instruction, steps, success, timestamp}, ...]
        
        Returns:
            发现的模式列表
        """
        if not instruction_history:
            return []
        
        # 按标准化指令分组
        normalized_groups = defaultdict(list)
        for record in instruction_history:
            instruction = record.get("instruction", "")
            normalized = self._normalize_instruction(instruction)
            normalized_groups[normalized].append(record)
        
        # 找出重复的模式
        patterns = []
        for normalized, records in normalized_groups.items():
            if len(records) >= self.min_occurrences:
                # 提取共同的动作序列
                action_sequences = []
                for r in records:
                    steps = r.get("steps", [])
                    if isinstance(steps, str):
                        try:
                            steps = json.loads(steps)
                        except:
                            steps = []
                    action_sequences.append(self._extract_action_sequence(steps))
                
                # 找最常见的动作序列
                if action_sequences:
                    seq_counter = Counter(tuple(seq) for seq in action_sequences)
                    most_common_seq = seq_counter.most_common(1)[0][0]
                    
                    # 成功率
                    success_count = sum(1 for r in records if r.get("success", True))
                    success_rate = success_count / len(records)
                    
                    patterns.append({
                        "pattern_name": self._generate_pattern_name(records[0].get("instruction", "")),
                        "normalized": normalized,
                        "action_sequence": list(most_common_seq),
                        "occurrences": len(records),
                        "success_rate": success_rate,
                        "example_instructions": [r.get("instruction", "")[:100] for r in records[:3]],
                        "suggested_workflow": self._create_workflow_template(records[0])
                    })
        
        # 按出现次数排序
        patterns.sort(key=lambda x: x["occurrences"], reverse=True)
        return patterns
    
    def _generate_pattern_name(self, instruction: str) -> str:
        """生成模式名称"""
        # 提取关键动作词
        action_words = ["下载", "整理", "删除", "重命名", "移动", "复制", "总结", 
                       "搜索", "打开", "关闭", "压缩", "解压", "转换", "处理"]
        
        found_actions = [w for w in action_words if w in instruction]
        
        if found_actions:
            return "+".join(found_actions[:3]) + "工作流"
        return "自定义工作流"
    
    def _create_workflow_template(self, record: Dict) -> Dict:
        """创建工作流模板"""
        steps = record.get("steps", [])
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except:
                steps = []
        
        return {
            "name": self._generate_pattern_name(record.get("instruction", "")),
            "description": record.get("instruction", "")[:200],
            "steps": steps,
            "created_from": "auto_discovery"
        }
    
    def suggest_workflow(
        self, 
        current_instruction: str, 
        patterns: List[Dict]
    ) -> Optional[Dict]:
        """
        根据当前指令建议工作流
        
        Returns:
            匹配的工作流建议，如果没有匹配则返回 None
        """
        normalized = self._normalize_instruction(current_instruction)
        
        for pattern in patterns:
            if pattern["normalized"] == normalized:
                return {
                    "pattern": pattern,
                    "message": f"发现你经常执行「{pattern['pattern_name']}」"
                              f"（已执行{pattern['occurrences']}次，成功率{pattern['success_rate']*100:.0f}%），"
                              f"是否保存为快捷命令？"
                }
        
        return None


class ProactiveLearner:
    """主动确认学习"""
    
    def __init__(self, confirmation_threshold: int = 3):
        """
        初始化主动学习器
        
        Args:
            confirmation_threshold: 需要确认的阈值（同一偏好出现次数）
        """
        self.confirmation_threshold = confirmation_threshold
        self.pending_confirmations = []  # 待确认的偏好
    
    def analyze_behavior(self, actions_history: List[Dict]) -> List[Dict]:
        """
        分析用户行为，发现可能的偏好
        
        Args:
            actions_history: 动作历史
        
        Returns:
            可能的偏好列表（需要向用户确认）
        """
        potential_preferences = []
        
        # 分析文件命名模式
        naming_patterns = self._analyze_naming_patterns(actions_history)
        potential_preferences.extend(naming_patterns)
        
        # 分析目录使用模式
        directory_patterns = self._analyze_directory_patterns(actions_history)
        potential_preferences.extend(directory_patterns)
        
        # 分析时间模式
        time_patterns = self._analyze_time_patterns(actions_history)
        potential_preferences.extend(time_patterns)
        
        # 过滤需要确认的
        confirmable = [p for p in potential_preferences 
                      if p["occurrences"] >= self.confirmation_threshold 
                      and not p.get("confirmed", False)]
        
        return confirmable
    
    def _analyze_naming_patterns(self, actions_history: List[Dict]) -> List[Dict]:
        """分析命名模式"""
        patterns = []
        naming_styles = defaultdict(int)
        
        for action in actions_history:
            step_type = action.get("type", "")
            if step_type in ["file_rename", "file_create", "file_save"]:
                name = action.get("params", {}).get("new_name", "") or action.get("params", {}).get("path", "")
                
                # 检测命名风格
                if re.search(r'\d{4}-\d{2}-\d{2}', name):
                    naming_styles["date_prefix"] += 1
                elif re.search(r'^\d+_', name):
                    naming_styles["number_prefix"] += 1
                elif re.search(r'_v\d+', name):
                    naming_styles["version_suffix"] += 1
        
        for style, count in naming_styles.items():
            if count >= self.confirmation_threshold:
                style_names = {
                    "date_prefix": "日期前缀命名（如 2024-01-01_文件）",
                    "number_prefix": "数字前缀命名（如 01_文件）",
                    "version_suffix": "版本后缀命名（如 文件_v1）"
                }
                patterns.append({
                    "type": "naming_style",
                    "value": style,
                    "description": style_names.get(style, style),
                    "occurrences": count,
                    "question": f"我注意到你最近 {count} 次使用「{style_names.get(style, style)}」，"
                               f"以后默认使用这种命名方式吗？"
                })
        
        return patterns
    
    def _analyze_directory_patterns(self, actions_history: List[Dict]) -> List[Dict]:
        """分析目录使用模式"""
        patterns = []
        directory_usage = defaultdict(int)
        
        for action in actions_history:
            path = action.get("params", {}).get("path", "")
            if path:
                # 提取目录
                import os
                directory = os.path.dirname(path)
                if directory:
                    directory_usage[directory] += 1
        
        for directory, count in directory_usage.items():
            if count >= self.confirmation_threshold * 2:  # 目录需要更高频率
                patterns.append({
                    "type": "preferred_directory",
                    "value": directory,
                    "description": f"常用目录: {directory}",
                    "occurrences": count,
                    "question": f"你经常使用「{directory}」目录，设为默认工作目录吗？"
                })
        
        return patterns
    
    def _analyze_time_patterns(self, actions_history: List[Dict]) -> List[Dict]:
        """分析时间模式"""
        patterns = []
        hour_counts = defaultdict(int)
        
        for action in actions_history:
            timestamp = action.get("timestamp", "")
            if timestamp:
                try:
                    hour = datetime.fromisoformat(timestamp).hour
                    hour_counts[hour] += 1
                except:
                    pass
        
        # 找高峰时段
        if hour_counts:
            peak_hour = max(hour_counts, key=hour_counts.get)
            peak_count = hour_counts[peak_hour]
            total = sum(hour_counts.values())
            
            if peak_count / total > 0.3:  # 某时段占比超过 30%
                patterns.append({
                    "type": "active_hours",
                    "value": peak_hour,
                    "description": f"活跃时段: {peak_hour}:00-{peak_hour+1}:00",
                    "occurrences": peak_count,
                    "question": f"你通常在 {peak_hour}:00 左右使用，需要在这个时间提醒你待办任务吗？"
                })
        
        return patterns
    
    def create_confirmation_request(self, preference: Dict) -> Dict:
        """创建确认请求"""
        return {
            "id": f"confirm_{preference['type']}_{hash(preference['value'])}",
            "type": "preference_confirmation",
            "preference": preference,
            "question": preference.get("question", "是否确认这个偏好？"),
            "options": ["是", "否", "以后不再询问"],
            "timestamp": datetime.now().isoformat()
        }


class AdvancedMemory:
    """高级记忆 - 整合情绪分析、工作流发现、主动学习"""
    
    def __init__(self):
        """初始化高级记忆"""
        self.emotion_analyzer = EmotionAnalyzer()
        self.workflow_discovery = WorkflowDiscovery()
        self.proactive_learner = ProactiveLearner()
        
        self.emotions_history: List[Dict] = []
        self.actions_history: List[Dict] = []
        self.discovered_patterns: List[Dict] = []
        
        logger.info("高级记忆已初始化")
    
    def analyze_emotion(self, text: str) -> Dict[str, Any]:
        """分析用户情绪"""
        result = self.emotion_analyzer.analyze(text)
        
        # 记录到历史
        self.emotions_history.append({
            **result,
            "timestamp": datetime.now().isoformat(),
            "text_preview": text[:100]
        })
        
        # 只保留最近 100 条
        if len(self.emotions_history) > 100:
            self.emotions_history = self.emotions_history[-100:]
        
        return result
    
    def record_action(self, action: Dict):
        """记录用户动作"""
        action["timestamp"] = datetime.now().isoformat()
        self.actions_history.append(action)
        
        # 只保留最近 500 条
        if len(self.actions_history) > 500:
            self.actions_history = self.actions_history[-500:]
    
    def discover_workflows(self, instruction_history: List[Dict]) -> List[Dict]:
        """发现工作流模式"""
        self.discovered_patterns = self.workflow_discovery.find_patterns(instruction_history)
        return self.discovered_patterns
    
    def get_workflow_suggestion(self, instruction: str) -> Optional[Dict]:
        """获取工作流建议"""
        if not self.discovered_patterns:
            return None
        return self.workflow_discovery.suggest_workflow(instruction, self.discovered_patterns)
    
    def get_pending_confirmations(self) -> List[Dict]:
        """获取待确认的偏好"""
        potential = self.proactive_learner.analyze_behavior(self.actions_history)
        return [self.proactive_learner.create_confirmation_request(p) for p in potential]
    
    def get_emotion_pattern(self) -> Dict:
        """获取情绪模式"""
        return self.emotion_analyzer.get_emotion_pattern(self.emotions_history)
    
    def get_memory_context(self) -> str:
        """获取高级记忆上下文"""
        context_parts = []
        
        # 当前情绪状态
        if self.emotions_history:
            latest = self.emotions_history[-1]
            emotion = latest.get("emotion", "neutral")
            suggestion = latest.get("suggestion", "")
            if emotion != "neutral":
                context_parts.append(f"**用户情绪**：{emotion}。{suggestion}")
        
        # 发现的工作流
        if self.discovered_patterns:
            pattern_items = [f"- {p['pattern_name']} (执行{p['occurrences']}次)" 
                          for p in self.discovered_patterns[:3]]
            context_parts.append("**常用工作流**：\n" + "\n".join(pattern_items))
        
        return "\n\n".join(context_parts) if context_parts else ""
    
    def export_state(self) -> Dict:
        """导出状态（用于持久化）"""
        return {
            "emotions_history": self.emotions_history[-50:],  # 只保留最近 50 条
            "actions_history": self.actions_history[-100:],
            "discovered_patterns": self.discovered_patterns
        }
    
    def import_state(self, state: Dict):
        """导入状态"""
        self.emotions_history = state.get("emotions_history", [])
        self.actions_history = state.get("actions_history", [])
        self.discovered_patterns = state.get("discovered_patterns", [])

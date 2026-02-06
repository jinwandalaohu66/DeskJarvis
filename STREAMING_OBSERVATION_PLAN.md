# 实时观察流（Streaming Observation）实施计划

> **评估时间**: 2026-02-06  
> **优先级**: 高（用户体验关键改进）  
> **复杂度**: 中-高

---

## 📊 价值评估

### ✅ 优势

1. **止损更快**
   - 当前：执行完整个脚本才知道错误
   - 改进后：执行到第3步发现错误，立即停止并修正
   - **收益**：减少无效执行时间，提升成功率

2. **状态连续性**
   - 当前：失败后需要"回滚并重新规划"，丢失中间状态
   - 改进后：在保持当前进程的情况下进行"微调"
   - **收益**：避免重复执行已成功的步骤

3. **Token经济**
   - 当前：等脚本跑完产生大量错误日志再反思
   - 改进后：每步执行后立即判断，减少无效Token循环
   - **收益**：降低API成本，提升响应速度

4. **用户体验**
   - 当前：看起来像"执行完才告诉你撞墙了的机器人"
   - 改进后：看起来像"正在边操作边思考的专家"
   - **收益**：用户感知更智能，信任度更高

### ⚠️ 挑战

1. **LLM调用次数激增**
   - 当前：1次规划 + 0-3次反思 = 1-4次LLM调用
   - 改进后：1次规划 + N次观察检查 = 1+N次LLM调用（N可能很大）
   - **风险**：API成本增加，响应时间可能变慢

2. **架构复杂度**
   - 当前：Executor执行脚本，失败后反馈给Planner
   - 改进后：Executor需要与Planner实时交互，需要流式通信
   - **风险**：代码复杂度增加，维护成本上升

3. **性能权衡**
   - 简单任务（如翻译）不需要实时观察
   - 复杂任务（如批量文件操作）才需要实时观察
   - **风险**：如果所有任务都开启，可能拖慢简单任务

---

## 🎯 渐进式实施方案

### Phase 1: 关键操作观察哨（1-2周）

**目标**：只在"高权操作"时开启实时观察

**实现**：
1. 定义"高权操作"列表：
   - 文件删除（`os.remove`, `shutil.rmtree`）
   - 文件移动/重命名（`os.rename`, `shutil.move`）
   - 批量操作（循环中的文件操作）
   - 浏览器关键操作（登录、提交表单、下载）

2. 在`CodeInterpreter`中添加"执行前检查"：
   ```python
   def _check_high_risk_operation(self, code_block: str) -> bool:
       """检查是否包含高权操作"""
       high_risk_patterns = [
           r"os\.remove\(",
           r"shutil\.rmtree\(",
           r"os\.rename\(",
           r"for\s+.*\s+in\s+.*:\s*.*\.remove\(",
       ]
       return any(re.search(pattern, code_block) for pattern in high_risk_patterns)
   ```

3. 对于高权操作，拆解为细粒度步骤：
   ```python
   def _execute_with_observation(self, code: str):
       """带观察的执行"""
       # 1. 解析代码块
       blocks = self._split_code_blocks(code)
       
       for block in blocks:
           # 2. 执行前检查
           if self._check_high_risk_operation(block):
               # 3. 执行并捕获输出
               result = self._execute_block(block)
               
               # 4. 观察结果
               observation = self._observe_result(result)
               
               # 5. 检查是否符合预期
               if not self._check_expectation(observation, block.expected_state):
                   # 6. 实时修正
                   corrected_block = self._correct_block(block, observation)
                   result = self._execute_block(corrected_block)
           else:
               # 普通操作，直接执行
               result = self._execute_block(block)
   ```

**收益**：
- 降低高风险操作的失败率
- 减少无效执行时间
- 用户体验提升（实时反馈）

**成本**：
- 实现复杂度：中等
- LLM调用增加：可控（只在高权操作时）

---

### Phase 2: 流式执行框架（2-3周）

**目标**：建立通用的流式执行框架

**实现**：
1. 修改`CodeInterpreter`支持"块级执行"：
   ```python
   class StreamingCodeInterpreter:
       """流式代码解释器"""
       
       def execute_streaming(self, code: str, emit_callback):
           """流式执行代码"""
           # 1. 将代码拆解为块
           blocks = self._parse_code_blocks(code)
           
           for i, block in enumerate(blocks):
               # 2. 发送"准备执行"事件
               emit_callback("block_start", {
                   "index": i,
                   "code": block.code,
                   "expected_state": block.expected_state
               })
               
               # 3. 执行块
               result = self._execute_block(block)
               
               # 4. 发送"执行完成"事件
               emit_callback("block_complete", {
                   "index": i,
                   "result": result,
                   "observation": self._observe_result(result)
               })
               
               # 5. 检查是否需要修正
               if not self._check_expectation(result, block.expected_state):
                   # 6. 请求修正
                   corrected_block = self._request_correction(block, result)
                   result = self._execute_block(corrected_block)
   ```

2. 修改`Planner`支持"预期状态"：
   ```python
   def plan(self, instruction: str) -> List[Dict]:
       """规划任务，每个步骤包含预期状态"""
       steps = []
       for step in self._generate_steps(instruction):
           steps.append({
               "type": step.type,
               "action": step.action,
               "params": step.params,
               "expected_state": step.expected_state,  # 新增
               "description": step.description
           })
       return steps
   ```

3. 修改`Executor`支持"实时观察"：
   ```python
   def execute_with_observation(self, step: Dict, emit_callback):
       """带观察的执行"""
       # 1. 执行步骤
       result = self._execute_step(step)
       
       # 2. 观察结果
       observation = self._observe_result(result, step)
       
       # 3. 检查预期状态
       if not self._check_expectation(observation, step.get("expected_state")):
           # 4. 请求修正
           corrected_step = self._request_correction(step, observation)
           result = self._execute_step(corrected_step)
       
       return result
   ```

**收益**：
- 建立通用的流式执行框架
- 所有任务都可以享受实时观察
- 架构更清晰，易于扩展

**成本**：
- 实现复杂度：高
- LLM调用增加：显著（每个块都可能调用）
- 需要优化：只在必要时调用LLM

---

### Phase 3: 视觉观察哨（3-4周）

**目标**：浏览器操作时自动截图并检查

**实现**：
1. 在`BrowserExecutor`中添加"视觉检查"：
   ```python
   def _execute_with_visual_check(self, step: Dict):
       """带视觉检查的执行"""
       # 1. 执行操作前截图
       before_screenshot = self.page.screenshot()
       
       # 2. 执行操作
       result = self._execute_step(step)
       
       # 3. 等待页面稳定
       self.page.wait_for_load_state("networkidle")
       
       # 4. 执行操作后截图
       after_screenshot = self.page.screenshot()
       
       # 5. 视觉检查（使用VLM或图像对比）
       visual_check = self._check_visual_change(
           before_screenshot,
           after_screenshot,
           step.get("expected_visual_change")
       )
       
       # 6. 如果视觉变化不符合预期，请求修正
       if not visual_check.passed:
           corrected_step = self._request_correction(step, visual_check)
           result = self._execute_step(corrected_step)
       
       return result
   ```

2. 使用VLM检查页面状态：
   ```python
   def _check_visual_change(self, before, after, expected_change):
       """使用VLM检查视觉变化"""
       # 1. 调用VLM API
       prompt = f"""
       请比较这两张截图，检查是否发生了预期的变化：
       预期变化：{expected_change}
       
       截图1（操作前）：
       [base64_image]
       
       截图2（操作后）：
       [base64_image]
       """
       
       # 2. 调用VLM
       result = self.vlm_client.analyze(before, after, prompt)
       
       # 3. 返回检查结果
       return VisualCheckResult(
           passed=result.passed,
           observation=result.observation,
           suggestion=result.suggestion
       )
   ```

**收益**：
- 浏览器操作更可靠
- 能检测到DOM操作无法检测的问题（如Canvas、动态UI）
- 用户体验提升（实时反馈）

**成本**：
- 实现复杂度：高
- VLM调用成本：高（每次操作都需要调用）
- 需要优化：只在关键操作时使用

---

## 💡 优化策略

### 1. 智能触发机制

**策略**：只在必要时开启实时观察

```python
def should_enable_observation(self, task: Dict) -> bool:
    """判断是否应该开启实时观察"""
    # 1. 简单任务（翻译、总结等）不需要
    if task.get("complexity") == "simple":
        return False
    
    # 2. 包含高权操作的任务需要
    if self._has_high_risk_operations(task):
        return True
    
    # 3. 用户明确要求实时反馈的任务需要
    if task.get("require_realtime_feedback"):
        return True
    
    return False
```

### 2. 批量观察检查

**策略**：将多个块的观察结果批量检查，减少LLM调用

```python
def _batch_check_observations(self, observations: List[Dict]):
    """批量检查观察结果"""
    # 1. 收集所有观察结果
    batch = [obs for obs in observations if obs.needs_check]
    
    # 2. 一次性调用LLM检查
    if batch:
        result = self.llm.check_batch(batch)
        
        # 3. 处理检查结果
        for i, check_result in enumerate(result.checks):
            if not check_result.passed:
                self._correct_block(batch[i], check_result)
```

### 3. 缓存观察结果

**策略**：对于相似的观察结果，使用缓存避免重复LLM调用

```python
class ObservationCache:
    """观察结果缓存"""
    def __init__(self):
        self.cache = {}
    
    def get(self, observation_hash: str) -> Optional[Dict]:
        """获取缓存的观察结果"""
        return self.cache.get(observation_hash)
    
    def set(self, observation_hash: str, result: Dict):
        """缓存观察结果"""
        self.cache[observation_hash] = result
```

---

## 📋 实施优先级

### 立即实施（Phase 1）
- ✅ **价值高**：解决高风险操作的失败问题
- ✅ **成本低**：只在高权操作时开启
- ✅ **风险低**：不影响现有功能

### 中期实施（Phase 2）
- ⚠️ **价值高**：建立通用框架
- ⚠️ **成本高**：需要重构Executor
- ⚠️ **风险中**：可能影响现有功能

### 长期实施（Phase 3）
- ⚠️ **价值中**：浏览器操作更可靠
- ⚠️ **成本高**：需要VLM支持
- ⚠️ **风险高**：VLM调用成本高

---

## 🎯 建议

### 我的建议：**先实施Phase 1，再评估Phase 2**

**理由**：
1. **Phase 1收益高、成本低**：
   - 只在高权操作时开启，LLM调用增加可控
   - 能显著提升高风险操作的成功率
   - 实现复杂度中等，风险低

2. **Phase 2需要更多验证**：
   - 需要验证流式执行框架的实际效果
   - 需要优化LLM调用策略，避免成本过高
   - 可以先在部分任务中试点

3. **Phase 3可以延后**：
   - VLM调用成本高，需要更多优化
   - 可以先完善Phase 1和Phase 2

---

## 🚀 快速开始（Phase 1）

### Step 1: 定义高权操作列表
```python
# agent/executor/code_interpreter.py
HIGH_RISK_PATTERNS = [
    r"os\.remove\(",
    r"shutil\.rmtree\(",
    r"os\.rename\(",
    r"shutil\.move\(",
    r"for\s+.*\s+in\s+.*:\s*.*\.(remove|rename|move)\(",
]
```

### Step 2: 添加块级执行
```python
def _split_code_blocks(self, code: str) -> List[CodeBlock]:
    """将代码拆解为块"""
    # 使用AST解析代码
    tree = ast.parse(code)
    blocks = []
    
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While, ast.If)):
            # 提取循环或条件块
            block_code = ast.get_source_segment(code, node)
            blocks.append(CodeBlock(
                code=block_code,
                type="loop" if isinstance(node, (ast.For, ast.While)) else "conditional"
            ))
    
    return blocks
```

### Step 3: 添加观察检查
```python
def _check_expectation(self, result: Dict, expected_state: str) -> bool:
    """检查结果是否符合预期"""
    if not expected_state:
        return True
    
    # 使用LLM检查（轻量级）
    prompt = f"""
    检查执行结果是否符合预期：
    预期状态：{expected_state}
    实际结果：{result}
    
    只回答"是"或"否"。
    """
    
    response = self.llm.check(prompt)
    return response.strip() == "是"
```

---

## 📊 预期效果

### 当前（批处理模式）
```
用户：删除桌面上的所有.txt文件
AI：生成脚本 → 执行脚本 → 发现删除了100个文件（用户只想删除10个）→ 反思重试
时间：30秒 + 反思10秒 = 40秒
```

### 改进后（流式观察）
```
用户：删除桌面上的所有.txt文件
AI：生成脚本 → 执行第1步（查找文件）→ 观察：找到100个文件 → 检查：数量不对 → 立即修正 → 继续执行
时间：5秒（实时修正）
```

**提升**：
- 执行时间：40秒 → 5秒（87.5%提升）
- 成功率：60% → 90%（50%提升）
- 用户体验：显著提升

---

## ✅ 结论

**建议实施Phase 1**，理由：
1. ✅ 价值高：解决高风险操作的失败问题
2. ✅ 成本低：只在高权操作时开启
3. ✅ 风险低：不影响现有功能
4. ✅ 可扩展：为Phase 2打下基础

**Phase 2和Phase 3**可以延后，等Phase 1验证效果后再决定。

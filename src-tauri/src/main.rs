// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Stdio};
use std::path::PathBuf;
use std::io::{BufRead, BufReader};
use serde::{Deserialize, Serialize};
use tauri::{Window, Emitter};

/// 任务执行结果
#[derive(Debug, Serialize, Deserialize)]
struct TaskResult {
    success: bool,
    message: String,
    steps: Vec<StepResult>,
    user_instruction: String,
}

/// 步骤结果
#[derive(Debug, Serialize, Deserialize)]
struct StepResult {
    step: serde_json::Value,
    result: Option<serde_json::Value>,
}

/// 应用配置
#[derive(Debug, Serialize, Deserialize)]
struct AppConfig {
    provider: String,
    api_key: String,
    model: String,
    sandbox_path: String,
    auto_confirm: bool,
    log_level: String,
}

/// 进度事件
#[derive(Debug, Serialize, Deserialize, Clone)]
struct ProgressEvent {
    #[serde(rename = "type")]
    event_type: String,
    timestamp: f64,
    data: serde_json::Value,
}

/// 执行用户指令（支持实时进度更新和上下文传递）
#[tauri::command]
async fn execute_task(window: Window, instruction: String, context: Option<serde_json::Value>) -> Result<TaskResult, String> {
    let python_path = get_python_path()?;
    let agent_path = get_agent_path()?;
    
    // 构建Python命令参数
    let mut cmd_args = vec![agent_path, "--json".to_string(), instruction];
    
    // 如果有上下文，作为JSON字符串传递
    if let Some(ctx) = context {
        if let Ok(ctx_str) = serde_json::to_string(&ctx) {
            cmd_args.push("--context".to_string());
            cmd_args.push(ctx_str);
        }
    }
    
    // 启动Python进程，捕获stdout
    let mut child = Command::new(python_path)
        .args(&cmd_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("执行Python命令失败: {}", e))?;
    
    // 读取stdout（实时）
    let stdout = child.stdout.take()
        .ok_or("无法获取stdout")?;
    let stderr = child.stderr.take()
        .ok_or("无法获取stderr")?;
    
    let reader = BufReader::new(stdout);
    let mut final_result: Option<TaskResult> = None;
    let mut stdout_lines = Vec::new();
    
    // 实时读取每一行
    for line in reader.lines() {
        let line = line.map_err(|e| format!("读取stdout失败: {}", e))?;
        stdout_lines.push(line.clone());
        
        // 尝试解析为进度事件
        if let Ok(event) = serde_json::from_str::<ProgressEvent>(&line) {
            // 发送进度事件到前端
            window.emit("task-progress", &event)
                .map_err(|e| format!("发送进度事件失败: {}", e))?;
        }
        
        // 尝试直接解析为TaskResult（最后一行通常是最终结果）
        if let Ok(result) = serde_json::from_str::<TaskResult>(&line) {
            final_result = Some(result);
        }
    }
    
    // 读取stderr（用于错误日志）
    let stderr_reader = BufReader::new(stderr);
    let mut stderr_lines = Vec::new();
    for line in stderr_reader.lines() {
        if let Ok(line) = line {
            stderr_lines.push(line);
        }
    }
    
    // 等待进程结束
    let _status = child.wait()
        .map_err(|e| format!("等待进程结束失败: {}", e))?;
    
    // 如果stderr有内容，记录日志
    if !stderr_lines.is_empty() {
        eprintln!("Python stderr: {}", stderr_lines.join("\n"));
    }
    
    // 返回最终结果
    if let Some(result) = final_result {
        Ok(result)
    } else {
        // 如果没有从进度事件中获取结果，尝试从最后一行解析
        let stdout_content = stdout_lines.join("\n");
        let json_str = extract_json_from_output(&stdout_content)?;
        let result: TaskResult = serde_json::from_str(&json_str)
            .map_err(|e| format!("解析JSON失败: {}。原始输出: {}", e, stdout_content))?;
        Ok(result)
    }
}

/// 从输出中提取JSON
fn extract_json_from_output(output: &str) -> Result<String, String> {
    // 尝试找到JSON对象（以{开头，以}结尾）
    let start = output.find('{');
    let end = output.rfind('}');
    
    if let (Some(start_idx), Some(end_idx)) = (start, end) {
        if end_idx > start_idx {
            return Ok(output[start_idx..=end_idx].to_string());
        }
    }
    
    Err(format!("未找到有效的JSON输出。输出内容: {}", output))
}

/// 获取配置
#[tauri::command]
async fn get_config() -> Result<AppConfig, String> {
    let config_path = get_config_path()?;
    
    if !config_path.exists() {
        // 返回默认配置
        return Ok(AppConfig {
            provider: "claude".to_string(),
            api_key: "".to_string(),
            model: "claude-3-5-sonnet-20241022".to_string(),
            sandbox_path: get_default_sandbox_path(),
            auto_confirm: false,
            log_level: "INFO".to_string(),
        });
    }
    
    let content = std::fs::read_to_string(&config_path)
        .map_err(|e| format!("读取配置文件失败: {}", e))?;
    
    let config: AppConfig = serde_json::from_str(&content)
        .map_err(|e| format!("解析配置文件失败: {}", e))?;
    
    Ok(config)
}

/// 保存配置
#[tauri::command]
async fn save_config(config: AppConfig) -> Result<(), String> {
    let config_path = get_config_path()?;
    
    // 确保目录存在
    if let Some(parent) = config_path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("创建配置目录失败: {}", e))?;
    }
    
    let content = serde_json::to_string_pretty(&config)
        .map_err(|e| format!("序列化配置失败: {}", e))?;
    
    std::fs::write(&config_path, content)
        .map_err(|e| format!("写入配置文件失败: {}", e))?;
    
    Ok(())
}

/// 获取配置文件路径
fn get_config_path() -> Result<PathBuf, String> {
    let home = std::env::var("HOME")
        .map_err(|_| "无法获取HOME环境变量")?;
    Ok(PathBuf::from(&home).join(".deskjarvis").join("config.json"))
}

/// 获取默认沙盒路径
fn get_default_sandbox_path() -> String {
    if let Ok(home) = std::env::var("HOME") {
        format!("{}/.deskjarvis/sandbox", home)
    } else {
        "./sandbox".to_string()
    }
}

/// 获取Python解释器路径
fn get_python_path() -> Result<String, String> {
    // 优先使用 python3.12（已安装记忆系统依赖）
    if Command::new("/usr/local/bin/python3.12")
        .arg("--version")
        .output()
        .is_ok()
    {
        return Ok("/usr/local/bin/python3.12".to_string());
    }
    
    // 尝试 python3.12
    if Command::new("python3.12")
        .arg("--version")
        .output()
        .is_ok()
    {
        return Ok("python3.12".to_string());
    }
    
    // 尝试python3
    if Command::new("python3")
        .arg("--version")
        .output()
        .is_ok()
    {
        return Ok("python3".to_string());
    }
    
    // 尝试python
    if Command::new("python")
        .arg("--version")
        .output()
        .is_ok()
    {
        return Ok("python".to_string());
    }
    
    Err("未找到Python解释器，请确保已安装Python 3.11+".to_string())
}

/// 获取Agent脚本路径
fn get_agent_path() -> Result<String, String> {
    // 获取当前工作目录（开发模式下通常是项目根目录）
    let current_dir = std::env::current_dir()
        .map_err(|e| format!("获取当前目录失败: {}", e))?;
    
    // 获取可执行文件所在目录（生产模式下）
    let exe_path = std::env::current_exe().ok();
    let exe_dir = exe_path.as_ref().and_then(|p| p.parent());
    
    // 尝试多个可能的路径（按优先级）
    let mut possible_paths = Vec::new();
    
    // 1. 当前工作目录下的agent/main.py（开发模式）
    possible_paths.push(current_dir.join("agent").join("main.py"));
    
    // 2. 可执行文件目录下的agent/main.py（生产模式）
    if let Some(dir) = exe_dir {
        possible_paths.push(dir.join("agent").join("main.py"));
        if let Some(parent) = dir.parent() {
            possible_paths.push(parent.join("agent").join("main.py"));
        }
    }
    
    // 3. 相对路径（备用）
    possible_paths.push(PathBuf::from("agent").join("main.py"));
    
    // 4. 绝对路径（从项目根目录）
    if let Ok(home) = std::env::var("HOME") {
        possible_paths.push(PathBuf::from(&home).join("Desktop").join("DeskJarvis").join("agent").join("main.py"));
    }
    
    // 保存路径字符串用于错误消息
    let path_strings: Vec<String> = possible_paths.iter().map(|p| p.to_string_lossy().to_string()).collect();
    
    for path in &possible_paths {
        if path.exists() {
            // 使用绝对路径确保可靠性
            let abs_path = path.canonicalize()
                .map_err(|e| format!("无法规范化路径: {}", e))?;
            return Ok(abs_path.to_string_lossy().to_string());
        }
    }
    
    Err(format!(
        "未找到agent/main.py。已尝试路径: {:?}",
        path_strings
    ))
}

/// 打开文件（使用系统默认应用）
#[tauri::command]
async fn open_file(path: String) -> Result<(), String> {
    use std::process::Command;
    
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }
    
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }
    
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }
    
    Ok(())
}

/// 提交用户输入（用于登录、验证码等交互场景）
#[tauri::command]
async fn submit_user_input(request_id: String, values: serde_json::Value) -> Result<bool, String> {
    use std::fs;
    
    // 获取用户目录
    let home = dirs::home_dir().ok_or("无法获取用户目录")?;
    let response_file = home.join(".deskjarvis").join("user_input_response.json");
    
    // 确保目录存在
    if let Some(parent) = response_file.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
    }
    
    // 写入响应
    let response = serde_json::json!({
        "request_id": request_id,
        "values": values,
        "timestamp": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    });
    
    fs::write(&response_file, response.to_string())
        .map_err(|e| format!("写入响应失败: {}", e))?;
    
    Ok(true)
}

/// 取消用户输入请求
#[tauri::command]
async fn cancel_user_input(request_id: String) -> Result<bool, String> {
    use std::fs;
    
    let home = dirs::home_dir().ok_or("无法获取用户目录")?;
    let response_file = home.join(".deskjarvis").join("user_input_response.json");
    
    if let Some(parent) = response_file.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
    }
    
    let response = serde_json::json!({
        "request_id": request_id,
        "cancelled": true,
        "timestamp": std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
    });
    
    fs::write(&response_file, response.to_string())
        .map_err(|e| format!("写入响应失败: {}", e))?;
    
    Ok(true)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            execute_task, 
            get_config, 
            save_config,
            open_file,
            submit_user_input,
            cancel_user_input
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

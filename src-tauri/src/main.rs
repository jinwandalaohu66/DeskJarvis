// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::Stdio;
use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, Window, Emitter, Manager,
    tray::{TrayIconBuilder, MouseButton, MouseButtonState, TrayIconEvent},
    menu::{MenuBuilder, MenuItemBuilder},
};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader as TokioBufReader};
use tokio::process::{Child as TokioChild, ChildStdin, ChildStdout, Command as TokioCommand};
use tokio::sync::Mutex;

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
    // 邮件服务配置 (可选，以兼容旧配置)
    email_sender: Option<String>,
    email_password: Option<String>,
    email_smtp_server: Option<String>,
    email_smtp_port: Option<i32>,
}

// ==================== 常驻 Python 服务进程 ====================

/// 常驻 Python 服务进程句柄
struct PythonServer {
    child: TokioChild,
    stdin: ChildStdin,
    reader: TokioBufReader<ChildStdout>,
}

/// 应用全局状态（通过 Tauri .manage() 注入）
struct AppState {
    server: Mutex<Option<PythonServer>>,
    current_task_id: Mutex<Option<String>>,  // 当前正在执行的任务ID
}

/// 启动常驻 Python 服务进程
///
/// 等待 "ready" 信号后返回，确保 Agent 完全初始化。
/// 超时 30 秒。
async fn launch_python_server() -> Result<PythonServer, String> {
    let python_path = get_python_path()?;
    let server_path = find_script("server.py")?;

    eprintln!("[Tauri] 启动 Python 服务: {} {}", python_path, server_path);

    let mut child = TokioCommand::new(&python_path)
        .arg(&server_path)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true) // 父进程退出时自动杀死子进程
        .spawn()
        .map_err(|e| format!("启动 Python 服务失败: {}", e))?;

    let stdin = child
        .stdin
        .take()
        .ok_or("无法获取 Python 服务 stdin")?;
    let stdout = child
        .stdout
        .take()
        .ok_or("无法获取 Python 服务 stdout")?;
    let stderr = child
        .stderr
        .take()
        .ok_or("无法获取 Python 服务 stderr")?;

    // 后台任务：读取 stderr 并打印（Python 日志输出）
    tauri::async_runtime::spawn(async move {
        let mut reader = TokioBufReader::new(stderr);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line).await {
                Ok(0) => break,        // EOF
                Ok(_) => eprint!("{}", line), // 转发到 Tauri 控制台
                Err(_) => break,
            }
        }
    });

    let mut reader = TokioBufReader::new(stdout);

    // 等待 "ready" 信号（最多 30 秒）
    let ready_result = tokio::time::timeout(
        std::time::Duration::from_secs(30),
        wait_for_ready(&mut reader),
    )
    .await;

    match ready_result {
        Ok(Ok(())) => {
            eprintln!("[Tauri] ✅ Python 服务已就绪");
            Ok(PythonServer {
                child,
                stdin,
                reader,
            })
        }
        Ok(Err(e)) => Err(format!("Python 服务初始化失败: {}", e)),
        Err(_) => Err("Python 服务启动超时(30s)".to_string()),
    }
}

/// 从 stdout 读取行直到收到 "ready" 事件
async fn wait_for_ready(
    reader: &mut TokioBufReader<ChildStdout>,
) -> Result<(), String> {
    let mut buf = String::new();
    loop {
        buf.clear();
        let n = reader
            .read_line(&mut buf)
            .await
            .map_err(|e| format!("读取 ready 信号失败: {}", e))?;
        if n == 0 {
            return Err("Python 服务启动后立即退出".to_string());
        }
        let trimmed = buf.trim();
        if let Ok(event) = serde_json::from_str::<serde_json::Value>(trimmed) {
            let event_type = event
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if event_type == "ready" {
                return Ok(());
            }
            if event_type == "error" {
                let msg = event
                    .get("message")
                    .and_then(|v| v.as_str())
                    .unwrap_or("未知错误");
                return Err(msg.to_string());
            }
        }
    }
}

/// 确保 Python 服务进程正在运行，必要时自动重启
async fn ensure_server_alive(
    server_opt: &mut Option<PythonServer>,
) -> Result<(), String> {
    let needs_restart = match server_opt.as_mut() {
        Some(s) => {
            match s.child.try_wait() {
                Ok(Some(_status)) => {
                    eprintln!("[Tauri] ⚠️ Python 服务已退出，正在重启...");
                    true
                }
                Ok(None) => false, // 仍在运行
                Err(e) => {
                    eprintln!("[Tauri] ⚠️ 检查 Python 服务状态失败: {}", e);
                    true
                }
            }
        }
        None => true,
    };

    if needs_restart {
        *server_opt = None;
        let new_server = launch_python_server().await?;
        *server_opt = Some(new_server);
    }

    Ok(())
}

/// 后台静默重启 Python 服务（崩溃后自动恢复）
fn spawn_background_restart(app_handle: AppHandle) {
    tauri::async_runtime::spawn(async move {
        // 稍等一下再重启，避免连续崩溃
        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
        let state = app_handle.state::<AppState>();
        let mut guard = state.server.lock().await;
        if guard.is_none() {
            eprintln!("[Tauri] 🔄 后台自动重启 Python 服务...");
            match launch_python_server().await {
                Ok(s) => {
                    *guard = Some(s);
                    eprintln!("[Tauri] ✅ Python 服务后台重启成功");
                }
                Err(e) => {
                    eprintln!("[Tauri] ❌ Python 服务后台重启失败: {}", e);
                }
            }
        }
    });
}

// ==================== Tauri 命令 ====================

/// 通过常驻 Python 服务执行任务
async fn execute_via_server(
    window: &Window,
    server: &mut PythonServer,
    instruction: &str,
    context: &Option<serde_json::Value>,
    request_id: &str,
) -> Result<TaskResult, String> {
    // 构建 JSON 命令
    let cmd = serde_json::json!({
        "cmd": "execute",
        "id": request_id,
        "instruction": instruction,
        "context": context,
    });
    let cmd_line = cmd.to_string() + "\n";

    // 写入 stdin
    server
        .stdin
        .write_all(cmd_line.as_bytes())
        .await
        .map_err(|e| format!("写入命令失败: {}", e))?;
    server
        .stdin
        .flush()
        .await
        .map_err(|e| format!("刷新 stdin 失败: {}", e))?;

    // 读取 stdout 直到收到 result 事件
    let mut line_buf = String::new();
    loop {
        line_buf.clear();
        let bytes_read = server
            .reader
            .read_line(&mut line_buf)
            .await
            .map_err(|e| format!("读取响应失败: {}", e))?;

        if bytes_read == 0 {
            // EOF - Python 服务崩溃
            return Err("PROCESS_CRASHED".to_string());
        }

        let trimmed = line_buf.trim();
        if trimmed.is_empty() {
            continue;
        }

        // 解析 JSON 事件
        let event: serde_json::Value = match serde_json::from_str(trimmed) {
            Ok(v) => v,
            Err(_) => continue, // 跳过非 JSON 行
        };

        let event_type = event
            .get("type")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        match event_type {
            "ready" | "pong" | "shutdown_ack" => {
                // 协议控制事件，跳过
                continue;
            }
            "result" => {
                // 最终结果
                if let Some(data) = event.get("data") {
                    return serde_json::from_value::<TaskResult>(data.clone())
                        .map_err(|e| format!("解析 TaskResult 失败: {}", e));
                }
                return Err("result 事件缺少 data 字段".to_string());
            }
            _ => {
                // 进度事件 → 转发到前端
                let _ = window.emit("task-progress", &event);
            }
        }
    }
}

/// 单次进程模式（降级方案：当常驻进程不可用时使用）
async fn execute_oneshot(
    window: &Window,
    instruction: &str,
    context: &Option<serde_json::Value>,
) -> Result<TaskResult, String> {
    let python_path = get_python_path()?;
    let agent_path = find_script("main.py")?;

    let mut cmd_args = vec![agent_path, "--json".to_string(), instruction.to_string()];

    if let Some(ctx) = context {
        if let Ok(ctx_str) = serde_json::to_string(ctx) {
            cmd_args.push("--context".to_string());
            cmd_args.push(ctx_str);
        }
    }

    let mut child = std::process::Command::new(python_path)
        .args(&cmd_args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("执行 Python 命令失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取 stdout")?;
    let stderr = child.stderr.take().ok_or("无法获取 stderr")?;

    let reader = std::io::BufRead::lines(std::io::BufReader::new(stdout));
    let mut final_result: Option<TaskResult> = None;
    let mut stdout_lines = Vec::new();

    for line in reader {
        let line = line.map_err(|e| format!("读取 stdout 失败: {}", e))?;
        stdout_lines.push(line.clone());

        if let Ok(event) = serde_json::from_str::<serde_json::Value>(&line) {
            let event_type = event
                .get("type")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            if event_type != "" {
                let _ = window.emit("task-progress", &event);
            }
        }

        if let Ok(result) = serde_json::from_str::<TaskResult>(&line) {
            final_result = Some(result);
        }
    }

    let stderr_reader = std::io::BufRead::lines(std::io::BufReader::new(stderr));
    let mut stderr_lines = Vec::new();
    for line in stderr_reader {
        if let Ok(line) = line {
            stderr_lines.push(line);
        }
    }

    let _status = child
        .wait()
        .map_err(|e| format!("等待进程结束失败: {}", e))?;

    if !stderr_lines.is_empty() {
        eprintln!("[oneshot] Python stderr: {}", stderr_lines.join("\n"));
    }

    if let Some(result) = final_result {
        Ok(result)
    } else {
        let stdout_content = stdout_lines.join("\n");
        let json_str = extract_json_from_output(&stdout_content)?;
        serde_json::from_str::<TaskResult>(&json_str)
            .map_err(|e| format!("解析 JSON 失败: {}。原始输出: {}", e, stdout_content))
    }
}

/// 执行用户指令（主入口）
///
/// 优先使用常驻 Python 服务，失败时自动降级为单次进程模式。
#[tauri::command]
async fn execute_task(
    window: Window,
    state: tauri::State<'_, AppState>,
    instruction: String,
    context: Option<serde_json::Value>,
) -> Result<TaskResult, String> {
    let request_id = format!(
        "task_{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis()
    );

    // 设置当前任务ID
    {
        let mut current_id = state.current_task_id.lock().await;
        *current_id = Some(request_id.clone());
    }

    // ---------- 尝试常驻进程模式 ----------
    {
        let mut guard = state.server.lock().await;

        // 确保服务进程存活
        if let Err(e) = ensure_server_alive(&mut guard).await {
            eprintln!("[Tauri] ⚠️ 无法启动常驻服务: {}，降级为单次模式", e);
            drop(guard);
            return execute_oneshot(&window, &instruction, &context).await;
        }

        let server = guard.as_mut().unwrap();
        let _result: Result<TaskResult, String> = match execute_via_server(&window, server, &instruction, &context, &request_id).await {
            Ok(r) => {
                // 清除当前任务ID
                {
                    let mut current_id = state.current_task_id.lock().await;
                    *current_id = None;
                }
                return Ok(r);
            },
            Err(ref e) if e == "PROCESS_CRASHED" => {
                eprintln!("[Tauri] ⚠️ Python 服务在执行中崩溃");
                *guard = None;
                // 清除当前任务ID
                {
                    let mut current_id = state.current_task_id.lock().await;
                    *current_id = None;
                }
                // 后台静默重启
                spawn_background_restart(window.app_handle().clone());
                Err(e.clone())
            }
            Err(e) => {
                eprintln!("[Tauri] ⚠️ 常驻进程执行失败: {}", e);
                // 可能是 stdin 写入失败等，标记需要重启
                *guard = None;
                // 清除当前任务ID
                {
                    let mut current_id = state.current_task_id.lock().await;
                    *current_id = None;
                }
                spawn_background_restart(window.app_handle().clone());
                Err(e)
            }
        };
        
        // 清除当前任务ID（如果执行失败）
        {
            let mut current_id = state.current_task_id.lock().await;
            *current_id = None;
        }
        
        // 继续降级处理
        drop(guard);
    }

    // ---------- 降级为单次进程模式 ----------
    eprintln!("[Tauri] 🔄 降级为单次进程模式执行");
    let result = execute_oneshot(&window, &instruction, &context).await;
    
    // 清除当前任务ID
    {
        let mut current_id = state.current_task_id.lock().await;
        *current_id = None;
    }
    
    result
}

/// 停止当前正在执行的任务
#[tauri::command]
async fn stop_task(
    state: tauri::State<'_, AppState>,
) -> Result<(), String> {
    // 获取当前任务ID
    let current_id = {
        let current_id = state.current_task_id.lock().await;
        current_id.clone()
    };
    
    if let Some(task_id) = current_id {
        eprintln!("[Tauri] 🛑 停止任务: {}", task_id);
        
        // 通过常驻进程发送停止命令
        let mut guard = state.server.lock().await;
        if let Some(server) = guard.as_mut() {
            let cmd = serde_json::json!({
                "cmd": "stop",
                "id": task_id,
            });
            let cmd_line = cmd.to_string() + "\n";
            
            if let Err(e) = server.stdin.write_all(cmd_line.as_bytes()).await {
                eprintln!("[Tauri] ⚠️ 发送停止命令失败: {}", e);
                return Err(format!("发送停止命令失败: {}", e));
            }
            
            if let Err(e) = server.stdin.flush().await {
                eprintln!("[Tauri] ⚠️ 刷新停止命令失败: {}", e);
                return Err(format!("刷新停止命令失败: {}", e));
            }
            
            eprintln!("[Tauri] ✅ 停止命令已发送");
            Ok(())
        } else {
            eprintln!("[Tauri] ⚠️ Python 服务未运行，无法发送停止命令");
            Err("Python 服务未运行".to_string())
        }
    } else {
        eprintln!("[Tauri] ⚠️ 没有正在执行的任务");
        Err("没有正在执行的任务".to_string())
    }
}

// ==================== 工具函数 ====================

/// 从输出中提取 JSON
fn extract_json_from_output(output: &str) -> Result<String, String> {
    let start = output.find('{');
    let end = output.rfind('}');

    if let (Some(start_idx), Some(end_idx)) = (start, end) {
        if end_idx > start_idx {
            return Ok(output[start_idx..=end_idx].to_string());
        }
    }

    Err(format!("未找到有效的 JSON 输出。输出内容: {}", output))
}

/// 获取 Python 解释器路径
fn get_python_path() -> Result<String, String> {
    // 按优先级查找
    let candidates = [
        "/usr/local/bin/python3.12",
        "python3.12",
        "python3",
        "python",
    ];

    for candidate in &candidates {
        if std::process::Command::new(candidate)
            .arg("--version")
            .output()
            .is_ok()
        {
            return Ok(candidate.to_string());
        }
    }

    Err("未找到 Python 解释器，请确保已安装 Python 3.11+".to_string())
}

/// 查找 agent 目录下的脚本文件
fn find_script(name: &str) -> Result<String, String> {
    let current_dir = std::env::current_dir()
        .map_err(|e| format!("获取当前目录失败: {}", e))?;

    let exe_path = std::env::current_exe().ok();
    let exe_dir = exe_path.as_ref().and_then(|p| p.parent());

    let mut possible_paths = Vec::new();

    // 1. 当前工作目录下
    possible_paths.push(current_dir.join("agent").join(name));

    // 2. 可执行文件目录下
    if let Some(dir) = exe_dir {
        possible_paths.push(dir.join("agent").join(name));
        if let Some(parent) = dir.parent() {
            possible_paths.push(parent.join("agent").join(name));
        }
    }

    // 3. 相对路径
    possible_paths.push(PathBuf::from("agent").join(name));

    // 4. 绝对路径（项目根目录）
    if let Ok(home) = std::env::var("HOME") {
        possible_paths.push(
            PathBuf::from(&home)
                .join("Desktop")
                .join("DeskJarvis")
                .join("agent")
                .join(name),
        );
    }

    let path_strings: Vec<String> = possible_paths
        .iter()
        .map(|p| p.to_string_lossy().to_string())
        .collect();

    for path in &possible_paths {
        if path.exists() {
            let abs_path = path
                .canonicalize()
                .map_err(|e| format!("无法规范化路径: {}", e))?;
            return Ok(abs_path.to_string_lossy().to_string());
        }
    }

    Err(format!(
        "未找到 {}。已尝试路径: {:?}",
        name, path_strings
    ))
}

/// 获取配置
#[tauri::command]
async fn get_config() -> Result<AppConfig, String> {
    let config_path = get_config_path()?;

    if !config_path.exists() {
        return Ok(AppConfig {
            provider: "claude".to_string(),
            api_key: "".to_string(),
            model: "claude-3-5-sonnet-20241022".to_string(),
            sandbox_path: get_default_sandbox_path(),
            auto_confirm: false,
            log_level: "INFO".to_string(),
            email_sender: None,
            email_password: None,
            email_smtp_server: Some("smtp.gmail.com".to_string()),
            email_smtp_port: Some(587),
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
    let home =
        std::env::var("HOME").map_err(|_| "无法获取 HOME 环境变量".to_string())?;
    Ok(PathBuf::from(&home)
        .join(".deskjarvis")
        .join("config.json"))
}

/// 获取默认沙盒路径
fn get_default_sandbox_path() -> String {
    if let Ok(home) = std::env::var("HOME") {
        format!("{}/.deskjarvis/sandbox", home)
    } else {
        "./sandbox".to_string()
    }
}

/// 打开文件（使用系统默认应用）
#[tauri::command]
async fn open_file(path: String) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new("explorer")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }

    #[cfg(target_os = "linux")]
    {
        std::process::Command::new("xdg-open")
            .arg(&path)
            .spawn()
            .map_err(|e| format!("打开文件失败: {}", e))?;
    }

    Ok(())
}

/// 提交用户输入（用于登录、验证码等交互场景）
#[tauri::command]
async fn submit_user_input(
    request_id: String,
    values: serde_json::Value,
) -> Result<bool, String> {
    use std::fs;

    let home = dirs::home_dir().ok_or("无法获取用户目录")?;
    let response_file = home.join(".deskjarvis").join("user_input_response.json");

    if let Some(parent) = response_file.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
    }

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

// ==================== 应用入口 ====================

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_os::init())
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        // 注入全局状态
        .manage(AppState {
            server: Mutex::new(None),
            current_task_id: Mutex::new(None),
        })
        .setup(|app| {
            // ========== 后台启动常驻 Python 服务 ==========
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                eprintln!("[Tauri] 🚀 正在后台启动 Python 服务...");
                let state = app_handle.state::<AppState>();
                let mut guard = state.server.lock().await;
                match launch_python_server().await {
                    Ok(s) => {
                        *guard = Some(s);
                        eprintln!("[Tauri] ✅ Python 服务已在后台启动完成");
                    }
                    Err(e) => {
                        eprintln!(
                            "[Tauri] ⚠️ Python 服务后台启动失败: {}（首次任务时将自动重试）",
                            e
                        );
                    }
                }
            });

            // ========== 创建系统托盘 ==========
            let show_item = MenuItemBuilder::new("显示主窗口")
                .id("show")
                .build(app)?;
            let hide_item = MenuItemBuilder::new("隐藏到后台")
                .id("hide")
                .build(app)?;
            let quit_item = MenuItemBuilder::new("退出 DeskJarvis")
                .id("quit")
                .build(app)?;

            let menu = MenuBuilder::new(app)
                .item(&show_item)
                .item(&hide_item)
                .separator()
                .item(&quit_item)
                .build()?;

            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .tooltip("DeskJarvis - AI 桌面助手")
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "hide" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.hide();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            execute_task,
            stop_task,
            get_config,
            save_config,
            open_file,
            submit_user_input,
            cancel_user_input
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

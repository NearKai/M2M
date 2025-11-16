# MIDI-MCSTRUCTURE API 服务

将 MIDI 音乐文件转换为 Minecraft 命令结构，支持基岩版和 Java 版。

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
python main_source_code.py
```

服务将在 `http://127.0.0.1:1080` 启动。

---

## API 端点

### 1. 上传 MIDI 文件

**请求**
```
POST /midi
```

**参数**
- `file` (multipart/form-data): MIDI 文件

**响应示例**
```json
{
  "task_id": 1,
  "filename": "test.mid",
  "status": "queued",
  "output": null,
  "error": null
}
```

**状态码**
- `200`: 文件已上传，转换任务已创建
- `400`: 请求格式错误（缺少文件或文件名为空）
- `500`: 服务器内部错误

---

### 2. 查询转换状态

**请求**
```
GET /check/<task_id>
```

**参数**
- `task_id` (path): 任务 ID（来自上传响应）

**响应示例（转换中）**
```json
{
  "task_id": 1,
  "filename": "test.mid",
  "status": "queued",
  "output": null,
  "error": null
}
```

**响应示例（转换完成）**
```json
{
  "task_id": 1,
  "filename": "test.mid",
  "status": "done",
  "output": "/workspaces/M2M/BE12345678.mcstructure",
  "error": null,
  "download_url": "http://127.0.0.1:1080/files/BE12345678.mcstructure"
}
```

**响应示例（转换失败）**
```json
{
  "task_id": 1,
  "filename": "test.mid",
  "status": "failed",
  "output": null,
  "error": "无可用模板"
}
```

**状态说明**
- `queued`: 等待转换
- `done`: 转换完成
- `failed`: 转换失败

---

### 3. 下载转换结果

**请求**
```
GET /files/<filename>
```

**参数**
- `filename` (path): 输出文件名

**响应**
- 返回文件的二进制内容，自动下载

**示例**
```bash
curl -O http://127.0.0.1:1080/files/BE12345678.mcstructure
```

---

### 4. 获取服务信息

**请求**
```
GET /
```

**响应**
- 返回 HTML 测试页面或简单信息页面

---

## 使用示例

### 使用 curl 上传并查询

```bash
# 1. 上传 MIDI 文件
curl -X POST -F "file=@song.mid" http://127.0.0.1:1080/midi

# 输出: {"task_id": 1, "filename": "song.mid", "status": "queued", "output": null, "error": null}

# 2. 查询转换状态（轮询）
curl http://127.0.0.1:1080/check/1

# 3. 当状态为 "done" 时，下载结果
curl -O http://127.0.0.1:1080/files/BE12345678.mcstructure
```

### 使用 Python 脚本

```python
import requests
import time

# 上传文件
with open('song.mid', 'rb') as f:
    r = requests.post('http://127.0.0.1:1080/midi', 
                      files={'file': f})
    task_id = r.json()['task_id']
    print(f"Task ID: {task_id}")

# 轮询查询状态
while True:
    r = requests.get(f'http://127.0.0.1:1080/check/{task_id}')
    status = r.json()
    print(f"Status: {status['status']}")
    
    if status['status'] == 'done':
        # 下载文件
        download_url = status['download_url']
        r = requests.get(download_url)
        with open('output.mcstructure', 'wb') as f:
            f.write(r.content)
        print("Download completed!")
        break
    elif status['status'] == 'failed':
        print(f"Conversion failed: {status['error']}")
        break
    
    time.sleep(1)
```

---

## 参数配置

转换行为由 `Asset/text/setting.json` 文件控制：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `fps` | 帧率 | 20 |
| `auto_gain` | 自动增益 | 0 |
| `speed` | 转换速度（滴答速率） | 100 |
| `skip` | 跳过空白 | true |
| `enable_percussion` | 启用打击乐 | true |
| `mode` | 输出模式 | 0 |
| `append_number` | 追加编号 | false |
| `file_type` | 文件类型（0=结构，1=行为包，2=Java数据包） | 0 |
| `adjust_pitch` | 调整音高 | 0 |
| `adjust_instrument` | 调整乐器 | false |
| `log_level` | 日志级别 | true |

### 输出格式说明

- **模式 0**: mcstructure 文件（推荐）
- **模式 1**: 基岩版行为包（.mcpack）
- **模式 2**: Java 版数据包（.zip）
- **模式 3**: 串口设备输出

---

## 输出文件

转换完成后的文件保存在程序运行目录下：

| 类型 | 文件名 | 说明 |
|------|--------|------|
| 结构文件 | `BE/JE` + 8位十六进制 + `.mcstructure` | 单个结构文件 |
| 行为包 | `BE` + 8位十六进制 + `.zip` | 基岩版行为包 |
| 数据包 | `JE` + 8位十六进制 + `.zip` | Java 版数据包 |

**示例**: `BE12ABCDEF.mcstructure`

---

## 错误处理

### 常见错误

| 错误信息 | 原因 | 解决方案 |
|---------|------|--------|
| `no file field` | 请求中缺少文件 | 确保使用 multipart/form-data 上传 |
| `empty filename` | 文件名为空 | 确保选择了有效的文件 |
| `unknown task id` | 任务 ID 不存在 | 检查任务 ID 是否正确 |
| `无可用模板` | 没有找到结构文件 | 检查 `Asset/mcstructure/` 目录 |

### 调试

启用日志记录查看详细信息：

```bash
python main_source_code.py 2>&1 | tee api.log
```

---

## 配置文件

### Asset/text/setting.json

主配置文件，控制全局转换参数：

```json
{
  "setting": {
    "fps": 20,
    "auto_gain": 0,
    "speed": 100,
    "skip": true,
    "enable_percussion": true,
    "mode": 0,
    "append_number": false,
    "file_type": 0,
    "adjust_pitch": 0,
    "adjust_instrument": false,
    "log_level": true,
    "id": 0
  }
}
```

### Asset/profile/

乐器配置文件，包含：
- `default.json`: 默认乐器配置
- `no_balance.json`: 禁用音量平衡配置
- `old_edition.json`: 旧版本支持配置

每个配置文件定义音符映射、音量控制和音效设置。

### Asset/mcstructure/

结构模板文件，支持不同大小：
- `空白小模板.mcstructure`: 小规模项目
- `空白中模板.mcstructure`: 中等规模项目
- `空白大模板(推荐).mcstructure`: 大规模项目

---

## 性能指标

| 指标 | 值 |
|------|-----|
| 最大并发任务 | 无限制（取决于系统资源） |
| 平均转换速度 | 10-30 秒/分钟 MIDI |
| 内存占用 | ~50-200 MB（取决于 MIDI 文件大小） |
| CPU 占用 | 单核 ~30-50% |

---

## 技术栈

- **框架**: Flask（轻量级 Python Web 框架）
- **MIDI 处理**: mido（MIDI I/O 库）
- **NBT 格式**: pynbt（Minecraft NBT 文件处理）
- **并发**: Python threading（线程池）
- **CORS**: flask-cors（跨域资源共享）

---

## 许可证

详见 LICENSE 文件

---

## 支持

如有问题或建议，请查看项目文档或提交 Issue。

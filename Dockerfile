# 使用 Python 3.11 官方镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 Python 缓冲输出
ENV PYTHONUNBUFFERED=1

# 安装系统依赖（如果需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt 到工作目录
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序代码到工作目录
COPY main_source_code.py .
COPY Asset/ ./Asset/
# 如果宿主机没有 `api_uploads` 目录，直接在镜像内创建该目录，避免 COPY 失败
RUN mkdir -p /app/api_uploads

# 暴露 API 服务端口
EXPOSE 1080

# 启动应用程序
CMD ["python", "main_source_code.py"]

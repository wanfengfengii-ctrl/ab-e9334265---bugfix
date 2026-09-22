# 验收服务：Playwright 驱动无头浏览器完成联调复核
# 基础镜像已内置 Chromium 与系统依赖
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# CJK 字体：让验收截图中的中文正常渲染
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY verify.py .

CMD ["python", "-u", "verify.py"]

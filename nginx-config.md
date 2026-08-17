# FIP.AI Nginx 配置

## 服务器信息
- 华为云服务器: 120.46.41.158
- 后端端口: 8001 (fipai-api)

## Nginx 配置文件位置
- `/etc/nginx/sites-available/fipai` (或 `/etc/nginx/conf.d/fipai.conf`)

## 部署步骤

### 1. 上传各个前端项目

```bash
# 官网 (fipai.cn)
scp -r ~/website/dist user@120.46.41.158:/var/www/fipai-cn/

# account.fipai.cn
scp -r ~/account/dist user@120.46.41.158:/var/www/account/

# console.fipai.cn (如果需要独立部署)
scp -r ~/app-en/dist user@120.46.41.158:/var/www/console/

# cms-admin
scp -r ~/cms-admin/dist user@120.46.41.158:/var/www/cms-admin/
```

### 2. Nginx 配置

```nginx
# /etc/nginx/sites-available/fipai

# =============================================================================
# fipai.cn - 官网
# =============================================================================
server {
    listen 80;
    server_name fipai.cn www.fipai.cn;

    root /var/www/fipai-cn/dist;
    index index.html;

    # Gzip 压缩
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # React Router 处理 SPA
    location / {
        try_files $uri $uri/ /index.html;
    }

    # 静态资源缓存
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}

# =============================================================================
# account.fipai.cn - 账户服务
# =============================================================================
server {
    listen 80;
    server_name account.fipai.cn;

    root /var/www/account/dist;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 代理到后端
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS 头
        add_header Access-Control-Allow-Origin $http_origin always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
    }
}

# =============================================================================
# console.fipai.cn - 控制台
# =============================================================================
server {
    listen 80;
    server_name console.fipai.cn;

    root /var/www/console/dist;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
    }
}

# =============================================================================
# cms.fipai.cn - CMS 管理后台
# =============================================================================
server {
    listen 80;
    server_name cms.fipai.cn;

    root /var/www/cms-admin/dist;
    index index.html;

    gzip on;
    gzip_types text/plain text/css application/json application/javascript;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        expires 1y;
    }
}

# =============================================================================
# api.fipai.cn - API 服务
# =============================================================================
server {
    listen 80;
    server_name api.fipai.cn;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # CORS
        add_header Access-Control-Allow-Origin $http_origin always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-CSRFToken" always;

        # 处理 OPTIONS 请求
        if ($request_method = 'OPTIONS') {
            add_header Access-Control-Allow-Origin $http_origin;
            add_header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS";
            add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-CSRFToken";
            add_header Access-Control-Max-Age 86400;
            add_header Content-Length 0;
            add_header Content-Type text/plain;
            return 204;
        }
    }

    # OAuth2 健康检查
    location /health {
        access_log off;
        return 200 "OK";
    }
}
```

### 3. 启用配置

```bash
# 创建软链接
sudo ln -s /etc/nginx/sites-available/fipai /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重载 Nginx
sudo systemctl reload nginx
```

### 4. SSL/HTTPS 配置 (Let's Encrypt)

```bash
# 安装 Certbot
sudo apt install certbot python3-certbot-nginx

# 获取证书
sudo certbot --nginx -d fipai.cn -d www.fipai.cn
sudo certbot --nginx -d account.fipai.cn
sudo certbot --nginx -d console.fipai.cn
sudo certbot --nginx -d cms.fipai.cn
sudo certbot --nginx -d api.fipai.cn

# 自动续期
sudo certbot renew --dry-run
```

### 5. 启动后端服务

```bash
# SSH 到服务器
ssh user@120.46.41.158

# 启动 fipai-api (使用 systemd 或 pm2)
cd /var/www/fipai-api
source venv/bin/activate
python manage.py runserver 0.0.0.0:8001 &

# 或使用 gunicorn
pip install gunicorn
gunicorn fipai.wsgi:application --bind 0.0.0.0:8001 --daemon
```

### 6. 防火墙设置

```bash
# 开放端口
sudo ufw allow 80
sudo ufw allow 443
sudo ufw allow 8001  # 后端 API
```

---

## 域名解析

在 DNS 服务商添加以下记录：

| 记录类型 | 主机名 | 值 |
|---------|-------|-----|
| A | fipai.cn | 120.46.41.158 |
| A | www.fipai.cn | 120.46.41.158 |
| A | account.fipai.cn | 120.46.41.158 |
| A | console.fipai.cn | 120.46.41.158 |
| A | cms.fipai.cn | 120.46.41.158 |
| A | api.fipai.cn | 120.46.41.158 |
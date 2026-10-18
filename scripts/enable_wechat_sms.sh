#!/usr/bin/env bash
# 一键把 07Account (account.fipai.cn) 的微信扫码 + 阿里云 SMS 切到真接通模式。
# 用法(在本机 mac):
#   WECHAT_APPID=wx123 WECHAT_SECRET=abc \
#   ALIYUN_KEY=LTAI5... ALIYUN_SECRET=xyz \
#   SMS_SIGN='飞谱智能' SMS_TPL_REG=SMS_xxx SMS_TPL_LOG=SMS_yyy \
#   bash /Users/admin/Documents/Developer/AI_Dev/fip_platform/07Account/scripts/enable_wechat_sms.sh
#
# 脚本通过 ssh ecs 把 env 写到 /etc/fipai-account-staging/runtime.env(systemd unit 的
# EnvironmentFile),然后 systemctl restart fipai-account-staging.service。
# 所有 credential 在 mac 临时 shell 里 export,不留在 ECS .env 文件。
set -euo pipefail

: "${WECHAT_APPID:?missing WECHAT_APPID}"
: "${WECHAT_SECRET:?missing WECHAT_SECRET}"
: "${ALIYUN_KEY:?missing ALIYUN_KEY}"
: "${ALIYUN_SECRET:?missing ALIYUN_SECRET}"
: "${SMS_SIGN:?missing SMS_SIGN}"
: "${SMS_TPL_REG:?missing SMS_TPL_REG}"
: "${SMS_TPL_LOG:?missing SMS_TPL_LOG}"

ENV_FILE=/etc/fipai-account-staging/runtime.env
SERVICE=fipai-account-staging.service

ssh ecs "set -e
# 1. 备份当前 env
cp -a $ENV_FILE \${ENV_FILE}.bak-\$(date +%Y%m%d-%H%M%S)

# 2. 把 sandbox flag 改成 false(sed 替换,如不存在则追加)
if grep -q '^ALIYUN_SMS_SANDBOX=' $ENV_FILE; then
  sed -i 's|^ALIYUN_SMS_SANDBOX=.*|ALIYUN_SMS_SANDBOX=false|' $ENV_FILE
else
  echo 'ALIYUN_SMS_SANDBOX=false' >> $ENV_FILE
fi
if grep -q '^WECHAT_SANDBOX=' $ENV_FILE; then
  sed -i 's|^WECHAT_SANDBOX=.*|WECHAT_SANDBOX=false|' $ENV_FILE
else
  echo 'WECHAT_SANDBOX=false' >> $ENV_FILE
fi

# 3. 去重已有的 wechat/sms 旧 key,然后追加新值
for k in WECHAT_OPEN_APPID WECHAT_OPEN_SECRET WECHAT_OPEN_REDIRECT_URI ALIYUN_SMS_ACCESS_KEY_ID ALIYUN_SMS_ACCESS_KEY_SECRET ALIYUN_SMS_SIGN_NAME ALIYUN_SMS_TEMPLATE_CODE_register ALIYUN_SMS_TEMPLATE_CODE_login; do
  sed -i \"/^\${k}=/d\" $ENV_FILE
done

cat >> $ENV_FILE <<EOF
WECHAT_OPEN_APPID=${WECHAT_APPID}
WECHAT_OPEN_SECRET=${WECHAT_SECRET}
WECHAT_OPEN_REDIRECT_URI=https://account.fipai.cn/api/auth/oauth/wechat/callback/
ALIYUN_SMS_ACCESS_KEY_ID=${ALIYUN_KEY}
ALIYUN_SMS_ACCESS_KEY_SECRET=${ALIYUN_SECRET}
ALIYUN_SMS_SIGN_NAME=${SMS_SIGN}
ALIYUN_SMS_TEMPLATE_CODE_register=${SMS_TPL_REG}
ALIYUN_SMS_TEMPLATE_CODE_login=${SMS_TPL_LOG}
EOF

echo '--- updated env tail ---'
tail -10 $ENV_FILE
"

# 4. 杀旧 gunicorn(若存在),systemd restart 接管
ssh ecs "set -e
# 杀残留 gunicorn(若有用户在 screen 启的)
pgrep -f 'gunicorn.*fipai.wsgi:application' | xargs -r kill -QUIT 2>/dev/null || true
sleep 1
systemctl restart $SERVICE
sleep 3
systemctl status $SERVICE --no-pager | head -10
echo '---'
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:18001/api/auth/me/
"

echo
echo "=== 接通验证(ECS 内调用) ==="
ssh ecs "set -e
echo '--- 微信端点:返回 authorize_url ---'
curl -s 'http://127.0.0.1:18001/api/auth/oauth/wechat/?redirect=https://home.fipai.cn/login' | python3 -m json.tool
echo
echo '--- 阿里云短信端点:真发短信(只演示不会报错) ---'
curl -s -X POST http://127.0.0.1:18001/api/auth/send-code/ \\
  -H 'Content-Type: application/json' \\
  -d '{\"phone\":\"13900008801\",\"purpose\":\"login\"}' | python3 -m json.tool
echo
echo '--- ECS 上的 gunicorn 日志(看 SDK 调用结果) ---'
journalctl -u $SERVICE --no-pager -n 30 2>/dev/null | grep -iE 'mock|sms|send_sms|sandbox|wechat' | tail -10
"
# 🚀 Шпаргалка - LSR_SKUD

## 📌 Основная информация

**Репо:** https://github.com/andreysafar/LSR_SKUD.git  
**Бот токен:** `5746077232:AAFpT0XzBAFA06xY6_JRVVgoEbPoa56Gqdw`  
**Авторы:** safar (safar@lsr.ru), ngatdd (Replit)  
**Текущая ветка:** `feature/anpr-batch-processing`  
**Админ-группа (логи, перезапуски, обратная связь):** `TECH_CHAT_ID=-1002161212817`

---

## 🎯 Быстрый старт

### Локально
```bash
cd /home/safar/Project/LSR_SKUD

# Проверка системы
python3 debug_bot.py
python3 check_gpu.py

# Запуск бота
GPU_ENABLED=true DEVICE=cuda python3 main.py

# Веб UI (в другом терминале)
streamlit run app.py --server.port=8501
```

### Docker
```bash
# Запуск всех сервисов
docker compose up -d

# Проверка логов
docker compose logs -f telegram-bot
docker compose ps

# Остановка
docker compose down
```

---

## 🔧 CI/CD Setup

### 1️⃣ Добавить GitHub Secrets

Settings → Secrets and variables → Actions

```
DEV_HOST=<IP сервера DEV>
DEV_USER=ubuntu
DEV_SSH_KEY=<приватный ключ>

PROD_HOST=<IP сервера PROD>
PROD_USER=root
PROD_SSH_KEY=<приватный ключ>

SLACK_WEBHOOK=<webhook URL>  # опционально
```

### 2️⃣ Генерировать SSH ключи

```bash
ssh-keygen -t ed25519 -f lsr_skud_deploy -C "LSR_SKUD CI/CD"

# На сервере
cat lsr_skud_deploy.pub >> ~/.ssh/authorized_keys
```

### 3️⃣ Разворачивание

**DEV:**
```bash
git checkout dev
git commit -m "Fix: issue"
git push origin dev
# ✅ Автоматический deploy на DEV
```

**PROD:**
```bash
git checkout main
git pull origin dev
git push origin main
# ✅ Автоматический deploy на PROD
```

---

## 🐛 Отладка

### Бот не отвечает
```bash
docker compose logs -f telegram-bot | head -100
docker compose ps
docker inspect lsr-skud-bot
```

### GPU не работает
```bash
python3 check_gpu.py
nvidia-smi
torch.cuda.is_available()
```

### Проблемы с кэшем
```bash
rm -rf /tmp/.uv-cache
rm -rf /home/lsrskud/.cache/uv
docker compose restart telegram-bot
```

---

## 📊 Мониторинг

**Веб UI:** http://localhost:8501  
**Prometheus:** http://localhost:9090  
**Grafana:** http://localhost:3001  

**Docker статус:**
```bash
docker compose ps                    # Все контейнеры
docker compose logs -f NAME          # Логи контейнера
docker compose logs -f --tail=50     # Последние 50 строк
```

---

## 📁 Ключевые файлы

```
LSR_SKUD/
├── .github/workflows/
│   ├── ci-cd.yml             # 🔄 CI/CD Pipeline
│   └── security.yml          # 🔒 Security сканирование
├── bot/telegram_bot.py       # 🤖 Telegram бот
├── main.py                   # 🎯 Запуск бота
├── app.py                    # 📊 Streamlit UI
├── docker-compose.yml        # 🐳 Docker конфиг
├── debug_bot.py              # 🐛 Диагностика
├── BOT_AND_CICD_REPORT.md   # 📋 Этот отчет
├── CI_CD_SETUP.md            # ⚙️ Настройка CI/CD
└── .env                      # 🔑 Переменные окружения
```

---

## ✅ Checklist

- [ ] Docker compose up -d работает
- [ ] telegram-bot контейнер running
- [ ] Streamlit UI доступен на :8501
- [ ] GitHub Secrets добавлены
- [ ] SSH ключи сгенерированы
- [ ] Test push в dev ветку прошел успешно
- [ ] GitHub Actions workflow выполнен

---

## 🆘 Контакты

- **Основной разработчик:** safar (safar@lsr.ru)
- **GitHub:** https://github.com/andreysafar
- **Репо:** https://github.com/andreysafar/LSR_SKUD

---

**Последнее обновление:** 2026-03-08  
**Версия:** 1.0

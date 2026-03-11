# 🎉 GitLab CI/CD - Итоговый отчет

## 📌 Резюме

✅ **Переход с GitHub Actions на GitLab CI/CD**  
✅ **GitLab Runner:** `10.205.111.13:180`  
✅ **Pipeline настроена для автоматического деплоя**  

---

## 🔄 Что было сделано

### 1. ✅ Создан `.gitlab-ci.yml`

**Stages:**
- **lint** - проверка кода
- **test** - unit тесты  
- **build** - Docker образы
- **deploy-dev** - deploy на DEV (manual)
- **deploy-prod** - deploy на PROD (manual)

**Features:**
- ✅ Автоматический backup БД перед PROD deploy
- ✅ Health check после deploy
- ✅ Slack notifications (опционально)
- ✅ SSH deploy через runner
- ✅ Docker image build и push в registry

### 2. ✅ Создана документация

- **`GITLAB_SETUP.md`** - полная инструкция по настройке
- Включает: установка runner, регистрация, переменные, troubleshooting

### 3. ✅ Удалены GitHub Actions файлы

- Удалены: `.github/workflows/ci-cd.yml`
- Удалены: `.github/workflows/security.yml`

---

## 🚀 Как работает Pipeline

### Dev Ветка (Разработка)

```
Push в dev ветку
    ↓
[1. Lint] - проверка кода (flake8, black, mypy)
    ↓
[2. Test] - unit тесты (pytest)
    ↓  
[3. Build] - Docker build + push в registry
    ↓
[4. Deploy DEV] - manual trigger (кнопка Play)
    ├─ SSH подключение
    ├─ Git pull latest code
    ├─ Docker pull images
    ├─ docker compose restart
    └─ Health check
```

### Main Ветка (Production)

```
Push в main ветку
    ↓
[1. Lint] - проверка кода
    ↓
[2. Test] - unit тесты
    ↓
[3. Build] - Docker build + push в registry
    ↓
[4. Deploy PROD] - manual trigger (кнопка Play)
    ├─ Backup БД (sqlite3)
    ├─ SSH подключение
    ├─ Git pull latest code
    ├─ Docker pull images
    ├─ docker compose restart
    ├─ Health check
    └─ Slack notification (если configured)
```

---

## ⚙️ Настройка Runner

### Быстрая установка

На `10.205.111.13`:

```bash
# 1. Установить GitLab Runner
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt-get install gitlab-runner

# 2. Зарегистрировать Runner
# Получить token из GitLab: Settings → CI/CD → Runners
sudo gitlab-runner register \
  --url http://10.205.111.13:180 \
  --registration-token <YOUR_TOKEN> \
  --executor docker \
  --docker-image docker:latest \
  --docker-privileged \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --description "LSR_SKUD Docker Runner" \
  --tag-list docker,lsr-skud

# 3. Проверить
sudo gitlab-runner status
```

### Добавить Secrets в GitLab

**Settings → CI/CD → Variables:**

```
DEV_SSH_HOST = <IP DEV сервера>
DEV_SSH_USER = ubuntu
DEV_SSH_PORT = 22
DEV_SSH_KEY = <приватный SSH ключ>

PROD_SSH_HOST = <IP PROD сервера>
PROD_SSH_USER = root
PROD_SSH_PORT = 22
PROD_SSH_KEY = <приватный SSH ключ>

SLACK_WEBHOOK = <webhook URL> (опционально)

CI_REGISTRY_USER = safar
CI_REGISTRY_PASSWORD = <personal access token>
```

---

## 📊 Variable Reference

### Автоматические переменные GitLab
```
$CI_COMMIT_BRANCH        # текущая ветка (dev, main, etc)
$CI_COMMIT_SHA           # полный хеш коммита
$CI_COMMIT_SHORT_SHA     # короткий хеш
$CI_COMMIT_MESSAGE       # сообщение коммита
$CI_COMMIT_AUTHOR        # автор коммита
$CI_JOB_ID               # ID текущего job
$CI_PIPELINE_ID          # ID pipeline
$CI_REGISTRY_IMAGE       # образ в GitLab registry
```

### Кастомные переменные (из Settings)
```
$DEV_SSH_HOST / $DEV_SSH_USER / $DEV_SSH_KEY / $DEV_SSH_PORT
$PROD_SSH_HOST / $PROD_SSH_USER / $PROD_SSH_KEY / $PROD_SSH_PORT
$SLACK_WEBHOOK
$CI_REGISTRY_USER / $CI_REGISTRY_PASSWORD
```

---

## 🎯 Типичный Workflow

### 1️⃣ Разработка Feature

```bash
git checkout -b feature/new-component
# ... write code ...
git add .
git commit -m "feat: add new component"
git push origin feature/new-component
```

GitLab Pipeline:
- ✅ Запускаются lint и test
- ❌ Build не запускается (только dev/main)
- ✅ Можно видеть результаты в CI/CD → Pipelines

### 2️⃣ Merge в Dev

```bash
# Pull request (GitLab: Merge Request)
# Settings → CI/CD может требовать успешный pipeline

# После merge в dev
git checkout dev
git merge feature/new-component
git push origin dev
```

GitLab Pipeline:
- ✅ lint, test, build автоматически
- ⏳ deploy:dev waiting for manual trigger

### 3️⃣ Deploy на Dev

1. Перейти в **CI/CD → Pipelines**
2. Найти последний pipeline для `dev` ветки
3. Нажать кнопку **▶️ Play** рядом с `deploy:dev`
4. Ждать выполнения и видеть логи

### 4️⃣ Merge в Main и Deploy на Prod

```bash
# После тестирования на dev
git checkout main
git merge dev
git push origin main
```

GitLab Pipeline:
- ✅ lint, test, build автоматически
- ⏳ deploy:prod waiting for manual trigger

Затем:
1. Перейти в **CI/CD → Pipelines**
2. Найти последний pipeline для `main` ветки
3. Нажать кнопку **▶️ Play** рядом с `deploy:prod`
4. **Перед деплоем автоматически делается backup БД!**
5. Ждать выполнения

---

## 🔍 Мониторинг Pipeline

### В GitLab UI

1. **CI/CD → Pipelines** - список всех pipelines
2. **Нажать на pipeline** - видеть все stages
3. **Нажать на job** - видеть полный лог выполнения

### Статусы

- 🟢 **Passed** - успешно
- 🔴 **Failed** - ошибка
- 🟡 **Pending** - ждет исполнения
- 🟠 **Running** - в процессе
- ⚪ **Skipped** - пропущен

### Логи Deploy

После запуска deploy в логах будут видны:
```
🚀 Deploying to DEV environment...
cd /home/safar/Project/LSR_SKUD
git fetch origin dev
git checkout dev
git reset --hard origin/dev
docker login -u ... -p ...
docker pull <image>:latest-dev
docker compose down
docker compose up -d
sleep 10
docker compose ps
✅ DEV deployment completed
```

---

## 🔧 Troubleshooting

### Runner не видится в GitLab

```bash
# На машине 10.205.111.13
sudo gitlab-runner verify
sudo gitlab-runner status

# Перезагрузить
sudo systemctl restart gitlab-runner
```

### Deploy зависает

```bash
# Проверить SSH
ssh -i <key> user@host "echo OK"

# Проверить доступ к docker
ssh user@host "docker ps"

# Проверить место на диске
ssh user@host "df -h"
```

### Build не может push образ

```bash
# Проверить registry credentials
# Settings → CI/CD → Variables
# CI_REGISTRY_USER и CI_REGISTRY_PASSWORD
```

Подробнее смотри: **GITLAB_SETUP.md**

---

## 📋 Готовый Checklist

- [ ] GitLab Runner установлен на `10.205.111.13`
- [ ] Runner зарегистрирован в GitLab
- [ ] `.gitlab-ci.yml` скоммитен в репо
- [ ] Secrets добавлены в GitLab (Settings → CI/CD → Variables)
- [ ] SSH ключи сгенерированы и добавлены на DEV/PROD
- [ ] Первый commit в dev ветку
- [ ] Pipeline запустился (видна в CI/CD → Pipelines)
- [ ] Успешно прошли lint, test, build
- [ ] Запущен deploy:dev и проверено на сервере
- [ ] Запущен deploy:prod и проверено на PROD

---

## 📁 Файлы в репо

```
LSR_SKUD/
├── .gitlab-ci.yml              # 🔄 GitLab Pipeline config
├── GITLAB_SETUP.md             # ⚙️ Setup инструкции
├── docker-compose.yml          # 🐳 Docker compose
├── Dockerfile                  # 🏗️ Docker build
├── main.py                     # 🤖 Telegram bot
├── app.py                      # 📊 Streamlit UI
└── ... другие файлы ...
```

---

## 🆘 Быстрая помощь

**Pipeline не запускается:**
- Проверить что `.gitlab-ci.yml` правильный синтаксис
- Убедиться что runner зарегистрирован
- Посмотреть logs: `sudo journalctl -u gitlab-runner -f`

**Deploy не работает:**
- Проверить SSH ключ: `ssh -i <key> user@host "echo OK"`
- Проверить переменные GitLab: Settings → CI/CD → Variables
- Посмотреть логи deploy в GitLab: CI/CD → Pipelines → job

**Образы не собираются:**
- Проверить место на диске: `docker system df`
- Очистить: `docker system prune -f`
- Проверить Docker daemon: `docker info`

---

## 📞 Полезные команды

```bash
# На runner машине (10.205.111.13)
sudo gitlab-runner register            # зарегистрировать runner
sudo gitlab-runner status              # статус runner
sudo gitlab-runner verify              # проверить
sudo systemctl restart gitlab-runner   # перезагрузить
sudo journalctl -u gitlab-runner -f    # логи runner

# Локально
git push origin dev                    # запустить pipeline
git push origin main                   # запустить pipeline prod
```

---

**✅ Статус:** Полностью готово к использованию

**Дата:** 2026-03-08  
**Version:** 1.0  
**CI/CD Platform:** GitLab  
**Runner Location:** 10.205.111.13:180

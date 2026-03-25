# ⚡ GitLab CI/CD - Шпаргалка

## 🎯 Быстрый старт

### 1️⃣ Первый коммит в dev

```bash
git checkout dev
git add .gitlab-ci.yml
git commit -m "ci: add GitLab CI/CD pipeline"
git push origin dev

# ✅ GitLab автоматически запускает pipeline
```

### 2️⃣ Дождитьсяурока build

1. Перейти в **GitLab → CI/CD → Pipelines**
2. Видеть stages: lint → test → build ✅
3. Deploy stage ждет manual trigger

### 3️⃣ Запустить deploy

1. Нажать кнопку **▶️ Play** рядом с `deploy:dev`
2. Ждать завершения
3. Проверить на сервере: `docker compose ps`

---

## 📝 Коммит в ветки

### Feature (не деплоится)
```bash
git checkout -b feature/new-feature
git push origin feature/new-feature
# ✅ Только lint + test
```

### Dev (деплоится на DEV)
```bash
git checkout dev
git push origin dev
# ✅ lint → test → build → deploy:dev (manual)
```

### Main (деплоится на PROD)
```bash
git checkout main
git push origin main
# ✅ lint → test → build → deploy:prod (manual)
# 📦 Автоматический backup перед deploy!
```

---

## 🔧 GitLab Secrets

**Settings → CI/CD → Variables:**

```
DEV_SSH_HOST        # IP dev сервера
DEV_SSH_USER        # SSH пользователь (ubuntu/root)
DEV_SSH_PORT        # SSH порт (обычно 22)
DEV_SSH_KEY         # Приватный SSH ключ

PROD_SSH_HOST       # IP prod сервера
PROD_SSH_USER       # SSH пользователь (root)
PROD_SSH_PORT       # SSH порт
PROD_SSH_KEY        # Приватный SSH ключ

SLACK_WEBHOOK       # Для уведомлений (опционально)
```

---

## 🐳 Docker Image

**Автоматически собираются:**
- `registry/lsr-skud:latest-dev` (для dev ветки)
- `registry/lsr-skud:batch-worker-dev`
- `registry/lsr-skud:latest-main` (для main ветки)
- `registry/lsr-skud:batch-worker-main`

---

## 📊 Pipeline Stages

| Stage | Trigger | Status | Action |
|-------|---------|--------|--------|
| **lint** | Все ветки | Auto | Проверка кода |
| **test** | Все ветки | Auto | Unit тесты |
| **build** | dev, main | Auto | Docker build + push |
| **deploy-dev** | dev | Manual | SSH deploy на DEV |
| **deploy-prod** | main | Manual | SSH deploy на PROD |

---

## 🚀 Deploy вручную

1. **GitLab → CI/CD → Pipelines**
2. Найти pipeline
3. Нажать **▶️ Play** кнопку
4. Ждать выполнения (10-30 сек)
5. Проверить логи

---

## ✅ Health Check

После deploy проверяется здоровье приложения:

```bash
# Streamlit UI
curl http://localhost:8501/_stcore/health

# Docker containers
docker compose ps

# Логи
docker compose logs -f telegram-bot
```

---

## 🔐 SSH ключи

### Генерировать

```bash
ssh-keygen -t ed25519 -f lsr_skud_deploy -C "LSR_SKUD"

# Приватный ключ (в GitLab Secret):
cat lsr_skud_deploy

# Публичный ключ (на сервере):
cat lsr_skud_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## 📋 Переменные в Pipeline

**Автоматические:**
```
$CI_COMMIT_BRANCH      # dev, main, feature/xxx
$CI_COMMIT_SHA         # Хеш коммита
$CI_COMMIT_SHORT_SHA   # Короткий хеш
$CI_COMMIT_AUTHOR      # Автор коммита
$CI_REGISTRY_IMAGE     # Image URL
```

**Из Settings:**
```
$DEV_SSH_HOST / $PROD_SSH_HOST
$DEV_SSH_USER / $PROD_SSH_USER
$DEV_SSH_KEY / $PROD_SSH_KEY
```

---

## 🔍 Мониторинг

### Смотреть Pipeline

```bash
# Локально через git
git log --oneline -5

# В GitLab UI
CI/CD → Pipelines → выбрать pipeline → смотреть stages
```

### Логи Deploy

В GitLab нажать на job → смотреть полный лог:

```
🚀 Deploying to DEV environment...
cd /home/safar/Project/LSR_SKUD
git fetch origin dev
docker pull registry/lsr-skud:latest-dev
docker compose up -d
✅ DEV deployment completed
```

### На сервере

```bash
docker compose ps              # контейнеры
docker compose logs -f NAME    # логи
tail -50 data/gate_control.db # БД (если нужна)
```

---

## 🐛 Быстрая отладка

**Runner не видится:**
```bash
sudo gitlab-runner status
sudo systemctl restart gitlab-runner
```

**Deploy не работает:**
```bash
ssh -i key user@host "echo OK"
ssh user@host "docker ps"
```

**Build падает:**
```bash
docker system df    # место
docker system prune # очистить
```

**Образ не собирается:**
```bash
docker build -t test .
# Смотреть ошибки
```

---

## 📞 Быстрая помощь

**Как запустить pipeline?**  
→ `git push origin dev` (автоматически запустится)

**Как запустить deploy?**  
→ GitLab UI → CI/CD → Pipelines → Play кнопка

**Как посмотреть логи?**  
→ GitLab → CI/CD → Pipelines → job → логи

**Как откатить deploy?**  
→ Есть автоматический backup перед deploy PROD

**Как добавить secret?**  
→ Settings → CI/CD → Variables → New

---

## 🎯 Типичный день разработчика

```bash
# Утро - новая фишер
git checkout -b feature/cool-thing
# ... code, test локально ...

# На обед - готово к review
git add .
git commit -m "feat: cool thing"
git push origin feature/cool-thing
# ✅ Pipeline запускается (lint + test)

# После обеда - merge в dev
git checkout dev
git merge feature/cool-thing
git push origin dev
# ✅ Pipeline: lint → test → build → ready for deploy:dev

# В конце дня - deploy на dev
# GitLab UI → Play deploy:dev button
# ✅ Приложение обновлено на dev сервере!

# Можно идти домой! 🏃
```

---

**GitLab Server:** `10.205.111.13:180`  
**Runner:** Docker на той же машине  
**Файл:** `.gitlab-ci.yml` в корне репо  

**✅ Все готово к использованию!**

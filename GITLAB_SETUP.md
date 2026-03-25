# 🚀 GitLab CI/CD Setup для LSR_SKUD

## 📋 Информация

- **GitLab Server:** `10.205.111.13:180`
- **Project:** LSR_SKUD
- **CI/CD File:** `.gitlab-ci.yml`
- **Runner:** Docker runner на `10.205.111.13:180`

---

## ⚙️ GitLab Runner Установка

### 1. На машине с GitLab (10.205.111.13)

#### Проверить что Docker установлен
```bash
docker --version
docker compose version
```

#### Установить GitLab Runner
```bash
# На Linux (если еще не установлен)
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt-get install gitlab-runner

# Или использовать Docker
docker pull gitlab/gitlab-runner:latest
```

#### Зарегистрировать Runner
```bash
# Получить Registration Token из GitLab:
# Settings → CI/CD → Runners

sudo gitlab-runner register \
  --url http://10.205.111.13:180 \
  --registration-token YOUR_REGISTRATION_TOKEN \
  --executor docker \
  --docker-image docker:latest \
  --docker-privileged \
  --docker-volumes /var/run/docker.sock:/var/run/docker.sock \
  --description "LSR_SKUD Docker Runner" \
  --tag-list docker,lsr-skud \
  --run-untagged
```

#### Проверить что runner запущен
```bash
sudo gitlab-runner status
sudo gitlab-runner list
docker ps | grep gitlab-runner
```

### 2. В GitLab UI

#### Добавить Secrets (для Deploy)

Перейти в: **Settings → CI/CD → Variables**

```
DEV_SSH_HOST        = <IP DEV сервера>
DEV_SSH_USER        = ubuntu (или root)
DEV_SSH_PORT        = 22
DEV_SSH_KEY         = <приватный SSH ключ>

PROD_SSH_HOST       = <IP PROD сервера>
PROD_SSH_USER       = root
PROD_SSH_PORT       = 22
PROD_SSH_KEY        = <приватный SSH ключ>

SLACK_WEBHOOK       = <Slack webhook URL> (опционально)

CI_REGISTRY_USER    = safar
CI_REGISTRY_PASSWORD = <GitLab personal access token>
```

#### Генерировать SSH ключи (если нужны)
```bash
ssh-keygen -t ed25519 -f lsr_skud_deploy -C "LSR_SKUD Runner"

# На DEV/PROD серверах
cat lsr_skud_deploy.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## 🔄 GitLab CI/CD Stages

### 1. **Lint Stage**
- Проверка кода (flake8, black, mypy)
- Запускается на всех ветках
- Можно игнорировать ошибки

### 2. **Test Stage**
- Unit тесты (pytest)
- Coverage report
- Артефакты (HTML отчет)
- Запускается на всех ветках

### 3. **Build Stage**
- Docker build (production image)
- Docker build (batch-worker image)
- Push в GitLab Registry
- Запускается только на `dev` и `main`

### 4. **Deploy DEV Stage**
- SSH подключение к DEV серверу
- Git pull latest code
- Docker pull новых образов
- docker compose restart
- Health check
- **Когда:** на `dev` ветке (manual trigger)

### 5. **Deploy PROD Stage**
- Backup БД перед деплоем
- SSH подключение к PROD серверу
- Git pull latest code
- Docker pull новых образов
- docker compose restart
- Health check
- **Когда:** на `main` ветке (manual trigger)

---

## 🚀 Использование

### Запуск Pipeline вручную

```bash
# Coммит в dev ветку
git checkout dev
git add .
git commit -m "Feature: add new component"
git push origin dev

# GitLab автоматически запустит:
# ✅ lint
# ✅ test
# ✅ build
# ⏳ deploy:dev (manual trigger)
```

### Запуск Deploy вручную

1. Перейти в **CI/CD → Pipelines**
2. Выбрать нужный pipeline
3. Нажать кнопку **Play** рядом с `deploy:dev` или `deploy:prod`
4. Ждать выполнения

Или через CLI:
```bash
# Запуск конкретного job
curl --request POST \
  --header "PRIVATE-TOKEN: <your_access_token>" \
  "http://10.205.111.13:180/api/v4/projects/<project_id>/jobs/<job_id>/play"
```

### Автоматический Deploy

Если убрать `when: manual` в `.gitlab-ci.yml`, будет автоматический deploy при успешной сборке.

---

## 📊 Pipeline Flow

```
Push в ветку
    ↓
[lint:code] ─────────┐
    ↓                 │
[test:unit] ◄────────┘
    ↓
[build:docker]
    ├─ Build production image
    ├─ Build batch-worker image
    └─ Push в registry
    ↓
[deploy:dev] (для dev ветки)
    ├─ SSH подключение
    ├─ Git pull
    ├─ Docker pull
    ├─ docker compose up -d
    └─ Health check
    
    или

[deploy:prod] (для main ветки)
    ├─ Backup БД
    ├─ SSH подключение
    ├─ Git pull
    ├─ Docker pull
    ├─ docker compose up -d
    └─ Health check
```

---

## 🔧 Troubleshooting

### Runner не видится в GitLab

```bash
# Проверить статус runner
sudo gitlab-runner status
sudo gitlab-runner verify

# Перезагрузить runner
sudo systemctl restart gitlab-runner

# Если Docker runner
docker logs <runner_container_id>
```

### Deploy не работает

```bash
# Проверить SSH ключ
ssh -i <key> user@host "echo OK"

# Проверить Docker доступ
ssh -i <key> user@host "docker ps"

# Проверить git доступ
ssh -i <key> user@host "cd /home/safar/Project/LSR_SKUD && git status"
```

### Pipeline зависает на build

```bash
# Проверить Docker daemon
docker info
docker system prune -f  # Очистить лишнее

# На runner машине
docker images  # Проверить образы
docker system df  # Проверить место
```

### Нет доступа к Registry

- Проверить CI_REGISTRY_USER и CI_REGISTRY_PASSWORD
- Убедиться что GitLab Container Registry включен
- `Settings → General → Container Registry`

---

## 📝 Переменные в Pipeline

**Автоматические переменные GitLab:**
- `$CI_COMMIT_BRANCH` - текущая ветка
- `$CI_COMMIT_SHA` - хеш коммита
- `$CI_COMMIT_SHORT_SHA` - короткий хеш
- `$CI_COMMIT_MESSAGE` - сообщение коммита
- `$CI_COMMIT_AUTHOR` - автор коммита
- `$CI_JOB_ID` - ID job
- `$CI_PIPELINE_ID` - ID pipeline
- `$CI_REGISTRY_IMAGE` - образ в registry

**Кастомные переменные:**
- `$DEV_SSH_HOST`, `$DEV_SSH_USER`, `$DEV_SSH_KEY`, `$DEV_SSH_PORT`
- `$PROD_SSH_HOST`, `$PROD_SSH_USER`, `$PROD_SSH_KEY`, `$PROD_SSH_PORT`
- `$SLACK_WEBHOOK`

---

## ✅ Checklist

- [ ] GitLab Runner установлен и запущен
- [ ] Runner зарегистрирован в GitLab
- [ ] SSH ключи генерированы
- [ ] Secrets добавлены в GitLab
- [ ] `.gitlab-ci.yml` скоммитен в repo
- [ ] Pipeline запущен и прошел успешно
- [ ] Deploy выполнен на DEV
- [ ] Deploy выполнен на PROD

---

## 🚀 Первый Deploy

### 1. Коммит в dev
```bash
git checkout dev
git add .gitlab-ci.yml
git commit -m "ci: add GitLab CI/CD pipeline"
git push origin dev
```

### 2. Проверить Pipeline
- GitLab → CI/CD → Pipelines
- Видеть статусы: lint → test → build

### 3. Запустить Deploy
- Нажать Play рядом с `deploy:dev`
- Ждать выполнения
- Проверить логи

### 4. Проверить на сервере
```bash
ssh user@dev_host
docker compose ps
docker compose logs -f telegram-bot
```

---

## 📞 Полезные команды

```bash
# Просмотр логов runner
sudo journalctl -u gitlab-runner -f

# Перезагрузка runner
sudo systemctl restart gitlab-runner

# Docker runner
docker pull gitlab/gitlab-runner:latest
docker run -d --name gitlab-runner gitlab/gitlab-runner:latest

# Проверка pipeline локально
gitlab-runner exec docker lint:code

# Отладка SSH
ssh -vv -i <key> user@host

# Проверка Docker на сервере
docker system df  # использование
docker images    # образы
docker ps -a     # контейнеры
```

---

## 🎓 Дополнительные ресурсы

- [GitLab CI/CD Docs](https://docs.gitlab.com/ee/ci/)
- [GitLab Runner Docs](https://docs.gitlab.com/runner/)
- [GitLab Container Registry](https://docs.gitlab.com/ee/user/packages/container_registry/)

---

**Статус:** ✅ Готово для использования  
**Дата:** 2026-03-08  
**Версия:** 1.0

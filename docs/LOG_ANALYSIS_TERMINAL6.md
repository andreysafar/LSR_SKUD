# Анализ логов (terminals/6.txt)

## Что получилось

- **Конфиг с .env:** при `set -a && source .env && set +a` конфиг подхватывается: `GPU=True`, `Device=cuda`, токен и Tech Chat ID заданы, Parsec доступен.
- **Бот запускается:** логи показывают `Bot start() called`, `Using Telegram proxy`, `Application started`, `Telegram bot started` — бот поднят и слушает обновления.
- **Авторизация:** пользователь 246484162 отправил контакт 79219130586, Parsec SOAP сессия открыта, ответы отправлены (sendMessage 200 OK).
- **Распознавание на GPU:** загружены детектор ТС (`yolo26n.pt`), детектор номеров, OCR в `gpu=True, offline mode`. Две камеры добавлены, пайплайн запущен.
- **Одна камера онлайн:** `Camera 2 connected: rtsp://...@10.203.4.162:554/...`, вторая камера (test_cam_1) даёт таймауты.

## Что не получилось

1. **Ошибка при /start в группе**  
   `telegram.error.BadRequest: Phone number can be requested in private chats only` — запрос номера телефона показывался в групповом чате. В коде добавлена проверка: в группе бот не запрашивает контакт, а просит перейти в личку.
2. **Камера test_cam_1:** стабильные таймауты (~30 с), переподключение раз в 5 с. Либо неверный URL/сеть, либо камера недоступна.
3. **Камера 2 (HEVC):** в логах много предупреждений `hevc ... Could not find ref with POC`, `First slice in a frame missing` — типичные потери/рассинхрон по RTSP; поток при этом может работать.

## Рекомендации

- Проверить URL и доступность камеры test_cam_1 (ping, VLC по RTSP).
- Убедиться, что в .env задан `TECH_CHAT_ID=-1002161212817` для админ-группы (логи, перезапуски, обратная связь).

## Отскок в Docker (torch.cuda.is_available(): False)

В контейнере GPU недоступен, если хост не отдаёт его в Docker. Что сделано:
- При запросе GPU и отсутствии CUDA пайплайн распознавания **не запускается** (одно предупреждение в лог, без спама ошибок). Бот продолжает работать.
- Чтобы в Docker была GPU: на хосте установить **nvidia-container-toolkit**, перезапустить Docker, в `docker-compose.yml` для сервиса `telegram-bot` указать `runtime: nvidia` или `deploy.resources.reservations.devices: - driver: nvidia; count: 1; capabilities: [gpu]`.

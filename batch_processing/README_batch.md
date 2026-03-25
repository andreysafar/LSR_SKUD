# ANPR Video Processing Daemon

Система пакетной обработки видеофайлов для автоматического распознавания номерных знаков с поддержкой двухпайплайновой архитектуры и обработки нескольких папок одновременно.

## Архитектура

Система использует двухпайплайновую архитектуру для максимальной производительности:

```
┌─────────────────────┐    ┌──────────────────────┐
│   FFmpeg Workers    │    │    Neural Workers    │
│     (CPU only)      │───▶│     (GPU only)       │
│                     │    │                      │
│ • Непрерывная       │    │ • Параллельный       │
│   конвертация       │    │   анализ             │
│ • Нет простоев      │    │ • Максимальная       │
│ • Оптимизация CPU   │    │   загрузка GPU       │
└─────────────────────┘    └──────────────────────┘
```

## Возможности

- **Двухпайплайновая обработка**: Разделение FFmpeg (CPU) и нейронных сетей (GPU)
- **Множественные входные папки**: Одновременная обработка нескольких CAM_* папок
- **Daemon режим**: Работа в фоне без привязки к терминалу
- **Управление процессом**: start/stop/restart/status команды
- **Кэширование форматов**: Автоматическое определение формата видео для каждой папки
- **Прогресс обработки**: Отслеживание количества обработанных файлов
- **Балансировка нагрузки**: Равномерное распределение файлов из разных папок

## Использование

### Python скрипт

#### Запуск с одной папкой
```bash
# Обычный режим
python3 process_videos.py /mnt/iss_media/CAM_14

# Daemon режим
python3 process_videos.py start /mnt/iss_media/CAM_14

# С настройкой воркеров
python3 process_videos.py start /mnt/iss_media/CAM_14 --cpu-workers 6 --gpu-workers 3
```

#### Запуск с несколькими папками
```bash
# Обработка нескольких папок одновременно
python3 process_videos.py start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16

# С настройкой параметров
python3 process_videos.py start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_13 \
    --cpu-workers 4 --gpu-workers 10 --ext .issvd
```

#### Управление daemon
```bash
# Статус процесса
python3 process_videos.py status

# Остановка
python3 process_videos.py stop

# Перезапуск
python3 process_videos.py restart /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16
```

### Bash wrapper

#### Основные команды
```bash
# Запуск с одной папкой
./manage_videos.sh start /mnt/iss_media/CAM_14

# Запуск с несколькими папками
./manage_videos.sh start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16

# С настройкой воркеров
./manage_videos.sh start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16 \
    --cpu-workers 6 --gpu-workers 3

# Управление процессом
./manage_videos.sh status
./manage_videos.sh stop
./manage_videos.sh restart /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16
```

#### Справка
```bash
./manage_videos.sh help
```

## Параметры

### Основные параметры
- `--cpu-workers <N>` - Количество CPU воркеров для FFmpeg (по умолчанию: 4)
- `--gpu-workers <N>` - Количество GPU воркеров для анализа (по умолчанию: 4)
- `--ext <extension>` - Расширение видеофайлов (по умолчанию: .issvd)

### Рекомендуемые настройки для RTX A5000
- **CPU workers**: 6-8 (зависит от количества ядер CPU)
- **GPU workers**: 2-4 (оптимально для GPU памяти)

## Файлы управления

- **PID файл**: `process_videos.pid` - содержит ID запущенного процесса
- **Лог файл**: `process_videos.log` - журнал работы daemon
- **CSV файл**: `plates.csv` - результаты распознавания

## Структура выходных данных

### CSV формат
```csv
folder,subfolder,plate_text,timestamp,image_path
CAM_14,2025-06-16T08+0300,ABC123,2025-06-16 08:15:30,detected_vehicles/20250616_081530_frame50_ABC123.jpg
CAM_16,2025-06-16T08+0300,XYZ789,2025-06-16 08:16:45,detected_vehicles/20250616_081645_frame120_XYZ789.jpg
```

### Изображения
Сохраняются в папку `detected_vehicles/` с именами:
`YYYYMMDD_HHMMSS_frameN_PLATE.jpg`

## Мониторинг

### Проверка статуса
```bash
# Через Python
python3 process_videos.py status

# Через bash wrapper
./manage_videos.sh status
```

### Просмотр логов
```bash
# Последние записи
tail -f process_videos.log

# Последние 50 строк
tail -50 process_videos.log

# Поиск ошибок
grep "ERROR\|✗" process_videos.log
```

### Мониторинг прогресса
В логах отображается прогресс: `✓ [45/120] video_file.issvd`
- ✓/✗ - успех/ошибка обработки
- [45/120] - обработано файлов / общее количество

## Производительность

### Преимущества двухпайплайновой архитектуры
- **Непрерывная работа GPU**: Нейронные сети работают без простоев
- **Параллельная конвертация**: FFmpeg готовит файлы пока GPU анализирует
- **Балансировка нагрузки**: Равномерное распределение задач

### Ожидаемая производительность
- **FFmpeg**: ~25-30 секунд на файл (CPU)
- **Neural**: ~8-15 секунд на файл (GPU)
- **Общее время**: Определяется самым медленным пайплайном

### Множественные папки
При обработке нескольких папок одновременно:
- Файлы чередуются между папками для равномерной нагрузки
- Кэш форматов работает независимо для каждой папки
- Общий прогресс показывается по всем файлам

## Устранение неполадок

### Процесс не останавливается
```bash
# Принудительная остановка
python3 process_videos.py stop

# Если не помогает, найти PID и убить
ps aux | grep process_videos
kill -9 <PID>
```

### Проблемы с GPU
- Проверить доступность CUDA: `nvidia-smi`
- Проверить загрузку GPU в логах
- Уменьшить `--gpu-workers` если нехватка памяти

### Проблемы с FFmpeg
- Проверить доступность `mediainfo` и `ffmpeg`
- Проверить права доступа к папкам
- Увеличить `--cpu-workers` если CPU недогружен

## Примеры использования

### Типичные сценарии
```bash
# Обработка одной камеры в фоне
./manage_videos.sh start /mnt/iss_media/CAM_14

# Обработка нескольких камер с настройкой производительности
./manage_videos.sh start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16 /mnt/iss_media/CAM_18 \
    --cpu-workers 8 --gpu-workers 4

# Быстрая обработка на мощном сервере
./manage_videos.sh start /mnt/iss_media/CAM_* --cpu-workers 12 --gpu-workers 6

# Мониторинг работы
watch -n 5 './manage_videos.sh status && tail -5 process_videos.log'
```

### Автоматизация
```bash
# Скрипт для автоматического запуска всех камер
#!/bin/bash
CAMERAS=(/mnt/iss_media/CAM_*)
./manage_videos.sh start "${CAMERAS[@]}" --cpu-workers 8 --gpu-workers 4
``` 
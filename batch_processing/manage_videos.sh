#!/bin/bash

# Простой wrapper для process_videos.py с поддержкой нескольких папок

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="$SCRIPT_DIR/batch_processor.py"

# Функция помощи
show_help() {
    echo "Использование: $0 <command> [directories...] [options]"
    echo ""
    echo "Команды:"
    echo "  start <dir1> [dir2] ... [options]  - Запустить обработку видео в daemon режиме"
    echo "  stop                               - Остановить daemon процесс"
    echo "  restart <dir1> [dir2] ... [options] - Перезапустить daemon процесс"
    echo "  status                             - Показать статус daemon процесса"
    echo ""
    echo "Опции:"
    echo "  --ext <extension>         - Расширение файлов (по умолчанию .issvd)"
    echo "  --cpu-workers <number>    - Количество CPU воркеров для FFmpeg (по умолчанию 4)"
    echo "  --gpu-workers <number>    - Количество GPU воркеров для анализа (по умолчанию 4)"
    echo ""
    echo "Примеры:"
    echo "  $0 start /mnt/iss_media/CAM_14"
    echo "  $0 start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16 --cpu-workers 6 --gpu-workers 3"
    echo "  $0 stop"
    echo "  $0 status"
    echo ""
    echo "Для обработки нескольких папок одновременно:"
    echo "  $0 start /mnt/iss_media/CAM_14 /mnt/iss_media/CAM_16 /mnt/iss_media/CAM_18"
}

# Проверяем аргументы
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# Извлекаем команду
COMMAND="$1"
shift

# Проверяем валидность команды
case "$COMMAND" in
    start|stop|restart|status)
        ;;
    help|--help|-h)
        show_help
        exit 0
        ;;
    *)
        echo "Ошибка: Неизвестная команда '$COMMAND'"
        echo "Используйте '$0 help' для получения справки"
        exit 1
        ;;
esac

# Для команд stop и status не нужны дополнительные параметры
if [ "$COMMAND" = "stop" ] || [ "$COMMAND" = "status" ]; then
    python3 "$PYTHON_SCRIPT" "$COMMAND"
    exit $?
fi

# Для команд start и restart собираем папки и опции
DIRECTORIES=()
OPTIONS=()

# Парсим аргументы
while [ $# -gt 0 ]; do
    case "$1" in
        --ext|--cpu-workers|--gpu-workers)
            OPTIONS+=("$1" "$2")
            shift 2
            ;;
        --*)
            echo "Ошибка: Неизвестная опция '$1'"
            exit 1
            ;;
        *)
            # Это должна быть директория
            if [ -d "$1" ]; then
                DIRECTORIES+=("$1")
            else
                echo "Предупреждение: Директория '$1' не найдена"
                DIRECTORIES+=("$1")  # Все равно добавляем, пусть Python скрипт обработает
            fi
            shift
            ;;
    esac
done

# Проверяем, что указана хотя бы одна директория
if [ ${#DIRECTORIES[@]} -eq 0 ]; then
    echo "Ошибка: Не указано ни одной директории для обработки"
    echo "Используйте '$0 help' для получения справки"
    exit 1
fi

# Выводим информацию о том, что будем обрабатывать
echo "Команда: $COMMAND"
echo "Директории для обработки:"
for dir in "${DIRECTORIES[@]}"; do
    echo "  - $dir"
done

if [ ${#OPTIONS[@]} -gt 0 ]; then
    echo "Дополнительные опции: ${OPTIONS[*]}"
fi

# Запускаем Python скрипт
exec python3 "$PYTHON_SCRIPT" "$COMMAND" "${DIRECTORIES[@]}" "${OPTIONS[@]}" 
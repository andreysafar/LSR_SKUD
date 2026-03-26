"""Панель администратора УК (Управляющей Компании) — Phase 5.

Вкладки: Собственники, Машиноместа, Пропуска, Чёрный список,
         Инциденты, Отчёты.
Доступ защищён паролем из переменной окружения UK_ADMIN_PASSWORD.
"""
import os
from datetime import date, datetime, timedelta

import streamlit as st

from config import get_config
from db.database import get_db
from reports.exporter import ReportExporter

# ---------------------------------------------------------------------------
# Конфигурация страницы
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Админ-панель УК", layout="wide")

config = get_config()
db = get_db(config.db_path)

# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------
ADMIN_PASSWORD = os.environ.get("UK_ADMIN_PASSWORD", "")

if ADMIN_PASSWORD:
    if "uk_authenticated" not in st.session_state:
        st.session_state.uk_authenticated = False

    if not st.session_state.uk_authenticated:
        st.title("Админ-панель УК")
        st.markdown("### Вход")
        pwd = st.text_input("Пароль:", type="password")
        if st.button("Войти", type="primary"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.uk_authenticated = True
                st.rerun()
            else:
                st.error("Неверный пароль")
        st.stop()

# ---------------------------------------------------------------------------
# Заголовок
# ---------------------------------------------------------------------------
st.title("Админ-панель УК")

# ---------------------------------------------------------------------------
# Боковая панель — сводные счётчики
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Сводка")
    try:
        stats = db.get_stats()
        st.metric("Пользователи", stats.get("total_users", 0))
        st.metric("Активные пропуска", stats.get("active_passes", 0))
        st.metric(
            "Нерешённые инциденты", stats.get("incidents_unresolved", 0)
        )
        st.metric(
            "Пропуска на погрузку", stats.get("loading_passes_active", 0)
        )
        st.metric(
            "Гостевые пропуска", stats.get("guest_passes_active", 0)
        )
    except Exception as exc:
        st.error(f"Ошибка получения статистики: {exc}")

    if ADMIN_PASSWORD and st.session_state.get("uk_authenticated"):
        st.markdown("---")
        if st.button("Выйти"):
            st.session_state.uk_authenticated = False
            st.rerun()

# ---------------------------------------------------------------------------
# Вкладки
# ---------------------------------------------------------------------------
(
    tab_owners,
    tab_spots,
    tab_passes,
    tab_blacklist,
    tab_incidents,
    tab_reports,
) = st.tabs(
    [
        "Собственники",
        "Машиноместа",
        "Пропуска",
        "Чёрный список",
        "Инциденты",
        "Отчёты",
    ]
)

# ===========================================================================
# Вкладка 1: Собственники
# ===========================================================================
with tab_owners:
    st.subheader("Зарегистрированные пользователи")

    try:
        users = db.get_all_users(limit=500)
    except Exception as exc:
        st.error(f"Ошибка загрузки пользователей: {exc}")
        users = []

    if users:
        # Поиск / фильтрация
        col_search1, col_search2 = st.columns(2)
        with col_search1:
            filter_name = st.text_input(
                "Поиск по ФИО", placeholder="Иванов", key="owners_name"
            )
        with col_search2:
            filter_phone = st.text_input(
                "Поиск по телефону", placeholder="+7", key="owners_phone"
            )

        filtered = users
        if filter_name:
            fn_lower = filter_name.lower()
            filtered = [
                u for u in filtered
                if fn_lower in (u.get("full_name") or "").lower()
            ]
        if filter_phone:
            filtered = [
                u for u in filtered
                if filter_phone in (u.get("phone_number") or "")
            ]

        display_columns = [
            "user_id", "full_name", "phone_number",
            "parsec_person_id", "created_at",
        ]
        display_data = [
            {k: u.get(k, "") for k in display_columns} for u in filtered
        ]

        st.caption(f"Найдено: {len(display_data)} из {len(users)}")
        st.dataframe(
            display_data,
            column_config={
                "user_id": st.column_config.NumberColumn("ID"),
                "full_name": st.column_config.TextColumn("ФИО"),
                "phone_number": st.column_config.TextColumn("Телефон"),
                "parsec_person_id": st.column_config.TextColumn("Parsec ID"),
                "created_at": st.column_config.TextColumn("Создан"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Пользователи не найдены.")

# ===========================================================================
# Вкладка 2: Машиноместа
# ===========================================================================
with tab_spots:
    st.subheader("Машиноместа")

    # --- Список машиномест ---
    try:
        spots = db.get_parking_spots()
    except Exception as exc:
        st.error(f"Ошибка загрузки машиномест: {exc}")
        spots = []

    if spots:
        st.caption(f"Всего машиномест: {len(spots)}")
        st.dataframe(
            spots,
            column_config={
                "id": st.column_config.NumberColumn("ID"),
                "spot_number": st.column_config.TextColumn("Номер М/М"),
                "owner_parsec_id": st.column_config.TextColumn("Parsec ID владельца"),
                "owner_user_id": st.column_config.NumberColumn("ID пользователя"),
                "level": st.column_config.TextColumn("Уровень"),
                "section": st.column_config.TextColumn("Секция"),
                "is_active": st.column_config.CheckboxColumn("Активно"),
                "created_at": st.column_config.TextColumn("Создано"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Машиноместа не найдены.")

    st.markdown("---")

    # --- Добавление нового машиноместа ---
    st.markdown("#### Добавить машиноместо")

    # Загружаем пользователей для выбора владельца
    try:
        all_users_for_spots = db.get_all_users(limit=500)
        user_options = {
            f"{u.get('full_name') or 'ID ' + str(u['user_id'])} — {u.get('phone_number', '')}": u["user_id"]
            for u in all_users_for_spots
        }
    except Exception:
        user_options = {}

    with st.form("add_parking_spot"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            new_spot_number = st.text_input("Номер М/М *", placeholder="А-001")
        with col2:
            new_level = st.text_input("Уровень", placeholder="-1")
        with col3:
            new_section = st.text_input("Секция", placeholder="А")
        with col4:
            owner_label = st.selectbox(
                "Владелец",
                options=["— не выбран —"] + list(user_options.keys()),
                key="spot_owner_select",
            )

        submitted_spot = st.form_submit_button("Добавить машиноместо", type="primary")
        if submitted_spot:
            if not new_spot_number.strip():
                st.error("Укажите номер машиноместа.")
            else:
                owner_uid = (
                    user_options[owner_label]
                    if owner_label != "— не выбран —"
                    else None
                )
                try:
                    db.save_parking_spot(
                        spot_number=new_spot_number.strip(),
                        owner_user_id=owner_uid,
                        level=new_level.strip() or None,
                        section=new_section.strip() or None,
                    )
                    st.success(f"Машиноместо «{new_spot_number.strip()}» добавлено.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ошибка при добавлении: {exc}")

    st.markdown("---")

    # --- Удаление машиноместа ---
    st.markdown("#### Удалить машиноместо")
    if spots:
        spot_numbers = [s["spot_number"] for s in spots]
        del_spot = st.selectbox("Выберите М/М для удаления", spot_numbers, key="del_spot_select")
        if st.button("Удалить машиноместо", type="secondary"):
            try:
                with db.get_connection() as conn:
                    conn.execute(
                        "UPDATE parking_spots SET is_active = 0 WHERE spot_number = ?",
                        (del_spot,),
                    )
                st.success(f"Машиноместо «{del_spot}» деактивировано.")
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка при удалении: {exc}")
    else:
        st.info("Нет машиномест для удаления.")

# ===========================================================================
# Вкладка 3: Пропуска
# ===========================================================================
with tab_passes:
    st.subheader("Активные пропуска")

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        subtype_filter = st.selectbox(
            "Тип пропуска",
            ["Все", "regular", "loading", "guest"],
            key="passes_subtype",
        )
    with col_f2:
        date_from_passes = st.date_input(
            "Дата с",
            value=date.today() - timedelta(days=30),
            key="passes_date_from",
        )
    with col_f3:
        date_to_passes = st.date_input(
            "Дата по",
            value=date.today(),
            key="passes_date_to",
        )

    try:
        passes = db.get_active_passes_by_subtype(
            subtype=None if subtype_filter == "Все" else subtype_filter
        )
    except Exception as exc:
        st.error(f"Ошибка загрузки пропусков: {exc}")
        passes = []

    # Фильтр по дате создания
    if passes and (date_from_passes or date_to_passes):
        dt_from = datetime.combine(date_from_passes, datetime.min.time())
        dt_to = datetime.combine(date_to_passes, datetime.max.time())
        filtered_passes = []
        for p in passes:
            raw = p.get("created_at", "")
            try:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
                    try:
                        dt = datetime.strptime(raw, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    continue
                if dt_from <= dt <= dt_to:
                    filtered_passes.append(p)
            except Exception:
                pass
        passes = filtered_passes

    if passes:
        st.caption(f"Найдено: {len(passes)}")
        st.dataframe(
            passes,
            column_config={
                "id": st.column_config.NumberColumn("ID"),
                "plate_number": st.column_config.TextColumn("Номер т/с"),
                "pass_subtype": st.column_config.TextColumn("Тип"),
                "vehicle_brand": st.column_config.TextColumn("Марка"),
                "driver_phone": st.column_config.TextColumn("Тел. водителя"),
                "valid_from": st.column_config.TextColumn("Начало"),
                "valid_to": st.column_config.TextColumn("Окончание"),
                "status": st.column_config.TextColumn("Статус"),
                "user_id": st.column_config.NumberColumn("ID пользователя"),
                "created_at": st.column_config.TextColumn("Создан"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Активные пропуска не найдены.")

    st.markdown("---")
    st.markdown("#### Отменить пропуск")
    if passes:
        pass_ids = [p["id"] for p in passes]
        cancel_id = st.number_input(
            "ID пропуска для отмены",
            min_value=1,
            step=1,
            key="cancel_pass_id",
        )
        if st.button("Отменить пропуск", type="secondary"):
            try:
                ok = db.deactivate_pass(int(cancel_id))
                if ok:
                    st.success(f"Пропуск #{cancel_id} отменён.")
                    st.rerun()
                else:
                    st.warning("Пропуск не найден или уже отменён.")
            except Exception as exc:
                st.error(f"Ошибка при отмене: {exc}")
    else:
        st.info("Нет активных пропусков для отмены.")

# ===========================================================================
# Вкладка 4: Чёрный список
# ===========================================================================
with tab_blacklist:
    st.subheader("Чёрный список")

    try:
        blacklist = db.get_blacklisted_users(limit=200)
    except Exception as exc:
        st.error(f"Ошибка загрузки чёрного списка: {exc}")
        blacklist = []

    if blacklist:
        st.caption(f"Всего в чёрном списке: {len(blacklist)}")
        st.dataframe(
            blacklist,
            column_config={
                "owner_parsec_id": st.column_config.TextColumn("Parsec ID"),
                "owner_user_id": st.column_config.NumberColumn("ID пользователя"),
                "full_name": st.column_config.TextColumn("ФИО"),
                "phone_number": st.column_config.TextColumn("Телефон"),
                "violation_type": st.column_config.TextColumn("Тип нарушения"),
                "count": st.column_config.NumberColumn("Кол-во нарушений"),
                "last_violation_at": st.column_config.TextColumn("Последнее нарушение"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Чёрный список пуст.")

    st.markdown("---")

    col_bl1, col_bl2 = st.columns(2)

    # --- Добавить в ЧС ---
    with col_bl1:
        st.markdown("#### Добавить в чёрный список")
        with st.form("add_blacklist"):
            bl_parsec_id = st.text_input("Parsec ID *", placeholder="12345")
            bl_user_id = st.number_input(
                "ID пользователя (необязательно)", min_value=0, step=1, value=0
            )
            bl_violation = st.text_input(
                "Тип нарушения", value="manual"
            )
            submitted_bl = st.form_submit_button("Добавить", type="primary")
            if submitted_bl:
                if not bl_parsec_id.strip():
                    st.error("Укажите Parsec ID.")
                else:
                    try:
                        db.add_to_blacklist(
                            owner_parsec_id=bl_parsec_id.strip(),
                            owner_user_id=int(bl_user_id) if bl_user_id else None,
                            violation_type=bl_violation.strip() or "manual",
                        )
                        st.success(
                            f"Parsec ID «{bl_parsec_id.strip()}» добавлен в чёрный список."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Ошибка: {exc}")

    # --- Удалить из ЧС ---
    with col_bl2:
        st.markdown("#### Удалить из чёрного списка")
        with st.form("remove_blacklist"):
            rm_parsec_id = st.text_input(
                "Parsec ID для удаления *", placeholder="12345"
            )
            rm_violation = st.text_input(
                "Тип нарушения (пусто — удалить все)",
                placeholder="manual",
            )
            submitted_rm = st.form_submit_button("Удалить", type="secondary")
            if submitted_rm:
                if not rm_parsec_id.strip():
                    st.error("Укажите Parsec ID.")
                else:
                    try:
                        removed = db.remove_from_blacklist(
                            owner_parsec_id=rm_parsec_id.strip(),
                            violation_type=rm_violation.strip() or None,
                        )
                        if removed:
                            st.success(
                                f"Удалено {removed} записей для Parsec ID «{rm_parsec_id.strip()}»."
                            )
                            st.rerun()
                        else:
                            st.warning("Записи не найдены.")
                    except Exception as exc:
                        st.error(f"Ошибка: {exc}")

# ===========================================================================
# Вкладка 5: Инциденты
# ===========================================================================
with tab_incidents:
    st.subheader("Инциденты")

    col_inc1, col_inc2 = st.columns(2)
    with col_inc1:
        inc_status = st.selectbox(
            "Статус",
            ["Все", "Нерешённые", "Решённые"],
            key="inc_status",
        )
    with col_inc2:
        inc_type_filter = st.text_input(
            "Тип инцидента (фильтр)", placeholder="unauthorized_access", key="inc_type"
        )

    resolved_map = {"Все": None, "Нерешённые": False, "Решённые": True}
    resolved_val = resolved_map[inc_status]

    try:
        incidents = db.get_incidents(
            limit=200,
            incident_type=inc_type_filter.strip() or None,
            resolved=resolved_val,
        )
    except Exception as exc:
        st.error(f"Ошибка загрузки инцидентов: {exc}")
        incidents = []

    if incidents:
        st.caption(f"Найдено: {len(incidents)}")
        st.dataframe(
            incidents,
            column_config={
                "id": st.column_config.NumberColumn("ID"),
                "incident_type": st.column_config.TextColumn("Тип"),
                "description": st.column_config.TextColumn("Описание"),
                "plate_number": st.column_config.TextColumn("Номер т/с"),
                "apartment": st.column_config.TextColumn("Квартира"),
                "created_at": st.column_config.TextColumn("Дата"),
                "resolved_at": st.column_config.TextColumn("Решено"),
                "resolution": st.column_config.TextColumn("Решение"),
            },
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Инциденты не найдены.")

    st.markdown("---")
    st.markdown("#### Закрыть инцидент")

    with st.form("resolve_incident"):
        resolve_id = st.number_input(
            "ID инцидента *", min_value=1, step=1, key="resolve_inc_id"
        )
        resolution_text = st.text_area(
            "Текст решения *", placeholder="Описание принятых мер..."
        )
        submitted_resolve = st.form_submit_button("Закрыть инцидент", type="primary")
        if submitted_resolve:
            if not resolution_text.strip():
                st.error("Укажите текст решения.")
            else:
                try:
                    ok = db.resolve_incident(
                        incident_id=int(resolve_id),
                        resolution=resolution_text.strip(),
                    )
                    if ok:
                        st.success(f"Инцидент #{resolve_id} закрыт.")
                        st.rerun()
                    else:
                        st.warning("Инцидент не найден или уже закрыт.")
                except Exception as exc:
                    st.error(f"Ошибка: {exc}")

# ===========================================================================
# Вкладка 6: Отчёты
# ===========================================================================
with tab_reports:
    st.subheader("Экспорт отчётов")

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        report_date_from = st.date_input(
            "Дата с",
            value=date.today() - timedelta(days=30),
            key="report_date_from",
        )
    with col_r2:
        report_date_to = st.date_input(
            "Дата по",
            value=date.today(),
            key="report_date_to",
        )
    with col_r3:
        report_format = st.selectbox(
            "Формат",
            ["CSV", "Excel"],
            key="report_format",
        )

    report_type = st.selectbox(
        "Тип отчёта",
        [
            "Реестр пропусков",
            "Чёрный список",
            "Инциденты",
            "Журнал въезда/выезда",
        ],
        key="report_type",
    )

    # Дополнительный фильтр для пропусков
    passes_subtype_report = None
    if report_type == "Реестр пропусков":
        passes_subtype_report = st.selectbox(
            "Подтип пропуска",
            ["Все", "regular", "loading", "guest"],
            key="report_subtype",
        )
        if passes_subtype_report == "Все":
            passes_subtype_report = None

    if st.button("Сформировать отчёт", type="primary"):
        exporter = ReportExporter(db)
        fmt = "excel" if report_format == "Excel" else "csv"
        date_from_str = report_date_from.strftime("%Y-%m-%d")
        date_to_str = report_date_to.strftime("%Y-%m-%d") + " 23:59:59"

        try:
            if report_type == "Реестр пропусков":
                data_bytes = exporter.export_passes(
                    date_from=date_from_str,
                    date_to=date_to_str,
                    subtype=passes_subtype_report,
                    export_format=fmt,
                )
                filename = f"passes_{report_date_from}_{report_date_to}"
            elif report_type == "Чёрный список":
                data_bytes = exporter.export_blacklist(export_format=fmt)
                filename = f"blacklist_{date.today()}"
            elif report_type == "Инциденты":
                data_bytes = exporter.export_incidents(
                    date_from=date_from_str,
                    date_to=date_to_str,
                    export_format=fmt,
                )
                filename = f"incidents_{report_date_from}_{report_date_to}"
            elif report_type == "Журнал въезда/выезда":
                data_bytes = exporter.export_entry_exit_log(
                    date_from=date_from_str,
                    date_to=date_to_str,
                    export_format=fmt,
                )
                filename = f"entry_exit_{report_date_from}_{report_date_to}"
            else:
                st.error("Неизвестный тип отчёта.")
                data_bytes = None
                filename = "report"

            if data_bytes:
                ext = "xlsx" if fmt == "excel" else "csv"
                mime = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if fmt == "excel"
                    else "text/csv"
                )
                st.download_button(
                    label=f"Скачать {report_type} ({report_format})",
                    data=data_bytes,
                    file_name=f"{filename}.{ext}",
                    mime=mime,
                )
        except RuntimeError as exc:
            # Excel без pandas/openpyxl
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Ошибка формирования отчёта: {exc}")

import streamlit as st
import io
import os
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
from database_module import get_detailed_report
from datetime import datetime, timedelta
import psutil

# --- 1. ЗАГРУЗКА КОНФИГУРАЦИИ ---
load_dotenv()
ADMIN_PASSWORD = os.getenv("ADMIN_PWD")
USER_PASSWORD = os.getenv("USER_PWD")

st.set_page_config(page_title="Report IT", layout="wide")

# --- 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def to_excel_combined(summary_df, detailed_df):
    try:
        output = io.BytesIO()
        # Подготовка детальных данных: только уникальные по ID_TICKET
        detailed_unique = detailed_df.drop_duplicates(subset=['ID_TICKET']).copy()

        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Лист 1: Сводная аналитика
            summary_df.to_excel(writer, sheet_name='Analytics', index=True)
            # Лист 2: Детальные данные (Уникальные заявки + Rules)
            detailed_unique.to_excel(writer, sheet_name='Detailed_Tickets', index=False)

            # Авто-подбор ширины колонок (опционально для красоты)
            for sheet in writer.sheets:
                writer.sheets[sheet].set_column('A:Z', 20)

        return output.getvalue()
    except Exception as e:
        st.error(f"❌ Ошибка при создании Excel: {e}")
        return None

# --- 2. КЭШИРОВАНИЕ ---
@st.cache_data(show_spinner="Загрузка данных из кэша...", ttl=3600, max_entries=2)
def get_cached_report(start_date, end_date):
    # ПРОВЕРКА ПАМЯТИ ПЕРЕД ВЫПОЛНЕНИЕМ
    mem = psutil.virtual_memory()
    # Если свободно меньше 15% ОЗУ (около 300МБ для вашей VM)
    if mem.percent > 90:
        st.warning()
        st.cache_data.clear()
    return get_detailed_report(start_date, end_date)


# --- 3. ФУНКЦИЯ АВТОРИЗАЦИИ ---
def check_auth():
    if "authenticated" not in st.session_state:
        st.title("🔐 Вход в систему IT")
        col_login, _ = st.columns([1, 2])
        with col_login:
            user = st.text_input("Логин", key="login_user")
            pwd = st.text_input("Пароль", type="password", key="login_pwd")
            if st.button("Войти", use_container_width=True):
                if user == "admin" and pwd == ADMIN_PASSWORD:
                    st.session_state.update({"authenticated": True, "role": "admin"})
                    st.rerun()
                elif user == "user" and pwd == USER_PASSWORD:
                    st.session_state.update({"authenticated": True, "role": "user"})
                    st.rerun()
                else:
                    st.error("❌ Неверный логин или пароль")
        return False
    return True


# --- 4. ОСНОВНОЙ БЛОК ПРИЛОЖЕНИЯ ---
if check_auth():
    if st.sidebar.button("Выйти"):
        del st.session_state["authenticated"]
        st.rerun()

    st.sidebar.success(f"Роль: {st.session_state['role']}")
    st.sidebar.header("⚙️ Настройки периода")
    today = datetime.now().date()

    quick_choice = st.sidebar.radio("Быстрый выбор:", ["Текущая неделя", "Последние 30 дней", "Произвольный период"],
                                    index=2)

    if quick_choice == "Текущая неделя":
        start_default = today - timedelta(days=today.weekday())
        end_default = today
    elif quick_choice == "Последние 30 дней":
        start_default = today - timedelta(days=30)
        end_default = today
    else:
        start_default = today - timedelta(days=7)
        end_default = today

    date_range = st.sidebar.date_input("Укажите диапазон:", value=(start_default, end_default), max_value=today)

    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_dt, end_dt = date_range
    else:
        st.warning("⚠️ Пожалуйста, выберите **дату окончания** периода.")
        st.stop()

    st.title("🔍 Отчет IT")
    st.info(f"Выбранный период: {start_dt.strftime('%d.%m.%Y')} — {end_dt.strftime('%d.%m.%Y')}")

    df = get_cached_report(start_dt, end_dt)

    if not df.empty:
        df.columns = [col.upper() for col in df.columns]

        # ПОДГОТОВКА ДАННЫХ
        df_unique = df.drop_duplicates(subset=['ID_TICKET']).copy()
        df_unique['DT_OBJ'] = pd.to_datetime(df_unique['TICKET_CREATED'], dayfirst=True, errors='coerce')
        df_unique['DATE_ONLY'] = df_unique['DT_OBJ'].dt.date

        total_unique = len(df_unique)
        closed_tickets = df_unique[
            df_unique['TICKET_CLOSED'].notna() & (df_unique['TICKET_CLOSED'].astype(str).str.strip() != '')].shape[0]
        in_progress = total_unique - closed_tickets

        # --- БЛОК МЕТРИК ---
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Всего строк (логи)", f"{len(df):,}".replace(",", " "))
        col_m2.metric("Уникальных заявок", f"{total_unique:,}".replace(",", " "))
        col_m3.metric("Закрыто уникальных", f"{closed_tickets:,}".replace(",", " "))
        col_m4.metric("Заявок в работе", f"{in_progress:,}".replace(",", " "))

        # --- 📈 ГРАФИК  ---
        st.markdown("---")
        st.subheader("📈 График за период")

        if not df_unique.empty:
            delta_days = (end_dt - start_dt).days

            if delta_days <= 7:
                freq, d_fmt, grid_step = 'D', "%d.%m", 86400000
            elif delta_days <= 31:
                freq, d_fmt, grid_step = 'D', "%d.%m", 86400000
            elif delta_days <= 180:
                freq, d_fmt, grid_step = 'W-MON', "W%V<br>%d.%m", 7 * 86400000
            else:
                freq, d_fmt, grid_step = 'MS', "%b %Y", "M1"

            df_trend = df_unique.copy().set_index('DT_OBJ')

            resampled_total = df_trend.resample(freq, label='left')['ID_TICKET'].count()
            resampled_closed = df_trend[df_trend['TICKET_CLOSED'].notna()].resample(freq, label='left')[
                'ID_TICKET'].count()

            daily_stats = pd.DataFrame({
                'Уникальных_заявок': resampled_total,
                'Закрыто': resampled_closed
            }).fillna(0)

            daily_stats['diff'] = daily_stats['Уникальных_заявок'].diff()
            daily_stats['В_работе'] = daily_stats['Уникальных_заявок'] - daily_stats['Закрыто']
            daily_stats = daily_stats.reset_index()

            chart_mode = 'lines+markers+text' if len(daily_stats) > 1 else 'markers+text'

            fig = go.Figure()

            text_labels_1 = []
            for v, d in zip(daily_stats['Уникальных_заявок'], daily_stats['diff']):
                formatted_v = f"{int(v):,}".replace(",", " ")
                label = f"<b>{formatted_v}</b>"
                if not pd.isna(d) and delta_days > 1:
                    if d > 0:
                        label += f"<br><span style='color:#2ca02c; font-size:14px; font-weight:bold;'>+</span>"
                    elif d < 0:
                        label += f"<br><span style='color:#d62728; font-size:14px; font-weight:bold;'>-</span>"
                text_labels_1.append(label)

            fig.add_trace(go.Scatter(
                x=daily_stats['DT_OBJ'], y=daily_stats['Уникальных_заявок'],
                mode=chart_mode, name='Уникальных заявок',
                line=dict(color='#1f77b4', width=4),
                text=text_labels_1, textposition="top center"
            ))

            fig.add_trace(go.Scatter(
                x=daily_stats['DT_OBJ'], y=daily_stats['Закрыто'],
                mode=chart_mode, name='Закрыто',
                line=dict(color='#2ca02c', dash='dot'),
                text=daily_stats['Закрыто'].astype(int), textposition="bottom center"
            ))

            fig.add_trace(go.Scatter(
                x=daily_stats['DT_OBJ'], y=daily_stats['В_работе'],
                mode=chart_mode, name='В работе',
                line=dict(color='#d62728'),
                text=daily_stats['В_работе'].astype(int), textposition="middle right"
            ))

            fig.update_layout(
                xaxis=dict(type='date', tickformat=d_fmt,
                           tickmode='auto' if delta_days <= 7 else 'linear',
                           dtick=grid_step, automargin=True),
                hovermode="x unified", height=550,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(t=100, l=40, r=40, b=40)
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Нет данных для отображения графика.")

        # --- 📊 АНАЛИТИКА ROOT CAUSE ---
        st.markdown("---")
        st.subheader("📊 Аналитика Root Cause")

        df_pivot_base = df_unique.dropna(subset=['ROOT_CAUSE'])
        df_pivot_base = df_pivot_base[df_pivot_base['ROOT_CAUSE'].astype(str).str.strip() != ""]

        if not df_pivot_base.empty:
            df_pivot_base = df_pivot_base.sort_values('DT_OBJ')
            df_pivot_base['SORT_MONTH'] = df_pivot_base['DT_OBJ'].dt.strftime('%Y-%m')
            df_pivot_base['DISPLAY_MONTH'] = df_pivot_base['DT_OBJ'].dt.strftime('%Y %b')

            pivot_count = df_pivot_base.pivot_table(
                index='ROOT_CAUSE', columns=['SORT_MONTH', 'DISPLAY_MONTH'],
                values='ID_TICKET', aggfunc='count', fill_value=0
            )

            current_months = pivot_count.columns.get_level_values(1).tolist()
            pivot_count.columns = current_months

            final_df = pd.DataFrame(index=pivot_count.index)
            month_totals = {}

            for i, col in enumerate(pivot_count.columns):
                count_series = pivot_count[col]
                if count_series.sum() == 0:
                    continue
                final_df[col] = count_series
                month_totals[col] = count_series.sum()

            row_sums = pivot_count.sum(axis=1)
            grand_total = row_sums.sum()
            final_df["ИТОГО ЗА ПЕРИОД"] = row_sums
            final_df["Доля %"] = ((row_sums / grand_total * 100) if grand_total > 0 else 0).round(1).astype(str) + "%"

            final_df = final_df[final_df["ИТОГО ЗА ПЕРИОД"] > 0]

            total_row_data = month_totals.copy()
            total_row_data["ИТОГО ЗА ПЕРИОД"] = grand_total
            total_row_data["Доля %"] = "100.0%"

            total_row_df = pd.DataFrame(total_row_data, index=["ИТОГО"])
            final_df = pd.concat([final_df, total_row_df])


            def apply_advanced_style(df):
                count_cols = [c for c in df.columns if c not in ["Доля %", "ИТОГО ЗА ПЕРИОД"]]
                styler = df.style
                styler = styler.set_properties(subset=count_cols, **{
                    'font-size': '18px', 'color': '#FFFFFF', 'text-align': 'center', 'min-width': '100px'
                })
                styler = styler.set_properties(subset=pd.IndexSlice[['ИТОГО'], :], **{
                    'background-color': '#1e2129', 'font-weight': 'bold', 'border-top': '2px solid #555'
                })
                styler = styler.set_properties(subset=["ИТОГО ЗА ПЕРИОД"], **{
                    'background-color': 'rgba(255, 215, 0, 0.1)', 'color': '#FFD700', 'font-size': '18px'
                })
                return styler


            st.dataframe(
                apply_advanced_style(final_df),
                use_container_width=True, height=700,
                column_config={
                    "_index": st.column_config.Column("Root Cause", pinned=True, width="large"),
                    "Доля %": st.column_config.Column("Доля %", width="small")
                }
            )

        # --- 📥 БЛОК ВЫГРУЗКИ ---
        st.markdown("---")
        if st.session_state.get("role") == "admin":
            st.subheader("📥 Единый отчет")

            # Проверка существования final_df перед выгрузкой
            if 'final_df' in locals():
                combined_file = to_excel_combined(final_df, df_unique)  # Передаем df_unique для детализации
                if combined_file:
                    st.download_button(
                        label="📥 Скачать полный отчет (Аналитика + Детализация)",
                        data=combined_file,
                        file_name=f"Full_Report_SCU_{start_dt}_{end_dt}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.info("Нет аналитических данных для формирования отчета.")
        else:
            st.warning("🔒 Выгрузка полного отчета доступна только администраторам.")

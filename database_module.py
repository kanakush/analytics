import oracledb
import pandas as pd
from dotenv import load_dotenv
import os
from mapping_rules import RULES # Импортируем наш словарь

# Загружаем переменные из .env в систему
load_dotenv()

host = os.getenv("DB_HOST")
print(f"--- DEBUG ---")
print(f"Host: [{os.getenv('DB_HOST')}]")
print(f"Service Name: [{os.getenv('DB_SERVICE')}]")
print(f"DB_PORT: [{os.getenv('DB_PORT')}] ")
print(f"DB_PASS: [{os.getenv('DB_PASS')}] ")
print(f"DB_USER: [{os.getenv('DB_USER')}] ")

# Безопасное получение переменных
db_host = os.getenv("DB_HOST")
db_port = os.getenv("DB_PORT", "1521") # 1521 по умолчанию
db_name = os.getenv("DB_SERVICE")

# Формируем TNS строку
dsn_tns = f"""(DESCRIPTION=
                (ADDRESS=(PROTOCOL=TCP)(HOST={db_host})(PORT={db_port}))
                (CONNECT_DATA=(SERVICE_NAME={db_name}))
              )"""

DB_CONFIG = {
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASS"),
    "dsn": dsn_tns
}

def get_connection():
    return oracledb.connect(
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        dsn=dsn_tns,
    )

def get_detailed_report(start_date, end_date):
    s_date = start_date.strftime('%Y-%m-%d') + " 00:00:00"
    e_date = end_date.strftime('%Y-%m-%d') + " 23:59:59"

    query = f"""
    SELECT 
    here your script
    """

    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(query)

        # Загрузка данных в DataFrame
        columns = [col[0] for col in cursor.description]
        df = pd.DataFrame(cursor.fetchall(), columns=columns)

        # Очистка TEH от пробелов и применение правил
        df['TEH'] = df['TEH'].astype(str).str.strip()

        # Применение правил Root_cause и создание ссылки
        df['ROOT_CAUSE'] = df['TEH'].map(RULES).fillna('Other')
        df['LINK'] = 'http://sao.kcell.kz/bt/view?id=' + df['ID_TICKET'].astype(str)

        # Определение финального набора столбцов (без MESSAGE)
        final_cols = [
            'ID_TICKET', 'LINK', 'MSISDN', 'CREATED_USER', 'CREATER_USERGROUP',
            'SUBJECT_NAME', 'PRODUCT_NAME', 'TICKET_CREATED', 'TICKET_CLOSED',
            'TEH', 'ROOT_CAUSE'
        ]

        df = df[final_cols]

        cursor.close()
        conn.close()
        return df

    except Exception as e:
        print(f"Ошибка выгрузки: {e}")
        return pd.DataFrame()

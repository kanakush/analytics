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
    SELECT /*+parallel (8)*/ 
        l.id_ticket as "ID_TICKET", 
        l.msisdn as "MSISDN",
        l.created_user as "CREATED_USER", 
        l.creater_usergroup as "CREATER_USERGROUP", 
        l.subject_name as "SUBJECT_NAME", 
        l.product_name as "PRODUCT_NAME",  
        TO_CHAR(l.CREATED_DATE, 'DD.MM.YYYY HH24:MI') as "TICKET_CREATED", 
        TO_CHAR(l.CLOSED_DATE, 'DD.MM.YYYY HH24:MI') as "TICKET_CLOSED",
        MAX(f.FIELD_VALS) as "TEH" 
    FROM 
        APP_PQSWEB.VWI_BT_RT_LIST l
    JOIN 
        APP_PQSWEB.VWI_BT_TICKET_FIELDS f ON l.ID_TICKET = f.id_ticket
    JOIN 
        APP_PQSWEB.VWI_BT_TICKET_ACTIVITY a ON l.ID_TICKET = a.id_ticket
    WHERE 
        l.created_date BETWEEN TO_DATE('{s_date}', 'YYYY-MM-DD HH24:MI:SS') 
                           AND TO_DATE('{e_date}', 'YYYY-MM-DD HH24:MI:SS')
        AND f.ID_FIELD = 456
        AND UPPER(a.group_name) LIKE '%L2%'
    GROUP BY 
        l.id_ticket, 
        l.msisdn, 
        l.created_user, 
        l.creater_usergroup, 
        l.subject_name, 
        l.product_name, 
        l.CREATED_DATE, 
        l.CLOSED_DATE
    ORDER BY 
        l.CREATED_DATE DESC
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

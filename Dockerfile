FROM python:3.10-slim

# Устанавливаем системные зависимости для работы с сетью
RUN apt-get update && apt-get install -y libaio1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Сначала копируем зависимости для кэширования слоев
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Streamlit будет работать на 8501
EXPOSE 8501

CMD ["streamlit", "run", "main.py", "--server.port=8501", "--server.address=0.0.0.0"]
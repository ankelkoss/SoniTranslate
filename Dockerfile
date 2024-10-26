# Используем базовый образ с поддержкой CUDA
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Устанавливаем необходимые инструменты
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget git ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Miniconda
RUN wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O miniconda.sh && \
    bash miniconda.sh -b -p /opt/conda && \
    rm miniconda.sh && \
    /opt/conda/bin/conda init

# Добавляем путь к conda в окружение
ENV PATH=/opt/conda/bin:$PATH

# Создаем и активируем окружение conda
RUN /opt/conda/bin/conda create -n sonitr python=3.10 -y && \
    /opt/conda/bin/conda run -n sonitr pip install pip==23.1.2

# Указываем рабочую директорию
WORKDIR /app

# Клонируем репозиторий SoniTranslate
RUN git clone https://github.com/r3gm/SoniTranslate.git

# Устанавливаем необходимые компиляторы и инструменты
RUN apt-get update && apt-get install -y build-essential cmake nano

# Устанавливаем зависимости requirements_base.txt
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install -r requirements_base.txt -v

# Устанавливаем зависимости requirements_extra.txt
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install -r requirements_extra.txt -v

# Устанавливаем onnxruntime-gpu
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install onnxruntime-gpu

# Устанавливаем зависимости requirements_xtts.txt
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install -q -r requirements_xtts.txt

# Устанавливаем TTS 0.21.1 без зависимостей
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install -q TTS==0.21.1 --no-deps

# Удаляем старые версии numpy, pandas и librosa
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip uninstall -y numpy pandas librosa

# Устанавливаем нужные версии numpy, pandas и librosa
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install numpy==1.23.1 pandas==1.4.3 librosa==0.10.0

# Устанавливаем нужные версии tts и torchcrepe
RUN cd /app/SoniTranslate && /opt/conda/bin/conda run -n sonitr pip install "tts<0.21.0" "torchcrepe<0.0.20"

# Настраиваем переменные окружения в conda
RUN /opt/conda/bin/conda run -n sonitr conda env config vars set YOUR_HF_TOKEN="INSERT_TOKEN_HERE"

# Настраиваем переменные окружения в conda
#RUN /opt/conda/bin/conda run -n sonitr conda env config vars set OPENAI_API_KEY="INSERT_TOKEN_HERE"

# Вносим изменения в файл app_rvc.py для добавления server_name="0.0.0.0" после max_threads=1
RUN sed -i '/app\.launch(/,/debug=/s/max_threads=1,/max_threads=1, server_name="0.0.0.0",/' /app/SoniTranslate/app_rvc.py

# Открываем порт 7860
EXPOSE 7860

# Копируем файл entrypoint.sh в контейнер
COPY entrypoint.sh /app/entrypoint.sh

# Переходим в директорию с репозиторием
WORKDIR /app/SoniTranslate

# Команда запуска Python-приложения через entrypoint.sh
CMD ["/bin/bash", "-c", "/app/entrypoint.sh"]

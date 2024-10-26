#!/bin/bash

# Активируем окружение 'sonitr'
source /opt/conda/etc/profile.d/conda.sh
conda activate sonitr

# Запускаем Python-приложение
python /app/SoniTranslate/app_rvc.py

web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile -
release: python -c "from database import init_db; init_db(); print('DB ready')"

web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
release: python -c "import database; database.init_db(); print('[release] DB migrada OK')"


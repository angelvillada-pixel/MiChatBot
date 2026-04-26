web: sh -c 'gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120'
release: python -c "import database; database.init_db(); print('[release] DB migrada OK')"

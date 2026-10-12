#!/bin/sh
# Azure App Service (Linux) start command. One worker only: refresh jobs, broker sessions and
# INDmoney login state are held in memory.
exec gunicorn -k uvicorn.workers.UvicornWorker -w 1 --timeout 600 --bind 0.0.0.0:${PORT:-8000} apps.api.main:app

# Windows + MT5 runtime. Requires MT5 Terminal installed and logged in,
# and MT5_LOGIN / MT5_PASSWORD / MT5_SERVER set as environment variables
# (e.g. via a local .env loaded by your shell — never commit it).
$env:APP_ENV = "windows"
uvicorn backend.main:app --host 0.0.0.0 --port 8000

#!/bin/bash
cd "$(dirname "$0")"
export SOURCE_FILE="bot/data/uploads/نتيجة الثانوية 25.xlsx"
export BOT_TOKEN="8769493338:AAFA5UCWY_N4UvciWdtle8l7bD911AdRbLU"
export LOG_LEVEL="INFO"
exec python3 -u -m bot.main

DC-QA-BOT/
└── discord-bot/
    ├── .env
    ├── index.js
    └── commands.json
└── discord_model/
    ├── database.py
    ├── main.py
    ├── question_gpt4o.py
    └── utils.py

「使用 screen（互動式背景執行）執行
screen -S discord-bot
node index.js

按下：
Ctrl + A 然後 D：離開 screen，但程式繼續跑
screen -r discord-bot：重新連線回來」

「.env檔包含
TOKEN=
CLIENT_ID=
API_BASE=

REDIS_URI="」

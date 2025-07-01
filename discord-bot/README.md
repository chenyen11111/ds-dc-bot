注意!先去申請一個dc-bot，會得到一份金鑰，把金鑰放進.env檔，才算串接上dc-bot



1.需下載node來寫javascript
https://summer10920.github.io/2020/12-30/article-nodejs/
但她是免安裝的
2.安裝nvm是參考這份文件:https://medium.com/@ray102467/nvm-windows-管理-windows-node-js-版本-68d789cf84d7
在下載node前 可以下載nvm-windows來進行版本控管
在github下載完exe後記得安裝
3.搜尋 Developer Portal，申請金鑰，可參考:https://hackmd.io/@iD40lBm-QAqgh62DVHbjPA/B1UUUU53s

DS-DC-BOT/
└── discord-bot/
    ├── .env(這個要自己建立)
    ├── index.js(main)
    └── commands.json(指令)

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

「discord機器人使用流程:
創建只有你的伺服器
連結:(在申請dc-bot的頁面找的到)
按下連結把機器人加進你的伺服器
接下來就可以開始嘗試」

前端啟動: cd discord-bot
node index.js

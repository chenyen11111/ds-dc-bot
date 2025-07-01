const { Client, Events, GatewayIntentBits } = require('discord.js');
const dotenv = require('dotenv');
const { REST } = require('@discordjs/rest');
const { Routes } = require('discord-api-types/v9');
const axios = require('axios');
const fs = require('fs');

dotenv.config(); // 載入環境變數

const API_BASE = 'http://localhost:5000';

// 創建 Discord 客戶端
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent
  ]
});
const userState = new Map(); // 創建用戶狀態的 Map

// 從commands.json中讀取指令設置，若新增斜線指令，要去json檔新增此指令名稱、內容
const commands = require('./commands.json'); 

//註冊斜線指令
client.once('ready', async () => {
  console.log(`Logged in as ${client.user.tag}!`);
  const rest = new REST({ version: '9' }).setToken(process.env.TOKEN);
  try {
    await rest.put( //上傳斜線指令到 Discord
      Routes.applicationCommands(process.env.CLIENT_ID),
      { body: commands },// 指令內容
    );
    console.log('斜線指令註冊成功!');// 註冊成功
  } catch (error) {
    console.error(error); //錯誤處理
  }
});

/* 斜線指令 登入，處理互動和選項
推遲回覆互動，取得互動的Discord使用者ID，從選項中取得學生ID和密碼 */
async function login(interaction, options) {
  try {
    await interaction.deferReply();
    const dc_id = interaction.user.id;
    const student_id = options.getString('student_id');
    const password = options.getString('password');

    const login_req = await axios.post(`${API_BASE}/api/login`, { // 發送登入請求
      student_id,
      password,
      discord_id: dc_id // 附加 Discord 使用者 ID
    });

    // 取得、輸出登入回應資料
    const login_res = login_req.data;
    console.log("login_res:", login_res);

    if (login_res.message === "登入成功") {
      await interaction.editReply("✅ 登入成功");
    } else if (login_res.message === "帳號已登入中，請先登出") {
      await interaction.editReply("⚠️ 你已經登入，請先使用 /logout 登出");
    } else {
      await interaction.editReply("❌ 登入失敗，請檢查學生ID或密碼");
    }
  } catch (err) {
    console.error("登入錯誤：", {
      data: err.response?.data,
      status: err.response?.status,
      message: err.message
    });
    await interaction.editReply("❗ 登入時發生錯誤，請稍後再試。");
  }
}

//斜線指令 登出，與相關互動
async function logout(interaction) {
  try {
    await interaction.deferReply();
    const dc_id = interaction.user.id;
    const logout_req = await axios.post(`${API_BASE}/api/logout`, {
      discord_id: dc_id
    });

    console.log("logout_req:", logout_req.data);

    if (logout_req.data.message === "登出成功") {
      return await interaction.editReply("✅ 登出成功");
    } else {
      return await interaction.editReply("❌ 登出失敗，請稍後再試。");
    }
  } catch (err) {
    console.error("登出錯誤：", {
      data: err.response?.data,
      status: err.response?.status,
      message: err.message
    });
    return await interaction.editReply("❗ 登出過程發生錯誤，請稍後再試。");
  }
}

//建立按鈕跟互動排版
const {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle
} = require('discord.js');

// 斜線指令 menu，包含延遲回復，取得使用者id
async function showMenu(interaction) {
  try {
    await interaction.deferReply();

    const dc_id = interaction.user.id;
    //發送 GET 請求給後端，取得該使用者的主選單資訊
    const menuRes = await axios.get(`${API_BASE}/api/student/${dc_id}/menu`);
    // 從回傳中取出 menu 陣列與錯誤訊息
    const menu = menuRes.data?.menu;
    const error = menuRes.data?.error;

    if (!menu || !Array.isArray(menu)) {
      throw new Error(error || "後端未正確回傳 menu");
    }

    const menuText = '📘 主選單如下：\n' + menu.join('\n');
    
    // 建立一排按鈕：查看進度、開始答題
    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('progress').setLabel('查看進度').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId('start').setLabel('開始答題').setStyle(ButtonStyle.Success)
    );
    // 回覆使用者主選單 + 按鈕
    await interaction.editReply({ content: menuText, components: [row] });
  } catch (err) {
    console.error("menu 發生錯誤：", {
      data: err.response?.data,
      status: err.response?.status,
      message: err.message
    });

    const errMsg = err.response?.data?.error || err.message || '❌ 無法取得主選單';
    await interaction.editReply(`❌ 無法取得主選單：${errMsg}`);
  }
}
//互動事件處理，註冊Discord bot的互動事件監聽器，當使用者觸發 /指令 或點擊按鈕時會進入這裡
client.on(Events.InteractionCreate, async interaction => {
  // 處理登入、登出、menu等斜線指令
  if (interaction.isCommand()) {
    const { commandName, options } = interaction;
    if (commandName === 'login') {
      await login(interaction, options);
    } else if (commandName === 'logout') {
      await logout(interaction);
    } else if (commandName === 'menu') {
      await showMenu(interaction);
    }
  } else if (interaction.isButton()) { //處理 按鈕互動事件，根據customId來分流
    const dc_id = interaction.user.id;
    const customId = interaction.customId;

    if (customId === 'progress') { // 待處理指令，目前僅顯示文字訊息
      await interaction.reply('📊 準備查詢進度...');
    } else if (customId === 'start') { //按下開始答題按鈕後
      await interaction.deferReply();
      try { //向後端取得該學生的主單元列表
        const res = await axios.get(`${API_BASE}/api/student/${dc_id}/units/menu`);
        const units = res.data.menu;

        const rows = [];
        let currentRow = new ActionRowBuilder();

        // 將所有單元按鈕平均分配成多行，每排最多放5個單元按鈕
        units.forEach((unit, idx) => {
          if (idx % 5 === 0 && idx !== 0) {
            rows.push(currentRow);
            currentRow = new ActionRowBuilder();
          }
          currentRow.addComponents(
            new ButtonBuilder().setCustomId(`unit_${idx}`).setLabel(unit).setStyle(ButtonStyle.Primary)
          );
        });
        if (currentRow.components.length > 0) rows.push(currentRow);

        //顯示所有主單元給使用者選擇，並處理錯誤狀況
        await interaction.editReply({ content: '📚 請選擇主單元：', components: rows });
      } catch (err) {
        console.error("取得單元錯誤:", err.message);
        await interaction.editReply('❌ 取得單元時發生錯誤。');
      }
    } else if (customId.startsWith('unit_')) { //抓出按下的主單元索引
      await interaction.deferReply();
      const index = parseInt(customId.split('_')[1]);
      //向後端再次取得所有單元文字，取出使用者點選的那一項
      try {
        const unitMenuRes = await axios.get(`${API_BASE}/api/student/${dc_id}/units/menu`);
        const unitText = unitMenuRes.data.menu[index];
        const unitName = unitText.split('. ')[1];
        userState.set(dc_id, { unit: unitName }); // 將選到的主單元存在記憶體中
        
        //接著向後端拿所有子主題資料，從中選出對應這個主單元的項目。
        const topicRes = await axios.get(`${API_BASE}/api/student/${dc_id}/topics`);
        const topicMap = topicRes.data;
        const topics = topicMap[unitName];

        //跟主單元一樣，把所有子主題依序包成按鈕，並分行顯示。
        if (!topics || topics.length === 0) {
          await interaction.editReply(`❌ 找不到「${unitName}」的子主題`);
          return;
        }

        const rows = [];
        let currentRow = new ActionRowBuilder();

        topics.forEach((topic, idx) => {
          if (idx % 5 === 0 && idx !== 0) {
            rows.push(currentRow);
            currentRow = new ActionRowBuilder();
          }
          currentRow.addComponents(
            new ButtonBuilder().setCustomId(`topic_${idx}`).setLabel(topic).setStyle(ButtonStyle.Secondary)
          );
        });
        if (currentRow.components.length > 0) rows.push(currentRow);

        //成功的話顯示所有子主題，否則回報錯誤
        await interaction.editReply({
          content: `🧩 你選擇了「${unitName}」，請選擇子主題：`,
          components: rows
        });
      } catch (err) {
        console.error("取得子主題錯誤:", err.message);
        await interaction.editReply('❌ 取得子主題時發生錯誤。');
      }
    } //取出使用者選擇的子主題索引，以及之前儲存的 unit 名稱
      else if (customId.startsWith('topic_')) {
      await interaction.deferReply();
      const index = parseInt(customId.split('_')[1]);
      const state = userState.get(dc_id);

      //確認是否選過主單元，並向後端取該單元對應的子主題名稱，更新記憶中的使用者狀態
      if (!state || !state.unit) {
        await interaction.editReply("⚠️ 請先選擇主單元！");
        return;
      }

      try {
        const unitMenuRes = await axios.get(`${API_BASE}/api/student/${dc_id}/topics/menu`, {
          params: { unitkey: state.unit }
        });
        const topicName = unitMenuRes.data.menu[index];
        state.topic = topicName;

        //送出請求產生對應主題的題目列表，儲存到該用戶的狀態中
        const res = await axios.post(`${API_BASE}/api/student/${dc_id}/questions`, {
          topic: topicName
        });
        const questions = res.data.questions;
        state.questions = questions;
        userState.set(dc_id, state);

        //將每一題組成按鈕（顯示題號與簡短描述），顯示給使用者選擇
        const row = new ActionRowBuilder().addComponents(
          questions.map((q, i) =>
            new ButtonBuilder()
              .setCustomId(`question_${i}`)
              .setLabel(`${i + 1}. ${q}`)
              .setStyle(ButtonStyle.Success)
          )
        );

        await interaction.editReply({
          content: `🧠 題目已生成，請選擇要作答的題目：`,
          components: [row]
        });
      } catch (err) {
        console.error("題目生成錯誤:", err.message);
        await interaction.editReply("❌ 題目生成錯誤，請稍後再試。");
      }
    } //從customId(使用者id)取得題目索引，並根據Discord使用者ID抓出該使用者的狀態
      else if (customId.startsWith('question_')) {
      await interaction.deferReply();
      const index = parseInt(customId.split('_')[1]);
      const state = userState.get(dc_id);
      
      //如果使用者還沒選過主單元或主題或題目資料不存在，代表流程斷裂，提示重新開始
      if (!state || !state.topic || !state.questions) {
        await interaction.editReply("⚠️ 找不到上下文資料，請輸入 `/menu` 重新開始。");
        return;
      }
      
      //將使用者選擇的題目存入狀態中，並記錄目前時間（用於後續計時），最後更新狀態
      const selectedQuestion = state.questions[index];
      state.question = selectedQuestion;
      state.questionIndex = index;
      state.total_start_time = Date.now();
      state.currentQuestion = selectedQuestion;
      userState.set(dc_id, state);
      
      //透過 /question API 傳送選定的題目名稱（簡短描述），後端回傳詳細敘述後儲存狀態
      try {
        const res = await axios.post(`${API_BASE}/api/student/${dc_id}/question`, null, {
          params: {
            question_data: selectedQuestion
          }
        });

        const fullQuestion = res.data.question;
        state.awaitingAnswer = true;
        state.typing_start_time = Date.now();
        userState.set(dc_id, state);

        //最終顯示詳細題目並清除互動元件（按鈕），提示使用者直接在文字頻道輸入答案
        await interaction.editReply({
          content: `📝 ${fullQuestion}\n請直接在此頻道輸入你的答案：`,
          components: []
        });
      } catch (err) {
        console.error("取得完整題目錯誤:", err.message);
        await interaction.editReply("❌ 題目讀取失敗，請稍後再試。");
      }
    }
  }
});

//這裡會在使用者輸入文字時觸發，如果他剛才有選擇題目、正在作答，就會進行送出答案、評分、顯示回饋的邏輯
client.on(Events.MessageCreate, async message => {
  if (message.author.bot) return;
  //抓出該使用者的狀態，如果不存在或沒有「目前題目」，表示目前不是在作答流程中，直接忽略
  const dc_id = message.author.id;
  const state = userState.get(dc_id);

  if (!state || !state.currentQuestion) return;

  //計算答題時間與開始輸入時間
  const answer = message.content;

  const total_start_time = state.total_start_time / 1000;//從題目顯示到送出答案的總時間
  const typing_start_time = (Date.now() - state.typing_start_time) / 1000;//從使用者開始輸入到送出的時間

  //組成送往後端 /answer API 的 payload，包含使用者回答與上下文資訊
  const payload = {
    answer,
    question: state.currentQuestion,
    unit: state.unit,
    topic: state.topic,
    total_start_time,
    typing_start_time
  };

  //呼叫後端評分 API
  try {
    const res = await axios.post(`${API_BASE}/api/student/${dc_id}/answer`, payload);
    const { score, feedback, is_suspected } = res.data;

    await message.reply(`✅ 評分完成\n📊 分數：${score}/10\n💬 評語：${feedback}`);

    userState.delete(dc_id); // 清除作答狀態，重新開始新流程

    //系統自動送出主選單，讓使用者可以快速進入下一輪答題或查看進度
    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder().setCustomId('progress').setLabel('查看進度').setStyle(ButtonStyle.Primary),
      new ButtonBuilder().setCustomId('start').setLabel('開始答題').setStyle(ButtonStyle.Success)
    );

    await message.channel.send({
      content: '📘 你已返回主選單：',
      components: [row]
    });
  } catch (err) {
    console.error("提交答案錯誤：", err.message);
    await message.reply("❌ 提交答案失敗，請稍後再試。");
  }
});

client.login(process.env.TOKEN); //啟動 bot，使用 .env 裡的 TOKEN 登入

//將commands註冊到discord
import { REST, Routes } from 'discord.js';
import { config } from 'dotenv';
import fs from 'node:fs';
import path from 'node:path';

config(); // 使用 .env 檔案

const commands = [];
const commandsPath = path.join(process.cwd(), 'commands');
const commandFiles = fs.readdirSync(commandsPath).filter(file => file.endsWith('.js'));

for (const file of commandFiles) {
  const { data } = await import(`./commands/${file}`);
  commands.push(data);
}

const rest = new REST({ version: '10' }).setToken(process.env.TOKEN);

try {
  console.log('⏳ 正在註冊指令...');
  await rest.put(
    Routes.applicationCommands(process.env.CLIENT_ID),
    { body: commands },
  );
  console.log('✅ 成功註冊斜線指令。');
} catch (error) {
  console.error(error);
}

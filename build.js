const os = require("os");
const path = require("path");
const CFG = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), ".config");
const SKILL = path.join(CFG, "gigatool", "skills", "word");
const H = require(path.join(SKILL, "helpers", "index.cjs"));

(async () => {
  const doc = H.createDoc({ title: "Перенос бота на другой ПК" });

  doc.heading("Перенос бота на другой ПК", 1);
  doc.paragraph("Чтобы установить и запустить торгового бота на другом компьютере, скопируйте папку проекта C:\\yobit_bot целиком и выполните несколько простых шагов.");

  doc.heading("Какие файлы переносить", 2);
  doc.bullets([
    "bot.py — основной код бота",
    "gui.py — окно с дашбордом и логом",
    "vk_control.py — управление из ВКонтакте",
    ".env — ключи и настройки (содержит секреты — переносите безопасно)",
    "position.json — текущая позиция (если есть)",
    "report.json — история сделок и отчёт о прибыли (если есть)",
  ]);
  doc.paragraph("Вспомогательные файлы (README.md, RUNBOOK.md, RISK.md и файлы тестов) переносить не обязательно — они не влияют на работу бота.");

  doc.heading("Что НЕ переносится", 2);
  doc.paragraph("Файл bot.log с логами создаётся заново при первом запуске. position.json на новом ПК лучше оставить пустым, если вы не переносите текущую открытую позицию:");

  doc.heading("Настройка на новом ПК", 2);
  doc.paragraph("1. Установите Python 3.11 или новее (добавьте в PATH).");
  doc.paragraph("2. Откройте PowerShell в папке проекта.");
  doc.paragraph("3. Выполните команду:", { mono: true });
  doc.paragraph("pip install python-dotenv requests");
  doc.paragraph("4. Если на новом ПК другой IP-адрес, создайте новый API-ключ на бирже и обновите YOBIT_API_KEY и YOBIT_SECRET в файле .env.");
  doc.paragraph("5. Запустите бота:");

  doc.heading("Первая команда", 3);
  doc.paragraph("python bot.py");

  doc.heading("Примечания", 2);
  doc.bullets([
    "Ключи API с привязкой по IP не сработают на новом адресе — создайте новые в личном кабинете биржи.",
    "ВК-токен (VK_TOKEN) переносится вместе с .env — менять его не нужно.",
    "Файл .env содержит пароли и ключи — никогда не отправляйте его через незащищённые каналы и не коммитьте в репозиторий.",
  ]);

  await doc.save("Перенос бота на другой ПК.docx");
  console.log("wrote Перенос бота на другой ПК.docx");
})();
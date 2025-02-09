import os
import yaml
import gspread
import logging
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext

# Настраиваем логирование
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TOKEN = ""
CREDENTIALS_FILE = "credentials.json"


def load_courses(directory="courses"):
    courses = []
    for index, filename in enumerate(sorted(os.listdir(directory)), start=1):
        filepath = os.path.join(directory, filename)
        if filename.endswith(".yaml"):
            with open(filepath, "r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
                labs = [lab.get("short-name") for lab in data.get("course", {}).get("labs", {}).values() if
                        "short-name" in lab]
                course_info = {
                    "id": str(index),
                    "name": data.get("course", {}).get("name", "Неизвестный курс"),
                    "semester": data.get("course", {}).get("semester", "Неизвестно"),
                    "spreadsheet": data.get("course", {}).get("google", {}).get("spreadsheet", ""),
                    "info_sheet": data.get("course", {}).get("google", {}).get("info-sheet", ""),
                    "labs": labs
                }
                courses.append(course_info)
    logging.info(f"Загружено {len(courses)} курсов")
    return courses


def get_groups(spreadsheet_id, info_sheet):
    logging.info(f"Получение групп для таблицы: {spreadsheet_id}, инфо-лист: {info_sheet}")
    credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE,
                                                                   ["https://spreadsheets.google.com/feeds",
                                                                    "https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    sheet_names = [sheet.title for sheet in spreadsheet.worksheets() if sheet.title != info_sheet]
    logging.info(f"Найдено {len(sheet_names)} групп: {sheet_names}")
    return sheet_names


def get_labs(spreadsheet_id, group_id, labs):
    logging.info(f"Получение лабораторных для группы: {group_id} в таблице {spreadsheet_id}")
    credentials = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE,
                                                                   ["https://spreadsheets.google.com/feeds",
                                                                    "https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        sheet = spreadsheet.worksheet(group_id)
    except gspread.exceptions.WorksheetNotFound:
        logging.error(f"Группа {group_id} не найдена в таблице {spreadsheet_id}")
        return []
    headers = sheet.row_values(1)
    found_labs = [lab for lab in labs if lab in headers]
    logging.info(f"Найдено {len(found_labs)} лабораторных: {found_labs}")
    return found_labs


async def start(update: Update, context: CallbackContext) -> None:
    context.user_data["courses"] = load_courses()
    courses = context.user_data["courses"]
    if not courses:
        await update.message.reply_text("Курсы не найдены.")
        return
    keyboard = [[course["name"]] for course in courses]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите курс:", reply_markup=reply_markup)


async def handle_course_selection(update: Update, context: CallbackContext) -> None:
    selected_course = update.message.text
    logging.info(f"Выбран курс: {selected_course}")

    courses = context.user_data.get("courses", [])
    course = next((c for c in courses if c["name"] == selected_course), None)

    if not course or not course["spreadsheet"]:
        logging.error(f"Информация о курсе '{selected_course}' не найдена")
        await update.message.reply_text("Информация о группах не найдена.")
        return

    context.user_data["selected_course"] = course
    groups = get_groups(course["spreadsheet"], course["info_sheet"])

    if not groups:
        logging.error(f"Для курса '{selected_course}' не найдены группы")
        await update.message.reply_text("Группы не найдены.")
        return

    keyboard = [[group] for group in groups]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите группу:", reply_markup=reply_markup)


async def handle_group_selection(update: Update, context: CallbackContext) -> None:
    selected_group = update.message.text
    logging.info(f"Выбрана группа: {selected_group}")

    course = context.user_data.get("selected_course")
    if not course:
        logging.error("Ошибка: курс не найден в user_data")
        await update.message.reply_text("Ошибка: курс не найден.")
        return

    labs = get_labs(course["spreadsheet"], selected_group, course["labs"])

    if not labs:
        logging.error(f"Лабораторные работы не найдены для группы '{selected_group}' в курсе '{course['name']}'")
        await update.message.reply_text("Лабораторные работы не найдены.")
        return

    keyboard = [[lab] for lab in labs]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите лабораторную работу:", reply_markup=reply_markup)


def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_course_selection))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_selection))
    logging.info("Бот запущен и ожидает команды...")
    app.run_polling()


if __name__ == "__main__":
    main()

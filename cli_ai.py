import os
import sys
import re
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.live import Live

if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))

dotenv_path = os.path.join(bundle_dir, '.env')

load_dotenv(dotenv_path)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL_NAME = "openrouter/free"
username = os.getlogin()

if username == "Пользователь":
    username = "User"

username = username.replace(" ", "_")  # Заменяем пробелы на подчеркивания
username = username.capitalize() # Делаем первую букву заглавной 
console = Console()

# Хранилище для контекста беседы
messages_history = [
    {"role": "system", "content": "Ты полезный AI-ассистент в терминале, аналог Claude Code. Отвечай кратко, по делу. Изучай контекст. Всегда используй Markdown для оформления кода."}
]

DATETIME_PATTERNS = [
    r'\b(который\s+час|сколько\s+времени|текущее\s+время|какое\s+время)\b',
    r'\b(какая\s+сегодня\s+дата|какое\s+сегодня\s+число|сегодняшняя\s+дата)\b',
    r'\b(какой\s+сегодня\s+день)\b',
    r'\b(дата\s+и\s+время|время\s+и\s+дата)\b',
    r'\b(what\s+time\s+is\s+it|current\s+time|what\'s\s+the\s+time)\b',
    r'\b(what\s+(is\s+)?today\'?s?\s+date|current\s+date)\b',
    r'\b(what\s+day\s+is\s+(it|today))\b',
]

DATETIME_PATTERN = re.compile('|'.join(DATETIME_PATTERNS), re.IGNORECASE)

WEEKDAYS_RU = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
MONTHS_RU = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
             'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']

def get_current_datetime_info() -> str:
    now = datetime.now()
    weekday = WEEKDAYS_RU[now.weekday()]
    month = MONTHS_RU[now.month - 1]
    return (
        f"**Текущая дата и время:**\n"
        f"🗓 {weekday}, {now.day} {month} {now.year} г.\n"
        f"🕐 {now.strftime('%H:%M:%S')}"
    )

def is_datetime_query(text: str) -> bool:
    return bool(DATETIME_PATTERN.search(text))

async def ask_ai(user_input: str):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    
    # Добавляем сообщение пользователя в историю
    messages_history.append({"role": "user", "content": user_input})

    # Ограничиваем контекст: системный промпт + последние 5 сообщений
    context = [messages_history[0]] + messages_history[-5:]
    
    data = {
        "model": MODEL_NAME,
        "messages": context,
        "stream": True # Включаем стриминг, чтобы ответ печатался по буквам, как в Claude
    }

    full_response = ""
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    console.print(f"\n[bold red]Ошибка API ({response.status}): {error_text}[/bold red]")
                    return

                # Создаем live-панель для эффекта печатающегося текста
                with Live(Panel("Думаю...", title="CLI AI", border_style="cyan"), refresh_per_second=8, console=console) as live:
                    async for line in response.content:
                        clean_line = line.decode('utf-8').strip()
                        if not clean_line or clean_line == "data: [DONE]":
                            continue
                        
                        if clean_line.startswith("data: "):
                            import json
                            try:
                                json_data = json.loads(clean_line[6:])
                                delta = json_data['choices'][0]['delta']
                                if 'content' in delta:
                                    full_response += delta['content']
                                    # Рендерим markdown на лету
                                    live.update(Panel(Markdown(full_response), title="CLI AI", border_style="green"))
                            except Exception:
                                pass
                                
        # Сохраняем ответ нейросети в историю для контекста
        messages_history.append({"role": "assistant", "content": full_response})

    except Exception as e:
        console.print(f"\n[bold red]Ошибка соединения: {e}[/bold red]")

async def main():
    # Очищаем экран при запуске (cls на Windows, clear на Linux/Mac)
    os.system("cls" if os.name == "nt" else "clear")

    if not OPENROUTER_API_KEY:
        console.print("[bold red]Ошибка: Не найден OPENROUTER_API_KEY в .env файле![/bold red]")
        return

    console.print(Panel.fit(
        "[bold magenta]CLI AI запущен![/bold magenta]\n"
        "Команды: [bold yellow].clear[/bold yellow] — очистить экран  "
        "[bold yellow].reset[/bold yellow] — сбросить историю  "
        "[bold yellow].help[/bold yellow] — справка  "
        "[bold yellow].exit[/bold yellow] — выйти",
        border_style="magenta"
    ), justify="center")
    
    while True:
        try:
            # Красивый промпт для ввода
            user_input = console.input(f"\n[bold blue]{username} $[/bold blue] ")
            
            stripped = user_input.strip()

            # --- Обработка команд ---
            if stripped.startswith("."):
                command = stripped.lstrip(".").split()[0].lower()

                if command in ['exit', 'quit', 'выход']:
                    console.print("[bold magenta]Пока! 👋[/bold magenta]")
                    break

                elif command == 'clear':
                    os.system("cls" if os.name == "nt" else "clear")
                    continue

                elif command == 'reset':
                    system_prompt = messages_history[0]
                    messages_history.clear()
                    messages_history.append(system_prompt)
                    console.print("[bold yellow]История беседы сброшена.[/bold yellow]")
                    continue

                elif command == 'help':
                    console.print(Panel(
                        "[bold yellow].clear[/bold yellow]  — очистить экран\n"
                        "[bold yellow].reset[/bold yellow]  — сбросить историю диалога\n"
                        "[bold yellow].help[/bold yellow]   — показать эту справку\n"
                        "[bold yellow].exit[/bold yellow]   — выйти из программы\n\n"
                        "Всё остальное — вопрос к AI.",
                        title="Справка",
                        border_style="cyan"
                    ))
                    continue

                else:
                    console.print(f"[bold red]Неизвестная команда:[/bold red] [yellow]{stripped}[/yellow]. Напиши [bold yellow].help[/bold yellow] для справки.")
                    continue

            # --- Пустой ввод ---
            if not stripped:
                continue

            # --- Проверяем, спрашивают ли дату/время ---
            if is_datetime_query(stripped):
                datetime_info = get_current_datetime_info()
                console.print(Panel(Markdown(datetime_info), title="CLI AI", border_style="green"))
                continue

            # --- Вопрос к AI ---
            await ask_ai(stripped)
            
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold magenta]Сессия завершена.[/bold magenta]")
            break

if __name__ == "__main__":
    asyncio.run(main())
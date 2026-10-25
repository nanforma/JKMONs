"""
Tiny translation layer. English text is the key; other languages are looked up in TR.
Usage:  from i18n import tr;  tr("Connect").  Templates use str.format placeholders: tr("found: {n}").format(n=3)
"""
LANGS = [("en", "English"), ("uk", "Українська"), ("ru", "Русский")]
DEFAULT = "en"

# (English, Ukrainian, Russian)
_ROWS = [
    # --- connect page
    ("Connect to JK BMS", "Підключення до JK BMS", "Подключение к JK BMS"),
    ("Before connecting, close the JK app on your phone and turn off Bluetooth on it: the BMS accepts only one connection.",
     "Перед підключенням закрийте застосунок JK на телефоні та вимкніть на ньому Bluetooth: BMS приймає лише одне підключення.",
     "Перед подключением закройте приложение JK на телефоне и отключите на нём Bluetooth: BMS принимает только одно подключение."),
    ("Find devices", "Знайти пристрої", "Найти устройства"),
    ("show unnamed", "показувати безіменні", "показывать безымянные"),
    ("scanning for 8 seconds…", "шукаю 8 секунд…", "ищу 8 секунд…"),
    ("found: {n}", "знайдено: {n}", "найдено: {n}"),
    ("Name", "Назва", "Имя"),
    ("Address", "Адреса", "Адрес"),
    ("Signal", "Сигнал", "Сигнал"),
    ("★ marks devices that look like a JK BMS. The name can be anything (for example, JK-B2A8S20P).",
     "★ — пристрій, схожий на JK BMS. Назва може бути будь-якою (наприклад, JK-B2A8S20P).",
     "★ — устройство, похожее на JK BMS. Имя может быть любым (например, JK-B2A8S20P)."),
    ("Enter the address manually:", "Введіть адресу вручну:", "Введите адрес вручную:"),
    ("(if an address is entered, the list above is ignored)",
     "(якщо адресу введено, список вище ігнорується)",
     "(если адрес введён, список выше не используется)"),
    ("PIN (optional)", "PIN (необов'язково)", "PIN (необязательно)"),
    ("Usually leave empty. Needed only if the BMS asks for a PIN during pairing.",
     "Зазвичай залиште порожнім. Потрібен, лише якщо BMS просить PIN під час сполучення.",
     "Обычно оставьте пустым. Нужен, только если BMS при сопряжении просит PIN."),
    ("Connect", "Підключитися", "Подключиться"),
    ("Demo", "Демо", "Демо"),
    ("(no name)", "(без назви)", "(без имени)"),
    ("{v} dBm", "{v} дБм", "{v} дБм"),
    ("Search failed: {err}\n\nCheck that Bluetooth is on (in a terminal: bluetoothctl power on).",
     "Пошук не вдався: {err}\n\nПеревірте, що Bluetooth увімкнено (у терміналі: bluetoothctl power on).",
     "Поиск не удался: {err}\n\nПроверьте, что Bluetooth включён (в терминале: bluetoothctl power on)."),
    ("The address must look like this: AA:BB:CC:DD:EE:FF",
     "Адреса має виглядати так: AA:BB:CC:DD:EE:FF",
     "Адрес должен выглядеть так: AA:BB:CC:DD:EE:FF"),
    ("Press “Find devices” and pick the BMS in the list, or enter the address manually.",
     "Натисніть «Знайти пристрої» й виберіть BMS у списку або введіть адресу вручну.",
     "Нажмите «Найти устройства» и выберите BMS в списке или введите адрес вручную."),
    ("The PIN must contain digits only.", "PIN має містити лише цифри.", "PIN должен состоять только из цифр."),
    # --- header / status
    ("Disconnect", "Відключитися", "Отключиться"),
    ("Language", "Мова", "Язык"),
    ("Not connected", "Не підключено", "Не подключено"),
    ("Disconnecting…", "Відключаюся…", "Отключаюсь…"),
    ("Starting…", "Запуск…", "Запуск…"),
    ("Searching for BMS…", "Шукаю BMS…", "Ищу BMS…"),
    ("Pairing…", "Сполучення…", "Сопряжение…"),
    ("Connecting…", "Підключаюся…", "Подключаюсь…"),
    ("Connected", "Підключено", "Подключено"),
    ("No connection, retrying…", "Немає зв'язку, пробую знову…", "Нет связи, пробую снова…"),
    ("PIN rejected", "PIN не прийнято", "PIN не принят"),
    ("Log", "Журнал", "Журнал"),
    ("Connection", "Підключення", "Подключение"),
    ("Monitor", "Моніторинг", "Мониторинг"),
    # --- monitor page
    ("Waiting for data from the BMS…", "Чекаю на дані від BMS…", "Жду данные от BMS…"),
    ("State of charge (SOC)", "Заряд (SOC)", "Заряд (SOC)"),
    ("Voltage", "Напруга", "Напряжение"),
    ("Current", "Струм", "Ток"),
    ("Power", "Потужність", "Мощность"),
    ("V", "В", "В"),
    ("A", "А", "А"),
    ("W", "Вт", "Вт"),
    ("sum of cells {v:.2f} V", "сума комірок {v:.2f} В", "сумма ячеек {v:.2f} В"),
    ("charging", "заряджання", "заряд"),
    ("discharging", "розряджання", "разряд"),
    ("idle", "простій", "простой"),
    ("{v:.1f} / {n:.1f} Ah", "{v:.1f} / {n:.1f} А·год", "{v:.1f} / {n:.1f} А·ч"),
    ("No errors", "Помилок немає", "Ошибок нет"),
    ("BMS flags", "Прапорці BMS", "Флаги BMS"),
    ("Cell overvoltage protection (OVP)", "Захист від перенапруги комірки (OVP)",
     "Защита от перенапряжения ячейки (OVP)"),
    ("bit {n}", "біт {n}", "бит {n}"),
    ("Recommendation: change the BMS settings password",
     "Рекомендація: змініть пароль налаштувань BMS",
     "Рекомендация: смените пароль настроек BMS"),
    ("Bit meanings are not verified: compare with the warning shown in the JK app.",
     "Значення бітів не підтверджено: звірте з попередженням у застосунку JK.",
     "Расшифровка битов не подтверждена: сверьте с предупреждением в приложении JK."),
    ("Pack voltage does not match the sum of the cells: your firmware may use different field offsets. Send a screenshot of the JK app.",
     "Напруга батареї не збігається із сумою комірок: можливо, у вашій прошивці інші зміщення полів. Надішліть знімок екрана застосунку JK.",
     "Напряжение батареи не сходится с суммой ячеек: возможно, на вашей прошивке другие смещения полей. Пришлите скриншот приложения JK."),
    ("Cells", "Комірки", "Ячейки"),
    ("#{n}", "№{n}", "№{n}"),
    ("{x:.0f} mΩ", "{x:.0f} мОм", "{x:.0f} мОм"),
    ("{v:.3f} V", "{v:.3f} В", "{v:.3f} В"),
    ("Voltage difference", "Різниця напруг", "Разница напряжений"),
    ("{v:.0f} mV", "{v:.0f} мВ", "{v:.0f} мВ"),
    ("average {avg:.3f} V · min {min:.3f} V (#{min_cell}) · max {max:.3f} V (#{max_cell})",
     "середнє {avg:.3f} В · мін {min:.3f} В (№{min_cell}) · макс {max:.3f} В (№{max_cell})",
     "среднее {avg:.3f} В · мин {min:.3f} В (№{min_cell}) · макс {max:.3f} В (№{max_cell})"),
    ("State", "Стан", "Состояние"),
    ("Temperatures", "Температури", "Температуры"),
    ("Charge {state}", "Заряджання {state}", "Заряд {state}"),
    ("Discharge {state}", "Розряджання {state}", "Разряд {state}"),
    ("Balance: off", "Баланс: вимк.", "Баланс: выкл"),
    ("Balance: charging {a:.2f} A", "Баланс: заряд {a:.2f} А", "Баланс: заряд {a:.2f} А"),
    ("Balance: discharging {a:.2f} A", "Баланс: розряд {a:.2f} А", "Баланс: разряд {a:.2f} А"),
    ("Heating {a:.2f} A", "Підігрів {a:.2f} А", "Подогрев {a:.2f} А"),
    ("Precharge", "Попередній заряд", "Предзаряд"),
    ("Sensor {n}", "Датчик {n}", "Датчик {n}"),
    ("Capacity", "Ємність", "Ёмкость"),
    ("Remaining", "Залишок", "Остаток"),
    ("Nominal", "Номінал", "Номинал"),
    ("Stored energy", "Запас енергії", "Запас энергии"),
    ("{v:.2f} Ah", "{v:.2f} А·год", "{v:.2f} А·ч"),
    ("{v:.2f} kWh", "{v:.2f} кВт·год", "{v:.2f} кВт·ч"),
    ("{v:.0f} Ah", "{v:.0f} А·год", "{v:.0f} А·ч"),
    ("Lifetime", "Ресурс", "Ресурс"),
    ("Cycles", "Цикли", "Циклов"),
    ("Total throughput", "Пропущено через АКБ", "Пропущено через АКБ"),
    ("Run time", "Напрацювання", "Наработка"),
    ("Device", "Пристрій", "Устройство"),
    ("Model", "Модель", "Модель"),
    ("Hardware", "Апаратна версія", "Версия железа"),
    ("Firmware", "Прошивка", "Прошивка"),
    ("Power-ons", "Увімкнень", "Включений"),
    ("Uptime", "Час роботи", "Время работы"),
    ("{d} d {h} h {m} min", "{d} д {h} год {m} хв", "{d} д {h} ч {m} мин"),
    ("{h} h {m} min", "{h} год {m} хв", "{h} ч {m} мин"),
    ("Current (A):", "Струм (А):", "Ток (А):"),
    ("Power (W):", "Потужність (Вт):", "Мощность (Вт):"),
    ("Status:", "Стан:", "Статус:"),
    ("Charging", "Заряджання", "Заряд"),
    ("Discharging", "Розряджання", "Разряд"),
    ("Idle", "Простій", "Простой"),
    ("Time left:", "Залишилось:", "Осталось:"),
]

TR = {
    "uk": {r[0]: r[1] for r in _ROWS},
    "ru": {r[0]: r[2] for r in _ROWS},
}

_current = DEFAULT


def set_lang(code: str) -> str:
    global _current
    _current = code if code in dict(LANGS) else DEFAULT
    return _current


def get_lang() -> str:
    return _current


def tr(text: str) -> str:
    return TR.get(_current, {}).get(text, text)

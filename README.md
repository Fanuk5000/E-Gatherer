# «Проєктування та реалізація бази даних інформаційної системи автоматизованого збору, зберігання та аналізу даних із вебресурсів»

![Python](https://img.shields.io/badge/Python-3.14%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17%20(pg__trgm)-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0%20asyncpg-D71F00?style=flat-square)
![Playwright](https://img.shields.io/badge/Playwright-Firefox%20(Gecko)-2EAD33?style=flat-square&logo=playwright&logoColor=white)
![httpx](https://img.shields.io/badge/httpx-AsyncClient-005571?style=flat-square)
![Grafana](https://img.shields.io/badge/Grafana-Analytics-F46800?style=flat-square&logo=grafana&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Planned-2496ED?style=flat-square&logo=docker&logoColor=white)
![uv](https://img.shields.io/badge/uv-Package%20Manager-DE5FE9?style=flat-square)

**E-Gatherer** — асинхронна ETL-система для автоматизованого збору цін із вебресурсів та курсів валют НБУ, збереження часових рядів (time-series) у PostgreSQL і побудови аналітичних представлень (views) для візуалізації в Grafana.

Проєкт оптимізований під апаратні обмеження цільового сервера (4 ГБ RAM, 2-ядерний CPU, 5400 RPM HDD): використовує `httpx` для легких JSON API, headless **Playwright (Firefox/Gecko)** лише там, де потрібен рендеринг JS, та `@dataclass(slots=True, frozen=True)` для зменшення витрат пам'яті.

---

## Архітектура бази даних (PostgreSQL 17)

Ініціалізація розширення `pg_trgm` виконується в [`database/init.sql`](database/init.sql), а схема таблиць та індексів описана у [`src/db/models.py`](src/db/models.py):

- **`catalog.stores`** — перелік відстежуваних магазинів (`name`, `base_url`, `is_active`).
- **`catalog.categories`** — ієрархія категорій товарів (`name`, `slug`, `parent_id`).
- **`catalog.products`** — еталонні товари (`brand`, `model_name`, `specs JSONB`) із GIN-індексом `ix_products_model_name_trgm` (`gin_trgm_ops`) для нечіткого пошуку `pg_trgm`.
- **`catalog.store_products`** — прив'язка пропозицій магазину до еталонного товару (`store_id`, `product_id`, `external_id`, `url`, `is_in_stock`).
- **`pricing.price_history`** — історія цін у UAH та обчисленому еквіваленті USD (`recorded_at DESC` індекс).
- **`pricing.exchange_rates`** — щоденні офіційні курси валют НБУ.
- **`etl.scrape_logs`** — журнал запусків колекторів (`SUCCESS` / `FAILED`, кількість елементів, час виконання).

### Аналітичні Views ([`src/db/sql_views.py`](src/db/sql_views.py))

- `analytics.v_daily_price_aggregates` — денні агрегати цін (`MIN`, `AVG`, `MAX`, медіана через `percentile_cont(0.5)`).
- `analytics.v_price_growth` — відстеження щоденної динаміки цін через віконну функцію `LAG()`.
- `analytics.v_product_match_bare_sql` — базове зіставлення назв товарів через `LIKE '%' || ... || '%'` (повільне сканування без індексу).
- `analytics.v_product_match_trgm` — нечітке зіставлення назв через `pg_trgm` (`%`, `similarity()`, `word_similarity()`).

---

## Структура проєкту

```text
E-gatherer/
├── database/              # SQL-ініціалізація PostgreSQL (pg_trgm)
├── grafana/               # Налаштування та дашборди Grafana
├── scripts/               # Утиліти та бенчмарк (bare SQL vs pg_trgm)
├── src/
│   ├── collectors/
│   │   ├── api/           # Легкі асинхронні API-колектори (НБУ, Brain)
│   │   ├── web/           # Playwright (Gecko) вебскрапери
│   │   ├── base.py        # Базовий контракт BaseParser
│   │   └── schemas.py     # Імутабельні DTO (slots=True, frozen=True)
│   └── db/                # SQLAlchemy 2.0 моделі, репозиторій, SQL views
├── todos/                 # Архітектурний план проєкту
├── Makefile               # Локальні команди запуску та налаштування
├── pyproject.toml         # Залежності та метадані Python
└── Dockerfile             # Контейнеризація застосунку (у розробці)
```

---

## Швидкий старт (локально)

### 1. Встановлення залежностей та браузера Firefox для Playwright

```bash
make setup
```

Для чистої Linux-системи (разом із системними бібліотеками для Firefox):

```bash
make setup-deps
```

### 2. Запуск колекторів та бенчмарку

```bash
# Тестовий запит курсу USD з API НБУ
make currency

# Dry-run Playwright (Firefox/Gecko) скрапера для webscraper.io (без запису в БД)
make scrape

# Запуск скрапера зі збереженням у PostgreSQL
make scrape-save

# Порівняння EXPLAIN (ANALYZE, BUFFERS) між bare SQL (ILIKE/LIKE) та pg_trgm
make bench
```

---

## Порівняння швидкості та точності: Bare SQL vs `pg_trgm`

Заміри виконано на `94` товарах у `catalog.products` (`uv run python -m scripts.benchmark_trgm --queries Mercedes Mercdes Ferari Toyta`, поріг `% >= 0.2`):

| Тест / Запит | Bare SQL (`ILIKE` / `LIKE`) | `pg_trgm` (`% >= 0.2` / `similarity`) | Bare SQL (хіти) | `pg_trgm` (хіти) |
| :--- | :---: | :---: | :---: | :---: |
| Пошук `'Mercedes'` (точний) | `0.108 ms` *(20.62 ms клієнт)* | `0.427 ms` *(8.46 ms клієнт)* | `10` | `10` |
| Пошук `'Mercdes'` (опечатка) | `0.154 ms` *(1.91 ms клієнт)* | `0.367 ms` *(3.02 ms клієнт)* | `0` | **`7`** *(score `0.207–0.250`)* |
| Пошук `'Ferari'` (опечатка) | `0.119 ms` *(1.56 ms клієнт)* | `0.426 ms` *(2.88 ms клієнт)* | `0` | **`13`** *(score `0.353`)* |
| Пошук `'Toyta'` (коротка опечатка) | `0.139 ms` *(1.52 ms клієнт)* | `0.327 ms` *(3.65 ms клієнт)* | `0` | `0` |
| View `v_product_match_*` (`LIMIT 50`) | `1.597 ms` *(4.73 ms клієнт, `11` buffers)* | `27.256 ms` *(30.19 ms клієнт, `191` buffers)* | `50` *(без сортування)* | `50` *(топ із `529` пар за `similarity`)* |

- **Чому на `94` рядках `ILIKE`/`LIKE` швидший (обидва роблять `Seq Scan`):** уся таблиця займає `1` сторінку пам'яті (`shared hit=1`), тому обидва запити читають ту саму сторінку, а різницю створює навантаження на CPU:
  - `ILIKE` виконує просте посимвольне порівняння підрядка без сортування й зупиняється одразу після набору `LIMIT`.
  - `pg_trgm` для кожного рядка будує триграми (3-символьні фрагменти), рахує їх перетин (`|A ∩ B| / |A ∪ B|`) і запускає `Sort` за `similarity()`.
  - У view `v_product_match_bare_sql` немає `ORDER BY`, тому `LIMIT 50` зупиняється вже на перших `5` рядках зовнішньої таблиці (`actual rows=5`), тоді як `v_product_match_trgm` перевіряє всі `94` рядки, знаходить `529` пар і сортує їх.
- **Точність проти швидкості:** `pg_trgm` знаходить опечатки (`Mercdes`, `Ferari`), де `ILIKE` дає `0`. Для коротких токенів на кшталт `Toyta` у довгих назвах краще підходить `word_similarity()` або нижчий поріг.
- **Висновок:** на малих обсягах даних (десятки–кілька тисяч рядків) `pg_trgm` **не швидший** за звичайні `ILIKE`/`LIKE`, але забезпечує значно вищу **точність і повноту (fuzzy recall)** для опечаток і зіставлення різних назв товарів. Перевага `pg_trgm` у швидкодії розкривається на великих каталогах (десятки тисяч+ рядків), коли `GIN (gin_trgm_ops)` перемикає план із `Seq Scan` на `Bitmap Index Scan` і пропускає ~99% сторінок таблиці.

### Простими словами: чому `LIKE` / `ILIKE` повільний на великій БД

Уявіть базу даних як книгу:

1. **Звичайний індекс (B-Tree) — це алфавітний словник (А–Я):**
   - Пошук за початком слова (`LIKE 'Merc%'`) миттєвий — одразу відкриваємо літеру **M**.
   - Пошук всередині рядка (`ILIKE '%erc%'`) ламає цю логіку: фрагмент `"erc"` може бути в `"M**erc**edes"`, `"Comm**erc**e"` чи `"P**erc**ent"`. Алфавітний порядок не допомагає, тому БД змушена **читати всю книгу сторінка за сторінкою** (`Seq Scan`).
2. **Чому `94` рядки швидко, а `1 000 000` — повільно:**
   - **94 рядки = 1 сторінка.** Прочитати 1 сторінку підряд швидше, ніж звертатися до індексу.
   - **1 000 000 рядків = десятки тисяч сторінок (ще й на повільному HDD).** Читати їх щоразу при пошуку — секунди затримки.
3. **Як допомагає `pg_trgm`:**
   - Працює як **предметний покажчик у кінці книги**: розбиває назви на 3-літерні шматочки (`"mer"`, `"erc"`, `"rce"`) і записує номери сторінок, де вони трапляються.
   - На великій БД пошук одразу стрибає на потрібні кілька сторінок замість читання всієї таблиці.
4. **Зіставлення товарів (`v_product_match_*`):**
   - Без індексу порівняння кожного товару з кожним (`N × N`) на 100 тис. рядків дає мільярди перевірок підрядків; з `pg_trgm` БД перевіряє лише пари зі спільними триграмами.

> **Примітка:** Docker-збірка (`Dockerfile`) запланована для фінального розгортання разом із сервісами PostgreSQL і Grafana.

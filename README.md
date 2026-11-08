# Платформа ставок: core, карточка маршрута, прогноз тарифа

Пакетный конвейер поверх снимка `deals_bigdata` на `2026-10-26`. Источник остаётся в `public`. Python оркестрирует, преобразования делает SQL. Поверх очищенного слоя считаются коридор ставок и пакетный прогноз `price_rub`.

`as_of` - дата снимка, не дата запуска машины. Пустой `AS_OF_DATE` означает `2026-10-26`.

## Архитектура

```text
public.prices, cities, body_types, price_body_types, price_dates, exchange_rates
        |
        v
etl  (окно loading_date, DELETE + INSERT в одной транзакции)
        |
        +-- core.cities, core.body_types, core.prices
        +-- dq.quarantine_prices
        v
mart.route_card                         полный пересчёт после загрузки
        v
ml  CatBoost + Ridge + DecisionTree     train / test по loading_date
        |
        +-- mart.ml_price_predictions   только CatBoost
        +-- mart.ml_model_metrics
```

Один запуск `python -m etl` берёт advisory lock `de_interviews.etl`, применяет DDL, пишет `etl.run_log`, грузит окно, пересобирает витрину и скорит модель. Повтор за то же окно не удваивает строки: core и карантин в окне стираются и пишутся заново, витрина и прогнозы перезаписываются целиком. Вставка в core и карантин - `INSERT ... SELECT`, прогнозы - `COPY`. Построчных `INSERT` на сотнях тысяч строк нет.

Частичное окно меняет только сделки с `loading_date` в `[start_date, end_date]`. Карточка маршрута и модель после этого всё равно пересчитываются по всему `core`: MoM/YoY и фиксированный сплит от `as_of` иначе разъедутся с обрезанным окном.

Города дедупятся в `core.cities`: один `gc_id`, строка с минимальным `cities.id`. Регион - часть `full_name_local` после первой запятой. `Казань, Республика Татарстан` даёт город `Казань` и регион `Республика Татарстан`.

## Стек

PostgreSQL 17 держит источник, core и витрины. Окно на 300 000 строк и перцентили карточки считаются одним SQL, отдельный аналитический движок для этого объёма не нужен.

Python 3.11 и psycopg 3 только оркестрируют: границы окна, блокировка, журнал прогона, обучение. Трансформации не размазаны по pandas.

CatBoost - основная модель: группы кузова и регионы остаются категориями, one-hot не раздувает матрицу. Ridge и DecisionTree считаются на том же сплите, их прогнозы в таблицу сделок не пишутся. Оркестратор не ставился: расписание здесь - повторный запуск того же процесса. Airflow, Superset и ClickHouse в базовое решение не входят.

Пароль и хост берутся из окружения. Локальные значения по умолчанию лежат в `.env.example`, чтобы `docker compose up` поднимался без ручных правок.

## Очистка

Строка с хотя бы одним кодом уходит в `dq.quarantine_prices` и в `core.prices` не попадает. Кодов на строке может быть несколько. View `public.dq_quarantine_prices` смотрит в ту же таблицу.

| Код | Условие |
| :--- | :--- |
| `UNKNOWN_LOADING_CITY` / `UNKNOWN_UNLOADING_CITY` | `gc_id` нет в дедуплицированном справочнике |
| `NON_POSITIVE_DISTANCE` | `distance` пустая, <= 0 или NaN |
| `NEGATIVE_WEIGHT` / `NEGATIVE_VOLUME` | пусто, < 0 или NaN |
| `NON_POSITIVE_PRICE` | `price` пустая, <= 0 или NaN |
| `RUB_PRICE_BELOW_MIN` | валюта `643` и `0 < price <= 1000` |
| `UNKNOWN_CURRENCY` | код не `643`, `840`, `978` |
| `MISSING_FX_RATE` | `840` или `978` и нет курса на `exchange_rates.setting_date = nearest_rate_date` |

Курс берётся только на точную `nearest_rate_date`. Подбора по `loading_date` нет. Несколько курсов на одну дату - строка с минимальным `id`. Для рубля `price_rub = price`. Для валюты `price_rub = price * rate`.

Категории заполняют только пустые поля. Вес округляется до 0.1 т: `G20T` от 30, `FTL` от 10, `10T` от 5, `5T` от 2.5, `L5T` от 0.5, иначе `OTH`. Объём: `FTL` при `0 < V <= 120`, иначе `OTH`. Одинаковый `FTL` у веса и объёма означает разные вещи.

`loading_city_gcid = unloading_city_gcid` не брак. Генератор такие пары сохраняет, конвейер тоже.

`outlier_mark` из источника не пересчитывается и в признаки модели не входит. Выброс остаётся в `core` и не попадает в карточку маршрута и в обучающую выборку. IQR по `price_group_id` не считался: в задании это необязательная замена флагу, а не DQ-шаг.

Сделки за день снимка `2026-10-26` ночной джоб разметки аномалий ещё не обрабатывал. В генераторе `outlier_mark` выставляется только при `created_at < 2026-10-26 02:30`, поэтому у свежих строк флаг в основном `false`. На полном прогоне в core за этот день 5925 строк и только 3 помеченных выброса. Это свойство снимка, а не пропуск фильтра.

## Карточка маршрута

`mart.route_card`, зерно `месяц x город отправления x город назначения x группа кузова x весовая категория`. Месяц - `date_trunc('month', price_dates.price_date)`. `volume_category` в зерно не входит: внутри одной весовой ячейки объём разный, и лишнее измерение режет доказательную базу.

В ячейку попадают факты (`is_fact`, `price_type IN (1, 2, 3, 4, 5, 9)`), прямые рейсы (`complex = false`), `price_rub > 0`, `distance > 0`, без `outlier_mark`. `price_date` позже `as_of` в историю не идёт.

Группа кузова по `std_id`: тент `56-61`, рефрижератор `4, 46-48`, изотерм `2`, борт `1, 15`, остальные коды - `Прочие`, пусто - `Не указан`. Связи берутся из `price_body_types`. Нет связей - fallback на `prices.body_type`. Два тента у одной сделки в одном месяце дают одну строку. Тент и борт дают две.

Метрики в рублях без НДС: P25, P50, P75 и среднее за рейс; те же перцентили для `price_rub / distance`. `trips_count` - уникальные сделки. `carriers_count` - уникальные `organization_id` только при `price_type IN (3, 9)`. `cv_rate` - `stddev_samp / avg`, пусто при одном наблюдении или нулевом среднем. `mom_pct` и `yoy_pct` - изменение медианы к календарному предыдущему месяцу и к тому же месяцу прошлого года. Нет ячейки или медиана-знаменатель равна нулю - `NULL`, последний доступный месяц не подставляется.

`HIGH`: не меньше 30 рейсов, не меньше 5 перевозчиков и последняя `price_date` ячейки не старше 30 дней от `as_of`. Иначе `MEDIUM` при 10 и более рейсах, иначе `LOW_DATA`. Сентябрь может быть `HIGH`, если в ячейке есть рейс `2026-09-26` или позже.

## Прогноз

Цель - `price_rub` за рейс. Границы от `as_of`: train `[as_of - 3 месяца, as_of - 21 день)`, test `[as_of - 21 день, as_of]`. Для снимка это train `2026-07-26`...`2026-10-04` и test `2026-10-05`...`2026-10-26`. День `2026-10-05` только в test. Перемешивания нет.

В train и test входят факты, не составные маршруты, без выброса, с положительными дистанцией и `price_rub`. Будущее - все строки `core` с `loading_date > as_of`. У них `actual_price_rub`, `abs_error_rub` и `ape_pct` пустые, даже если в источнике цена заполнена.

Признаки: группа кузова из `prices.body_type`, весовая и объёмная категории, регион и координаты отправления и назначения раздельно, дистанция, вес, объём, год, месяц, день недели (понедельник = 0), день года и sin/cos с периодами 12, 7 и 365.25. Одна сделка - один прогноз, поэтому витринное размножение по нескольким кузовам здесь не используется.

В матрицу не входят `price_rub`, исходная цена, руб./км, цена с НДС, `outlier_mark`, `price_group_id`, `avg_price`, `min_km_price`, `max_km_price`, курс. `SimpleImputer`, one-hot и `StandardScaler` для Ridge и дерева учатся только на train. CatBoost принимает категории как есть: 400 итераций, глубина 8, learning rate 0.08, RMSE, `random_seed = 20261026`. Файл модели не сохраняется.

## Запуск

Нужны Docker и Compose v2. Из корня репозитория:

```bash
docker compose up --build
```

Postgres при пустом томе выполняет `sql/schema.sql` и `sql/synthetic.sql` (`N_PRICES`, по умолчанию 300 000). Первая инициализация занимает около минуты. Сервис `etl` ждёт healthy и прогоняет очистку, витрину и скоринг. Код `etl/`, `ml/` и `sql/` смонтирован в контейнер. Новая Python-зависимость требует `docker compose build etl`.

Повтор полного прогона, когда база уже поднята:

```bash
docker compose run --rm etl python -m etl
```

Окно по `loading_date`, обе границы сразу. Витрина и модель после него всё равно полные.

```bash
docker compose run --rm etl python -m etl --start-date 2026-09-01 --end-date 2026-09-30
```

То же через окружение: `ETL_START_DATE` и `ETL_END_DATE`. Другая дата снимка: `--as-of` или `AS_OF_DATE`.

Том `pgdata` переживает перезапуск. `N_PRICES` читается только при создании тома. `docker compose down -v` удаляет базу, следующий `up` генерирует источник заново.

Проверки:

```bash
docker compose exec postgres psql -U postgres -d deals_bigdata -f /assignment/checks/etl_status.sql
docker compose exec postgres psql -U postgres -d deals_bigdata -f /assignment/checks/mart_route_card.sql
docker compose exec postgres psql -U postgres -d deals_bigdata -f /assignment/checks/ml_predictions.sql
```

Лог - строки `key=value`: `etl_start`, `etl_finished` (прочитано, core, карантин, выбросы, строки витрины, коды DQ, `snapshot_day_rows`), `ml_split`, `ml_metrics`, `ml_scored`.

Тесты. Правила очистки, идемпотентность окна и карточка ходят в ту же базу, выборка на `1999-01-01` и откатывается. Юнит-тесты сплита и признаков база не нужна.

```bash
docker compose run --rm -e RUN_DB_TESTS=1 -e POSTGRES_HOST=postgres etl pytest -q
```

## Что лежит в базе после прогона на 300 000

`as_of = 2026-10-26`, полное окно.

| Слой | Результат |
| :--- | :--- |
| Источник | 300 000 |
| `core.prices` | 299 797, сумма `price_rub` 51 312 682 850.03 |
| Карантин | 203 строки. Коды: `NON_POSITIVE_PRICE` 164, `RUB_PRICE_BELOW_MIN` 156, `MISSING_FX_RATE` 39. Сумма кодов больше 203: на одной строке их несколько |
| Выбросы в core | 5 045, из них в день снимка 3 из 5 925 |
| Одинаковый город | 0 |
| `mart.route_card` | 203 644 ячейки. `HIGH` 10 ячеек / 498 рейсов, `MEDIUM` 924 / 13 922, `LOW_DATA` 202 710 / 276 600. Будущих месяцев нет |

Самая плотная ячейка: Москва -> Ростов-на-Дону, тент, `FTL`, октябрь 2026. Медиана 126 992 руб./рейс и 106 руб./км, 112 рейсов, 39 перевозчиков, MoM +0.5%, YoY +17.7%, `HIGH`.

```sql
SELECT month_date, loading_city_name, unloading_city_name, body_group,
       weight_category, round(median_trip::numeric, 2) AS median_trip,
       round(median_km::numeric, 2) AS median_km,
       trips_count, carriers_count,
       round(mom_pct::numeric, 2) AS mom_pct,
       round(yoy_pct::numeric, 2) AS yoy_pct,
       reliability_level
FROM mart.route_card
WHERE loading_city_name = 'Москва'
  AND unloading_city_name = 'Ростов-на-Дону'
  AND body_group = 'Тент'
  AND weight_category = 'FTL'
ORDER BY month_date;
```

Метрики на test, 12 808 сделок. Train 24 226. Будущих строк в скоринге 5 998, у всех факт и ошибки пустые. В `mart.ml_price_predictions` 18 806 строк, это test и будущее.

| Модель | R2 | MAPE, % | RMSE, руб. | MAE, руб. |
| :--- | ---: | ---: | ---: | ---: |
| CatBoostRegressor | 0.9193 | 15.60 | 54 333.90 | 28 059.98 |
| DecisionTreeRegressor | 0.9131 | 15.72 | 56 395.62 | 29 524.64 |
| Ridge | 0.8402 | 49.47 | 76 470.11 | 48 450.89 |

Хвост MAPE - дешёвые рейсы, которые модель завышает. В отчёт идёт средний MAPE, не этот хвост.

## Состав репозитория

`sql/schema.sql` и `sql/synthetic.sql` - источник, без изменений. `sql/dwh/` - DDL слоёв. `sql/checks/` - запросы выше. `etl/sql/` - шаги загрузки и пересчёт витрины. `ml/` - сплит, признаки, обучение, запись прогнозов. `tests/` - pytest. `docker/initdb.sh` - инициализация тома.

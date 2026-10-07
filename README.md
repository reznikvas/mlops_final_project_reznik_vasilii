# E-commerce: вероятность покупки

Сервис оценивает вероятность покупки товара тем же посетителем в течение 24 часов
после просмотра. Вход: `itemid`, час UTC, день недели (0 — понедельник).
Выход: `purchase_probability` из `CatBoostClassifier.predict_proba` и версия модели.
Это оценка по товару и времени, без персональных признаков посетителя.

Фактический результат: test AP **0,0243904** при baseline **0,0111961**;
цепочка на ВМ и дополнительный Kubernetes проверены, включая остановку API
и снятие алерта. Восстановление Airflow/ClearML проверено на новых volumes.
Версии, метрики и ограничения: [итоговый отчёт](docs/report.md).
Соответствие требованиям: [docs/checklist.md](docs/checklist.md).
Текущие адреса, повторный запуск и резервные копии: [эксплуатация](docs/operations.md).
Фактические результаты сохраняются в [docs/evidence](docs/evidence).
Удалённый [pipeline №11202](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii/-/pipelines/11202):
все восемь jobs — **success**, включая `test_alerts`, `deploy` и `deploy_k8s`.
Один образ по digest и одна версия модели развёрнуты на ВМ и в Kubernetes.
Проверены V2, Helm-мониторинг, замена Pod и повторная загрузка модели из S3.
Ссылка на репозиторий: [docs/submission.md](docs/submission.md).

## Структура

| Каталог / файл | Назначение |
|---|---|
| `src/data.py`, `src/features.py` | Валидация, target, временное разбиение, единые признаки |
| `src/training.py` | Три конфигурации CatBoost, выбор по validation AP |
| `src/storage.py`, `src/loaded_models.py` | S3, SHA256, однократная загрузка модели |
| `src/main.py`, `src/schema.py`, `src/v2.py` | FastAPI, прежний API и HTTP V2, логи, метрики |
| `tests/` | Изолированные unit-тесты |
| `mlops/airflow/` | Airflow 2.11, DAG S3 → S3 |
| `mlops/clearml/` | Эксперименты и выбор модели в ClearML |
| `mlops/deploy/`, `mlops/grafana/` | Инференс, мониторинг и дашборд |
| `mlops/deploy/k8s/`, `mlops/grafana/chart/` | Kubernetes Deployment/Service и Helm-chart мониторинга |
| `scripts/` | Загрузка данных и модели, доставка из CI |

## Окружение и проверки

Python 3.12.13, uv; версии зависимостей закреплены в `uv.lock` и `requirements.txt`.
`requirements.txt` содержит runtime; инструменты качества — группа `dev` в lockfile.

```bash
uv venv --python 3.12.13 .venv
uv sync --frozen
# Альтернатива для runtime: uv pip install -r requirements.txt
uv run --no-sync ruff check .
uv run --no-sync black --check --workers 1 .
uv run --no-sync mypy
uv run --no-sync pytest
```

При отсутствии доступа к общему кэшу uv используется `UV_CACHE_DIR=.cache/uv`.
Unit-тесты не требуют S3, Airflow, ClearML или файла обученной модели.

## Данные и постановка

Четыре исходных файла RetailRocket: `events.csv`, `category_tree.csv`,
`item_properties_part1.csv`, `item_properties_part2.csv`. Две части свойств объединяются.
Сырые данные не хранятся в этом Git-репозитории.

Один уникальный просмотр — одна строка. Target равен 1, если есть покупка того же
товара тем же посетителем **строго после** просмотра и не позже 24 часов.
Последние 24 часа наблюдений исключены: исход ещё не наблюдаем полностью.
Ближайшая последующая покупка ищется через `merge_asof`, без размножения строк.

Первые 20% временного диапазона — история для признаков; 20–60% — train,
60–80% — validation, 80–100% — test. Перед границами train/validation исключаются
24 часа, чтобы окна target не пересекали следующую выборку. Seed: 42.

Снимок признаков фиксируется **до train** и одинаков для train, validation, test и API.
Признаки: исторические `views`, `purchases`, отношение `ctr`, `hour`, `weekday`,
`categoryid`, `available`. Свойства выбираются по timestamp из обеих частей.
`ctr` — отношение исторических покупок к просмотрам, а не вероятность API.
Неизвестная категория/доступность: -1. Каталог включает только известные на дату
снимка товары; будущие неизвестные товары исключены из offline-оценки и дают 404 в API.
Это предотвращает использование будущих признаков, но ограничивает охват и допускает
устаревание lookup. Динамические признаки и cold-start требуют следующей версии.

Метрика выбора — **Average Precision**, ступенчатая оценка площади PR-кривой:
покупки редки, ROC-AUC менее наглядна для этой задачи.
Сравниваются три фиксированные конфигурации по одной validation AP;
test используется только для финальной оценки выбранной модели. Дополнительно
измеряются log loss и Brier, с константной вероятностью train как baseline.
Калибровка оценивается на отложенном test.

```bash
uv run python prepare_features.py --raw /путь/к/четырём/csv
uv run python train_model.py
uv run python main.py
curl -f http://127.0.0.1:32000/health
curl -f http://127.0.0.1:32000/docs
curl -f 'http://127.0.0.1:32000/predict_purchase?itemid=356475&hour=14&weekday=3'
```

## S3 и происхождение артефактов

Файл `.secrets/s3.env` содержит `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`S3_BUCKET` (фактически выданный бакет), `S3_ENDPOINT_URL`, `AWS_DEFAULT_REGION`.
Права каталога 700, файлов 600. Префикс `Reznik_Vasilii_project` находится **внутри** бакета.

```bash
set -a
. .secrets/s3.env
set +a
uv run python -m scripts.upload_raw /путь/к/четырём/csv
uv run python prepare_features.py --raw-manifest "$RAW_MANIFEST_KEY" --upload
uv run python train_model.py --upload
```

Команда загрузки печатает ключ manifest; его значение записывается в `RAW_MANIFEST_KEY`.
Структура: `raw_data/<version>/`, `processed_data/<version>/`,
`models/<version>/` под общим префиксом. Manifest публикуется последним,
содержит SHA256 файлов, версию схемы, параметры, происхождение и границы выборок.
Версия processed зависит от исходных SHA256, рецепта, кода и библиотек.
Каждое скачивание проверяет SHA256. Повторная обработка тех же входов воспроизводима.
`ranker.pkl` содержит классификатор; загружать pickle допустимо только из доверенного
проектного S3. Lookup и модель проверяются вместе до готовности API.

## Airflow

Используется Airflow **2.11.0**, LocalExecutor и PostgreSQL; команды относятся к ветке v2.
Файл `.secrets/services.env` содержит: `AIRFLOW_DB_PASSWORD`, `AIRFLOW_FERNET_KEY`
(Fernet, 32 случайных байта в urlsafe base64), `AIRFLOW_WEB_SECRET`, `GRAFANA_PASSWORD`.

```bash
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml up -d --build
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml exec airflow airflow dags list
```

Интерфейс: `127.0.0.1:8082`; доступ к ВМ выполняется через SSH-туннель.
Standalone создаёт пользователя admin; пароль хранится внутри контейнера в
`/opt/airflow/standalone_admin_password.txt` и исключён из отчётов.
Для S3 требуется Connection `ecom_s3` (тип aws): login = Access Key, password = Secret Key,
extra = JSON с `endpoint_url` и `bucket`. Секрет шифруется Fernet в PostgreSQL.
Возможен `airflow connections import` из временного файла с правами 600;
перед импортом владельцем файла назначается UID 50000, после импорта файл удаляется.

```bash
docker compose --env-file .secrets/services.env -f mlops/airflow/docker-compose.yaml exec airflow \
  airflow dags trigger preprocessing_data --conf "{\"raw_manifest\":\"$RAW_MANIFEST_KEY\"}"
```

DAG скачивает raw, проверяет данные, вызывает общую `src.data.prepare`, загружает
processed и manifest. XCom содержит ключ manifest, а не таблицы. Один активный run,
повтор после сбоя безопасен: те же входы формируют тот же префикс.

## ClearML

Адреса сервера и SDK credentials задаются в `~/clearml.conf` либо через переменные
`CLEARML_API_HOST`, `CLEARML_WEB_HOST`, `CLEARML_FILES_HOST`,
`CLEARML_API_ACCESS_KEY`, `CLEARML_API_SECRET_KEY`.

```bash
PYTHONPATH="$PWD" uv run python -m mlops.clearml.clearml_pipeline \
  --processed-manifest "$PROCESSED_MANIFEST_KEY"
```

Вход pipeline — manifest **успешного Airflow run**. Pipeline скачивает одну processed-версию,
последовательно обучает три модели, выбирает максимальную validation AP,
оценивает победителя на test и публикует модель с lookup и manifest в S3.
Режим local mode регистрирует задачи на сервере ClearML и запускает шаги
локальными подпроцессами. Автоматическое определение Git-репозитория отключено.
Документация режима: https://clear.ml/docs/latest/docs/references/sdk/automation_controller_pipelinedecorator/.

## Docker и ВМ

```bash
DOCKER_BUILDKIT=1 docker build -t ecom-purchase:local .
```

Файл `.secrets/release.env` содержит `APP_IMAGE`, `MODEL_VERSION`, `MODEL_MANIFEST_KEY`,
`S3_ENV_FILE` (абсолютный путь удобнее). Пароль Grafana — в services.env.

```bash
docker compose --env-file .secrets/services.env --env-file .secrets/release.env \
  -f mlops/deploy/docker-compose.yml up -d --wait --wait-timeout 180
curl -f http://127.0.0.1:8000/health
curl -f 'http://127.0.0.1:8000/predict_purchase?itemid=356475&hour=14&weekday=3'
```

`model-init` скачивает модель отдельно от образа. У каждой версии свой volume;
API получает его read-only, без S3-ключей, загружает модель один раз на процесс.
Контейнер работает от непривилегированного пользователя. Health возвращает 503,
пока модель не загружена. Для локальной доставки без Registry:

```bash
docker save ecom-purchase:local | gzip > .artifacts/ecom-image.tar.gz
scp .artifacts/ecom-image.tar.gz ubuntu@VM:/home/ubuntu/
ssh ubuntu@VM 'gzip -dc ~/ecom-image.tar.gz | sudo docker load'
```

Каталоги `mlops/deploy`, `mlops/grafana` и приватные env доставляются отдельно по SSH.
Секреты хранятся вне каталога релиза. Откат выполняется выбором предыдущей пары
`APP_IMAGE`/`MODEL_VERSION` и её manifest с повторным запуском `compose up`.
Срок жизни учебной ВМ — 5 часов. Возобновление ресурсов доступно в учебном тренажёре.

## Мониторинг и негативные проверки

`/metrics`: счётчики запросов/статусов, histogram задержки и вероятности, готовность.
Prometheus опрашивает API каждые 10 секунд. Grafana получает provisioned dashboard
`ecom`. Alloy доставляет stdout/stderr только контейнера `ecom-api` в Loki.
Логи прогнозов содержат itemid, вероятность и версию модели, ошибки — тип и статус.
Метрики не используют itemid как label, чтобы избежать неограниченного числа рядов.

Интерфейсы привязаны к loopback ВМ: Grafana 3000, Prometheus 9090, Loki 3100.
Доступ через SSH `-L`. Пароль Grafana хранится в приватном env.
Алерты Prometheus: недоступность 30 с, доля 5xx >5% одну минуту, p95 >1 с две минуты.
Это эксплуатационные пороги, не критерии ML-качества. Внешняя рассылка не настроена.

```bash
curl -i 'http://127.0.0.1:8000/predict_purchase?itemid=-1&hour=14&weekday=3' # 422
curl -i 'http://127.0.0.1:8000/predict_purchase?itemid=999999999&hour=14&weekday=3' # 404
curl -f http://127.0.0.1:8000/metrics
```

Автоматическая сквозная проверка с SSH-туннелями из инструкции эксплуатации:

```bash
uv run python -m scripts.smoke --url http://127.0.0.1:32000
uv run python -m scripts.smoke --url http://127.0.0.1:18000 --output docs/evidence/vm-api.json
uv run python -m scripts.verify_monitoring --password-file .secrets/grafana_password
# Временно останавливает API ВМ; восстановление запускается в finally:
uv run python -m scripts.check_alert
```

Мониторинговая проверка создаёт 120 прогнозов и проверяет реальные ряды/логи.
`check_alert` использует SSH-конфигурацию `.secrets/ssh_config`, хост `course-vm`.

Контролируемая проверка алерта: остановка только `api` через Compose, ожидание
`EcomUnavailable` в `/api/v1/alerts`, затем `compose start api`. Условия восстановления:
health=200 и отсутствие firing. Команда `down -v` удаляет накопленные данные
и не используется для этой проверки.
Распределение вероятностей выявляет изменение поведения, но **не измеряет точность**.
Без связки прогноз → фактический исход онлайн AP/Brier недоступны; offline-качество
фиксируется в manifest. Исторические данные 2015 года не доказывают качество на
современном трафике.

Для проверки правил алертинга на синтетических рядах:

```bash
docker run --rm --entrypoint promtool -v "$PWD/mlops/deploy:/checks:ro" \
  -w /checks prom/prometheus:v3.5.0 test rules alerts-test.yml
```

## CI/CD

Стадии: `lint`, `formating`, `test`, `build`, `save`, `deploy`. Восемь jobs включают
отдельные `test_alerts` и `deploy_k8s`. Black запускается с
`--check`. BuildKit rootless публикует образ в Registry с временным тегом
`build-<pipeline-id>`; digest передаётся небольшим `build-metadata.json` artifact.
Stage save через Skopeo публикует тот же digest с тегом commit SHA
(`--preserve-digests`), без Docker daemon. Это исключает зависимость от размера
GitLab artifacts. Датасеты и tar-архивы в Git не загружаются. Deploy использует
immutable digest и явно выбранную версию модели. Деплой manual на основной ветке.

В GitLab требуются masked/hidden Variables: `SSH_PRIVATE_KEY_B64`,
`SSH_KNOWN_HOSTS_B64` (проверенный host key), `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`.
Base64 нужен для совместимости маскирования многострочных значений.
Дополнительно задаются `S3_BUCKET`, `DEPLOY_USER`, `DEPLOY_HOST`, `MODEL_VERSION`, `MODEL_MANIFEST_KEY`.
Protected Variables требуют protected основной ветки. Registry credentials в save
предоставляет GitLab. На ВМ требуются файлы `~/ecom-secrets/s3.env`,
`~/ecom-secrets/monitoring.env` (с `GRAFANA_PASSWORD`).
Deploy передаёт короткоживущий `CI_REGISTRY_PASSWORD` через SSH stdin;
`scripts/deploy_on_vm.sh` использует временный Docker config и удаляет его после
завершения. Постоянный Registry token на ВМ не требуется.
S3-ключи хранятся в masked/hidden Variables для операций с данными;
init на ВМ использует свой приватный файл. Временные Registry-теги `build-*`
можно удалять после проверки соответствующего commit-тега.

Учебный Runner принимает только jobs с тегом `k8s`; он указан в `default.tags`.
DinD на выданном Runner недоступен; используется BuildKit rootless по
[инструкции GitLab](https://docs.gitlab.com/ci/docker/using_buildkit/).
Для Kubernetes дополнительно используются protected Variables `KUBE_CONFIG_B64`,
`KUBE_NAMESPACE`, `GRAFANA_PASSWORD`; kubeconfig и пароль — masked/hidden.

Результаты проверок и ограничения — в [docs/report.md](docs/report.md).

Дополнительный Kubernetes: [Deployment/Service, API V2 и Helm-мониторинг](docs/kubernetes.md).

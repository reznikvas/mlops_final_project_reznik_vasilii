# Эксплуатация и сохранённые результаты

Состояние проверено 05–06.10.2026. Срок жизни учебной ВМ — 5 часов.
S3-артефакты и локальные протоколы проверок хранятся независимо от ВМ.

## Доступ к текущему запуску

Адрес локального API: http://127.0.0.1:32000/docs.
При работающих SSH-туннелях доступны:

| Интерфейс | Адрес на ПК |
|---|---|
| API ВМ | http://127.0.0.1:18000/docs |
| Airflow | http://127.0.0.1:18082 |
| ClearML | http://127.0.0.1:18080 |
| Grafana | http://127.0.0.1:13000/d/ecom |
| Prometheus | http://127.0.0.1:19090 |

SSH-конфигурация — `.secrets/ssh_config`, имя хоста `course-vm`.
Пользователи Airflow и Grafana: `admin`; пароли находятся соответственно в
`.secrets/airflow_admin_password` и `.secrets/grafana_password`.
Эти файлы приватные и не входят в Git. ClearML открыт только через loopback/SSH.

Команда запуска туннелей в отдельном терминале после закрытия прежних подключений:

```bash
ssh -F .secrets/ssh_config -N -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
  -L 18000:127.0.0.1:8000 -L 18082:127.0.0.1:8082 \
  -L 13000:127.0.0.1:3000 -L 19090:127.0.0.1:9090 \
  -L 13100:127.0.0.1:3100 -L 18008:127.0.0.1:8008 \
  -L 18080:127.0.0.1:8080 -L 18081:127.0.0.1:8081 course-vm
```

После перевыдачи требуется обновление SSH HostName и проверка нового host key.
Порты для новых туннелей должны быть свободны.

## Повтор обучения и обновление сервисов

Текущий проект на ВМ: `/home/ubuntu/ecom`, секреты: `/home/ubuntu/ecom-secrets`.
Локальный `.secrets/release.env` фиксирует фактически развёрнутые образ и модель.
Они также перечислены в [отчёте](report.md).

Проектный ClearML запускается на ВМ из каталога проекта:

```bash
sudo docker compose --env-file ../ecom-secrets/clearml.env \
  -f mlops/clearml/docker-compose.yaml up -d
```

`clearml.env` содержит собственные случайные `CLEARML_API_ACCESS_KEY` и
`CLEARML_API_SECRET_KEY`, заданные серверу. При восстановлении используются прежние значения.
Для повторного pipeline на ПК с открытым туннелем:

```bash
set -a
. .secrets/s3.env
. .secrets/clearml-sdk.env
set +a
PYTHONPATH="$PWD" uv run python -m mlops.clearml.clearml_pipeline \
  --processed-manifest Reznik_Vasilii_project/processed_data/f21822b6eef45530/manifest.json
```

SDK env задаёт API/Web/Files адреса `127.0.0.1` на портах 18008/18080/18081
и те же credentials. Файл `~/clearml.conf` при этом не изменяется.

После изменения кода DAG/подготовки требуется пересборка Airflow и замена контейнера
(команды на ВМ, из `/home/ubuntu/ecom`):

```bash
sudo docker compose --env-file ../ecom-secrets/services.env \
  -f mlops/airflow/docker-compose.yaml build airflow
sudo docker compose --env-file ../ecom-secrets/services.env \
  -f mlops/airflow/docker-compose.yaml up -d --no-deps --force-recreate airflow
```

БД и Fernet key сохраняются. Обычное обновление выполняется без `down -v`.
Для новой модели согласованно меняются `MODEL_VERSION` и `MODEL_MANIFEST_KEY`,
затем выполняется deploy Compose из README. Старые модельные volumes позволяют откат.

## Резервные копии

После возобновления ВМ 05.10 обнаружены и устранены два сбоя:
PostgreSQL Airflow не имел политики рестарта (добавлена `unless-stopped`),
а Docker-журнал API содержал 262 нулевых байта после выключения.
Старый журнал сохранён приватно в `.artifacts/backups/api-log-before-recreate.gz`;
пересоздан только API, без удаления модельного volume. Повторная проверка
Prometheus/Grafana/Loki на новых прогнозах прошла.
Протокол: [recovery-after-renewal.json](evidence/recovery-after-renewal.json).

При ошибке Alloy `invalid character '\\x00'` от Docker daemon сначала сохраняется
повреждённый журнал из `docker inspect --format '{{.LogPath}}' ecom-api` вне Git,
затем выполняется `compose up -d --no-deps --force-recreate --wait api` с текущими
env релиза. Активный Docker-журнал и volumes сохраняются без ручного изменения.
После восстановления выполняется `scripts.verify_monitoring`.

На ПК сохранены `.artifacts/backups/airflow.sql.gz` и
`.artifacts/backups/clearml-volumes.tar.gz`, права 600. Первый — `pg_dump` БД Airflow;
второй — архив volumes остановленного ClearML: `mongo/`, `elastic/`, `redis/`, `files/`.
После архивации ClearML запущен и все задачи повторно проверены.
`gzip -t` обоих архивов прошёл. Восстановление проверено 06.10.2026 в отдельном
Compose-проекте с пустыми volumes на существующей ВМ: 5 DAG runs, 12 ClearML-задач,
расшифровка Connection и SHA256 четырёх файлов артефактов совпали.
[Протокол](evidence/backup-restore.json). Временные контейнеры и volumes удалены;
развёртывание инфраструктуры на новой ВМ отдельно не проверялось.

Архивы содержат приватные данные сервисов. Резервная копия `.secrets/` также
хранится в приватном хранилище: без исходного Fernet key Airflow не расшифрует Connection.
CSV, processed и модель доступны в S3; Docker-образ сохранён локально в
`.artifacts/ecom-image.tar.gz`. Эти файлы исключены из Git.

Порядок восстановления на **новой ВМ с пустыми volumes**:

1. Доставка проекта, приватных env и архивов по SSH с сохранением версий образов.
2. Создание остановленных контейнеров ClearML через `compose create`.
   Архив распаковывается в volumes `ecom-clearml_mongo`, `ecom-clearml_elastic`,
   `ecom-clearml_redis`, `ecom-clearml_files`, смонтированные соответственно как
   `/restore/mongo`, `/restore/elastic`, `/restore/redis`, `/restore/files`.
   Команда распаковки внутри вспомогательного контейнера: `tar -xzf /backup/clearml-volumes.tar.gz -C /restore`.
   Затем выполняются запуск ClearML и проверка задач из отчёта. Fileserver и
   webserver ожидают успешный healthcheck API; его готовность обязательна.
3. Запуск только PostgreSQL Airflow, ожидание readiness и импорт dump
   через `gzip -dc airflow.sql.gz | docker compose ... exec -T postgres psql -v ON_ERROR_STOP=1 -U airflow -d airflow`.
   Затем выполняются запуск Airflow с прежним Fernet key и проверка DAG/Connections.
4. Загрузка Docker-образа через `docker load`, запуск инференса и мониторинга
   по README; model-init скачает согласованную модель из S3.
5. Повтор smoke и проверки мониторинга. При восстановлении существующих volumes
   сначала требуется отдельная резервная копия; описанный порядок рассчитан на пустые БД.

## CI/CD в новом окружении

Для нового окружения требуются CI Variables и Runner с тегом `k8s`.
Сборка использует rootless BuildKit; privileged Runner не требуется.
Registry login использует токен текущего CI job и временный Docker config на ВМ.
Полный перечень переменных — в README; дополнения Kubernetes — в [инструкции](kubernetes.md).
Все шесть стадий CI/CD пройдены в pipeline 11202, включая deploy jobs 66164/66165 и тесты алертов.
В следующих pipeline manual deploy выбранной пары image digest/model запускается
после успешных build/save. Смена ВМ требует проверки адреса и доверенного host key.

## Отдельный SSH-ключ CI

Ключ пользователя `ubuntu` действует до 05.11.2026 23:59:59 по Белграду
(22:59:59 UTC). На ВМ с часовым поясом `Etc/UTC` запись имеет параметры
`restrict,expiry-time="20261105225959"`. OpenSSH этой ВМ принимает время
в системном часовом поясе без суффикса `Z`. `restrict` запрещает перенаправление
портов, agent/X11 forwarding, PTY и пользовательский rc; команды deploy разрешены.
Вход проверен с `IdentitiesOnly=yes`, перенаправление получило
`administratively prohibited`. [Протокол и fingerprint](evidence/ci-ssh-key.json).

Закрытый ключ находится только в `.secrets/ci_deploy_key` и CI Variable
`SSH_PRIVATE_KEY_B64` (masked, hidden, protected). Для досрочного отзыва из
`~ubuntu/.ssh/authorized_keys` удаляется только строка с указанным fingerprint/comment
`ecom-gitlab-ci-deploy`, затем удаляется эта переменная GitLab. Перевыдача ВМ
не продлевает срок действия ключа.

## Kubernetes

Инференс: `http://127.0.0.1:28000/docs`, Grafana: `http://127.0.0.1:23000/d/ecom`,
Prometheus: `http://127.0.0.1:29090`, Loki: `http://127.0.0.1:23100` при работающих
port-forward. Команды запуска, Secret, quota и восстановление — в [kubernetes.md](kubernetes.md).
После замены Pod требуется новый port-forward API; мониторинг использует PVC.

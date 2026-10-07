# Репозиторий и результаты CI

Обязательный вариант на ВМ и дополнительный нативный Kubernetes реализованы. Код и доказательства опубликованы в
[репозитории проекта](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii).
[Pipeline 11202](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii/-/pipelines/11202)
и все восемь jobs — **success**, включая
[deploy 66164](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii/-/jobs/66164)
и [deploy_k8s 66165](https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii/-/jobs/66165).
После deploy повторены проверки API и мониторинга.

## Доступ CI

Отдельный SSH-ключ установлен для `ubuntu`. Срок действия — до 05.11.2026
23:59:59 по Белграду; перенаправление портов запрещено и проверено.
`SSH_PRIVATE_KEY_B64` создана как masked/hidden/protected Variable.
Все 12 CI Variables, включая доступ Kubernetes и пароль Grafana, настроены. Порядок отзыва — в [эксплуатации](operations.md).

## Ссылка

```text
https://mlops.gitlab.yandexcloud.net/s87443/mlops_final_project_reznik_vasilii
```

Датасеты и модели находятся в S3. Закрытые ключи, приватные архивы
и локальные отчёты исключены из Git. Инференс в Kubernetes использует Deployment/Service.

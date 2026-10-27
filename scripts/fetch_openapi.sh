#!/usr/bin/env bash
# Обновление вендорённой спецификации OpenAPI hh.ru (канон контрактных тестов).
# Спецификация публикуется по адресу ниже и перезаписывает docs/openapi/hh-openapi.yaml.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC_URL="https://api.hh.ru/openapi/specification/public"
SPEC_PATH="${REPO_ROOT}/docs/openapi/hh-openapi.yaml"

# Требование hh.ru к запросам: осмысленный User-Agent.
curl --fail --location --silent --show-error \
    --user-agent "ati-hh-mcp-dev" \
    --output "${SPEC_PATH}.tmp" \
    "${SPEC_URL}"

# Санитарная проверка: файл должен быть YAML-документом с ключом openapi.
if ! grep -q '^openapi:' "${SPEC_PATH}.tmp"; then
    echo "Ошибка: скачанный файл не похож на спецификацию OpenAPI" >&2
    rm -f "${SPEC_PATH}.tmp"
    exit 1
fi

mv "${SPEC_PATH}.tmp" "${SPEC_PATH}"
echo "Спецификация обновлена: ${SPEC_PATH} ($(stat -c%s "${SPEC_PATH}") байт)"

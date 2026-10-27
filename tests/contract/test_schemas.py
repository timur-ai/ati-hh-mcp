"""Контрактные тесты схем: записанные живые фикстуры против вендор-спеки.

Каждая фикстура ``docs/fixtures/*.json`` (конверт с полем ``operation``
и ``body``; записана ``scripts/record_fixtures.py`` с живого API и
санитизирована) валидируется через ``jsonschema`` против схемы ответа
этой операции в вендоренной спецификации.

Подготовка схем (обязательная, иначе ложные срабатывания):
- OAS 3.0 ``nullable: true`` переводится в объединение с ``null``
  (JSON Schema ключевого слова ``nullable`` не знает);
- все внутренние ``$ref`` переписываются в абсолютный URI документа
  спецификации, зарегистрированного в ``referencing.Registry``.

Расхождения живого API со спецификой собираются в ``KNOWN_DEVIATIONS``:
тест ЗЕЛЁНЫЙ и для валидных фикстур, и для перечисленных отклонений.
Защита от устаревших записей: если отклонение больше не воспроизводится
(фикстура стала валидной) или ключ не соответствует ни одной фикстуре –
тест красный, запись надо убрать.

Охват (план M4): каждая схема ответа read-only операций реализованных
публичных наборов (dictionaries/suggests/vacancies + справочники
employer_misc) покрыта хотя бы одной фикстурой; пробелы допустимы
только явной записью в ``COVERAGE_EXCEPTIONS``.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from . import groups_dictionaries, groups_suggests, groups_vacancies

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "docs" / "openapi" / "hh-openapi.yaml"
FIXTURES_DIR = PROJECT_ROOT / "docs" / "fixtures"
SPEC_URI = "hh-openapi.yaml"

MAX_ERRORS_IN_MESSAGE = 5

# Расхождения живого API со схемами вендор-спеки (доказано записанными
# фикстурами). Ключ – операция ("METHOD /path"), значение – комментарий.
KNOWN_DEVIATIONS: dict[str, str] = {
    "GET /suggests/companies": (
        "живой API возвращает null в полях, объявленных без nullable: "
        "items[].url, items[].area.name, items[].logo_urls "
        "(у компаний без сайта/логотипа и региона)"
    ),
}

# Схемы, сознательно не покрытые фикстурами (план M4 допускает пробелы
# только явной записью). Ключ – имя компонента схемы, значение – причина.
COVERAGE_EXCEPTIONS: dict[str, str] = {
    "VacanciesVacanciesResponse": (
        "живой API отвечает 403 forbidden с датацентрового IP "
        "(гео-блокировка поиска); перезаписать фикстуры запуском "
        "scripts/record_fixtures.py с разрешённой сети"
    ),
    "VacanciesVacancy": (
        "то же: карточка вакансии недоступна без успешного поиска "
        "(403 с этого IP)"
    ),
    "VacanciesVacancyConditions": (
        "то же: /vacancy_conditions отвечает 403 с этого IP"
    ),
}

# Справочники статистики зарплат (employer_misc-словари); группа
# employer_misc может ещё не существовать – тогда встроенный список.
_SALARY_DICTIONARY_OPERATIONS: set[tuple[str, str]] = {
    ("GET", "/salary_statistics/dictionaries/salary_industries"),
    ("GET", "/salary_statistics/dictionaries/professional_areas"),
    ("GET", "/salary_statistics/dictionaries/employee_levels"),
    ("GET", "/salary_statistics/dictionaries/salary_areas"),
}


def _prepare_spec_node(node: Any) -> Any:
    """Абсолютные ``$ref`` по всему документу + nullable -> union с null."""
    if isinstance(node, dict):
        prepared = {}
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/"):
                prepared[key] = SPEC_URI + value
            else:
                prepared[key] = _prepare_spec_node(value)
        if prepared.get("nullable") is True:
            base = {k: v for k, v in prepared.items() if k != "nullable"}
            if "type" in base:
                type_name = base["type"]
                base["type"] = (
                    type_name if isinstance(type_name, list) else [type_name, "null"]
                )
                prepared = base
            else:
                prepared = {"anyOf": [base, {"type": "null"}]}
        return prepared
    if isinstance(node, list):
        return [_prepare_spec_node(item) for item in node]
    return node


@cache
def _spec() -> dict[str, Any]:
    """Вендор-спека с препроцессингом (парсится один раз на процесс)."""
    with SPEC_PATH.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _prepare_spec_node(raw)


@cache
def _registry() -> Registry:
    spec = _spec()
    return Registry().with_resource(SPEC_URI, Resource.opaque(spec))


def _operation(operation_id: str) -> dict[str, Any]:
    method, _, path = operation_id.partition(" ")
    path_item = _spec().get("paths", {}).get(path)
    assert path_item is not None, f"путь {path!r} отсутствует в спецификации"
    op = path_item.get(method.lower())
    assert op is not None, f"операция {operation_id!r} отсутствует в спецификации"
    return op


def _response_schema(operation_id: str, status: int) -> dict[str, Any] | None:
    """Схема тела ответа операции (по статусу, иначе default)."""
    variants = _operation(operation_id).get("responses", {})
    variant = variants.get(str(status)) or variants.get("default")
    if not isinstance(variant, dict):
        return None
    for media in variant.get("content", {}).values():
        if isinstance(media, dict) and "schema" in media:
            schema: dict[str, Any] = media["schema"]
            return schema
    return None


def _top_schema_name(operation_id: str) -> str | None:
    """Имя компонента схемы ответа 200 (для учёта охвата), иначе None."""
    schema = _response_schema(operation_id, 200)
    if isinstance(schema, dict):
        ref = schema.get("$ref", "")
        if isinstance(ref, str) and ref.startswith(SPEC_URI + "#/components/schemas/"):
            return ref.rsplit("/", 1)[-1]
    return None


def _fixture_files() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def _format_errors(errors: list[ValidationError]) -> str:
    parts = []
    for error in errors[:MAX_ERRORS_IN_MESSAGE]:
        location = "/".join(str(part) for part in error.absolute_path) or "<корень>"
        parts.append(f"{location}: {error.message}")
    hidden = len(errors) - len(parts)
    suffix = f" … и ещё {hidden}" if hidden > 0 else ""
    return "; ".join(parts) + suffix


@pytest.fixture(scope="module")
def fixtures_by_operation() -> dict[str, Path]:
    """operation -> файл фикстуры (последняя при повторах)."""
    result: dict[str, Path] = {}
    for path in _fixture_files():
        envelope = json.loads(path.read_text(encoding="utf-8"))
        result[str(envelope["operation"])] = path
    return result


def test_fixtures_present() -> None:
    assert FIXTURES_DIR.is_dir(), "каталог docs/fixtures отсутствует"
    files = _fixture_files()
    assert files, "нет ни одной фикстуры – запустите scripts/record_fixtures.py"


@pytest.mark.parametrize("fixture_path", _fixture_files(), ids=lambda p: p.stem)
def test_fixture_matches_openapi_schema(fixture_path: Path) -> None:
    """Тело фикстуры валидно против схемы операции (или отклонение задокументировано)."""
    envelope = json.loads(fixture_path.read_text(encoding="utf-8"))
    operation_id = str(envelope["operation"])
    status = int(envelope["status"])

    schema = _response_schema(operation_id, status)
    assert schema is not None, (
        f"{fixture_path.name}: у операции {operation_id} нет схемы ответа "
        f"со статусом {status} (и default)"
    )

    validator = Draft202012Validator(schema, registry=_registry())
    errors = sorted(validator.iter_errors(envelope["body"]), key=lambda e: e.absolute_path)

    if errors:
        assert operation_id in KNOWN_DEVIATIONS, (
            f"{fixture_path.name}: живой ответ {operation_id} не проходит "
            f"валидацию схемы и не задокументирован как отклонение: "
            f"{_format_errors(errors)}"
        )
    else:
        assert operation_id not in KNOWN_DEVIATIONS, (
            f"{fixture_path.name}: {operation_id} валиден против спеки – "
            "запись KNOWN_DEVIATIONS устарела, удалите её"
        )


def test_known_deviations_reference_existing_fixtures(
    fixtures_by_operation: dict[str, Path],
) -> None:
    """Каждая запись KNOWN_DEVIATIONS соответствует фикстуре (защита от гнили)."""
    stale = sorted(set(KNOWN_DEVIATIONS) - set(fixtures_by_operation))
    assert not stale, (
        f"KNOWN_DEVIATIONS ссылается на операции без фикстур (устарело): {stale}"
    )


def _coverage_operations() -> set[tuple[str, str]]:
    ops: set[tuple[str, str]] = set()
    for group in (groups_dictionaries, groups_suggests, groups_vacancies):
        ops |= set(group.OPERATIONS)
    try:
        from . import groups_employer_misc

        salary = {
            (method, path)
            for method, path in groups_employer_misc.OPERATIONS
            if path.startswith("/salary_statistics/dictionaries/")
        }
        ops |= salary or _SALARY_DICTIONARY_OPERATIONS
    except ImportError:
        ops |= _SALARY_DICTIONARY_OPERATIONS
    return ops


def test_response_schema_coverage(fixtures_by_operation: dict[str, Path]) -> None:
    """≥1 фикстуры на каждую схему ответа read-only публичных наборов."""
    required: dict[str, set[str]] = {}  # схема -> операции, которые её отдают
    for method, path in sorted(_coverage_operations()):
        operation_id = f"{method} {path}"
        name = _top_schema_name(operation_id)
        if name is not None:
            required.setdefault(name, set()).add(operation_id)

    covered = {
        name
        for name in (
            _top_schema_name(operation_id) for operation_id in fixtures_by_operation
        )
        if name is not None
    }

    missing = {
        name: ops
        for name, ops in required.items()
        if name not in covered and name not in COVERAGE_EXCEPTIONS
    }
    stale = sorted(set(COVERAGE_EXCEPTIONS) & covered)
    unknown = sorted(set(COVERAGE_EXCEPTIONS) - set(required))

    assert not stale, (
        f"COVERAGE_EXCEPTIONS содержит уже покрытые схемы (устарело): {stale}"
    )
    assert not unknown, (
        f"COVERAGE_EXCEPTIONS содержит схемы вне публичных наборов: {unknown}"
    )
    assert not missing, (
        "схемы без фикстур (добавьте запись в COVERAGE_EXCEPTIONS с "
        "обоснованием либо запишите фикстуру): "
        + "; ".join(f"{name} <- {sorted(ops)}" for name, ops in sorted(missing.items()))
    )

    covered_required = len([name for name in required if name in covered])
    print(
        f"\n[coverage] схем ответа покрыто фикстурами: {covered_required} "
        f"из {len(required)}; явных исключений: {len(COVERAGE_EXCEPTIONS)}"
    )

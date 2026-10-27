"""Запись живых фикстур hh.ru для контрактных тестов (M4).

Только read-only GET-запросы к публичному API; ответы sanitiz-ируются
(репозиторий публичный) и складываются в ``docs/fixtures/`` в формате::

    {
      "operation": "GET /areas/{area_id}",   # операция вендор-спеки
      "url": "/areas/113",                    # фактический запрос
      "recorded_at": "<ISO-8601 UTC>",
      "status": 200,
      "sanitize": "basic" | "strict",
      "body": <ответ API>
    }

Запуск::

    uv run python scripts/record_fixtures.py

Поведение:
- пауза 0.7 с между запросами; при 429 – пауза Retry-After (фолбэк 2 с)
  и повтор, до 3 попыток; прочие неуспехи – пропуск с предупреждением;
- ``HH_TOKEN``/``HH_LIVE_TOKEN`` (только env, не из репозитория)
  включают запись ``GET /me`` и ``GET /negotiations`` с ЖЁСТКОЙ
  санитизацией (имена, телефоны, email, токены, ссылки с секретами);
- ``HH_UA_EMAIL`` добавляет контактный email в User-Agent (правило hh.ru).

Скрипт идемпотентен: повторный запуск перезаписывает фикстуры свежими
ответами.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API_BASE = os.environ.get("HH_API_BASE", "https://api.hh.ru").rstrip("/")
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "docs" / "fixtures"
PAUSE_SECONDS = 0.7
MAX_ATTEMPTS = 3
RATE_LIMIT_FALLBACK_PAUSE = 2.0

USER_AGENT = "ati-hh-mcp-dev"
_ua_email = os.environ.get("HH_UA_EMAIL", "").strip()
if _ua_email:
    USER_AGENT = f"{USER_AGENT} ({_ua_email})"

# -- санитизация ---------------------------------------------------------

# Email в любом строковом значении.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Российский телефон: +7/8 и 10 цифр с типичными разделителями.
_PHONE_RE = re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")
# Маркеры секретов в query-части ссылки.
_SECRET_QUERY_RE = re.compile(r"(token|key|secret|code|client_id|jwt)", re.IGNORECASE)

NAME_SUBSTITUTES = {"first_name": "Иван", "last_name": "Иванов", "middle_name": "Иванович"}
PHONE_OBJECT_KEYS = frozenset({"country", "city", "number"})


def _sanitize_string(value: str) -> str:
    """Замена email и телефонов в строке."""
    value = _EMAIL_RE.sub("user@example.com", value)
    return _PHONE_RE.sub("+70000000000", value)


def _sanitize_url_query(value: str) -> str:
    """Ссылки с секретоподобными query-параметрами – без query-части."""
    if value.startswith(("http://", "https://")) and "?" in value:
        base, _, query = value.partition("?")
        if _SECRET_QUERY_RE.search(query):
            return base
    return value


def sanitize_body(node: Any, *, strict: bool) -> Any:
    """Рекурсивная санитизация ответа API.

    Базовая (все фикстуры): email и телефоны в строках.
    Жёсткая (/me, /negotiations): дополнительно имена, структурированные
    телефоны, ключи с токенами (удаляются), query-секреты в ссылках.
    Замены сохраняют типы и структуру – фикстура остаётся валидной
    против схемы ответа.
    """
    if isinstance(node, dict):
        result: dict[str, Any] = {}
        keys = set(node)
        for key, value in node.items():
            if strict and "token" in key.lower():
                continue  # ключи-токены удаляются целиком
            if strict and key in NAME_SUBSTITUTES and isinstance(value, str):
                result[key] = NAME_SUBSTITUTES[key]
                continue
            if strict and keys >= PHONE_OBJECT_KEYS and isinstance(value, str):
                result[key] = "0"  # блок телефона: цифры в нули
                continue
            result[key] = sanitize_body(value, strict=strict)
        return result
    if isinstance(node, list):
        return [sanitize_body(item, strict=strict) for item in node]
    if isinstance(node, str):
        value = _sanitize_string(node)
        if strict:
            value = _sanitize_url_query(value)
        return value
    return node


# -- описание шагов записи ------------------------------------------------


@dataclass
class Step:
    """Один записываемый эндпоинт.

    ``path`` может быть шаблоном с ``{зависимостями}``, значения которых
    берутся из ``store`` (тела ранее записанных ответов).
    """

    operation: str  # операция вендор-спеки, напр. "GET /areas/{area_id}"
    path: str  # фактический путь, напр. "/areas/113" или "/skills?id={skill_id}"
    slug: str  # имя файла: get_<slug>.json
    params: dict[str, Any] = field(default_factory=dict)
    strict: bool = False
    requires_token: bool = False


def _first_item(body: Any, *keys: str) -> Any:
    """Первый элемент items ответа (или вложенного поля)."""
    if not isinstance(body, dict):
        return None
    node = body
    for key in keys:
        node = node.get(key)
        if node is None:
            return None
    if isinstance(node, list) and node:
        return node[0]
    return None


def _vacancy_id(store: dict[str, Any]) -> str | None:
    item = _first_item(store.get("get_vacancies"), "items")
    if isinstance(item, dict):
        nested = item.get("vacancy")
        if isinstance(nested, dict) and nested.get("id") is not None:
            return str(nested["id"])
        if item.get("id") is not None:
            return str(item["id"])
    return None


PUBLIC_STEPS: list[Step] = [
    Step("GET /dictionaries", "/dictionaries", "dictionaries"),
    Step("GET /areas", "/areas", "areas"),
    Step("GET /areas/countries", "/areas/countries", "areas_countries"),
    Step("GET /areas/{area_id}", "/areas/113", "areas_area_id"),
    Step("GET /industries", "/industries", "industries"),
    Step("GET /professional_roles", "/professional_roles", "professional_roles"),
    Step("GET /languages", "/languages", "languages"),
    Step("GET /locales", "/locales", "locales"),
    Step("GET /locales/resume", "/locales/resume", "locales_resume"),
    Step("GET /districts", "/districts", "districts", params={"area_id": "113"}),
    Step("GET /metro", "/metro", "metro"),
    Step("GET /metro/{city_id}", "/metro/4", "metro_city_id"),
    Step("GET /vacancy_conditions", "/vacancy_conditions", "vacancy_conditions"),
    # Подсказки (11): осмысленные тексты; id для skills/вузов берутся из них.
    Step("GET /suggests/areas", "/suggests/areas", "suggests_areas", {"text": "Москва"}),
    Step("GET /suggests/area_leaves", "/suggests/area_leaves", "suggests_area_leaves",
         {"text": "Моск", "area_id": "113"}),
    Step("GET /suggests/companies", "/suggests/companies", "suggests_companies",
         {"text": "HeadHunter"}),
    Step("GET /suggests/educational_institutions",
         "/suggests/educational_institutions", "suggests_educational_institutions",
         {"text": "Московский"}),
    Step("GET /suggests/fields_of_study", "/suggests/fields_of_study",
         "suggests_fields_of_study", {"text": "эконом"}),
    Step("GET /suggests/positions", "/suggests/positions", "suggests_positions",
         {"text": "разработчик"}),
    Step("GET /suggests/professional_roles", "/suggests/professional_roles",
         "suggests_professional_roles", {"text": "программист"}),
    Step("GET /suggests/resume_search_keyword", "/suggests/resume_search_keyword",
         "suggests_resume_search_keyword", {"text": "python"}),
    Step("GET /suggests/skill_set", "/suggests/skill_set", "suggests_skill_set",
         {"text": "python"}),
    Step("GET /suggests/vacancy_positions", "/suggests/vacancy_positions",
         "suggests_vacancy_positions", {"text": "инженер"}),
    Step("GET /suggests/vacancy_search_keyword", "/suggests/vacancy_search_keyword",
         "suggests_vacancy_search_keyword", {"text": "python"}),
    # skills и вузы: обязательный id – из подсказок выше.
    Step("GET /skills", "/skills", "skills", params={"id": "{skill_id}"}),
    Step("GET /educational_institutions", "/educational_institutions",
         "educational_institutions", params={"id": "{university_id}"}),
    Step("GET /educational_institutions/{id}/faculties",
         "/educational_institutions/{university_id}/faculties",
         "educational_institutions_id_faculties"),
    # Вакансии: поиск -> карточка -> похожие/related одного id.
    Step("GET /vacancies", "/vacancies", "vacancies",
         params={"text": "python", "per_page": "3"}),
    Step("GET /vacancies/{vacancy_id}", "/vacancies/{vacancy_id}", "vacancies_vacancy_id"),
    Step("GET /vacancies/{vacancy_id}/similar_vacancies",
         "/vacancies/{vacancy_id}/similar_vacancies", "vacancies_vacancy_id_similar"),
    Step("GET /vacancies/{vacancy_id}/related_vacancies",
         "/vacancies/{vacancy_id}/related_vacancies", "vacancies_vacancy_id_related"),
    # Работодатели: поиск -> карточка.
    Step("GET /employers", "/employers", "employers",
         params={"text": "HeadHunter", "per_page": "3"}),
    Step("GET /employers/{employer_id}", "/employers/{employer_id}",
         "employers_employer_id"),
    # Справочники статистики зарплат (employer_misc-словари).
    Step("GET /salary_statistics/dictionaries/salary_industries",
         "/salary_statistics/dictionaries/salary_industries",
         "salary_statistics_salary_industries"),
    Step("GET /salary_statistics/dictionaries/professional_areas",
         "/salary_statistics/dictionaries/professional_areas",
         "salary_statistics_professional_areas"),
    Step("GET /salary_statistics/dictionaries/employee_levels",
         "/salary_statistics/dictionaries/employee_levels",
         "salary_statistics_employee_levels"),
    Step("GET /salary_statistics/dictionaries/salary_areas",
         "/salary_statistics/dictionaries/salary_areas",
         "salary_statistics_salary_areas"),
]

TOKEN_STEPS: list[Step] = [
    Step("GET /me", "/me", "me", strict=True, requires_token=True),
    Step("GET /negotiations", "/negotiations", "negotiations",
         params={"per_page": "3"}, strict=True, requires_token=True),
]


# -- запись ---------------------------------------------------------------


def resolve_placeholders(text: str, store: dict[str, Any], step: Step) -> str | None:
    """Подставляет {ключи} в путь/параметры из уже записанных ответов.

    Возвращает None, если зависимость недоступна (шаг пропускается).
    """
    dependencies: dict[str, str | None] = {
        "skill_id": None,
        "university_id": None,
        "vacancy_id": _vacancy_id(store),
        "employer_id": None,
    }
    skill = _first_item(store.get("get_suggests_skill_set"), "items")
    if isinstance(skill, dict) and skill.get("id") is not None:
        dependencies["skill_id"] = str(skill["id"])
    university = _first_item(store.get("get_suggests_educational_institutions"), "items")
    if isinstance(university, dict) and university.get("id") is not None:
        dependencies["university_id"] = str(university["id"])
    employer = _first_item(store.get("get_employers"), "items")
    if isinstance(employer, dict) and employer.get("id") is not None:
        dependencies["employer_id"] = str(employer["id"])

    def substitute(value: str) -> str | None:
        found = re.findall(r"\{(\w+)\}", value)
        for name in found:
            resolved = dependencies.get(name)
            if resolved is None:
                print(
                    f"[skip] {step.operation}: нет зависимости {name!r} "
                    "(предыдущий шаг не записан)",
                    file=sys.stderr,
                )
                return None
            value = value.replace("{" + name + "}", resolved)
        return value

    return substitute(text)


async def fetch_json(
    client: httpx.AsyncClient, path: str, headers: dict[str, str] | None = None
) -> tuple[int, Any] | None:
    """GET с повторами на 429; None – шаг пропущен."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.get(path, headers=headers)
        except httpx.HTTPError as exc:
            print(f"[skip] {path}: сетевая ошибка {exc.__class__.__name__}", file=sys.stderr)
            return None
        if response.status_code != 429:
            break
        if attempt == MAX_ATTEMPTS:
            print(f"[skip] {path}: 429 после {MAX_ATTEMPTS} попыток", file=sys.stderr)
            return None
        retry_after = response.headers.get("Retry-After")
        try:
            pause = float(retry_after) if retry_after is not None else RATE_LIMIT_FALLBACK_PAUSE
        except ValueError:
            pause = RATE_LIMIT_FALLBACK_PAUSE
        await asyncio.sleep(max(pause, PAUSE_SECONDS))
    if response.status_code != 200:
        print(f"[skip] {path}: HTTP {response.status_code}", file=sys.stderr)
        return None
    try:
        return response.status_code, response.json()
    except ValueError:
        print(f"[skip] {path}: ответ не является JSON", file=sys.stderr)
        return None


async def record_step(
    client: httpx.AsyncClient,
    step: Step,
    store: dict[str, Any],
    token: str = "",
) -> str | None:
    """Записывает один шаг; возвращает slug или None."""
    request_path = resolve_placeholders(step.path, store, step)
    if request_path is None:
        return None
    params: dict[str, str] = {}
    for key, value in step.params.items():
        if isinstance(value, str) and "{" in value:
            resolved = resolve_placeholders(value, store, step)
            if resolved is None:
                return None
            value = resolved
        params[key] = str(value)

    query = f"?{httpx.QueryParams(params)}" if params else ""
    print(f"[get ] {step.operation} -> {request_path}{query}")
    # Токен прикрепляется только к токен-зависимым шагам (публичные
    # ответы остаются обезличенными).
    headers = {"Authorization": f"Bearer {token}"} if step.requires_token and token else None
    fetched = await fetch_json(client, f"{request_path}{query}", headers=headers)
    await asyncio.sleep(PAUSE_SECONDS)
    if fetched is None:
        return None
    status, body = fetched

    envelope = {
        "operation": step.operation,
        "url": f"{request_path}{query}",
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "sanitize": "strict" if step.strict else "basic",
        "body": sanitize_body(body, strict=step.strict),
    }
    target = FIXTURES_DIR / f"get_{step.slug}.json"
    target.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    store[f"get_{step.slug}"] = body
    print(f"[ok  ] {target.name} ({status})")
    return step.slug


async def main() -> int:
    token = (os.environ.get("HH_TOKEN") or os.environ.get("HH_LIVE_TOKEN") or "").strip()
    if not token:
        print(
            "[info] HH_TOKEN/HH_LIVE_TOKEN не заданы: /me и /negotiations "
            "пропускаются (токен-зависимые фикстуры)"
        )
    steps = list(PUBLIC_STEPS) + ([s for s in TOKEN_STEPS] if token else [])

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    recorded: list[str] = []
    store: dict[str, Any] = {}
    async with httpx.AsyncClient(base_url=API_BASE, headers=headers, timeout=30.0) as client:
        for step in steps:
            slug = await record_step(client, step, store, token=token)
            if slug is not None:
                recorded.append(slug)

    skipped = len(steps) - len(recorded)
    print(f"\nИтого: записано {len(recorded)}, пропущено {skipped} из {len(steps)} шагов")
    print(f"Каталог: {FIXTURES_DIR}")
    return 0 if recorded or not steps else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

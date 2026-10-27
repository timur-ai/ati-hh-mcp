"""Набор «extended»: операции hh.ru вне публичной OpenAPI.

ВНИМАНИЕ: операции этого набора не описаны в публичной спецификации
hh.ru и могут измениться без уведомления. Набор выключен по умолчанию
(включается через ``HH_TOOLSETS=extended``); каждый инструмент помечен
префиксом ``[UNDOCUMENTED hh.ru API]`` и флагом ``undocumented`` в реестре.

Подтверждённые источники (легаси-документация и проба живого API):
- ``POST /negotiations`` – отклик на вакансию; multipart/form-data
  (vacancy_id, resume_id, message); 201 Created + заголовок Location,
  303 See Other для вакансий с прямым откликом. Источник:
  docs/negotiations.md репозитория hhru/api (коммит до 2024-01-09,
  когда раздел перевели в OpenAPI; в текущей публичной спецификации
  операции нет – у /negotiations определён только GET);
- ``GET /resumes/mine`` – список резюме текущего пользователя; URL
  упоминается публичной спецификацией в ответе /me (поле resumes_url),
  но самой операции в спецификации нет;
- ``GET /artifacts/{photo|portfolio}`` – список артефактов; источник:
  docs/artifacts.md репозитория hhru/api (удалён в 2022);
- ``DELETE /artifacts/{artifact_id}`` – удаление артефакта (204);
  тот же источник. Вариант пути ``DELETE /artifacts/{type}/{id}``
  живым API отвергается (404) – не используется.

TODO (не реализовано, источник не подтверждает ссылочный механизм):
- ``POST /artifacts`` – прямая multipart-загрузка файла (type,
  description, file; ограничения – GET /artifacts/{type}/conditions).
  Загрузка бинарного файла через MCP-инструмент требует отдельного
  проектирования; ссылочного эндпоинта (upload_link) для артефактов
  в документации нет. Источник: docs/artifacts.md (hhru/api, 2022).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import quote

from fastmcp import FastMCP

from ..config import Config
from ..hh.client import HHClient
from ..hh.errors import HHError
from ..registry import REGISTRY, ToolEntry

TOOLSET_NAME = "extended"

ClientFactory = Callable[[], HHClient]

_ARTIFACT_TYPES = ("photo", "portfolio")


def _default_client_factory() -> HHClient:
    return HHClient(Config.from_env())


def _confirm_required() -> HHError:
    """Ошибка не подтверждённой мутации (единая семантика с toolkit)."""
    return HHError("confirm_required", "Подтвердите операцию: передайте confirm=True.")


def register(mcp: FastMCP, client_factory: ClientFactory | None = None) -> None:
    """Подключает инструменты extended-набора к серверу.

    ``client_factory`` возвращает настроенный HHClient (токен выбирается
    на стороне сервера: env/заголовок/OAuth-профиль).
    """
    factory = client_factory if client_factory is not None else _default_client_factory

    entries = (
        ToolEntry(
            name="apply_to_vacancy",
            operation_id="POST /negotiations",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=True,
            undocumented=True,
        ),
        ToolEntry(
            name="my_resumes",
            operation_id="GET /resumes/mine",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=False,
            undocumented=True,
        ),
        ToolEntry(
            name="artifacts_list",
            operation_id="GET /artifacts/{artifact_type}",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=False,
            undocumented=True,
        ),
        ToolEntry(
            name="artifact_delete",
            operation_id="DELETE /artifacts/{artifact_id}",
            toolset=TOOLSET_NAME,
            requires_auth=True,
            is_mutation=True,
            undocumented=True,
        ),
    )
    for entry in entries:
        REGISTRY.register(entry)

    # -- apply_to_vacancy -------------------------------------------------
    async def apply_to_vacancy(
        vacancy_id: str,
        resume_id: str,
        message: str | None = None,
        confirm: bool = False,
    ) -> Any:
        """[UNDOCUMENTED hh.ru API] Apply to a vacancy with a resume.

        Undocumented POST /negotiations: multipart form with vacancy_id,
        resume_id and optional cover-letter message. Returns the created
        negotiation (201 Created) or a redirect URL for direct-apply
        vacancies (303). Mutation: requires confirm=True.
        """
        if not confirm:
            raise _confirm_required()
        fields = {"vacancy_id": vacancy_id, "resume_id": resume_id}
        if message is not None:
            fields["message"] = message
        client = factory()
        try:
            # Клиентский multipart: троттлинг и маппинг ошибок как обычно;
            # сырой ответ нужен для различения 201/303 и заголовка Location.
            response = await client.post_multipart("/negotiations", fields=fields)
        finally:
            await client.aclose()
        if response.status_code == 303:
            return {
                "created": False,
                "redirect_url": response.headers.get("Location"),
                "note": "вакансия с прямым откликом: перейдите по ссылке",
            }
        if response.content:
            try:
                return response.json()
            except ValueError:
                pass
        return {"created": True, "location": response.headers.get("Location")}

    # -- my_resumes --------------------------------------------------------
    async def my_resumes() -> Any:
        """[UNDOCUMENTED hh.ru API] List resumes of the current user.

        Undocumented GET /resumes/mine: published resumes of the
        authorized applicant (the URL is referenced by the public /me
        response field resumes_url).
        """
        client = factory()
        try:
            return await client.get("/resumes/mine")
        finally:
            await client.aclose()

    # -- artifacts_list ----------------------------------------------------
    async def artifacts_list(artifact_type: Literal["photo", "portfolio"] = "photo") -> Any:
        """[UNDOCUMENTED hh.ru API] List user artifacts (photo, portfolio).

        Undocumented GET /artifacts/{photo|portfolio}: uploaded images
        with state (processing/failed/ok) and size variants.
        """
        if artifact_type not in _ARTIFACT_TYPES:
            raise HHError(
                "bad_request",
                f"Недопустимый тип артефакта: {artifact_type!r}.",
                hint=f"допустимые значения: {', '.join(_ARTIFACT_TYPES)}",
            )
        client = factory()
        try:
            return await client.get(f"/artifacts/{quote(artifact_type, safe='')}")
        finally:
            await client.aclose()

    # -- artifact_delete ---------------------------------------------------
    async def artifact_delete(artifact_id: str, confirm: bool = False) -> Any:
        """[UNDOCUMENTED hh.ru API] Delete a user artifact by id.

        Undocumented DELETE /artifacts/{artifact_id} (204 No Content).
        Mutation: requires confirm=True.
        """
        if not confirm:
            raise _confirm_required()
        encoded = quote(artifact_id, safe="")
        client = factory()
        try:
            await client.delete(f"/artifacts/{encoded}")
        finally:
            await client.aclose()
        return {"deleted": True, "artifact_id": artifact_id}

    for tool in (apply_to_vacancy, my_resumes, artifacts_list, artifact_delete):
        mcp.tool(tool)

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Request, Response, status
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.dependencies import get_email_settings_service, require_admin
from app.core.request_context import get_request_context
from app.models.user import User
from app.schemas.email_settings import (
    CreateNotificationRecipientRequest,
    CreateSenderIdentityRequest,
    CreateSmtpProfileRequest,
    ReplaceWorkflowMappingsRequest,
    SmtpTestEmailRequest,
    UpdateNotificationRecipientRequest,
    UpdateSenderIdentityRequest,
    UpdateSmtpProfileRequest,
)
from app.services.email_settings_service import EmailSettingsService

ADMIN = require_admin

router = APIRouter(
    prefix="/email-settings",
    tags=["email-settings"],
    dependencies=[Depends(ADMIN)],
)


@router.get("/smtp")
async def get_smtp_settings(
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.get_overview()


@router.get("/smtp/profiles/{profile_id}")
async def get_smtp_profile(
    profile_id: int,
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.get_profile(profile_id)


@router.post("/smtp/profiles", status_code=status.HTTP_201_CREATED)
async def create_smtp_profile(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = CreateSmtpProfileRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.create_draft(
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.patch("/smtp/profiles/{profile_id}")
async def update_smtp_profile(
    profile_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = UpdateSmtpProfileRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.update_draft(
        profile_id,
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/smtp/profiles/{profile_id}/test-connection")
async def test_smtp_connection(
    profile_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.test_connection(
        profile_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/smtp/profiles/{profile_id}/test-email")
async def send_smtp_test_email(
    profile_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = SmtpTestEmailRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.test_email(
        profile_id,
        recipient_email=payload.recipient_email,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/smtp/profiles/{profile_id}/activate")
async def activate_smtp_profile(
    profile_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.activate(
        profile_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/smtp/use-environment")
async def use_environment_smtp(
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.use_environment(
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.get("/senders")
async def list_sender_identities(
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.list_senders()


@router.get("/senders/{sender_id}")
async def get_sender_identity(
    sender_id: int,
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.get_sender(sender_id)


@router.post("/senders", status_code=status.HTTP_201_CREATED)
async def create_sender_identity(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = CreateSenderIdentityRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.create_sender(
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.patch("/senders/{sender_id}")
async def update_sender_identity(
    sender_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = UpdateSenderIdentityRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.update_sender(
        sender_id,
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/senders/{sender_id}/activate")
async def activate_sender_identity(
    sender_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.activate_sender(
        sender_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/senders/{sender_id}/deactivate")
async def deactivate_sender_identity(
    sender_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.deactivate_sender(
        sender_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.get("/workflows")
async def get_workflow_catalogue(
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.get_workflow_catalogue()


@router.get("/workflow-mappings")
async def get_workflow_mappings(
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.get_workflow_mappings()


@router.put("/workflow-mappings")
async def replace_workflow_mappings(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = ReplaceWorkflowMappingsRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.replace_workflow_mappings(
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.get("/recipients")
async def list_notification_recipients(
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.list_recipients()


@router.post("/recipients", status_code=status.HTTP_201_CREATED)
async def create_notification_recipient(
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = CreateNotificationRecipientRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.create_recipient(
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.patch("/recipients/{recipient_id}")
async def update_notification_recipient(
    recipient_id: int,
    request: Request,
    body: dict[str, Any] = Body(...),
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    try:
        payload = UpdateNotificationRecipientRequest.model_validate(body)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors(include_url=False)) from exc
    return await service.update_recipient(
        recipient_id,
        payload,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/recipients/{recipient_id}/activate")
async def activate_notification_recipient(
    recipient_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.activate_recipient(
        recipient_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.post("/recipients/{recipient_id}/deactivate")
async def deactivate_notification_recipient(
    recipient_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> dict[str, Any]:
    return await service.deactivate_recipient(
        recipient_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification_recipient(
    recipient_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> Response:
    await service.delete_recipient(
        recipient_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/senders/{sender_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sender_identity(
    sender_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    service: EmailSettingsService = Depends(get_email_settings_service),
) -> Response:
    await service.delete_sender(
        sender_id,
        actor_user_id=user.id,
        context=get_request_context(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

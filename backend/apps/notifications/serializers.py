"""Serializers for Notifications API (Phase 3A)."""

from rest_framework import serializers

from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
    NotificationTemplateStatus,
)


class NotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "code",
            "name",
            "channel",
            "version",
            "subject_template",
            "body_ref",
            "status",
            "is_transactional",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "version", "created_at", "updated_at"]


class CreateNotificationTemplateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=128)
    channel = serializers.ChoiceField(choices=NotificationChannel.choices, default=NotificationChannel.EMAIL)
    subject_template = serializers.CharField(max_length=255)
    body_ref = serializers.CharField(max_length=255)
    is_transactional = serializers.BooleanField(default=True)


class NewTemplateVersionSerializer(serializers.Serializer):
    subject_template = serializers.CharField(max_length=255)
    body_ref = serializers.CharField(max_length=255)
    name = serializers.CharField(max_length=128, required=False)
    is_transactional = serializers.BooleanField(required=False, default=True)


class TemplatePreviewSerializer(serializers.Serializer):
    context = serializers.DictField(required=False, default=dict)


class NotificationDeliverySerializer(serializers.ModelSerializer):
    template_code = serializers.CharField(source="template.code", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True)
    channel = serializers.CharField(source="template.channel", read_only=True)

    class Meta:
        model = NotificationDelivery
        fields = [
            "id",
            "template",
            "template_code",
            "template_name",
            "channel",
            "recipient_email",
            "recipient_user",
            "status",
            "retry_count",
            "max_retries",
            "failure_reason",
            "payload_context",
            "queued_at",
            "sent_at",
            "failed_at",
        ]
        read_only_fields = fields

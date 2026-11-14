from __future__ import annotations

from rest_framework import serializers


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False, write_only=True)
    new_password = serializers.CharField(trim_whitespace=False, write_only=True, max_length=128)
    new_password_confirm = serializers.CharField(trim_whitespace=False, write_only=True, max_length=128)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password_confirm": "Пароли не совпадают."})
        return attrs

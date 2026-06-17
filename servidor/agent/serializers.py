from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = ['id', 'role', 'content', 'created_at', 'metadata']
        read_only_fields = ['id', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(source='messages.count', read_only=True)

    class Meta:
        model = Conversation
        fields = ['id', 'title', 'created_at', 'updated_at', 'message_count']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ChatInputSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=10000)
    map_state = serializers.JSONField(required=False, default=None)
    provider = serializers.CharField(max_length=100, required=False, default=None)
    model = serializers.CharField(max_length=200, required=False, default=None)


class ToolResultSerializer(serializers.Serializer):
    tool_name = serializers.CharField(max_length=100)
    tool_call_id = serializers.CharField(max_length=200, required=False, default="")
    result = serializers.JSONField(default=dict)
    success = serializers.BooleanField(default=True)
    provider = serializers.CharField(max_length=100, required=False, default=None)
    model = serializers.CharField(max_length=200, required=False, default=None)

"""
Views — Thin HTTP wrappers that delegate to the Agent.

These views handle:
- HTTP request/response (serialization, status codes)
- Persistence (saving messages to DB)
- Conversation management (create, list, delete)

They do NOT contain agent logic (prompt building, LLM calls, RAG retrieval).
"""
import json

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .agent import Agent
from .models import Conversation, Message
from .serializers import ChatInputSerializer, ConversationSerializer, MessageSerializer, ToolResultSerializer


class ConversationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer

    @action(detail=True, methods=['get'], url_path='messages')
    def messages(self, request, pk=None):
        """List all messages in a conversation."""
        conversation = self.get_object()
        serializer = MessageSerializer(conversation.messages.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat(self, request, pk=None):
        """Send a message and get an AI response."""
        conversation = self.get_object()

        input_serializer = ChatInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user_content = input_serializer.validated_data['content']
        map_state = input_serializer.validated_data.get('map_state')

        # Persist user message
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=user_content,
        )
        if not conversation.title:
            conversation.title = user_content[:100]
            conversation.save(update_fields=['title'])

        # Build history and delegate to Agent
        history = _build_history(conversation)
        agent = Agent()
        result = agent.run(user_content, history, map_state=map_state)

        # Persist and return response
        metadata = {"sources": result.sources}
        if result.tool_calls:
            metadata["tool_calls"] = result.tool_calls

        assistant_msg = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=result.content,
            metadata=metadata,
        )

        data = MessageSerializer(assistant_msg).data
        data["type"] = result.type
        if result.tool_calls:
            data["tool_calls"] = result.tool_calls
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='tool-result')
    def tool_result(self, request, pk=None):
        """Receive tool execution results from the plugin."""
        conversation = self.get_object()

        serializer = ToolResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool_name = serializer.validated_data['tool_name']
        tool_call_id = serializer.validated_data['tool_call_id']
        result_data = serializer.validated_data['result']
        success = serializer.validated_data['success']

        # Persist tool result
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.SYSTEM,
            content=json.dumps({"tool": tool_name, "result": result_data, "success": success}),
            metadata={"role": "tool", "tool_call_id": tool_call_id, "tool_name": tool_name},
        )

        # Delegate to Agent
        history = _build_history(conversation)
        agent = Agent()
        result = agent.process_tool_result(tool_name, result_data, success, history)

        # Persist and return
        assistant_msg = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=result.content,
            metadata={"sources": result.sources},
        )

        data = MessageSerializer(assistant_msg).data
        data["type"] = result.type
        return Response(data, status=status.HTTP_201_CREATED)


def _build_history(conversation) -> list:
    """Convert conversation messages to list of dicts for the Agent."""
    messages = []
    for msg in conversation.messages.all():
        m = {"role": msg.role, "content": msg.content}
        if msg.metadata.get("tool_calls"):
            m["tool_calls"] = msg.metadata["tool_calls"]
        if msg.metadata.get("role") == "tool":
            m["role"] = "tool"
            m["tool_call_id"] = msg.metadata.get("tool_call_id", "")
        messages.append(m)
    return messages

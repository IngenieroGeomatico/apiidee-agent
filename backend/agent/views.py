from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .llm.config import get_llm_provider
from .models import Conversation, Message
from .prompts import SYSTEM_PROMPT
from .rag.retriever import retrieve_context
from .serializers import ChatInputSerializer, ConversationSerializer, MessageSerializer


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
        messages = conversation.messages.all()
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat(self, request, pk=None):
        """Send a message and get an AI response."""
        conversation = self.get_object()

        # Validate input
        input_serializer = ChatInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user_content = input_serializer.validated_data['content']

        # Save user message
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=user_content,
        )

        # Auto-title on first message
        if not conversation.title:
            conversation.title = user_content[:100]
            conversation.save(update_fields=['title'])

        # Retrieve conversation history
        history = conversation.messages.all()
        history_messages = [
            {"role": msg.role, "content": msg.content} for msg in history
        ]

        # RAG: retrieve relevant context
        rag_results = retrieve_context(query=user_content)
        context_text = _format_context(rag_results)

        # Build messages for LLM
        system_content = SYSTEM_PROMPT.format(context=context_text)
        llm_messages = [{"role": "system", "content": system_content}]
        llm_messages.extend(history_messages)

        # Call LLM
        provider = get_llm_provider()
        assistant_content = provider.chat(llm_messages)

        # Build source metadata from RAG results
        sources = [chunk["metadata"] for chunk in rag_results] if rag_results else []

        # Save assistant message
        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=assistant_content,
            metadata={"sources": sources},
        )

        serializer = MessageSerializer(assistant_message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


def _format_context(rag_results: list) -> str:
    """Format RAG results into a context string for the system prompt."""
    if not rag_results:
        return "No additional context available."

    parts = ["Relevant context from the API-IDEE codebase:\n"]
    for i, chunk in enumerate(rag_results, 1):
        source = chunk["metadata"].get("source", "unknown")
        parts.append(f"--- Source {i}: {source} ---")
        parts.append(chunk["content"])
        parts.append("")
    return "\n".join(parts)

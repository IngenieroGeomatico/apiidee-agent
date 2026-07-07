import uuid

from django.test import TestCase

from agent.models import Conversation, Message


class ConversationModelTest(TestCase):
    """Tests para el modelo Conversation."""

    def test_crear_conversation_uuid_autogenerado(self):
        """Verifica que al crear una Conversation se genera un UUID automáticamente."""
        conv = Conversation.objects.create(title="Test")
        self.assertIsInstance(conv.id, uuid.UUID)

    def test_crear_conversation_sin_titulo(self):
        """Verifica que se puede crear una Conversation sin título (blank=True)."""
        conv = Conversation.objects.create()
        self.assertEqual(conv.title, "")

    def test_str_con_titulo(self):
        """Verifica que __str__ devuelve el título cuando existe."""
        conv = Conversation.objects.create(title="Mi conversación")
        self.assertEqual(str(conv), "Mi conversación")

    def test_str_sin_titulo(self):
        """Verifica que __str__ devuelve el UUID como string cuando no hay título."""
        conv = Conversation.objects.create()
        self.assertEqual(str(conv), str(conv.id))

    def test_ordering_por_updated_at_descendente(self):
        """Verifica que las conversaciones se ordenan por -updated_at (más reciente primero)."""
        conv1 = Conversation.objects.create(title="Primera")
        conv2 = Conversation.objects.create(title="Segunda")
        # conv2 se creó después, así que debería aparecer primero
        conversaciones = list(Conversation.objects.all())
        self.assertEqual(conversaciones[0].id, conv2.id)
        self.assertEqual(conversaciones[1].id, conv1.id)

    def test_timestamps_se_generan_automaticamente(self):
        """Verifica que created_at y updated_at se generan automáticamente."""
        conv = Conversation.objects.create(title="Test timestamps")
        self.assertIsNotNone(conv.created_at)
        self.assertIsNotNone(conv.updated_at)


class MessageModelTest(TestCase):
    """Tests para el modelo Message."""

    def setUp(self):
        """Crea una conversación de prueba para vincular mensajes."""
        self.conversation = Conversation.objects.create(title="Conversación de prueba")

    def test_crear_message_vinculado_a_conversation(self):
        """Verifica que se puede crear un Message vinculado a una Conversation."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content=[{"type":"text","text":"Hola, ¿qué tal?"}],
        )
        self.assertEqual(msg.conversation, self.conversation)
        self.assertIsInstance(msg.id, uuid.UUID)

    def test_str_muestra_rol_y_contenido_truncado(self):
        """Verifica que __str__ muestra el rol y el contenido truncado a 50 caracteres."""
        contenido_largo = "A" * 100
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content=contenido_largo,
        )
        esperado = f"assistant: {'A' * 50}"
        self.assertEqual(str(msg), esperado)

    def test_str_contenido_corto(self):
        """Verifica que __str__ muestra el contenido completo si es menor a 50 caracteres."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Hola",
        )
        self.assertEqual(str(msg), "user: Hola")

    def test_role_choices_user(self):
        """Verifica que el rol 'user' es válido."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Mensaje de usuario",
        )
        self.assertEqual(msg.role, "user")

    def test_role_choices_assistant(self):
        """Verifica que el rol 'assistant' es válido."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="Mensaje de asistente",
        )
        self.assertEqual(msg.role, "assistant")

    def test_role_choices_system(self):
        """Verifica que el rol 'system' es válido."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.SYSTEM,
            content="Mensaje de sistema",
        )
        self.assertEqual(msg.role, "system")

    def test_cascade_delete_borra_mensajes(self):
        """Verifica que al borrar una Conversation se eliminan sus Messages en cascada."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Mensaje 1",
        )
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="Mensaje 2",
        )
        self.assertEqual(Message.objects.count(), 2)
        self.conversation.delete()
        self.assertEqual(Message.objects.count(), 0)

    def test_metadata_por_defecto_es_dict_vacio(self):
        """Verifica que metadata tiene como valor por defecto un diccionario vacío."""
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Sin metadata",
        )
        self.assertEqual(msg.metadata, {})

    def test_metadata_con_datos(self):
        """Verifica que metadata acepta datos JSON arbitrarios."""
        datos = {"sources": ["doc1.md", "doc2.md"], "tokens": 150}
        msg = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="Con metadata",
            metadata=datos,
        )
        msg.refresh_from_db()
        self.assertEqual(msg.metadata, datos)

    def test_ordering_por_created_at_ascendente(self):
        """Verifica que los mensajes se ordenan por created_at ascendente."""
        msg1 = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content="Primero",
        )
        msg2 = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="Segundo",
        )
        mensajes = list(Message.objects.all())
        self.assertEqual(mensajes[0].id, msg1.id)
        self.assertEqual(mensajes[1].id, msg2.id)

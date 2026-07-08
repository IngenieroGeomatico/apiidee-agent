from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, conversation_config, providers_list, test_api_key

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet)

urlpatterns = [
    path('providers/', providers_list, name='providers-list'),
    path('test-key/', test_api_key, name='test-api-key'),
    path('conversation-config/', conversation_config, name='conversation-config'),
    path('', include(router.urls)),
]

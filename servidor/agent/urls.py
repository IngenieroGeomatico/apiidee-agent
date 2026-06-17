from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ConversationViewSet, providers_list

router = DefaultRouter()
router.register(r'conversations', ConversationViewSet)

urlpatterns = [
    path('providers/', providers_list, name='providers-list'),
    path('', include(router.urls)),
]

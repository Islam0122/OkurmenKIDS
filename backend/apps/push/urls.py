from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.PushConfigView.as_view(), name="push-config"),
    path("subscriptions/", views.SubscriptionsView.as_view(), name="push-subscriptions"),
    path("subscriptions/unsubscribe/", views.UnsubscribeView.as_view(), name="push-unsubscribe"),
    path("preferences/", views.PreferencesView.as_view(), name="push-preferences"),
    path("test/", views.TestPushView.as_view(), name="push-test"),
]

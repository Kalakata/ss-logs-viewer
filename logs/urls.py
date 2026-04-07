from django.urls import path
from . import views

urlpatterns = [
    path('', views.explorer, name='explorer'),
    path('movements/', views.movements, name='movements'),
    path('cron/send-report/', views.trigger_report, name='trigger_report'),
    path('debug/types/', views.debug_types, name='debug_types'),
]

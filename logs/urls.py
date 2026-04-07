from django.urls import path
from . import views

urlpatterns = [
    path('', views.explorer, name='explorer'),
    path('cron/send-report/', views.trigger_report, name='trigger_report'),
]

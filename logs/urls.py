from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('api/search-groups/', views.search_groups, name='search_groups'),
    path('group/<str:group_id>/logs/', views.group_logs, name='group_logs'),
]

from django.conf.urls import url

from lists import views

urlpatterns = [
    url(r'^new$', views.new_list, name='new'),
    url(r'^(?P<list_id>\d+)/$', views.view_list, name='list'),
]

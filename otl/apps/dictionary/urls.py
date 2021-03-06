from django.conf.urls.defaults import *
from otl.apps.dictionary import views

urlpatterns = patterns('',
    (ur'^$', views.index),
    (ur'^search/$', views.search),
    (ur'^view/(\w+)/$', views.view),
    (ur'^professor/(\d+)/$', views.view_professor),
    (ur'^add_comment/$', views.add_comment),
    (ur'^delete_comment/$', views.delete_comment),
    (ur'^update_comment/$', views.update_comment),
    (ur'^professor_comment/$', views.professor_comment),
    (ur'^add_summary/$', views.add_summary),
    (ur'^autocomplete/$', views.get_autocomplete_list),
    (ur'^show_more_comments/$', views.show_more_comments),
    (ur'^add_favorite/$', views.add_favorite),
    (ur'^delete_favorite/$', views.delete_favorite),
    (ur'^get_recommend/$', views.interesting_courses),
    (ur'^get_summary_and_semester/$', views.get_summary_and_semester),
    (ur'^get_year_list/$', views.get_year_list),
    (ur'^add_lecture_summary/$', views.add_lecture_summary),
    (ur'^add_professor_info/$', views.add_professor_info),
)


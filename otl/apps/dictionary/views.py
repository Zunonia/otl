# -*- coding: utf-8
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.paginator import Paginator
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.utils.html import strip_tags, escape
from otl.apps.favorites.models import CourseLink
from otl.apps.common import *
from otl.utils.decorators import login_required_ajax
from otl.apps.accounts.models import Department
from otl.apps.timetable.models import Lecture
from otl.apps.dictionary.models import *

from django import template
template.add_to_builtins('django.templatetags.i18n')

from django.utils.translation import ugettext

def index(request):
    departments = Department.objects.all()
    return render_to_response('dictionary/index.html', {
        'section' : 'dictionary',
        'title' : ugettext(u'과목 사전'),
        'departments' : departments
    }, context_instance=RequestContext(request))

def department(request, department_id):
    dept = Department.objects.get(id=department_id)
    courses = Course.objects.filter(department=dept)
    return render_to_response('dictionary/department.html', {
        'section' : 'dictionary',
        'title' : ugettext(u'과목 사전'),
        'dept' : dept,
        'courses' : courses }, context_instance=RequestContext(request))

def search(request):
    pass

def view(request, course_code):
    course = None
    if Course.objects.filter(code=course_code).count() == 0:
        lecture = Lecture.objects.get(code=course_code)
        course = Course.objects.create(\
            code = course_code,\
            department = lecture.department,\
            title = lecture.title,\
            title_en = lecture.title_en,\
            type = lecture.type,\
            type_en = lecture.type_en,\
            audience = lecture.audience,\
            credit = lecture.credit,\
            num_classes = lecture.num_classes,\
            num_labs = lecture.num_labs,\
            credit_au = lecture.credit_au,\
            limit = lecture.limit,\
            is_english = lecture.is_english,\
            deleted = lecture.deleted,\
            summary = ''
        )
        for lecture in Lecture.objects.filter(code=course_code):
            course.lectures.add(lecture)
        course.save()
    else:
        course = Course.objects.get(code=course_code)
    comments = Comment.objects.filter(course=course)
    return render_to_response('dictionary/view.html', {
        'section' : 'dictionary',
        'title' : ugettext(u'과목 사전'),
        'course' : course,
        'comments' : comments
    }, context_instance=RequestContext(request))

@login_required
def add_comment(request, course_id):
    new_course = Course.objects.get(id=course_id)
    #TODO : new_lecture 는 코드는 복잡하나 교수님 정보밖에 불러오지 않으므로 최후에 더 필요하지 않을 경우 제거한다.
    new_lecture = Lecture.objects.filter(code = new_course.code, professor=request.POST['lecture_professor'], year=int(request.POST['lecture_semester'])/10, semester=int(request.POST['lecture_semester'])%10)
    new_comment = escape(strip_tags(request.POST['comment']))
    if request.POST['load'] == '1':
        new_load = 1
    elif request.POST['load'] == '2':
        new_load = 2
    else:
        new_load = 3
    if request.POST['score'] == '1':
        new_score = 1
    elif request.POST['score'] == '2':
        new_score = 2
    else:
        new_score = 3
    if request.POST['gain'] == '1':
        new_gain = 1
    elif request.POST['gain'] == '2':
        new_gain = 2
    else:
        new_gain = 3
    new_professor = new_lecture[0].professor
    new_semester = int(request.POST['lecture_semester'])
    comment = Comment.objects.create(\
        writer = request.user,\
        professor = new_professor,\
        course = new_course,\
        comment = new_comment,\
        load = new_load,\
        score = new_score,\
        gain = new_gain,\
        semester = new_semester\
    )
    comment.save()
    return HttpResponseRedirect('/dictionary/view/' + new_course.code)

@login_required
def delete_comment(request, comment_id):
    comment = Comment.objects.get(id=comment_id)
    if comment.User == request.user:
        comment.delete()
    return HttpResponseRedirect('/dictionary/view/' + comment.course.code)


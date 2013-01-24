# -*- coding: utf-8
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.core.paginator import Paginator
from django.core.exceptions import *
from django.core.serializers.json import DjangoJSONEncoder
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth.models import User
from django.http import *
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Avg, Max
from django.utils.html import strip_tags, escape
from django.utils import simplejson as json
from otl.apps.favorites.models import CourseLink
from otl.apps.common import *
from otl.utils import respond_as_attachment
from otl.utils.decorators import login_required_ajax
from otl.apps.accounts.models import Department, UserProfile
from otl.apps.timetable.models import Lecture
from otl.apps.dictionary.models import *
from otl.apps.timetable.views import _lectures_to_output

from django import template
template.add_to_builtins('django.templatetags.i18n')

from django.utils.translation import ugettext
from StringIO import StringIO
import datetime

from sets import Set

def index(request):

    #Make the semester info to make users select the semester which they want to view.
    semester_info = []
    semester_info.append({'year' : settings.START_YEAR, 'semester' : settings.START_SEMESTER})
    if settings.START_SEMESTER == 1 and settings.NEXT_YEAR > settings.START_YEAR:
        semester_info.append({'year' : settings.START_YEAR, 'semester' : 3})
    for y in range(settings.START_YEAR+1,settings.NEXT_YEAR):
        semester_info.append({'year' : y, 'semester' : 1})
        semester_info.append({'year' : y, 'semester' : 3})
    if settings.NEXT_SEMESTER == 3 and settings.NEXT_YEAR > settings.START_YEAR:
        semester_info.append({'year' : settings.NEXT_YEAR, 'semester' : 1})

    # Read the current user's timetable.
    if request.user.is_authenticated():
        my_lectures = [_lectures_to_output(Lecture.objects.filter(year=settings.NEXT_YEAR, semester=settings.NEXT_SEMESTER, timetable__user=request.user, timetable__table_id=id), False, request.session.get('django_language', 'ko')) for id in xrange(0,settings.NUMBER_OF_TABS)]
    else:
        my_lectures = [[], [], []]
    if settings.DEBUG:
        my_lectures_output = json.dumps(my_lectures, indent=4, ensure_ascii=False)
    else:
        my_lectures_output = json.dumps(my_lectures, ensure_ascii=False, sort_keys=False, separators=(',',':'))

    todo_comment_list = []
    if request.user.is_authenticated():
        comment_lecture_list = _get_unwritten_lecture_by_db(request.user)
        todo_comment_list = _lectures_to_output(comment_lecture_list, False, request.session.get('django_language','ko'))

    taken_lectures = taken_lecture_list(request)
    taken_lectures.reverse()

    return render_to_response('dictionary/index.html', {
        'section': 'dictionary',
        'title': ugettext(u'과목 사전'),
        'departments': Department.objects.filter(visible=True).order_by('name'),
        'my_lectures': my_lectures_output,
        'lang' : request.session.get('django_language', 'ko'),
        'semester_info' : semester_info,
        'dept': -1,
        'classification': 0,
        'keyword': json.dumps('',ensure_ascii=False,indent=4), 
        'in_category': json.dumps(False),
        'active_tab': -1,
        'favorite':favorites(request),
        'lecture_list': taken_lectures,
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
    try:
        q = {}
        for key, value in request.GET.iteritems():
            q[str(key)] = value
	output = _search(**q)
        lang = request.session.get('django_language','ko') 
        
        courses = _courses_to_output(output['courses'],False,lang)
        if output['professors'] != None:
            professors = _professors_to_output(output['professors'],False,lang)
        else:
            professors = [] 
        return HttpResponse(json.dumps({'courses':courses, 'professors':professors}, ensure_ascii=False, indent=4))
    except:
        return HttpResponseBadRequest()

def get_autocomplete_list(request):
    try:
        def reduce(list):
            return [item for sublist in list for subsublist in sublist for item in subsublist]
        q = {}

        department = request.GET.get('dept', None)
        type = request.GET.get('type', None)
        lang = request.GET.get('lang', 'ko')

        output = None
        cache_key = 'autocomplete-list-dict-cache:department=%s:type=%s:lang=%s'%(department,type,lang)
        output = cache.get(cache_key)
        if output is None:
            if lang == 'ko':
                func = lambda x:[[x.title, x.old_code],map(lambda y : y.professor_name,x.professors.all())] 
            elif lang == 'en':
                func = lambda x:[[x.title_en,x.old_code], map(lambda y: y.professor_name_en,x.professors.all())] 
            result = list(set(reduce(map(func, _search_by_dt(department, type)))))
            while None in result:
                result[result.index(None)] = 'None'
            output = json.dumps(result, ensure_ascii=False, indent=4)
            cache.set(cache_key, output, 3600)
        return HttpResponse(output)
    except:
        return HttpResponseBadRequest()

def show_more_comments(request):
    course_id = int(request.GET.get('course_id', -1))
    next_comment_id = int(request.GET.get('next_comment_id', -1))
    prof_id = int(request.GET.get('professor_id', -1))
    course = Course.objects.get(id=course_id)
    if next_comment_id == -2 : #nothing 
        return HttpResponse(json.dumps({
            'next_comment_id':0,
            'comments':[]}))
    if prof_id == -1 : #General
        if next_comment_id == -1:  #starting point
            comments = Comment.objects.filter(course=course).order_by('-id')[:settings.COMMENT_NUM]
        else:
            comments = Comment.objects.filter(course=course,id__lte=next_comment_id).order_by('-id')[:settings.COMMENT_NUM]
    else:
        professor = Professor.objects.get(professor_id=prof_id)
        lectures = professor.lecture_professor.all()
        q = Q()
        for lecture in lectures:
            q |= Q(lecture=lecture)
        q &= Q(course=course)
        if next_comment_id == -1:  #starting point
            comments = Comment.objects.filter(q).order_by('-id')[:settings.COMMENT_NUM]
        else:
            q &= Q(id__lte=next_comment_id)
            comments = Comment.objects.filter(q).order_by('-id')[:settings.COMMENT_NUM]

    lang=request.session.get('django_language','ko')
    comments_output = _comments_to_output(comments,False,lang,False)
   
    if len(comments)==0:
        return HttpResponse(json.dumps({
            'next_comment_id': -2,
            'comments':comments_output}))
    return HttpResponse(json.dumps({
        'next_comment_id': (comments[len(comments)-1].id)-1,
        'comments': comments_output}))


def view(request, course_code):
    course = None
    summary_output = None

    try:
        dept = int(request.GET.get('dept', -1))
        classification = int(request.GET.get('classification', 0))
        keyword = request.GET.get('keyword', "")
        in_category = request.GET.get('in_category', json.dumps(False))
        active_tab = int(request.GET.get('active_tab', -1))

        course = Course.objects.get(old_code=course_code.upper())
        lang=request.session.get('django_language','ko')

        course_output = _courses_to_output(course,True,lang)
        lectures_output = _lectures_to_output(Lecture.objects.filter(course=course), True, lang)
        professors_output = _professors_to_output(course.professors,True,lang)
        result = 'OK'
    except ObjectDoesNotExist:
        result = 'NOT_EXIST'

    return render_to_response('dictionary/view.html', {
        'result' : result,
        'lang' : request.session.get('django_language', 'ko'),
        'departments': Department.objects.filter(visible=True).order_by('name'),
        'course' : course_output,
        'lectures' : lectures_output,
        'professors' : professors_output,
        'dept': dept,
        'classification': classification,
        'keyword': keyword,
        'in_category': in_category,
        'active_tab': active_tab
        }, context_instance=RequestContext(request))

def view_professor(request, prof_id):
    professor = None

    try:
        dept = int(request.GET.get('dept', -1))
        classification = int(request.GET.get('classification', 0))
        keyword = request.GET.get('keyword', "")
        in_category = request.GET.get('in_category', json.dumps(False))
        active_tab = int(request.GET.get('active_tab', -1))

        professor = Professor.objects.filter(professor_id=int(prof_id))
        professor_output = _professors_to_output(professor,True,'ko')

        professor = Professor.objects.get(professor_id=int(prof_id))
        prof_info = ProfessorInfor.objects.filter(professor = professor).order_by('-id')
        if prof_info.count() > 0 :
            recent_prof_info = prof_info[0]
        else:
            recent_prof_info = None

        lang=request.session.get('django_language','ko')

        courses = Course.objects.filter(professors=professor)
        result = 'OK'

    except ObjectDoesNotExist:
        result = 'NOT_EXIST'

    return render_to_response('dictionary/professor.html', {
        'result' : result,
        'lang' : request.session.get('django_language', 'ko'),
        'departments': Department.objects.filter(visible=True).order_by('name'),
        'courses' : courses,
        'professor' : professor_output,
        'prof_info' : _professor_info_to_output(recent_prof_info,True,'ko'),
        'dept': dept,
        'classification': classification,
        'keyword': keyword,
        'in_category': in_category,
        'active_tab': active_tab
        }, context_instance=RequestContext(request))

@login_required
def add_professor_info(request):
    try:
        major = request.POST.get('major', None)
        email = request.POST.get('email', None)
        homepage = request.POST.get('homepage', None)
        prof_id = int(request.POST.get('prof_id', -1))
        if major == None or email == None or homepage == None or prof_id < 0:
            raise ValidationError()
        professor = Professor.objects.get(professor_id = prof_id)
        writer = request.user
        written_datetime = datetime.datetime.now()
        new_prof_info = ProfessorInfor(major=major, email=email, homepage=homepage, writer=writer, written_datetime=written_datetime, professor=professor)
        new_prof_info.save()
        result = 'OK'
    except ValidationError():
        return HttpResponseBadReqeust()
    except:
        return HttpResponseServerError()
    return HttpResponse(json.dumps({
        'result': result,
        'prof_info': _professor_info_to_output(new_prof_info,False,'ko')}))

def interesting_courses(request):
    # login이 되있든, 안되있든 교양과목은 추천에 들어간다
    hss = Department.objects.filter(code=settings.HSS_DEPARTMENT_CODE)
    q = Q()
    for dept in hss:
        q |= Q(department=dept)
    try:
        user = request.user
    	userprofile = UserProfile.objects.get(user=user)
	favorite_departments = userprofile.favorite_departments.all()
        user_department_id = 0

        if user.is_authenticated():
            user_profile = UserProfile.objects.get(user=user)
            department = user_profile.department
	    q |= Q(department=department)
        
	for department in favorite_departments:
	    q |= Q(department=department)
    except:
	user_department_id = 0 #Means Nothing

    courses = Course.objects.filter(q).distinct()
    courses_sorted=_get_courses_sorted(courses)	
    return HttpResponse(json.dumps({
	 'courses_sorted' : courses_sorted[:settings.INTERESTING_COURSE_NUM]}, ensure_ascii=False, indent=4))
 
def view_comment_by_professor(request):
    try:
        professor_id = int(request.GET.get('professor_id', -1))
        course_id = int(request.GET.get('course_id', -1))
        if professor_id < 0 or course_id < 0:
            raise ValidationError()
        professor = Professor.objects.get(professor_id=professor_id)
        course = Course.objects.get(id=course_id)
        lecture = Lecture.objects.filter(professor=professor, course=course) 
        if not lecture.count() == 1:
            raise ValidationError()
        comments = Comment.objects.filter(course=course, lecture=lecture)
        result = 'OK'
    except ValidationError:
        result = 'ERROR'
    except ObjectDoesNotExist:
        result = 'NOT_EXIST'
    return HttpResponse(json.dumps({
        'result': result,
        'comments': _comments_to_output(comments,False,request.session.get('django_language','ko'),False)}, ensure_ascii=False, indent=4))

@login_required_ajax
def add_comment(request):
    comment_num = 0
    try:
        new_comment = Comment.objects.none()
        course_id = int(request.POST.get('course_id',-1))
        year = int(request.POST.get('year',-1))
        semester = int(request.POST.get('semester',-1))
        professor_id = int(request.POST.get('professor_id',-1))
	status = int(request.POST.get('status',-1))
        if course_id >= 0 and year >=0 and semester >=0 and professor_id >=0:
            course = Course.objects.get(id=course_id)
        else:
            raise ValidationError()

        professor= Professor.objects.get(professor_id = professor_id)
        lectures = Lecture.objects.filter(course=course, professor=professor,year=year,semester=semester).order_by('class_no')

        if not lectures:
            lecture = None
        else:
            lecture = lectures[0]   # 여러번 들었을 경우 가장 최근에 들은 과목 기준으로 한다.
        
        comment = request.POST.get('comment', None)
        load = int(request.POST.get('load', -1))
        gain = int(request.POST.get('gain', -1))
        score = int(request.POST.get('score', -1))
        writer = request.user
        
        if load < 0 or gain < 0 or score < 0:
            raise ValidationError()

        #if Comment.objects.filter(course=course, lecture=lecture, writer=writer).count() > 0:
        #    raise AlreadyWrittenError()

        new_comment = Comment(course=course, lecture=lecture, writer=writer, comment=comment, load=load, score=score, gain=gain)
        new_comment.save()
	
	lectures = Lecture.objects.filter(course=course, professor=professor).order_by('class_no')
	if status == -1:
	    q = Q(course=course)
        else:
	    q=Q()
	    for lec in lectures:
		q |= Q(lecture=lec)
	    q &= Q(course=course) 
	comments = Comment.objects.filter(q) 
        new_comment = Comment.objects.filter(id=new_comment.id)  
        average = comments.aggregate(avg_score=Avg('score'),avg_gain=Avg('gain'),avg_load=Avg('load'))
        Course.objects.filter(id=course.id).update(score_average=average['avg_score'], load_average=average['avg_load'], gain_average=average['avg_gain'])
        comment_num = comments.count()

        result = 'ADD'

    except AlreadyWrittenError:
        result = 'ALREADY_WRITTEN'
        return HttpResponse(json.dumps({
            'result':result},  ensure_ascii=False, indent=4))
    except ValidationError:
        return HttpResponseBadRequest()
    #except:
    #    return HttpResponseServerError()

    return HttpResponse(json.dumps({
        'result': result,
        'average': average,
        'comment_num': comment_num,
        'comment': _comments_to_output(new_comment, False, request.session.get('django_language','ko'),False)}, ensure_ascii=False, indent=4))
            
@login_required_ajax
def delete_comment(request):
    average = {'avg_score':0, 'avg_gain':0, 'avg_load':0}
    comment_num = 0
    try:
        user = request.user
        comment_id = int(request.POST.get('comment_id', -1))
	prof_id = int(request.POST.get('prof_id', -1))
        if comment_id < 0:
            raise ValidationError()
        comment = Comment.objects.get(pk=comment_id, writer=user)
        comment.delete()
	course = comment.course
        
	result = 'DELETE'
        q=Q()
	if prof_id == -1:
	    q=Q(course=course)
	else:
            professor= Professor.objects.get(professor_id = prof_id)
            lectures = Lecture.objects.filter(course=course, professor=professor).order_by('class_no')
	    for lec in lectures:
		q |= Q(lecture=lec)
	    q &= Q(course=course)
	comments = Comment.objects.filter(q)
        average = {'score':0, 'gain':0, 'load':0}
        comment_num = comments.count()
        if comments.count() != 0 :
            average = comments.aggregate(avg_score=Avg('score'),avg_gain=Avg('gain'),avg_load=Avg('load'))
            Course.objects.filter(id=course.id).update(score_average=average['avg_score'],load_average=average['avg_load'],gain_average=average['avg_gain'])
        else :
            average = {'avg_score':0, 'avg_gain':0, 'avg_load':0}
            Course.objects.filter(id=course.id).update(score_average=0,load_average=0,gain_average=0)

    except ObjectDoesNotExist:
        result = 'REMOVE_NOT_EXIST'
    except ValidationError:
        return HttpResponseBadReqeust()
    #except:
    #    return HttpResponseServerError()

    return HttpResponse(json.dumps({
        'result': result, 'average': average, 'comment_num': comment_num}, ensure_ascii=False, indent=4)) 

@login_required_ajax
def delete_favorite(request):
    try:
        user = request.user
        course_id = int(request.POST.get('course_id', -1))
        
        if course_id < 0:
            raise ValidationError()
        
        course = Course.objects.get(id=course_id)
        UserProfile.objects.get(user=user).favorite.remove(course) 

        result = 'DELETE'

    except ObjectDoesNotExist:
        result = 'REMOVE_NOT_EXIST'
    except ValidationError:
        return HttpResponseBadReqeust()
    except:
        return HttpResponseServerError()

    return HttpResponse(json.dumps({
        'result': result}, ensure_ascii=False, indent=4)) 

def update_comment(request):
    comments = []

    try:
        count = int(request.POST.get('count', -1))
        q = {}
        hss = list(Department.objects.filter(code=settings.HSS_DEPARTMENT_CODE))
        if request.user.is_authenticated():
            user = request.user
            userprofile = UserProfile.objects.get(user=user)
            q['dept'] = userprofile.department
            q['fav_dept'] = hss
            for department in userprofile.favorite_departments.all():
                q['fav_dept'].append(department)
        else:
            q['dept'] = hss[0]
            if len(hss)>1:
                q['fav_dept'] = hss[1:]
	comments = _update_comment(count, **q)
	result = 'OK'

    except ObjectDoesNotExist:
        result = 'ERROR'

    comments_to_output = _comments_to_output(comments,False,request.session.get('django_language','ko'),True)
    return HttpResponse(json.dumps({
        'result': result,
        'comments': comments_to_output}, ensure_ascii=False, indent=4))

def professor_comment(request):
    comments = []

    try:
        count = int(request.POST.get('count', -1))
        prof_id = int(request.POST.get('prof_id', -1))
        q = {}
        q['professor'] = Professor.objects.get(professor_id=prof_id)
        comments = _update_comment(count, **q)
        result = 'OK'

    except ObjectDoesNotExist:
        result = 'ERROR'

    return HttpResponse(json.dumps({
        'result': result,
        'comments': _comments_to_output(comments,False,request.session.get('django_language','ko')) }, ensure_ascii=False, indent=4))

@login_required
def like_comment(request, comment_id):
    return

@login_required
def add_summary(request):
    try:
        content = request.POST.get('content', None)
        require = request.POST.get('require', None)
        course_id = int(request.POST.get('course_id', -1))
        course = Course.objects.get(id=course_id)
        if content == None or require == None or course_id < 0:
            raise ValidationError()
        writer = request.user
        written_datetime = datetime.datetime.now()
        new_summary = Summary(summary=content, writer=writer, written_datetime=written_datetime, course=course, prerequisite=require)
        new_summary.save()
        result = 'OK'
    except ValidationError:
        return HttpResponseBadRequest()
    except:
        return HttpResponseServerError()

    return HttpResponse(json.dumps({
        'result': result,
        'summary': _summary_to_output(new_summary,False,'ko')}))

@login_required
def add_lecture_summary(request):
    try:
        homepage = request.POST.get('homepage', None)
        mainbook = request.POST.get('mainbook', None)
	subbook = request.POST.get('subbook', None)
        course_id = int(request.POST.get('course_id', -1))
	prof_id = int(request.POST.get('professor_id', -1))
        course = Course.objects.get(id=course_id)
	if homepage == None or mainbook == None or course == None  or course_id < 0 or prof_id < 0:	
            raise ValidationError()
	professor = Professor.objects.get(professor_id=prof_id) 
	lectures = Lecture.objects.filter(professor=professor, course=course).order_by('-id')
	if lectures.count() == 0 :
	    raise ValidationError()
	lecture = lectures[0]
        writer = request.user
        written_datetime = datetime.datetime.now()
        new_summary = LectureSummary(homepage=homepage, main_material=mainbook, sub_material=subbook, writer=writer, written_datetime=written_datetime, lecture=lecture)
        new_summary.save()
        result = 'OK'
    except ValidationError:
        return HttpResponseBadRequest()
    except:
        return HttpResponseServerError()
    
    return HttpResponse(json.dumps({
        'result': result,
        'summary': _lecture_summary_to_output(new_summary,False,'ko')}))

@login_required
def get_year_list(request):
    try:
        course_id = int(request.POST.get('course_id',-1))
        year = int(request.POST.get('year',-1))
        semester = int(request.POST.get('semester',-1))
        course = Course.objects.get(id=course_id)
        lang=request.session.get('django_language','ko')
        lectures = Lecture.objects.filter(course=course,year=year,semester=semester)
        if lectures.count()>0:
            q = Q()
            for lecture in lectures:
                q |= Q(lecture_professor=lecture)
            professor = Professor.objects.filter(q).distinct()
        else:
            professor = []
        result = 'OK'
    except ObjectDoesNotExist:
        result='NOT_EXIST'
    except:
        return HttpResponseServerError()
    return HttpResponse(json.dumps({
        'result': result,
        'professor': _professors_to_output(professor,False,lang)}))

def get_summary_and_semester(request):
    summary_output = None
    average = {'avg_score':0, 'avg_gain':0, 'avg_load':0}
    comment_num = 0
    lang=request.session.get('django_language','ko')
    professor_name = ""
    lecture_title = ""
    try:
        prof_id = int(request.POST.get('professor_id',-1))
        course_id = int(request.POST.get('course_id',-1))
        course = Course.objects.get(id=course_id)
	if prof_id == -1:       # General
            summary = Summary.objects.filter(course=course).order_by('-id')
            semester = Lecture.objects.filter(course=course).order_by('-year','-semester').values('year', 'semester').distinct()
	    comments = Comment.objects.filter(course=course)
	    comment_num = comments.count()
	    if comments.count() != 0:
		average=comments.aggregate(avg_score=Avg('score'),avg_gain=Avg('gain'),avg_load=Avg('load'))
            if summary.count() > 0:
                recent_summary = summary[0]
                summary_output = _summary_to_output(recent_summary,False,lang);
                result = 'GENERAL'
            else:
                result = 'GEN_EMPTY'
        else:
	    professor = Professor.objects.get(professor_id=prof_id)
	    semester = Lecture.objects.filter(course=course,professor=professor).order_by('-year','-semester').values('year', 'semester').distinct()
	    professor_name = professor.professor_name
	    lectures = Lecture.objects.filter(professor=professor, course=course).order_by('-id')
	    lecture = lectures[0]
            lecture_title = _trans(lecture.title,lecture.title_en,lang)
	    summary = LectureSummary.objects.filter(lecture=lecture).order_by('-id')
	    q=Q()
	    for lec in lectures:
		q |= Q(lecture=lec)
	    comments = Comment.objects.filter(q)
	    comment_num = comments.count()
	    if comments.count() != 0:
		average=comments.aggregate(avg_score=Avg('score'),avg_gain=Avg('gain'),avg_load=Avg('load'))
	    if summary.count() > 0:
		recent_summary = summary[0]
		summary_output = _lecture_summary_to_output(recent_summary,False,lang)
		result = 'PROF'
	    else:
		result = 'PROF_EMPTY'
    except ObjectDoesNotExist:
        result='NOT_EXIST'
    except:
        return HttpResponseServerError()
    return HttpResponse(json.dumps({
        'result': result,
        'semester': _semesters_to_output(semester,False,lang),
	'average': average,
	'comment_num': comment_num,
	'prof_name': professor_name,
        'summary': summary_output,
        'lecture_title': lecture_title}))


@login_required
def add_favorite(request):
    try:
        if request.user.is_authenticated():
            user= request.user
            userprofile= UserProfile.objects.get(user=user)
            
            result = "ADD"

            course_id = int(request.POST.get('course_id',-1))
            course = Course.objects.get(id=course_id)
         
            if course_id < 0:
                raise ValidationError()
            
            if course in UserProfile.objects.get(user=user).favorite.all():
                result = "ALEADY_ADDED"
            else:
                userprofile.favorite.add(course)
                userprofile.save()
            new_favorite=[]
            new_favorite.append(course)
            return HttpResponse(json.dumps({
                    'result' : result,
                    'favorite' : _favorites_to_output(new_favorite,False,request.session.get('django_language','ko'))}))
    except ValidationError:
        return HttpResponseBadRequest()
    except:
        return HttpResponseServerError()

def favorites(request):
    """dictionary의 즐겨찾기 정보를 가지고 있는다."""
    if request.user.is_authenticated():
        try: 
            favorite_list = _favorites_to_output(UserProfile.objects.get(user=request.user).favorite.all(), True, request.session.get('django_language','ko'))
        except ObjectDoesNotExist:
            favorite_list = []
    else:
        favorite_list = []
    
    return favorite_list 

def taken_lecture_list(request):
    """dictionary의 들었던 과목 정보를 가지고 있는다."""
    if request.user.is_authenticated():
        try:
            take_lecture_list = UserProfile.objects.get(user=request.user).take_lecture_list.order_by('-year', '-semester')
            take_year_list = take_lecture_list.values('year', 'semester').distinct()
            separate_list = []
            result = []
            for lecture in take_lecture_list:
                if len(separate_list)==0:
                    separate_list.append(lecture)
                    continue
                if lecture.year!=separate_list[0].year or lecture.semester!=separate_list[0].semester :
                    result.append(_taken_lectures_to_output(request.user, separate_list, request.session.get('django_language','ko')))
                    separate_list = []
                separate_list.append(lecture)
            result.append(_taken_lectures_to_output(request.user, separate_list, request.session.get('django_language','ko')))
        except ObjectDoesNotExist:
            result = []
            take_year_list = []
    else:
        take_year_list = []
        result = []

    result = zip(take_year_list,result)
    return result

# -- Private functions   
def _taken_lectures_to_output(user, lecture_list, lang='ko'):
    try:
        written_list=[comment.lecture.code for comment in Comment.objects.filter(writer=user,lecture__year__exact=lecture_list[0].year,lecture__semester__exact=lecture_list[0].semester)]
    except ObjectDoesNotExist:
        written_list=[]

    show_list=[]

    for lecture in lecture_list:
        written=False
        if lecture.code in written_list:
            written=True
        item= {
                'url': "/dictionary/view/" + lecture.old_code + "/",
                'title': _trans(lecture.title,lecture.title_en,lang),
                'code': lecture.old_code,
                'written':written
            }
        show_list.append(item)
    return show_list

def _trans(ko_message, en_message, lang) :
    if en_message == None or lang == 'ko' :
        return ko_message
    else :
        return en_message

def _update_comment(count, **conditions):
    department = conditions.get('dept', None)
    professor = conditions.get('professor', None)
    favorite_department = conditions.get('fav_dept', None)
    if department != None:
        q = Q(course__department=department)
        if favorite_department != None:
            for department in favorite_department:
                q |= Q(course__department=department)
        comments = Comment.objects.filter(q).distinct()
    elif professor != None:
        comments = Comment.objects.filter(course__professors=professor)
    else:
        comments = Comment.objects.all()
    comments = comments.order_by('-id')
    comments_size = comments.count()
    if comments_size < count:
        return comments[0:comments_size]
    return comments[0:count]

def _search(**conditions):
    department = conditions.get('dept', None)
    type = conditions.get('type', None)
    lang = conditions.get('lang', 'ko')
    keyword = conditions.get('keyword', None)
    output = None
    if department != None and type != None and keyword != None:
        keyword = keyword.strip()
        courses= _search_by_dt(department, type) 
        professors = Professor.objects.all()
        if keyword == u'':
            professors = None
            if department == u'-1' and type == u'전체보기':
                raise ValidationError()
        else:
            words = keyword.split()
            for word in words:
                if lang=='ko':
                    courses= courses.filter(Q(old_code__icontains=word) | Q(title__icontains=word) | Q(professors__professor_name__icontains=word)).distinct()
                    professors= professors.filter(professor_name__icontains=word)
                elif lang=='en':
                    courses= courses.filter(Q(old_code__icontains=word) | Q(title_en__icontains=word) | Q(professors__professor_name_en__icontains=word)).distinct()
                    professors= professors.filter(professor_name_en__icontains=word)
	courses = courses.order_by('type','old_code').select_related()
	output = {'courses':courses, 'professors':professors}
    else:
        raise ValidationError()

    return output

def _search_by_dt(department, type):
    cache_key = 'dictionary-search-cache:department=%s:type=%s' % (department,type)
    output = cache.get(cache_key)
    if output is None:
        output = Course.objects.all()
        if department != u'-1':
            output = output.filter(department__id__exact=int(department))
        if type != u'전체보기':
            output = output.filter(type__exact=type)
        cache.set(cache_key,output,3600)
    return output

def _comments_to_output(comments,conv_to_json=True, lang='ko',preview=True):
    all = []
    if not isinstance(comments, list):
        comments = comments.select_related()
    for comment in comments:
        writer = comment.writer
        try:
            profile = UserProfile.objects.get(user=writer)
            nickname = profile.nickname
        except:
            nickname = ''
        if comment.lecture == None:
            lecture_id = -1
        else:
            lecture_id = comment.lecture.id
        comment_to_return =''
        if preview :
            if len(comment.comment)>85 :
                comment_to_return = comment.comment[:85]+' ...'
            else :
                comment_to_return = comment.comment
        else :
            comment_to_return = comment.comment
        item = {
            'comment_id': comment.id,
            'course_id': comment.course.id,
            'course_code': comment.course.old_code, 
            'course_title': _trans(comment.course.title,comment.course.title_en,lang),
            'lecture_id': lecture_id,
            'writer_id': comment.writer.id,
            'writer_nickname': nickname,
            'professor': _professors_to_output(_get_professor_by_lecture(comment.lecture),False,lang),
            'written_datetime': comment.written_datetime.isoformat(),
            'written_date':comment.written_datetime.isoformat()[:10],
            'comment': comment_to_return,
            'score': comment.score,
            'gain': comment.gain,
            'load': comment.load,
            'like': comment.like,
            'semester': comment.lecture.semester,
            'year': comment.lecture.year
        }
        all.append(item)
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(all,io,ensure_ascii=False,indent=4)
        else:
            json.dump(all,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        return io.getvalue()
    else :
        return all

def _professors_to_output(professors,conv_to_json=True,lang='ko'):
    all = []
    if not isinstance(professors, list):
        professors = professors.select_related()
    for professor in professors:
        item = {
                'professor_name': _trans(professor.professor_name,professor.professor_name_en,lang),
                'professor_id': professor.professor_id
                }
        all.append(item)
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(all,io,ensure_ascii=False,indent=4)
        else:
            json.dump(all,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        return io.getvalue()
    else :
        return all

def _semesters_to_output(semesters,conv_to_json=True,lang='ko'):
    all = []
    for semester in semesters:
        item = {
                'semester': semester['semester'],
                'year': semester['year']
                }
        all.append(item)
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(all,io,ensure_ascii=False,indent=4)
        else:
            json.dump(all,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        return io.getvalue()
    else:
        return all


def _courses_to_output(courses,conv_to_json=True,lang='ko'):
    all = []
    if isinstance(courses, Course):
        item = {
                'id': courses.id,
                'old_code': courses.old_code,
                'dept_id': courses.department.id,
                'type': _trans(courses.type,courses.type_en,lang),
                'title': _trans(courses.title,courses.title_en,lang),
                'comment_num': len(Comment.objects.filter(course=courses)),
                'score_average': courses.score_average,
                'load_average': courses.load_average,
                'gain_average': courses.gain_average
                }
        if conv_to_json:
            io = StringIO()
            if settings.DEBUG:
                json.dump(item,io,ensure_ascii=False,indent=4)
            else:
                json.dump(item,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
            return io.getvalue()
        else :
            return item

    if not isinstance(courses, list):
        courses = courses.select_related()
    for course in courses:
        item = {
                'id': course.id,
                'old_code': course.old_code,
                'dept_id': course.department.id,
                'type': _trans(course.type,course.type_en,lang),
                'title': _trans(course.title,course.title_en,lang),
                'score_average': course.score_average,
                'load_average': course.load_average,
                'gain_average': course.gain_average
                }
        all.append(item)
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(all,io,ensure_ascii=False,indent=4)
        else:
            json.dump(all,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        return io.getvalue()
    else :
        return all

def _summary_to_output(summary,conv_to_json=True,lang='ko'):
    item = {
        'summary': summary.summary,
        'prerequisite': summary.prerequisite,
        'writer': UserProfile.objects.get(user = summary.writer).nickname,
        'written_datetime': summary.written_datetime.isoformat()[:10],
        'course_id': summary.course.id
        }
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(item,io,ensure_ascii=False,indent=4, cls=DjangoJSONEncoder)
        else:
            json.dump(item,io,ensure_ascii=False,sort_keys=False,separators=(',',':'), cls=DjangoJSONEncoder)
        return io.getvalue()
    else :
        return item

def _lecture_summary_to_output(summary,conv_to_json=True,lang='ko'):
    item = {
        'homepage': summary.homepage,
        'main_material': summary.main_material,
	'sub_material': summary.sub_material,
        'writer': UserProfile.objects.get(user = summary.writer).nickname,
        'written_datetime': summary.written_datetime.isoformat()[:10],
        'lecture_id': summary.lecture.id,
        }
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(item,io,ensure_ascii=False,indent=4, cls=DjangoJSONEncoder)
        else:
            json.dump(item,io,ensure_ascii=False,sort_keys=False,separators=(',',':'), cls=DjangoJSONEncoder)
        return io.getvalue()
    else :
        return item

def _professor_info_to_output(prof_info,conv_to_json=True,lang='ko'):
    if prof_info == None:
        item = {
                'major': '',
                'email': '',
                'homepage': '',
                'writer': '',
                'written_datetime': '',
                'professor_id': -1
                }
    else:
        item = {
                'major': prof_info.major,
                'email': prof_info.email,
                'homepage': prof_info.homepage,
                'writer': UserProfile.objects.get(user = prof_info.writer).nickname,
                'written_datetime': prof_info.written_datetime.isoformat()[:10],
                'professor_id': prof_info.professor.professor_id
                }
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(item,io,ensure_ascii=False,indent=4, cls=DjangoJSONEncoder)
        else:
            json.dump(item,io,ensure_ascii=False,sort_keys=False,separators=(',',':'), cls=DjangoJSONEncoder)
        return io.getvalue()
    else:
        return item

def _get_professor_by_lecture(lecture):
    if lecture == None:
        return Professor.objects.none()
    return lecture.professor.all()

def _get_taken_lecture_by_db(user, course):
    try:
        lectures = Lecture.objects.filter(course=course)
        take_lecture_list = UserProfile.objects.get(user=user).take_lecture_list

        result = take_lecture_list.filter(course=course).order_by('-year','-semester')

        return result
    except ObjectDoesNotExist:
        return Lecture.objects.none()

def _get_unwritten_lecture_by_db(user):
    try:
        take_lecture_list = UserProfile.objects.get(user=user).take_lecture_list.all()
    except ObjectDoesNotExist:
        return Lecture.objects.none()

    try:
        comment_list = Comment.objects.filter(writer=user)
    except ObjectDoesNotExist :
        comment_list = []
   
    ret_list = list(take_lecture_list)
    for comment in comment_list:
        if comment.lecture in ret_list:
            ret_list.remove(comment.lecture)
    return ret_list

def _favorites_to_output(favorites,conv_to_json=True,lang='ko'):
    all = []
    if isinstance(favorites, Course):
        favorites = [favorites]
    for favorite in favorites:
        item = {
            'course_id': favorite.id,
            'code': favorite.old_code,
            'title': _trans(favorite.title,favorite.title_en,lang),
            'url': "/dictionary/view/" + favorite.old_code + "/"
            }
        all.append(item) 
    if conv_to_json:
        io = StringIO()
        if settings.DEBUG:
            json.dump(all,io,ensure_ascii=False,indent=4)
        else:
            json.dump(all,io,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        return io.getvalue()
    else :
        return all



def _get_courses_sorted(courses):
    all = []
    for course in courses:
        average_sum = (course.score_average + course.load_average + course.gain_average) / 3
           
        lecture = Lecture.objects.filter(course=course).order_by('-year', '-semester')[0]
        num_people = lecture.num_people
        professor_name = lecture.professor.all()[0].professor_name
        professor_id = lecture.professor.all()[0].professor_id

        interesting_score = average_sum * num_people

        item = {
             'course_code': course.old_code,
             'interesting_score': interesting_score,
             'course_title':course.title,
             'professor_name':professor_name,
             'professor_id':professor_id,
             }
        all.append(item)

    sorted_courses = sorted(all, key=lambda k:-k['interesting_score'])

    return sorted_courses

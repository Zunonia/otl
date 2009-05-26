# encoding: utf-8
from django.db import models
from django import forms
from django.utils import simplejson as json
from django.http import HttpResponse
from django.core.cache import cache
from django.conf import settings

def get_choice_display(choices, key):
	for item in choices:
		if item[0] == key:
			return item[1]
	return u'(None)'

def cache_with_default(key, default, timeout=300):
	"""
	cache.get() 메소드에도 default 인자가 있지만, 호출 당시 이미 evaluate되므로
	항상 다음과 같은 구조를 사용해야 한다.
	
	value = cache.get(key)
	if value is None:
		value = calculate()
		cache.set(key, value)
	
	그러나 Python에서 제공되는 lambda 함수를 사용하면 인자로 넘길 때 바로
	evaluate되지 않고 명시적으로 호출해야만 하므로 cache가 있는 경우 그냥
	무시하고 없는 경우에만 호출하여 default 인자를 바로 연산값으로 사용할
	경우 보다 간결한 코드로 표현할 수 있다.
	"""
	if not callable(default):
		raise TypeError('The argument default should be a callable, normally lambda function to work efficiently.')
	value = cache.get(key)
	if value is None:
		value = default()
		cache.set(key, value, timeout)
	return value

def response_as_json(request, obj):
	output = json.dumps(obj, ensure_ascii=False, indent=4 if settings.DEBUG else 0)
	type = 'application/json' if request.is_ajax() else 'text/plain'
	return HttpResponse(output, mimetype=type)


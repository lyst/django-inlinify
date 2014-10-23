# for testing, we'll use the default cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache'
    }
}

# django will complain if we don't include this
SECRET_KEY = 'dummysecret'

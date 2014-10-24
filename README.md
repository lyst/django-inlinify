django-premailer
=========

This is just a personalized version of premailer, which is ~10x faster. Read the docs in https://github.com/peterbe/premailer for more info

Usage
--------------
Just include `django_premailer` in your `INSTALLED_APPS` and
```python
from django_premailer.premailer import Premailer

html = '<html>
        <head>
        <title>Title</title>
        <style type="text/css">
        p * { color: blue }
        </style>
        </head>
        <body>
        <h1>Title</h1>
        <p><strong>Text1</strong></p>
        <p><strong>Text2</strong></p>
        </body>
        </html>'

p = Premailer()
p.transform(html)
```

Settings
--------------

Override the following in your Django settings according to your needs. You can check their default values on `django_premailer/defaults.py`

```python
# the default cache backend. Make sure it exists in `CACHES`
DEFAULT_CACHE_BACKEND_NAME

# CSS parser cache key prefix
CSSPARSER_CACHE_KEY_PREFIX
# CSS parser cache key TTL
CSSPARSER_CACHE_KEY_TTL
# CSS attribute to HTML attribute mapping
CSS_HTML_ATTRIBUTE_MAPPING

# CSS loader cache key prefix
CSSLOADER_CACHE_KEY_PREFIX
# CSS loader cache key TTL
CSSLOADER_CACHE_KEY_TTL
```

Running tests
----

```python
DJANGO_SETTINGS_MODULE="django_premailer.test_settings" python setup.py test
```

Version
----

0.0.8

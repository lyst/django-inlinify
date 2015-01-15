django-inlinify
=========

Django app for in-lining CSS. This project was initially based on [premailer](https://github.com/peterbe/premailer).

Usage
--------------
Just include `django_inlinify` in your `INSTALLED_APPS` and
```python
from django_inlinify.inlinify import Inlinify

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

p = Inlinify()
p.transform(html)
```

Settings
--------------

Override the following in your Django settings according to your needs. You can check their default values on `django_inlinify/defaults.py`

```python
# the default cache backend. Make sure it exists in `CACHES`
DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME

# CSS parser cache key prefix
DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX

# CSS parser cache key TTL
DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL

# CSS attribute to HTML attribute mapping
DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING

# CSS loader cache key prefix
DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX

# CSS loader cache key TTL
DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL
```

Running tests
----

```python
DJANGO_SETTINGS_MODULE="django_inlinify.test_settings" python setup.py test
```

Version
----

0.0.13

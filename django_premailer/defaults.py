# The default cache backend to use
DJANGO_PREMAILER_DEFAULT_CACHE_BACKEND_NAME = 'default'

# CSS Parser default settings
DJANGO_PREMAILER_CSSPARSER_CACHE_KEY_PREFIX = 'django_premailer_parsed_css_'
DJANGO_PREMAILER_CSSPARSER_CACHE_KEY_TTL = 60 * 60 * 24
DJANGO_PREMAILER_CSS_HTML_ATTRIBUTE_MAPPING = {
        'text-align': ('align', lambda value: value.strip()),
        'vertical-align': ('valign', lambda value: value.strip()),
        'background-color': ('bgcolor', lambda value: value.strip()),
        'width': ('width', lambda value: value.strip().replace('px', '')),
        'height': ('height', lambda value: value.strip().replace('px', ''))
}


# CSS Loader default settings
DJANGO_PREMAILER_CSSLOADER_CACHE_KEY_PREFIX = 'django_premailer_css_contents_'
DJANGO_PREMAILER_CSSLOADER_CACHE_KEY_TTL = 60 * 60 * 24

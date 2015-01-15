# The default cache backend to use
DJANGO_INLINIFY_DEFAULT_CACHE_BACKEND_NAME = 'default'

# CSS Parser default settings
DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_PREFIX = 'django_inlinify_parsed_css_'
DJANGO_INLINIFY_CSSPARSER_CACHE_KEY_TTL = 60 * 60 * 24

DJANGO_INLINIFY_CSS_HTML_ATTRIBUTE_MAPPING = {
    'text-align': ('align', lambda value: value.strip()),
    'vertical-align': ('valign', lambda value: value.strip()),
    'background-color': ('bgcolor', lambda value: value.strip()),
    'width': ('width', lambda value: value.strip().replace('px', '')),
    'height': ('height', lambda value: value.strip().replace('px', '')),
    'cellspacing': ('cellspacing', lambda x: x.strip()),
    'cellpadding': ('cellpadding', lambda x: x.strip()),
}

# CSS Loader default settings
DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_PREFIX = 'django_inlinify_css_contents_'
DJANGO_INLINIFY_CSSLOADER_CACHE_KEY_TTL = 60 * 60 * 24

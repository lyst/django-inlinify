from setuptools import setup, find_packages

setup(
    name='django-inlinify',
    version='0.0.17',
    description="In-lines CSS into HTML and leverages Django's caching framework.",
    long_description="In-lines CSS into HTML and leverages Django's caching framework.",
    keywords='html lxml email mail style',
    author='Lyst Ltd.',
    author_email='devs@lyst.com',
    url='http://github.com/ssaw/django-inlinify/',
    license='Python',
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        'six',
        'lxml',
        'cssselect',
        'cssutils',
        'django>=1.7',
        'requests',
        'tox'
    ]
)

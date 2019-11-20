import os
from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))

requirements = []
with open('requirements.txt') as file_requirements:
    requirements = file_requirements.read().splitlines()

about = {}
with open(os.path.join(here, 'fbctl', '__version__.py'), 'r') as f:
    exec(f.read(), about)

setup(
    name=about['__title__'],
    version=about['__version__'],
    description=about['__description__'],
    author='dudaji',
    author_email='shhong@dudaji.com',
    url=about['__url__'],
    install_requires=requirements,
    packages=find_packages(exclude=['tests', 'docs', 'sql']),
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*',
    package_data={},
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'fbctl = fbctl.cli_main:main'
        ]
    },
    classifiers=[
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ]
)

from setuptools import setup, find_packages


REQUIREMENTS = []
with open('requirements.txt') as file_requirements:
    REQUIREMENTS = file_requirements.read().splitlines()

setup(
    name='fbctl',
    version='0.2.7',
    description='flashbase command line tool',
    author='dudaji',
    author_email='shhong@dudaji.com',
    url='https://github.com/mnms/share/tree/master/fbcli',
    install_requires=REQUIREMENTS,
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

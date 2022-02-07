from setuptools import setup, find_packages

setup(
    name='portmgr',
    version='1.4.3rc0',
    url="https://github.com/Craeckie/portmgr",
    description="Simple command interface to manage multiple Docker container",
    packages=find_packages(), #['portmgr'],
    license='Creative Commons Attribution-Noncommercial-Share Alike license',
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    zip_safe=False,

    install_requires=[
        'docker-compose',
        'jsonschema',
        'tabulate',
        'PyYAML',
        'jsonschema',
        'humanfriendly'
    ],
    entry_points = {
        'console_scripts': [
            'portmgr = portmgr:main'
        ]
    }
)

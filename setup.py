# from distutils.core import setup
import setuptools

setuptools.setup(
    name='portmgr',
    version='1.0.0',
    url="https://github.com/Craeckie/portmgr",
    description="Simple command interface to manage multiple Docker container",
    packages=setuptools.find_packages(),
    license='Creative Commons Attribution-Noncommercial-Share Alike license',
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",

    install_requires=[
        'docker-compose',
        'jsonschema'
    ]
)

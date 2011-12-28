from setuptools import setup, find_packages
import sys, os

version = '0.0.1'

setup(name='dispatcher',
      version=version,
      description="dispatcher",
      long_description="""\
""",
      classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
      keywords='',
      author='intellilink',
      author_email='',
      url='',
      license='',
      packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
      include_package_data=True,
      zip_safe=False,
      install_requires=[
          # -*- Extra requirements: -*-
      ],
      scripts=[
        'bin/dispatcher'
        ],
      entry_points={
        'paste.app_factory': [
            'dispatcher=dispatcher.server:app_factory',
            ],
        'paste.filter_factory': [
            'metadata_glance=dispatcher.common.middleware.metadata_glance:filter_factory',
            'keystone_merge=dispatcher.common.middleware.keystone_merge:filter_factory',
            'swift3_for_colony=dispatcher.common.middleware.swift3:filter_factory',
            ],
        },
      )

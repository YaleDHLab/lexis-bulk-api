from setuptools import setup

setup(
  name='lexis_bulk_api',
  version='0.0.2',
  packages=['lexis_bulk_api'],
  keywords = ['lexis-nexis', 'api', 'data', 'glam', 'vendor-data'],
  description='Visualize large image collections with WebGL',
  url='https://github.com/yaledhlab/pix-plot',
  author='Douglas Duhaime',
  author_email='douglas.duhaime@gmail.com',
  license='MIT',
  install_requires=[
    'beautifulsoup4>=4.5.1',
    'xmltodict>=0.11.0',
  ],
  entry_points={
    'console_scripts': [
      'pixplot=pixplot:parse',
    ],
  },
)

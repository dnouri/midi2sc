from setuptools import setup, find_packages

version = '0.1'

setup(name='midi2sc',
      version=version,
      description="Control SuperCollider Synths with MIDI",
      long_description=open('doc/README.txt').read(),
      classifiers=[
          "Topic :: Multimedia :: Sound/Audio :: MIDI",
          "Topic :: Multimedia :: Sound/Audio :: Sound Synthesis",

          "Development Status :: 3 - Alpha",
          "License :: OSI Approved :: MIT License",
          ],

      keywords='supercollider midi gui',
      author='Daniel Nouri',
      author_email='daniel.nouri@gmail.com',
      url='http://pypi.python.org/pypi/midi2sc',
      license='MIT',

      packages=find_packages(exclude=['ez_setup']),
      include_package_data=True,
      entry_points="""
      [console_scripts]
      midi2sc=midi2sc.core:main
      """,

      test_suite = 'nose.collector',
      )

=======
midi2sc
=======

Installation
============

You can install ``midi2sc`` with ``easy_install``::

  $ easy_install midi2sc

However, you also need to install pkaudio_ and its dependencies.

.. _pkaudio: http://trac2.assembla.com/pkaudio

You can use subversion to check out a known good version of pkaudio
from SVN like so::

  svn co http://subversion.assembla.com/svn/pkaudio/ -r13

Then, run ``python setup.py install`` inside the pkaudio directory to
install pkaudio.

Usage
=====

``midi2sc`` allows you to assign MIDI controllers to SuperCollider_
``SynthDefs``.

.. _SuperCollider: http://supercollider.sourceforge.net

Configuration
-------------

An example configuration::

  [SOSkick]
  midi_channel = 01
  001 = amp_mul=            AbsoluteControl(min=0.0, max=1.27, start_vel=100.0)
  106 = mod_freq=           IDC(min=2.0, max=20.0, steps=50, value=2.0)
  107 = mod_index=          IDC(min=2.0, max=20.0, steps=50, value=2.0)
  108 = beater_noise_level= IDC(min=2.0, max=20.0, steps=50, value=18.0)
  109 = decay=              IDC(min=0.05, max=1.0, steps=70, value=0.3)
  noteon_args = out=18

This configuration will create and assign 7 controls: one of type
``AbsoluteControl``, four of type ``IDC`` (IncDecControl).  The two
controls implicitly created are a ``NoteOnControl`` and a
``NoteOffControl``.

The ``001`` midi controller is usually the modulation wheel.  Here
it's bound to the ``amp_mul`` argument of an ``SOSkick`` SynthDef.
``min`` is the value sent to the SuperCollider Synth when the wheel is
at its lowest position, ``max`` the value at its highest position.

The ``106`` midi controller is bound to an endless encoder that sends
relative values between ``01 to 64`` for increment and ``127 to 065``
for decrement.  There's 50 ``steps`` between the ``min`` and ``max``
value.  And the value at which we start is ``2.0``.

SuperCollider
-------------

This is how a SynthDef could look like that uses the configuration
from before::

  SynthDef("SOSkick", {

    arg out = 0, freq = 50, mod_freq = 6.5, mod_index = 19.5,
    decay = 0.1, amp = 0.8, beater_noise_level = 0.001, amp_mul = 1.0;
    
    var x;
    // ...
    Out.ar(out, x);
  });

Make sure you have your SuperCollider server up and SynthDefs loaded
before you start ``midi2sc``.

Starting midi2sc
----------------

On the command-line, ``midi2sc`` is run like this::

  $ midi2sc

This assumes that you have a ``midi2sc.ini`` configuration file in the
current working directory.  You can also provide this filename as an
option on the command-line.  Refer to the built-in help for more
options::

  $ midi2sc --help

``midi2sc`` will ask you for a MIDI port to bind to, and then it'll
start a GUI that shows all sliders and finally drop you into an
interactive shell with access to variables like dictionary of control
``handlers`` and the ``save_presets`` and ``load_presets`` functions.
To save presets (values from all controllers) from a file on the
Python shell and then load them again later, you write::

  >>> save_presets('presets1.pickle', midi_in)
  >>> # ... time passes
  >>> load_presets('presets0.pickle', midi_in)

You can also load a new ``midi2sc.ini`` configuration::

  >>> handlers.update(configure.read('midi2sc2.ini'))

Screenshot
----------

.. image:: http://danielnouri.org/media/midi2sc-01.png
   :alt: midi2sc's GUI together with Seq24

Development Status
==================

``midi2sc`` is somewhat mature, and I use it.  At the same time it's a
big hack and probably not thread-safe.

Change Log
----------

0.1 - 2009-06-30
````````````````

  - First release.

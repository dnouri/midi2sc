import code
import copy
import logging
import operator
import optparse
import pickle
import threading
import traceback

import rtmidi
import scosc

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('midi2sc')

_state = dict(verbosity=1)

def set_verbosity(value):
    _state['verbosity'] = value

def get_verbosity():
    return _state['verbosity']

def set_server(value):
    _state['server'] = value

def get_server():
    return _state['server']

server_lock = threading.Lock()

class KeyErrorLessDict(dict):
    def __init__(self, prototype):
        self.prototype = prototype

    def __getitem__(self, key):
        if key not in self:
            self[key] = copy.copy(self.prototype)
        return super(KeyErrorLessDict, self).__getitem__(key)

class DispatchingDict(dict):
    """Event dispatching dict that's used by SynthRegistry.
    """
    def __init__(self, listeners):
        super(DispatchingDict, self).__init__()
        self.listeners = listeners

    def __setitem__(self, id, synth):
        super(DispatchingDict, self).__setitem__(id, synth)
        for handler in self.listeners[synth.group]:
            handler.set_params_for(synth)

class SynthRegistry(dict):
    def __init__(self):
        super(SynthRegistry, self).__init__()
        self.event_listeners = KeyErrorLessDict(set())

    def __getitem__(self, key):
        if key not in self:
            self[key] = DispatchingDict(self.event_listeners)
        return super(SynthRegistry, self).__getitem__(key)

    def set_params_for_all(self):
        for group, synths in self.items():
            for handler in self.event_listeners[group]:
                for synth in synths.values():
                    handler.set_params_for(synth)

class Synth(dict):
    """A Synth is an instance of a instrument; it corresponds to a
    Synth() in SuperCollider.

    This is an abstract base class that mostly describes the
    attributes and methods available.

    The ``synths`` attribute is the registry of all synths that are
    currently playing.  Synths add and remove themselves from this
    dict.  In ``synths`` they're keyed by synth ``group`` and ``id``.
    That is, to get hold all synths belonging to a group, use:

      >>> Synth.synths['my-group'].values()
      []

    If you know the synth's id, you can access it like this:
    
      >>> Synth.synths['my-group'][123]
      Traceback (most recent call last):
      KeyError: 123

    A Synth can tell us if it's still alive, that is, if it hasn't
    removed itself already:

      >>> Synth('my-group').alive
      True
      >>> Synth('my-group').remove().alive
      False
      
    For convenience, the Synth also holds the list of parameter keys
    and values which it was created with in the ``params_orig``
    attribute:

      >>> Synth('my-group', frequency=440).params_orig
      {'frequency': 440}

    """
    # Commonly used by all subclasses of Synth
    synths = SynthRegistry()

    # Messages waiting to be sent, acquire ``server_lock``!
    messages = []

    alive = False

    def int_pool(start=2000):
        while True:
            yield start
            start += 1
    int_pool = int_pool()

    def __init__(self, group, **kwargs):
        super(Synth, self).__init__(**kwargs)

        self.group = group
        self.id = id = self.int_pool.next()
        self.params_orig = kwargs
        Synth.synths[group][id] = self
        self.alive = True

    def remove(self):
        del self.synths[self.group][self.id]
        self.alive = False
        return self

class SCSynth(Synth):
    def __init__(self, group, server=None,
                 synthdef=None, add_action=0, add_target_id=1, **kwargs):
        super(SCSynth, self).__init__(group, **kwargs)

        if synthdef is None:
            synthdef = group
        self.synthdef = synthdef

        # These could be different servers per synth, but the Timer
        # below doesn't support that really:
        if server is not None:
            logger.error("You can no longer pass a server to SCSynth().")
        self.server = get_server()

        # Create a new Synth with our parameters.  Note that we use
        # ``self.items`` and not ``kwargs`` because that ``super()``
        # call might actually change parameters.
        params = reduce(operator.add, self.items(), ())
        try:
            server_lock.acquire()
            self.server.sendMsg('/s_new', synthdef, self.id,
                                add_action, add_target_id, *params)
        finally:
            server_lock.release()

    def __setitem__(self, key, value):
        super(SCSynth, self).__setitem__(key, value)
        if self.alive:
            try:
                server_lock.acquire()
                self.messages.append(('/n_set', self.id, key, value))
            finally:
                server_lock.release()

    def __getitem__(self, key):
        try:
            return super(SCSynth, self).__getitem__(key)
        except KeyError:
            print "Doing it for %s %s" % (self.id, key)
            try:
                server_lock.acquire()
                self.server.sendMsg('/s_get', self.id, key)
                try:
                    rcmd, rid, rkey, rvalue = self.server.receive('/n_set')
                except IOError, e:
                    raise KeyError(key)
            finally:
                server_lock.release()
            if rid == self.id and rkey == key:
                super(SCSynth, self).__setitem__(rkey, rvalue)
                return rvalue
            else:
                raise KeyError(key)

class MessagesTimer(threading.Thread):
    def __init__(self, interval):
        super(MessagesTimer, self).__init__()
        self.interval = interval
        self.finished = threading.Event()

    def run(self):
        messages = Synth.messages
        finished = self.finished
        interval = self.interval
        global server_lock

        while not finished.isSet():
            locked = False
            try:
                finished.wait(interval)
                # Process all pending messages and empty:
                locked = server_lock.acquire(False)
                if not locked:
                    continue
                if messages:
                    get_server().sendBundle(0.001, messages)
                    messages[:] = []
            finally:
                if locked:
                    server_lock.release()

class MidiIn(threading.Thread):
    running = True

    def __init__(self, midi, port, handlers=None):
        super(MidiIn, self).__init__()
        self.setDaemon(True)
        self.midi = midi
        self.port = port
        if handlers is None:
           handlers = {} 
        self.handlers = handlers

    def run(self):
        self.midi.openPort(self.port, True)
        verbose = get_verbosity()
        while self.running:
            message = self.midi.getMessage()
            if message:
                if verbose:
                    logger.debug("%r received: %s" % (self, message))
                # `message[0]` is the MIDI command, see
                # http://ccrma-www.stanford.edu/~craig/articles/linuxmidi/misc/essenmidi.html
                handler = self.handlers.get(message[0])
                if handler is not None:
                    try:
                        handler(*message[1:])
                    except IOError:
                        traceback.print_exc()

    def __repr__(self):
        return '<MidiIn port=%r>' % (self.midi.getPortName(self.port))
                

def ask_for_port(midi):
    ports = range(midi.getPortCount())
    assert ports
    for i in ports:
        print '    [%s]: %s' % (i, midi.getPortName(i))
    print 'Enter midi midi number [0]:',

    entry = raw_input()
    if entry:
        return int(entry)
    else:
        return 0

def _all_notes_off(handlers):
    from midi2sc import control

    for handler in handlers.values():
        if isinstance(handler, control.GroupControl):
            _all_notes_off(handler)
        else:
            if isinstance(handler, control.NoteOffControl):
                for key in handler.notes.keys():
                    handler(key, 0, None)

def save_presets(filename, midi_in):
    handlers = midi_in.handlers
    midi_in.handlers = {}
    _all_notes_off(handlers)
    f = open(filename, 'w')
    pickle.dump(handlers, f)
    f.close()
    midi_in.handlers = handlers

def load_presets(filename, midi_in):
    handlers = midi_in.handlers
    midi_in.handlers = {}
    _all_notes_off(handlers)
    Synth.synths.event_listeners.clear()
    f = open(filename, 'r')
    handlers = pickle.load(f)
    f.close()
    Synth.synths.set_params_for_all()
    midi_in.handlers = handlers
    return midi_in.handlers

def connect(host='localhost', port=57110, verbose=None, spew=None):
    if verbose is None:
        verbose = get_verbosity()
    if spew is None:
        spew = get_verbosity()
    server = scosc.Controller((host, port), verbose=verbose, spew=spew)
    set_server(server)

    server._timer = timer = MessagesTimer(0.001)
    timer.start()

    return server

def disconnect():
    get_server()._timer.finished.set()

def _parse_options():
    parser = optparse.OptionParser()
    parser.add_option("-f", "--file", dest="filename", metavar="FILE",
                      help="File to load MIDI bindings from [midi2sc.ini]")
    parser.add_option('-s', "--host", dest="host", metavar="HOST",
                      help="Host of SuperCollider server [localhost]")
    parser.add_option('-p', "--port", dest="port", metavar="PORT",
                      default='57110',
                      help="Port of SuperCollider server [57710]")
    parser.add_option('-m', "--midi-port", dest="midi_port", metavar="MIDIPORT",
                      help="MIDI port to bind to (default: ask)")
    parser.add_option("-v", "--verbose",
                      action="store_true", dest="verbose", default=False,
                      help="Make lots of noise")
    
    (options, args) = parser.parse_args()
    return (options, args)

def main(options=None, callback=None):
    if options is None:
        options, args = _parse_options()

    if not isinstance(options, dict):
        # options doesn't have a very nice interface at this point; it
        # has ``None`` for all values not set when using optparse, but
        # it may missing values instead in case of manual call of
        # ``main()``.
        options = dict(options.__dict__)

    set_verbosity(options['verbose'])
    server = connect(options.get('host') or 'localhost',
                     options.get('port') and int(options['port']) or 57110)

    midi = rtmidi.RtMidiIn()
    midi_port = options.get('midi_port')
    if midi_port is None:
        midi_port = ask_for_port(midi)
    midi_port = int(midi_port)

    from midi2sc import configure
    handlers = configure.read(options.get('filename') or 'midi2sc.ini')
    midi_in = MidiIn(midi, midi_port, handlers=handlers)
    midi_in.start()

    if callback is None:
        from midi2sc import gui
        gui.start()

        scope = dict(globals())
        scope.update(locals())
        code.interact(local=scope)
    else:
        callback(locals())

if __name__ == '__main__':
    main()

import ConfigParser
import StringIO
import traceback

from midi2sc import control
from midi2sc import core # used inside an eval only

handler_factories = dict(
    AbsoluteControl = control.AbsoluteControl,
    IDC = control.IncDecControl,
    )

class ConfigurationError(Exception):
    pass

def _eval(string, reason=None):
    try:
        return eval(string)
    except Exception, e:
        if reason is not None:
            msg = "Error while trying to process '%s': %s" % (reason, string)
        else:
            msg = "Error while trying to evaluate: %s" % string
        traceback.print_exc()
        raise ConfigurationError(msg)

def read(f):
    if isinstance(f, (str, unicode)):
        fp = open(f)
        f = StringIO.StringIO(fp.read())
        fp.close()
    
    parser = ConfigParser.ConfigParser()
    parser.readfp(f)
    f.seek(0)
    contents = f.read()

    handlers = {}

    sections = sorted(parser.sections(),
                      key=lambda s: contents.index('[%s]' % s))
    for group in sections:
        options = dict(parser.items(group))
        midi_channel = int(options.pop('midi_channel'))

        args = options.pop('args', '')
        args = args.replace('in=', 'in_=') # ugh!
        noteon = options.pop('noteon', 'true').lower() in ('true', '1', 't')

        handlers[0xb0 + midi_channel-1] = group_ctrl = control.GroupControl({})
        controls = {}

        for key in sorted(options.keys()):
            value = options[key]
            key = int(key)
            param_name, rest = [i.strip() for i in value.split('=', 1)]
            handler_name, func_params = rest.split('(', 1)
            handler = _eval("handler_factories[%r](%r, param_name=%r, %s" % (
                handler_name, group, param_name, func_params), key)
            group_ctrl[key] = handler

        if noteon:
            noteon_ctrl = _eval(
                "control.NoteOnControl(%r, %s)" % (group, args))
            noteoff_ctrl = control.NoteOffControl(noteon_ctrl.notes)
            handlers[0x90 + midi_channel-1] = noteon_ctrl
            handlers[0x80 + midi_channel-1] = noteoff_ctrl
        else:
            _eval("core.SCSynth(%r, %s)" % (group, args))

    return handlers

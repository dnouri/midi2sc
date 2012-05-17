import pprint
import traceback

from midi2sc import core
from midi2sc import gui

_empty = object()

class GroupControl(dict):
    """Group controls by key.
    """
    def __init__(self, controls):
        super(GroupControl, self).__init__()
        self.update(controls)

    def __call__(self, key, vel, timestamp):
        control = self.get(key)
        if control is not None:
            try:
                control(vel, timestamp)
            except IOError:
                traceback.print_exc()

    def __repr__(self):
        controls = pprint.pformat(dict(self)).replace('\n', '\n  ').strip()
        return '<GroupControl \n  %s>' % controls

class NoteOnControl(object):
    def __init__(self, group, synthfactory=None, **kwargs):
        self.group = group
        if synthfactory is None:
            synthfactory = core.SCSynth
        self.synthfactory = synthfactory
        self.notes = {}
        self.params = kwargs

    def __call__(self, key, vel, timestamp):
        notes = self.notes
        synth = notes.get(key)
        if vel and synth is None:
            freq = 440 * 2 ** ((key - 69) / 12.)
            notes[key] = self.synthfactory(
                self.group, freq=freq, amp=vel/127., **self.params)
        elif vel == 0 and synth is not None:
            synth['gate'] = 0
            synth.remove()
            del notes[key]

    def __repr__(self):
        return '<NoteOnControl group=%r, params=%s>' % (
            self.group, pprint.pformat(self.params))

class NoteOffControl(object):
    def __init__(self, notes):
        self.notes = notes

    def __call__(self, key, vel, timestamp):
        notes = self.notes
        synth = notes.get(key)
        if synth is not None:
            synth['gate'] = 0
            synth.remove()
            del notes[key]

    def __repr__(self):
        return '<NoteOffControl notes=%r>' % self.notes

class NoteOnParam(object):
    """Set params by hitting keys.
    """
    def __init__(self, group, key_param=None, vel_param=None,
                 key_range=(0.0, 128.0), vel_range=(0.0, 1.0)):
        self.group = group
        self.key_param = key_param
        self.vel_param = vel_param
        self.key_range = key_range
        self.vel_range = vel_range
        self.key_div = 128. / (key_range[1] - key_range[0])
        self.vel_div = 128. / (vel_range[1] - vel_range[0])
        
    def __call__(self, key, vel, timestamp):
        if vel == 0.0:
            return
        key_val, vel_val = self.compute_values(key, vel)
        for synth in core.Synth.synths[self.group].values():
            self.set_params_for(synth, key_val, vel_val)

    def set_params_for(self, synth, key_val=_empty, vel_val=_empty):
        if key_val is _empty:
            key_val, vel_val = self.compute_values(key_val, vel_val)
        if key_val is not None:
            synth[self.key_param] = key_val
        if vel_val is not None:
            synth[self.vel_param] = vel_val

    def compute_values(self, key, vel):
        key_val, vel_val = None, None
        if self.key_param:
            key_val = (key / self.key_div) + self.key_range[0]
        if self.vel_param:
            vel_val = (vel / self.vel_div) + self.vel_range[0]
        return key_val, vel_val

    def __repr__(self):
        return '<NoteOnParam key_param=%r vel_param=%r>' % (
            self.key_param, self.vel_param)

class AbsoluteControl(object):
    """A MIDI control that sets values between min and max.
    """
    def __init__(self, group,
                 min=0.20, max=1.80, start_vel=0, param_name='freq'):
        self.group = group
        self.div = 127. / (max - min)
        self.min = min
        self.param_name = param_name
        self.vel = start_vel
        core.Synth.synths.event_listeners[self.group].add(self)

        # `self.max` and `self.step` exist solely to support the GUI
        self.max = max
        self.step = (max - min) / 127.
        gui.register(self)

    def __call__(self, vel, timestamp):
        self.vel = vel
        value = self.value
        for synth in core.Synth.synths[self.group].values():
            self.set_params_for(synth, value=value)
        self.vel = vel
        gui.update(self, vel)

    def set_params_for(self, synth, value=None):
        value = self.value if value is None else value
        synth[self.param_name] = value

    @property
    def value(self):
        val = (self.vel / self.div) + self.min
        return val

    def update_value(self, value):
        gui.disable_updates() # wee!!
        self((value * self.div) + self.min, None)
        gui.enable_updates()

    def __repr__(self):
        return "<%s for %r param %r>" % (
            self.__class__.__name__, self.group, self.param_name)

    def __del__(self):
        core.Synth.synths.event_listeners[self.group].remove(self)

class IncDecControl(object):
    """A MIDI control for endless dial data
    """
    group_values = {}
    
    def __init__(self, group, min=None, max=None, step=None, steps=None,
                 param_name='freq', sticky=True, value=None):
        self.group = group
        self.min = min
        self.max = max
        assert step or steps and not (step and steps)
        if step is None:
            step = float(max - min) / steps
        self.step = step
        self.param_name = param_name
        self.sticky = sticky
        if self.min is not None and self.max is not None:
            self.check_range = self._check_min_max
        elif self.min is not None:
            self.check_range = self._check_min
        elif self.max is not None:
            self.check_range = self._check_max
        if sticky:
            core.Synth.synths.event_listeners[self.group].add(self)
        self.value = value
        gui.register(self)

    @apply
    def value():
        def _key(self):
            return '%s.%s' % (self.group, self.param_name)
        def get(self):
            return self.group_values.get(_key(self))
        def set(self, value):
            self.group_values[_key(self)] = value
        return property(get, set)

    def update_value(self, value):
        gui.disable_updates()
        self.value = value
        self(0, None)
        gui.enable_updates()

    def __call__(self, vel, timestamp):
        """Implements 2's complement inc/dec method with linear steps.
        """
        if vel > 63:
            step = -(128 - vel) * self.step
        else:
            step = vel * self.step

        param_name = self.param_name
        sticky = self.sticky
        next_value = None
        value = self.value
        
        for synth in core.Synth.synths[self.group].values():
            if next_value is None:
                if sticky and value is None:
                    # We're sticky, so we're supposed to keep a value
                    # around that we can apply at set_params_for time:
                    try:
                        self.value = value = synth[param_name]
                    except KeyError:
                        continue
                if sticky:
                    # We can calculate the parameter's next value
                    # using self.value if we're sticky:
                    next_value = self.value + step
                else:
                    # If we're not sticky, we'll just add whatever
                    # step to the existing value of the parameter of
                    # the synth:
                    next_value = synth[param_name] + step
                next_value = self.check_range(next_value)

            synth[self.param_name] = next_value

        if sticky and next_value is not None:
            self.value = next_value
        elif sticky and self.value is not None:
            self.value = self.check_range(self.value + step)

    def set_params_for(self, synth):
        if self.sticky and self.value is not None:
            synth[self.param_name] = self.value

    def check_range(self, value):
        return value

    def _check_min(self, value):
        if value < self.min:
            gui.update(self, self.min)
            return self.min
        else:
            gui.update(self, value)
            return value

    def _check_max(self, value):
        if value > self.max:
            gui.update(self, self.max)
            return self.max
        else:
            gui.update(self, value)
            return value

    def _check_min_max(self, value):
        gui.update(self, value)
        #display.slider(100.0 * (value - self.min) / (self.max - self.min))
        max = self._check_max(value)
        if max != value:
            return max
        return self._check_min(value)

    def __repr__(self):
        return "<IDC for %r param %r>" % (self.group, self.param_name)

    def __getstate__(self):
        return (self.group, self.min, self.max, self.step, None,
                self.param_name, self.sticky, self.value)

    def __setstate__(self, state):
        self.__init__(*state)

class RelativeControl(AbsoluteControl):
    """A derivee of AbsoluteControl that uses min and max as factors
    to multiply the synth's original parameter value.  Used for the
    pitch bend control.
    """
    def __init__(self, group, min=0.25, max=1.75, start_vel=64,
                 *args, **kwargs):
        super(RelativeControl, self).__init__(
            group, min, max, start_vel, *args, **kwargs)

    def set_params_for(self, synth, value=None):
        param_name = self.param_name
        value = self.value() if value is None else value
        synth[param_name] = synth.params_orig[param_name] * value

class AfterTouch(RelativeControl):
    def __init__(self, group,
                 min=1.0, max=1.5, start_vel=0, param_name='amp'):
        super(AfterTouch, self).__init__(group, min, max, start_vel, param_name)

    def __call__(self, vel, timestamp):
        super(AfterTouch, self).__call__(vel, timestamp)


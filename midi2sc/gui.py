import threading
import Queue
import Tkinter

COLUMNS = 7

_queue = Queue.Queue()

class Window(threading.Thread):
    def __init__(self):
        super(Window, self).__init__()
 
    def run(self):
        self.root = Tkinter.Tk()
        self.frame = Tkinter.Frame(self.root)
        self.frame.pack()
        self.scale_frames = {}
        self._process_queue()
        self.root.mainloop()

    def _process_queue(self):
        if not _queue.empty():
            while True:
                try:
                    item = _queue.get(block=False)
                    item[0](*item[1], **item[2])
                except Queue.Empty:
                    break
        self.root.after(50, self._process_queue)

class ScaleFrame(Tkinter.LabelFrame):
    frame_options = dict(bd=1, relief=Tkinter.RIDGE)
    scale_options = dict(orient=Tkinter.HORIZONTAL, length=200)

    _moving_scale = None

    def __init__(self, parent, group):
        Tkinter.LabelFrame.__init__(
            self, parent, text=group, **self.frame_options)
        self.parent = parent
        self.group = group
        self.controls = []
        self.scales = []

    def add(self, control):
        self.controls.append(control)
        tickinterval = control.step
        diff = control.max - control.min
        while tickinterval / diff < 0.25:
            tickinterval *= 2
        scale = Tkinter.Scale(
            self, from_=control.min, to=control.max,
            variable=Tkinter.DoubleVar(),
            resolution=control.step, tickinterval=tickinterval,
            label=control.param_name,
            **self.scale_options)

        if control.value is None:
            scale._initialized = False
            scale.set(control.min)
            scale.configure(fg="#aaa", state=Tkinter.DISABLED)
        else:
            scale._initialized = True
            scale.set(control.value)

        scale.configure(command=lambda value: self.scale_moved(
            scale, control, value))
        scale.pack(side=Tkinter.TOP)
        self.scales.append(scale)

    def scale_moved(self, scale, control, value):
        if scale._initialized:
            control.update_value(float(value))

    def move_scale(self, control, value):
        _queue.put((self._move_scale, (control, value), {}))

    def _move_scale(self, control, value):
        index = self.controls.index(control)
        scale = self.scales[index]
        if not scale._initialized:
            scale._initialized = True
            scale.configure(fg='#000', state=Tkinter.ACTIVE)
        scale.set(value)

window = None

def start():
    global window
    window = Window()
    window.start()

def register(control):
    _queue.put((_register, (control,), {}))

def _register(control):
    scale_frame = window.scale_frames.get(control.group)
    if scale_frame is None:
        column = len(window.scale_frames) % COLUMNS
        row = len(window.scale_frames) // COLUMNS
        window.scale_frames[control.group] = ScaleFrame(
            window.frame, control.group)
        scale_frame = window.scale_frames[control.group]
        scale_frame.grid(column=column, row=row)
    scale_frame.add(control)

def _update(control, value):
    _queue.put((_do_update, (control, value), {}))

def _do_update(control, value):
    scale_frame = window.scale_frames[control.group]
    scale_frame.move_scale(control, value)

def _no_update(control, value):
    pass

update = _update

def disable_updates():
    global update
    update = _no_update

def enable_updates():
    global update
    update = _update

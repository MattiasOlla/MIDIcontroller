import mido
import queue
import sys
import threading
import time
import traceback

MIDI_MAX = 2 ** 20 - 1

name_num = {num + 56: f'{num + 1}/{num + 9}' for num in range(8)}
name_num[12] = 'MASTER'

FADER = (66, 48, 104)
CONTROL_ASSIGN = (66, 48, 104, 67, 26)
MIXER = [(109, 0, 0, 0), (4,)] # Add fader number between and value after
MASTER = [(67, 7, 0, 0), (0,)] # Add fader number between and value after

GET_COMBI = mido.Message.from_hex('F0 42 30 68 74 01 F7')
GET_PROGRAM = mido.Message.from_hex('F0 42 30 68 74 00 F7')
GET_ALL = mido.Message.from_hex('F0 42 30 68 72 01 00 00 41 F7')
GET_SETTINGS = mido.Message.from_hex('F0 42 30 68 74 03 F7')
GET_MODE = mido.Message.from_hex('F0 42 30 68 12 F7')

def midi_value(num):
    if isinstance(num, (int, float)):
        if num >= 0:
            return (0, 0, int(num))
        else:
            return (127, 127, 128 + int(num))
    elif isinstance(num, (tuple, list)):
        if num[0] == 0:
            return num[-1]
        else:
            return num[-1] - 128            
        # val = sum(n * 128 ** i for i, n in enumerate(reversed(num)))
        # if val > MIDI_MAX:
        #     val -= 2 * MIDI_MAX + 2
        # return val

class Fader:
    # Each fader will later have its own thread for reading and controlling the physical fader
    def __init__(self, name: str, num: int, send_thread=None, val=0, is_master=False):
        self.name = name
        self.num = num
        self.val = val
        self.send_thread = send_thread
        if is_master:
            self.cmd = FADER + MASTER[0] + (self.num,) + MASTER[1]
        else:
            self.cmd = FADER + MIXER[0] + (self.num,) + MIXER[1]
    
    def set_val(self, new_val: int):
        self.val = new_val
    
    def send(self):
        assert self.send_thread is not None, 'Must have a sender thread to send!'
        msg = mido.Message('sysex', time=0, data=(self.cmd + midi_value(self.val)))
        send_thread.send(msg)

    def __repr__(self):
        return f'Fader_{self.name}: {self.val}'

faders = {num: Fader(name, num, is_master=(name=='MASTER'))
          for num, name in name_num.items()}

class MidiThread(threading.Thread):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.lock = threading.Lock()
        self.stopped = False
        self.name = ''
    
    def run(self):
        raise NotImplementedError
    
    def start(self):
        self.name = next(k for k, v in sys.modules['__main__'].__dict__.items() if v is self)
        return super().start()

    def stop(self):
        if not self.stopped:
            self.stopped = True
            print('Stopped thread', self.name)
        else:
            print('Thread', self.name, 'already stopped')

class ListenerThread(MidiThread):
    def __init__(self, port):
        self.saved_messages = {}
        self.last_message = None
        self.wait_for = None
        self.wait_event = threading.Event()
        self.wait_result = None
        return super().__init__(port)

    def run(self):
        with mido.open_input(self.port) as self.inport:
            print('Thread', self.name, 'opened inport', self.inport)
            for msg in self.inport:
                if self.stopped:
                    break
                if msg.type != 'clock':
                    print('Listener received', msg)
                    self.last_message = msg
                if msg.type == 'sysex':
                    if self.wait_for:
                        if msg.data[:len(self.wait_for)] == self.wait_for:
                            self.wait_result = msg
                            self.wait_for = None
                            self.wait_event.set()
                    if msg.data[0:5] == CONTROL_ASSIGN:
                        print('Changed to control assign', msg.data[11])
                    elif msg.data[0:3] == FADER:
                        try:
                            num, val = msg.data[7], midi_value(msg.data[9:12])
                            faders[num].set_val(val)
                            # print_faders(faders)
                        except (KeyError, IndexError):
                            pass
                elif msg.type == 'program_change':
                        print('Changed program!')

    def save_last(self, name):
        self.saved_messages[name] = self.last_message
        
    def diff_saved(self, *names):
        messages = [self.saved_messages[name].data for name in names]
        return [(i, *data) for i, data in enumerate(zip(*messages)) if len(set(data)) > 1]

    def wait(self, data):
        if self.wait_for:
            print(self.name, 'already waiting for', self.wait_for)
        else:
            self.wait_for = data
            self.wait_event.clear()
            print(self.name, 'now waiting for', self.wait_for)

class SenderThread(MidiThread):
    def __init__(self, port, listener_thread: ListenerThread):
        super().__init__(port)
        self.listener = listener_thread
        self.event = threading.Event()
        self.send_queue = queue.Queue()
    
    def send(self, *messages):
        for message in messages:
            self.send_queue.put(message)
        self.event.set()
    
    def send_hex(self, hex_str):
        message = mido.Message.from_hex(hex_str)
        self.send(message)
    
    def run(self):
        with mido.open_output(self.port) as self.outport:
            print('Thread', self.name, 'opened outport', self.outport)
            while True:
                self.event.wait()
                if self.stopped:
                    break
                while not self.send_queue.empty():
                    msg = self.send_queue.get()
                    self.outport.send(msg)
                    print('Sender sent', msg)
                self.event.clear()

    def send_note(self, pitch: str, velocity=50, on=True):
        pitch_dict = {'C': 12, 'D': 14, 'E': 16, 'F': 17, 'G': 19, 'A': 21, 'B': 23}
        assert len(pitch) in (2, 3)
        name, *accidental, octave = pitch
        note = pitch_dict[name.upper()]
        if len(accidental):
            assert accidental[0] in 'b#'
            if accidental[0] == 'b':
                note -= 1
            elif accidental[0] == '#':
                note += 1
        note += int(octave) * 12
        assert 21 <= note <= 108, 'Note out of MIDI range'
        command = 'note_on' if on else 'note_off'
        self.send(mido.Message(command, note=note, velocity=velocity))
    
    def send_all_notes_off(self):
        with self.lock:
            for note in range(21, 108+1):
                self.send_queue.put(mido.Message('note_off', note=note))
        self.event.set()
    
    def stop(self):
        super().stop()
        self.event.set()

def print_faders(fader_dict: dict):
    names, vals = zip(*[(f.name, str(f.val)) for f in fader_dict.values()])
    print('\t'.join(names) + '\n' + '\t'.join(vals))

m1 = mido.Message('sysex', time=0, data=bytearray(b'F07E7F0601F7'))
m2 = mido.Message('sysex', time=0, data=bytearray(b'F04230687403F7'))
m3 = mido.Message('sysex', time=0, data=bytearray(b'F04230684E02F7'))
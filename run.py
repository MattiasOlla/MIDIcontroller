from midi_contr import *
import sys

Listener = Sender = None

MODES = {0: 'COMBI', 2: 'PROG', 4: 'SEQ', 6: 'SAMPLING', 7: 'GLOBAL', 8: 'DISK', 9: 'SETLIST'}

def wait_for_connection():
    print('Waiting for connection')
    while True:
        if (any('kronos' in x.lower() for x in mido.get_input_names()) and
            any('kronos' in x.lower() for x in mido.get_output_names())):
            IN_PORT = [x for x in mido.get_input_names() if 'kronos' in x.lower()][0]
            OUT_PORT = [x for x in mido.get_output_names() if 'kronos' in x.lower()][0]
            global Listener, Sender
            Listener = ListenerThread(IN_PORT)
            Sender = SenderThread(OUT_PORT, Listener)
            for fader in faders.values():
                fader.send_thread = Sender
            Listener.start()
            Sender.start()
            print('Got connection, starting')
            break
        else:
            time.sleep(0.1)

_exit = exit
def exit():
    for obj in globals().values():
        if isinstance(obj, MidiThread):
            obj.stop()
            obj.join()
    _exit()

def find_all(data, value):
    res = []
    for i, v in enumerate(data):
        if v == value:
            res.append(i)
    return res

def save(name):
    Listener.save_last(name)

def diff(*messages):
    data = [mess.data for mess in messages]
    return [(i, *d) for i, d in enumerate(zip(*data)) if len(set(d)) > 1]

def send_wait(message, wait_tag=None):
    if not wait_tag:
        wait_tag = list(message.data[:5])
        wait_tag[3] += 1
        wait_tag = tuple(wait_tag)
    Listener.wait(wait_tag)
    t0 = time.time()
    Sender.send(message)
    Listener.wait_event.wait()
    print(f'Got result after {time.time() - t0} seconds')    
    return Listener.wait_result

def get_mode():
    reply = send_wait(GET_MODE, (66, 48, 104, 66))
    num = reply.data[4]
    return (num, MODES[num])

wait_for_connection()
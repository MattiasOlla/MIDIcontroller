class Unique_Listener_Thread(threading.Thread):
    def __init__(self, name, port):
        super().__init__(name=name)
        self.port = port
        self.lock = threading.Lock()
        self.unique_data = set()
        self.file = 'unique.txt'
    
    def run(self):
        with mido.open_input(self.port) as inport:
            print(inport)
            for msg in inport:
                if msg.type == 'sysex':
                    if msg.data[:-1] not in self.unique_data:
                        print(msg.data)
                        self.unique_data.add(msg.data[:-1])
                        with open(self.file, 'a') as f:
                            f.write(str(msg.data))
                            f.write('\n')
                elif msg.type == 'program_change':
                    print('Changed program!')
    
    def write(self, message):
        with open(self.file, 'a') as f:
            f.write(str(message))
            f.write('\n')

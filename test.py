import os

folder = "KRONOS_SysEx_2_1"
to_find = 'fader'
res = {}

for root, dirs, files in os.walk(folder):
    for name in files:
        path = os.path.join(root, name)
        if os.path.splitext(path)[-1] == '.txt':
            res[name] = 0
            with open(path) as f:
                for line in f:
                    res[name] += line.lower().count(to_find)

for path, count in filter(lambda x: x[1] > 0, res.items()):
    print(path, count)

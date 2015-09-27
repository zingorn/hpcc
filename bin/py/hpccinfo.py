import subprocess
import re
import json

class HpccInfo:
    def __init__(self, tool=None, options=None):
        self.inputFile = options.file
        self.function = options.function.split(',') if options.function is not None else None

        if tool is None:
            return

        self.tool = tool
        self.duration = None
        self.defstate = []
        self.nodesCount = 0

        process = subprocess.Popen(["xstftool", self.inputFile, '--print-statistics', '--convert'],
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        line = process.stdout.readline()
        while line:
            m = re.match(r"DEFGROUP\s+All_Processes\s+NMEMBS\s+(?P<node>\d+)", line)
            if m:
                self.nodesCount = float(m.group("node"))

            m = re.match(r"DURATION\s+\d+\s+(?P<duration>\d+)", line)
            if m:
                self.duration = float(m.group("duration"))

            m = re.match(r"DEFSTATE\s+\d+\s+ACT\s+\"(?P<func>[^\"]+)\"", line)
            if m:
                self.defstate.append(m.group("func"))
            line = process.stdout.readline()

        process.stdout.close()

    def load(self, string):
        obj = json.loads(string)
        self.tool = obj['tool']
        self.duration = obj['duration']
        self.defstate = obj['defstate']
        self.nodesCount = obj['nodesCount']

    def __str__(self):
        return json.dumps({
            'inputFile': self.inputFile,
            'function': self.function,
            'tool': self.tool,
            'duration': self.duration,
            'defstate': self.defstate,
            'nodesCount': self.nodesCount
        })


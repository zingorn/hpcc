
import json
import operator


class LengthStat:
    def __init__(self):
        self.dataByFunction = {}
        self.data = {}
        self.max = 0  # max for all data
        self.maxInFunc = {}  # max in each function
        self.maxSender = {}  # max for each senders
        self.duplex = {}
        self.sorted = {}
        # self.cache = []

    def normalize(self):
        for func in self.dataByFunction:
            for sender in self.dataByFunction[func]:
                for receiver in self.dataByFunction[func][sender]:
                    r = round(100 * self.dataByFunction[func][sender][receiver]['len'] / self.max, 3)
                    self.dataByFunction[func][sender][receiver]['pMax'] = r

        for sender in self.data:
            for receiver in self.data[sender]:
                self.data[sender][receiver]['pMax'] = round(100 * self.data[sender][receiver]['len'] / self.max, 3)

        # sorting by sender len
        self.sorted = sorted(self.maxSender.items(), key=operator.itemgetter(1), reverse=True)

    def load(self, string):
        obj = json.loads(string)
        self.dataByFunction = obj['dataByFunction']
        self.data = obj['data']
        self.max = obj['max']
        self.maxInFunc = obj['maxInFunc']
        self.duplex = obj['duplex']
        self.maxSender = obj['maxSender']

    def __str__(self):
        return json.dumps({
            'dataByFunction': self.dataByFunction,
            'data': self.data,
            'max': self.max,
            'maxInFunc': self.maxInFunc,
            'duplex': self.duplex,
            'maxSender': self.maxSender
        })

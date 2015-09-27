#!/usr/bin/env python

import sys
import os
import re
import json
import subprocess
import operator
import datetime
from optparse import OptionParser, OptionGroup


class LengthStat:
    def __init__(self):
        self.dataByFunction = {}
        self.data = {}
        self.max = 0            # max for all data
        self.maxInFunc = {}     # max in each function
        self.maxSender = {}     # max for each senders
        self.duplex = {}
        self.sorted = {}
        #self.cache = []

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

    def __str__(self):
        #return ''#json.dumps(self.cache)
        return json.dumps({'data': self.dataByFunction, 'max': self.max,
                           'maxInFunc': self.maxInFunc, 'duplex': self.duplex, 'maxSender': self.maxSender})


class Parser:
    def __init__(self, info, options):
        """

        :param info:
        :param options:
        :return:
        """
        self.info = info
        self.lengthStat = LengthStat()
        self.out_file = options.out
        self.options = options
        self.format = options.format
        self.cacheFile = options.cache

    def print_progress(self, time):
        sys.stdout.write(chr(13) + "{0}{1:9.3f}%".format(datetime.datetime.now().ctime(),
                                                         round(100 * float(time) / self.info.duration, 3)))

    # def read_cache(self):
    #     if not os.path.exists(self.cacheFile):
    #         print "File %s not exists" % self.cacheFile
    #         return False
    #
    #     with open(self.cacheFile, 'r') as f:
    #         obj = json.loads(f.read())
    #         self.lengthStat = LengthStat()
    #         self.lengthStat.cache = obj
    #
    #         for i in obj:
    #             self.collect_add_to_data()
    #         # self.lengthStat.dataByFunction = obj['data']
    #         # self.lengthStat.max = obj['max']
    #         # self.lengthStat.maxInFunc = obj['maxInFunc']
    #         # self.lengthStat.duplex = obj['duplex']
    #         # self.lengthStat.maxSender = obj['maxSender']
    #         data = {}
    #         for func in self.lengthStat.dataByFunction:
    #             for sender in self.lengthStat.dataByFunction[func]:
    #                 for recver in self.lengthStat.dataByFunction[func][sender]:
    #                     if sender not in data:
    #                         data[sender] = {recver: {'len': 0}}
    #
    #                     if recver not in data[sender]:
    #                         data[sender][recver] = {'len': 0}
    #                     data[sender][recver]['len'] += self.lengthStat.dataByFunction[func][sender][recver]['len']
    #
    #         self.lengthStat.data = data
    #     return True

    def parse(self):
        # cache not exists, then create he and work with one
        if not os.path.exists(self.cacheFile):
            print "Create cache..."
            cacheFile = open(self.cacheFile, 'w')
            process = subprocess.Popen(["xstftool", self.info.inputFile, '--convert'], stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            line = process.stdout.readline()
            lines = 0
            time = 0

            while line:
                lines += 1
                if lines % 100000 == 0:
                    self.print_progress(time)
                line = process.stdout.readline().rstrip()
                split = line.split(" ", 2)
                if len(split) != 3:
                    continue

                (time, cmd, args) = split
                if cmd not in ["SENDMSG", "RECVMSG", "GLOBALOP"]:
                    continue
                cacheFile.write(line + "\n")
            process.stdout.close()
            self.print_progress(self.info.duration)
            cacheFile.close()
            print ''

        # read data from cache
        f = open(self.cacheFile, 'r')
        line = f.readline()
        lines = 0
        time = 0
        while line:
            lines += 1
            if lines % 10000 == 0:
                self.print_progress(time)
            split = line.split(" ", 2)
            if len(split) != 3:
                continue

            (time, cmd, args) = split
            self.collect_length(cmd, args)
            line = f.readline()
        self.print_progress(self.info.duration)

    @staticmethod
    def parse_globalop_string(line):
        s = line.split(" ")
        func = s[0]
        receiver = s[2].replace('0:', '')
        sender = s[6].replace('0:', '')
        sent = float(s[8])
        recv = float(s[10])
        return func, sender, receiver, sent, recv

    @staticmethod
    def parse_sendmsg_string(line):
        s = line.split(' ')
        func = s[10]
        receiver = s[4].replace('0:', '')
        sender = s[6].replace('0:', '')
        sent = float(s[8])
        return func, sender, receiver, sent

    @staticmethod
    def parse_recvmsg_string(line):
        s = line.split(' ')
        func = s[10]
        receiver = s[4].replace('0:', '')
        sender = s[6].replace('0:', '')
        sent = float(s[8])
        return func, sender, receiver, sent

    def collect_add_to_data(self, func_name, sender, recver, value):
        func_name = func_name.rstrip().replace('"', '')

        if func_name not in self.info.function:
            return

        # data by function name
        if func_name not in self.lengthStat.dataByFunction:
            self.lengthStat.dataByFunction[func_name] = {sender: {recver: {'len': 0}}}

        if sender not in self.lengthStat.dataByFunction[func_name]:
            self.lengthStat.dataByFunction[func_name][sender] = {recver: {'len': 0}}

        if recver not in self.lengthStat.dataByFunction[func_name][sender]:
            self.lengthStat.dataByFunction[func_name][sender][recver] = {'len': 0}

        self.lengthStat.dataByFunction[func_name][sender][recver]['len'] += float(value)
        if self.lengthStat.max < self.lengthStat.dataByFunction[func_name][sender][recver]['len']:
            self.lengthStat.max = self.lengthStat.dataByFunction[func_name][sender][recver]['len']

        # data by sender
        if sender not in self.lengthStat.data:
            self.lengthStat.data[sender] = {recver: {'len': 0}}

        if recver not in self.lengthStat.data[sender]:
            self.lengthStat.data[sender][recver] = {'len': 0}

        self.lengthStat.data[sender][recver]['len'] += float(value)

        # common statistic
        if sender not in self.lengthStat.maxSender:
            self.lengthStat.maxSender[sender] = 0

        self.lengthStat.maxSender[sender] += float(value)
        self.lengthStat.duplex[sender + '-' + recver] = None
        if recver + '-' + sender in self.lengthStat.duplex:
            self.lengthStat.duplex[recver + '-' + sender] = recver

    def collect_length(self, cmd, args):
        func = sender = recver = sent = None

        if cmd == 'GLOBALOP':
            func, sender, recver, sent, recv = self.parse_globalop_string(args)
            
            if sent > 0:
                self.collect_add_to_data(func, sender, recver, sent)
            if recv > 0:
                self.collect_add_to_data(func, recver, sender, recv)
            return

        if cmd == 'SENDMSG':
            func, sender, recver, sent = self.parse_sendmsg_string(args)

        if cmd == 'RECVMSG':
            func, sender, recver, sent = self.parse_recvmsg_string(args)

        self.collect_add_to_data(func, sender, recver, sent)

    def to_print(self):
        self.lengthStat.normalize()
        out_data = {}
        duplex_list = self.lengthStat.duplex

        for item in self.lengthStat.sorted:
            sender = item[0]
            for recver in self.lengthStat.data[sender]:
                if sender not in out_data:
                    out_data[sender] = {'imports': [], 'label': sender, 'name': sender}
                if sender+'-'+recver in duplex_list and duplex_list[sender+'-'+recver] == sender:
                    duplex = 1
                else:
                    if recver + '-' + sender in duplex_list and duplex_list[recver + '-' + sender] == recver:
                        duplex = 2
                    else:
                        duplex = 0
                out_data[sender]['imports'].append({
                    'name': recver,
                    'stat': self.lengthStat.data[sender][recver],
                    'duplex': duplex
                })
        out_data = out_data.values()

        template_file = os.path.dirname(__file__) + os.path.sep + 'd3' + os.path.sep + self.format + '.d3wrapper.html'
        with open(template_file, 'r') as f:
            content = f.read()
            file_name = os.path.expanduser(self.out_file) if self.out_file[0] == '~' \
                else (os.getcwd() + os.path.sep + self.out_file if self.out_file[0] != '/' else self.out_file)

            with open(file_name + '.html', 'w') as f2:
                f2.write(content.replace('%json%', json.dumps(out_data)).replace('%function_name%', ','.join(self.info.function)))


class HpccInfo:
    def __init__(self, tool, options):
        self.inputFile = options.file
        self.function = options.function.split(',')
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


def main():
    parser = OptionParser(usage="Usage: %prog [options] [[--] <application> [<args>]]")
    collection_group = OptionGroup(parser, "Collection options")
    collection_group.add_option("--file",
                                metavar="FILE",
                                dest="file",
                                help="")

    collection_group.add_option("--func",
                                metavar="OUT",
                                dest="function",
                                help="")

    collection_group.add_option("--out",
                                metavar="OUT",
                                dest="out",
                                help="")

    collection_group.add_option("--cache",
                                metavar="CACHE",
                                dest="cache",
                                help="")

    collection_group.add_option("--format",
                                metavar="FORMAT",
                                dest="format",
                                help="")

    collection_group.add_option("--max-node",
                                metavar="ITERATION",
                                dest="max_node",
                                help="")

    parser.add_option_group(collection_group)

    (options, arguments) = parser.parse_args()
    if options.file:
        if not os.path.exists(options.file):
            parser.error("file not found")
    else:
        parser.error("file not specified")

    info = HpccInfo('xstftool', options)
    parser = Parser(info, options)

    print datetime.datetime.now().ctime() + ' Start'
    parser.parse()
    parser.to_print()
    print "\n" + datetime.datetime.now().ctime() + ' End'
    return 0

if __name__ == "__main__":
    return_code = main()
    sys.exit(return_code)

#!/usr/bin/env python

import os
import datetime
import subprocess
import json
import sys
import csv
from lengthstat import LengthStat


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
        self.groups = None

    def print_progress(self, time):
        sys.stdout.write(chr(13) + "{0}{1:9.3f}%".format(datetime.datetime.now().ctime(),
                                                         round(100 * float(time) / self.info.duration, 3)))

    def parse(self):
        if os.path.exists('.lencache'):
            with open('.lencache', 'r') as f:
                self.lengthStat = LengthStat()
                self.lengthStat.load(f.readline())
            return

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

        with open('.lencache', 'w') as f:
            f.write(str(self.lengthStat))

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

        if self.info.function is not None and func_name not in self.info.function:
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

            if self.options.max_node is not None \
                    and (int(self.options.max_node) < float(sender) or int(self.options.max_node) < float(recver)):
                # cut operation if need less nodes
                return

            # extra data
            iter = 1
            if self.options.max_node is not None and int(self.options.max_node) > self.info.nodesCount:
                iter = int(int(self.options.max_node) / self.info.nodesCount)

            for i in range(0, iter):
                nsender = str(int(self.info.nodesCount * i + int(sender)))
                nrecver = str(int(self.info.nodesCount * i + int(recver)))
                if sent > 0:
                    self.collect_add_to_data(func, nsender, nrecver, sent)
                if recv > 0:
                    self.collect_add_to_data(func, nrecver, nsender, recv)
            return

        if cmd == 'SENDMSG':
            func, sender, recver, sent = self.parse_sendmsg_string(args)

        if cmd == 'RECVMSG':
            func, sender, recver, sent = self.parse_recvmsg_string(args)

        if self.options.max_node is not None \
                and (int(self.options.max_node) < float(sender) or int(self.options.max_node) < float(recver)):
            # cut operation if need less nodes
            return

        # extra data
        iter = 1
        if self.options.max_node is not None and int(self.options.max_node) > self.info.nodesCount:
            iter = int(int(self.options.max_node) / self.info.nodesCount)

        for i in range(0, iter):
            nsender = str(int(self.info.nodesCount * i + int(sender)))
            nrecver = str(int(self.info.nodesCount * i + int(recver)))
            self.collect_add_to_data(func, nsender, nrecver, sent)

    def get_data_item_to_print(self, sender, recver):
        duplex_list = self.lengthStat.duplex
        if sender + '-' + recver in duplex_list and duplex_list[sender + '-' + recver] == sender:
            duplex = 1
        else:
            if recver + '-' + sender in duplex_list and duplex_list[recver + '-' + sender] == recver:
                duplex = 2
            else:
                duplex = 0

        if hasattr(self.options, 'percent') and self.options.percent is not None \
                and self.lengthStat.data[sender][recver]['pMax'] < float(self.options.percent):
            return None

        return {
            'name': recver,
            'stat': self.lengthStat.data[sender][recver],
            'duplex': duplex
        }

    def get_group_data_item_to_print(self, sender, recver):
        duplex_list = self.groups['duplex']
        if sender + '-' + recver in duplex_list and duplex_list[sender + '-' + recver] == sender:
            duplex = 1
        else:
            if recver + '-' + sender in duplex_list and duplex_list[recver + '-' + sender] == recver:
                duplex = 2
            else:
                duplex = 0

        # if hasattr(self.options, 'percent') and self.options.percent is not None \
        #         and self.groups['data'][sender][recver]['pMax'] < float(self.options.percent):
        #     return None

        return {
            'name': recver,
            'stat': self.groups['data'][sender][recver],
            'duplex': duplex
        }

    def get_sorter_data(self):
        out_data = {}

        for item in self.lengthStat.sorted:
            sender = item[0]
            for recver in self.lengthStat.data[sender]:
                if sender not in out_data:
                    out_data[sender] = {'imports': [], 'label': sender, 'name': sender}
                itm = self.get_data_item_to_print(sender, recver)
                if itm is not None:
                    out_data[sender]['imports'].append(itm)

        return out_data.values()

    def get_smart_order_data(self):
        # normalize group
        for sender in self.groups['data']:
            for receiver in self.groups['data'][sender]:
                p_max = round(100 * self.groups['data'][sender][receiver]['len'] / self.groups['max'], 3)
                self.groups['data'][sender][receiver]['pMax'] = p_max

        out_data = {}

        for sender in self.groups['data']:
            for recver in self.groups['data'][sender]:
                if sender not in out_data:
                    out_data[sender] = {'imports': [], 'label': sender, 'name': sender}
                itm = self.get_group_data_item_to_print(sender, recver)

                if itm is not None:
                    out_data[sender]['imports'].append(itm)

        out = []
        for o in self.groups['order']:
            if o in out_data:
                out.append(out_data[o])
            else:
                out.append({'name': o, 'label': o, 'imports': []})
        return out

    def get_order_data(self):
        out_data = {}

        for group in self.groups['groups']:
            for sender in group['nodes']:
                for recver in self.lengthStat.data[sender]:
                    k = self.groups['nodes'][sender] + '.' + sender
                    if k not in out_data:
                        out_data[k] = {'imports': [],
                                         'label': self.groups['nodes'][
                                                      sender] + '.' + sender,
                                         'name': self.groups['nodes'][
                                                     sender] + '.' + sender}
                    itm = self.get_data_item_to_print(sender, recver)

                    if itm is not None:
                        itm['name'] = self.groups['nodes'][itm['name']] + '.' + itm['name']
                        out_data[k]['imports'].append(itm)

        return out_data.values()

    def to_print(self):
        self.lengthStat.normalize()
        if hasattr(self.options, 'order') and self.options.order is not None:
            out_data = self.get_order_data()
        elif hasattr(self.options, 'smart_order') and self.options.smart_order is not None:
            out_data = self.get_smart_order_data()
        else:
            out_data = self.get_sorter_data()

        template_file = os.path.dirname(__file__) + os.path.sep + 'd3' + os.path.sep + self.format + '.d3wrapper.html'
        with open(template_file, 'r') as f:
            content = f.read()
            file_name = os.path.expanduser(self.out_file) if self.out_file[0] == '~' \
                else (os.getcwd() + os.path.sep + self.out_file if self.out_file[0] != '/' else self.out_file)

            with open(file_name + '.html', 'w') as f2:
                functionName = self.info.function if self.info.function is not None else ['All']
                f2.write(content.replace('%json%', json.dumps(out_data)).replace('%function_name%',
                                                                                 ','.join(functionName)))

    def read_groups(self, file_name):
        groups = []
        nodes = {}
        order = []
        with open(file_name, 'r') as f:
            line = f.readline().rstrip('\n')

            while line:
                split = line.split(" ")
                group_name = split.pop(0)
                order.append(group_name)
                groups.append({'group_name': group_name, 'nodes': split})
                for n in split:
                    nodes[n] = group_name
                line = f.readline().rstrip('\n')
            f.close()

        self.groups = {
            'groups': groups,
            'nodes': nodes,
            'order': order,
            'data': None,
            'duplex': None,
            'max': 0
        }

    def order(self):
        if self.options.order is None or not os.path.exists(self.options.order):
            print "Order file not specified"
            sys.exit()

        self.read_groups(self.options.order)
        self.parse()
        self.to_print()

    def smart_order2(self):
        return self.smart_order(True)

    def smart_order(self, no_duplex=False):
        self.read_groups(self.options.smart_order)
        self.parse()
        group_data = {}
        group_duplex = {}
        max_len = 0

        # filter data
        self.lengthStat.normalize()

        for sender in self.lengthStat.data:
            for recver in self.lengthStat.data[sender]:

                if hasattr(self.options, 'percent') and self.options.percent is not None \
                        and self.lengthStat.data[sender][recver]['pMax'] < float(self.options.percent):
                    continue

                sender_group = self.groups['nodes'][sender]
                recver_group = self.groups['nodes'][recver]

                if sender_group not in group_data:
                    group_data[sender_group] = {recver_group: {'len': 0}}

                if recver_group not in group_data[sender_group]:
                    group_data[sender_group][recver_group] = {'len': 0}

                group_data[sender_group][recver_group]['len'] += self.lengthStat.data[sender][recver]['len']

                if max_len < group_data[sender_group][recver_group]['len']:
                    max_len = group_data[sender_group][recver_group]['len']

                group_duplex[sender_group + '-' + recver_group] = None
                if recver_group + '-' + sender_group in group_duplex:
                    group_duplex[recver_group + '-' + sender_group] = recver_group

        self.groups['data'] = group_data
        self.groups['max'] = max_len

        self.groups['duplex'] = [] if no_duplex else group_duplex
        self.to_print()

    def matrix(self):
        self.parse()
        with open(self.options.matrix, 'wb') as f:
            writer = csv.writer(f, delimiter=';')
            process = self.options.max_node if \
                hasattr(self.options, 'max_node') and self.options.max_node is not None \
                else self.info.nodesCount
            r = range(1, int(process) + 1)
            # header
            writer.writerow([0] + r)

            for x in r:
                row = ["" for i in range(0, int(process) + 1)]
                row[0] = x

                for y in r:
                    row[y] = self.lengthStat.data[str(x)][str(y)]['len'] \
                        if str(x) in self.lengthStat.data and str(y) in self.lengthStat.data[str(x)] else ''

                writer.writerow(row)

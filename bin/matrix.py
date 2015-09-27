#!/usr/bin/env python
"""
Date: 19.09.2015
Version: 1
"""

import sys
import os
import datetime
import csv
from optparse import OptionParser, OptionGroup
from py.hpccinfo import HpccInfo
from py.parser import Parser


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

    collection_group.add_option("--matrix",
                                metavar="ITERATION",
                                dest="matrix",
                                help="")


    parser.add_option_group(collection_group)

    (options, arguments) = parser.parse_args()
    if options.file:
        if not os.path.exists(options.file):
            parser.error("file not found")
    else:
        parser.error("file not specified")

    if not os.path.exists('.stfinfo'):
        info = HpccInfo('xstftool', options)
        with open('.stfinfo', 'w') as f:
            f.write(str(info))
    else:
        with open('.stfinfo', 'r') as f:
            info = HpccInfo(None, options)
            info.load(f.readline())

    parser = Parser(info, options)
    print datetime.datetime.now().ctime() + ' Start'
    parser.matrix()
    print "\n" + datetime.datetime.now().ctime() + ' End'
    return 0


if __name__ == "__main__":
    return_code = main()
    sys.exit(return_code)

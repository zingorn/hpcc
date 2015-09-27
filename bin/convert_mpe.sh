#!/bin/sh

#
# Gone to folder with results of runs.
# Usage:
#     convert_mpe.sh <app>
# Example:
#     convert_mpe.sh hpcc
#
#
CURDIR="$( pwd )"
DIR="$( cd "$(dirname "$0")" && pwd )"
# "

convert_mpe()
{
    if [ ! -d "$1" ]; then
        echo "MPE folder not found ($1)"
        exit 1
    fi
    app="$2"

    export JVMFLAGS=-Xmx4096m
    for runPath in `ls -d $1/*/`
    do
        for rankPath in `ls -d $runPath*/`
        do
            echo "Convert $rankPath/$app.mpe.clog2"
            clog2TOslog2 -o $rankPath/$app.mpe.slog2 $rankPath/$app.mpe.clog2
        done
    done
}
#start


convert_mpe $CURDIR/$1/mpe $1

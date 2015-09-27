#!/bin/sh
#
# Gone to folder with results of runs.
# Usage:
#     convert_hpctk.sh <app>
# Example:
#     convert_hpctk.sh hpcc
#
#
CURDIR="$( pwd )"
DIR="$( cd "$(dirname "$0")" && pwd )"
# "


convert_hpctk()
{
    if [ ! -d "$1" ]; then
        echo "HPCToolkit folder not found ($1)"
        exit 1
    fi
    app="$2"
    if [ ! -f $DIR/$app.hpctk.hpcstruct ]; then
        echo "HPCToolKit Structure file $app.hpctk.hpcstruct not found (try hpcstruct -o $app.hpctk.hpcstruct $app.hpc)"
        exit 1
    fi

    for runPath in `ls -d $1/*/`
    do
    echo $runPath
        for rankPath in `ls -d $runPath*/`
        do
            echo "Convert $rankPath"
            cd $rankPath
            hpcprof-mpi -S $DIR/$app.hpctk.hpcstruct `ls -d $rankPath/hpctoolkit-*/`
        done
    done
}

convert_hpctk $CURDIR/$1/hpctk $1
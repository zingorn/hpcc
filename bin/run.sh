#!/bin/sh

CURDIR="$( pwd )"
DIR="$( cd "$(dirname "$0")" && pwd )"
# "

run=$( date +'run_%d%m%Y_%H%M%S' )
LOG="$CURDIR/$run/log"
ranks="1 2 4 8 16 32 64 128 256 512"
forceConvert=false
NODES=16
CORES=16
let PROCESSNUM=$NODES*$CORES

usage()
{
    cat <<EOF
Usage:
    Execute tests:
    $0 -n <number run> -i <mpe|mpip|itac|hpctk|scal> -a <cpi|hpcc> [-r <ranks>] [-f]
	-n	Number of runs
	-i	Instrument names (via comma).
	-a 	Application names (via comma)
	-r	Number of ranks (via comma). Default value 1,2,4,8,16,32,64,128,256,512
	-f	Force convert
    $0 -n 10 -i scal,hpctk -r 8,16,32 -a hpcc
    
    Convert results
    $0 -c <instrument> <path>
    
EOF
    exit
}

die()
{
    echo "error: $*" 1>&2
    exit 1;
}
checkfreeres()
{
          # check finishe tasks
          while true
          do
            d=$( squeue | grep udigo |wc | awk '{ print $1}' )
            if test "$d" != '0'
              then
              d="$(squeue | grep udigo)"
              cat << EOF
`date`
$d
EOF
              sleep 5s
            else
              break
            fi
          done

}
cPerCore()
{
  n=$1
  let perCore=($n+$PROCESSNUM-1)/$PROCESSNUM;
  perCore=2
  echo $perCore
}
cpi_mpe()
{
    ranks="$1"
    runPath="$2"
    for n in $ranks;
    do
	mkdir $runPath/$n; cd $runPath/$n
	perCore=$( cPerCore $n )
        cmd="srun -p all -t 60 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/cpi.mpe &> >(tee -a $LOG)"
        echo $cmd
        $cmd
        mv $DIR/cpi.mpe.clog2 $runPath/$n/cpi.mpe.clog2
    done
}

cpi_itac()
{
    ranks="$1"
    runPath="$2"
    for n in $ranks;
    do
	mkdir $runPath/$n; cd $runPath/$n
	perCore=$( cPerCore $n )
        cmd="srun -p all -t 60 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/cpi.itac &> >(tee -a $LOG)"
        echo $cmd
        $cmd
    done
}

cpi_scal()
{
    ranks="$1"
    runPath="$2"
    for n in $ranks;
    do
	mkdir $runPath/$n; cd $runPath/$n
	perCore=$( cPerCore $n )
        cmd="srun -p all -t 60 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/cpi.scal &> >(tee -a $LOG)"
        echo $cmd
        $cmd
    done
}

cpi_mpip()
{
    ranks="$1"
    runPath="$2"
    for n in $ranks;
    do
	mkdir $runPath/$n; cd $runPath/$n
	perCore=$( cPerCore $n )
        cmd="srun -p all -t 60 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/cpi.mpip &> >(tee -a $LOG)"
        echo $cmd
        $cmd
    done
}

cpi_hpctk()
{
    ranks="$1"
    runPath="$2"
    for n in $ranks;
    do
	mkdir $runPath/$n; cd $runPath/$n
	#let perCore=($n+255)/256;
	perCore=$( cPerCore $n )
        cmd="srun -p all -t 60 --reservation=mpiperf -n $n --ntasks-per-core=$perCore hpcrun -t $DIR/cpi.hpc &> >(tee -a $LOG)"
        echo $cmd
        $cmd
    done
}


unpackHpcc()
{
    tar -xf $DIR/hpcc.inf.tar.bz2
}

hpcc_mpe()
{
    ranks="$1"
    runPath="$2"
    unpackHpcc
    for n in $ranks;
    do
        cd $runPath/$n
        perCore=$( cPerCore $n )
        cmd="srun -p all -t 10  --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/hpcc.mpe &> >(tee -a $LOG)"
        echo $cmd
        $cmd
        mv $DIR/hpcc.mpe.clog2 $runPath/$n/hpcc.mpe.clog2
        sleep 3
    done
}

hpcc_itac()
{
    ranks="$1"
    runPath="$2"
    unpackHpcc
    for n in $ranks;
    do
        cd $runPath/$n
        perCore=$( cPerCore $n )
        cmd="srun -p all -t 15 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/hpcc.itac &> >(tee -a $LOG)"
        echo $cmd
        $cmd
        sleep 3
    done
}

hpcc_mpip()
{
    ranks="$1"
    runPath="$2"
    unpackHpcc
    for n in $ranks;
    do
        cd $runPath/$n
        perCore=$( cPerCore $n )
        cmd="srun -p all -t 15 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/hpcc.mpip &> >(tee -a $LOG)"
        echo $cmd
        $cmd
        sleep 3
    done
}

hpcc_scal()
{
    ranks="$1"
    runPath="$2"
    unpackHpcc
    for n in $ranks;
    do
        cd $runPath/$n
        perCore=$( cPerCore $n )
        cmd="scalasca -analyze srun -p all -t 15 --reservation=mpiperf -n $n --ntasks-per-core=$perCore $DIR/hpcc.scal"
        echo $cmd
        $cmd
        sleep 3
    done
}

hpcc_hpctk()
{
    ranks="$1"
    runPath="$2"
    unpackHpcc
    for n in $ranks;
    do
        cd $runPath/$n
        perCore=$( cPerCore $n )
        cmd="srun -p all -t 15 --reservation=mpiperf -n $n --ntasks-per-core=$perCore hpcrun -t $DIR/hpcc.hpctk &> >(tee -a $LOG)"
        echo $cmd
        $cmd
        sleep 3
    done
}

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

# start script
args=$@
while test "x$1" != x
do
    case "$1" in
        -h | --help )
    	    usage
    	    exit;
    	    ;;
	-a )
	    test "x$2" != x || die "missing argumet for -t"
    	    appTypes=${2//,/ }
	    shift; shift;
	    ;;
        -n )
	    test "x$2" != x || die "missing argumet for -n"
	    number="$2" 
	    shift; shift;
	    ;;
	-i )
	    test "x$2" != x || die "missing argumet for -t"
    	    instrTypes=${2//,/ }
	    shift; shift;
	    ;;
	-r )
	    test "x$2" != x || die "missing argumet for -r"
    	    ranks=${2//,/ }
	    shift; shift;
	    ;;
	-c )
	    test "x$2" != x || die "missing argumet for -c"
	    convertType="$2"
	    shift; shift;
	    break;
	    ;;
	-f )
	    forceConvert=true
	    shift;
	    ;;
	--tee )
	    tee=1
	    shift
	    ;;
        -- )
            shift
            break
            ;;
        -* )
            die "unknown option: $1"
            ;;
        * )
            break
            ;;
    esac;
done;

if test "x$convertType" != x; then
    if [[ ${str:0:1} == "/" ]]; then path=$1/; else path=$CURDIR/$1/; fi
    convert_$convertType ${path}/$2/$convertType $2
    exit 0;
fi

test "x$number" != x || die "Number runs not specified (-n <digit>)"
test "x$instrTypes" != x || die "Instrument type not specified (-i <mpe|itac|hpc|scalasca>)"
test "x$appTypes" != x || die "Application types not specified (-a <cpi|hpcc>)"
mkdir -p -- $CURDIR/$run
# full log
if [ "$tee" != "1" ]; then
  $0 --tee $args 2>&1 | tee $LOG
  exit $?
fi
cat << EOF
`date`
Run $args
EOF
converMpe=""
converHpctk=""
checkfreeres
for appType in $appTypes;
do
  for instrType in $instrTypes;
  do
      runFunc="${appType}_${instrType}"
      if test "$instrType" = "mpe"
  	then convertMpe="1"
      fi
      if test "$instrType" = "hpctk"
	then convertHpctk="1"
      fi
      for i in $(seq 1 $number);
      do
          runPath=$CURDIR/$run/$appType/$instrType/r$i
          echo "Run #$i. Location $runPath"
          mkdir -p -- $runPath
          cd $runPath
          $runFunc "$ranks" "$runPath"
          checkfreeres
      done # for i
  done # for 
done


if test "$convertMpe" = "1"; then
  if [ ! forceConvert ]; then
    while true; do
      read -p "Convert MPE logs (y/n)? " yn
      case $yn in
          [Yy]* ) convertM=true; break;;
          [Nn]* ) convertM=false;break;;
          * ) echo "Please answer yes or no.";;
      esac
    done
  else 
    convertM=true
  fi
  if [ $convertM ]; then
    for appType in $appTypes
    do
      convert_mpe $CURDIR/$run/$appType/mpe $appType
    done
  fi
fi

if test "$convertHpctk" = "1"; then
  if [ ! forceConvert ]; then
    while true; do
      read -p "Convert HPCToolKit logs (y/n)? " yn
      case $yn in
          [Yy]* ) convertH=true; break;;
          [Nn]* ) convertH=false;break;;
          * ) echo "Please answer yes or no.";;
      esac
    done
  else
    convertH=true
  fi
  if [ $convertH ]; then
    for appType in $appTypes
    do
        convert_hpctk $CURDIR/$run/$appType/hpctk $appType
    done
  fi
fi 
cat << EOF
`date`
See log file $LOG
End runs.
EOF
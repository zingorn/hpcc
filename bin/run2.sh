#!/bin/sh

CURDIR="$( pwd )"
#instrTypes=(itac hpctk scal mpip mpe)
instrTypes=(mpe)
number=1
#ranks=(1 2 4 8 16 32 64 128 256 512 1024 2048 4096)
ranks=(1 2 4 8 16 32 64 128 256 512 1024)

checkfreeres()
{
          # check finishe tasks
          while true
          do
            d=$( squeue | grep udigo |wc | awk '{ print $1}' )
            if test "$d" != '0'
              then
              d="$(squeue | grep udigo)"
              echo `date`
              echo $d

              sleep 5s
            else
              break
            fi
          done

}

  for instrType in ${instrTypes[@]};
  do
      for i in $(seq 1 $number);
      do
          runPath=$CURDIR/hpcc/$instrType/r$i
          mkdir -p -- $runPath
          cd $runPath
          tar -xf $CURDIR/hpcc.inf.tar.bz2
          for n in ${ranks[@]};
          do
            cd $runPath/$n
            out_file="../job$n.sh"
            echo "#!/bin/sh" > $out_file
            echo "#SBATCH -N 16 -n 512" >> $out_file
            echo "mpirun -l  -wdir $runPath/$n -genv I_MPI_PIN_DOMAIN=core -n $n $CURDIR/hpcc.$instrType" >> $out_file
            # hpctk only
            #echo "mpirun -l  -wdir $runPath/$n -genv I_MPI_PIN_DOMAIN=core -n $n hpcrun -t $CURDIR/hpcc.hpctk" >> $out_file
            
            
            echo "$instrType r$i $n"
            
            #run_f=true
            
            #while $run_f; do
              sbatch -t 160 -p all --reservation=mpiperf ../job$n.sh
              checkfreeres
              sleep 2s
              mv $CURDIR/hpcc.mpe.clog2 $runPath/$n/hpcc.mpe.clog2
              #/home/udigo/runs/bin/clear.tmp
              #result=`cat *.out`
            
              #cond=`echo "$result" | grep -q "fault"`
            
              #if [ -n "$cond" ]; then
            #    echo $cond
            #    rm -f *.out
            #  else
            #    echo "done"
            #    run_f=false
            #  fi
            #done
          done
      done # for i
  done # for

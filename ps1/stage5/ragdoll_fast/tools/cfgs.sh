# solver configurations compared in the report: name -> cflags
cfg() { case $1 in
 l1)  echo "-DRP_LEVEL=1";;
 c1)  echo "-DRP_LEVEL=2";;
 c4)  echo "-DRP_LEVEL=2 -DRP_NS_BASE=2 -DRP_NS_DIV=12 -DRP_NSMAX=5 -DRP_HINGE_LAST=1";;
 c5)  echo "-DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1";;
 c2)  echo "-DRP_LEVEL=2 -DRP_ITER=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1";;
 c3)  echo "-DRP_LEVEL=2 -DRP_ITER=2 -DRP_NS_BASE=2 -DRP_NS_DIV=15 -DRP_NSMAX=4 -DRP_HINGE_LAST=1";;
 esac; }
cfg2() { case $1 in
 c6)  echo "-DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1 -DRP_COLL_LAST=1";;
 c7)  echo "-DRP_LEVEL=2 -DRP_NS_BASE=2 -DRP_NS_DIV=10 -DRP_NSMAX=5 -DRP_HINGE_LAST=1 -DRP_COLL_LAST=1";;
 c8)  echo "-DRP_LEVEL=2 -DRP_ITER=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1 -DRP_COLL_LAST=1";;
 esac; }
# stage 5 speed pass: the shipped c5 plus RP_FAST (caches, GTE, sleeping, adaptive substeps); the game-side governor is -DPOLICY (src/scenario.inc)
cfg3() { case $1 in
 f1)  echo "-DRP_LEVEL=2 -DRP_NS_BASE=3 -DRP_NS_DIV=10 -DRP_NSMAX=6 -DRP_HINGE_LAST=1 -DRP_FAST=1 -DPOLICY";;
 esac; }

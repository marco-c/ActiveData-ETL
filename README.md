TestLog-ETL
===========

The ETL process responsible for filling ActiveData.

Branches
--------

Many branches are meant as stable versions for each of the processes involved 
in the ETL.  Ideally, they would be unified, but library upgrades can cause 
unique instability: deployment of a branch does not happen until (manual) 
testing has been done.

Here are the important branches:

* **dev** - unstable - primary branch for accepting changes
* **etl** - stable - for ETL machines
* **primary** - stable - for the "primary" and "coordinator" ES nodes 
* **pulse-logger** - stable - for the PulseLogger
* **push-to-es** - stable - code installed on ES spot instance machines for 
final indexing. 
* **beta** - stable - of all branches for testing on the beta machines 
* **master** - unstable - intermittently updated to track **dev**, eventually 
intended as the single-stable-version 

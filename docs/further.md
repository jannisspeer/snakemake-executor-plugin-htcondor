It is recommended to use the dedicated snakemake profile for HTCondor, which you can find [here](https://github.com/Snakemake-Profiles/htcondor).
This plugin currently only supports job submission with a shared file system.
As executable the jobs use `bin/bash`.
As default the jobs will be executed with the same set of environment variables that the user had at submit time. If you don't want this behavior set the following in resources `getenv: False`.

Jobs status is checked from log with htcondor.JobEventType
https://htcondor.readthedocs.io/en/latest/man-pages/condor_submit.html
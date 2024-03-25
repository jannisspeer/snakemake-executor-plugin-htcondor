- It is recommended to use the dedicated snakemake profile for HTCondor, which you can find [here](https://github.com/Snakemake-Profiles/htcondor).
- This plugin currently only supports job submission with a shared file system.
- The jobs use the python binary of the environment that the user had when starting snakemake as the executable.
- Error messages, the output of stdout and log files are written to `htcondor-jobdir` (see in the usage section above).
- The job directive `threads` is used to set `request_cpu` command for HTCondor.
- As default, the jobs will be executed with the same set of environment variables that the user had at submit time. 
  If you don't want this behavior, set the following in resources `getenv: False`.
- For the job status, this plugin reports the values of the [job ClassAd Attribute](https://htcondor.readthedocs.io/en/latest/classad-attributes/job-classad-attributes.html) `JobStatus`.
- To determine whether a job was successful, this plugin relies on `htcondor.Schedd.history` (see [API reference](https://htcondor.readthedocs.io/en/latest/apis/python-bindings/api/htcondor.html)) and checks the values of the [job ClassAd Attribute](https://htcondor.readthedocs.io/en/latest/classad-attributes/job-classad-attributes.html) `ExitCode`.


The following [submit description file commands](https://htcondor.readthedocs.io/en/latest/man-pages/condor_submit.html) are supported (add them as user-defined resources):
| Basic             | Matchmaking      | Matchmaking (GPU)         | Policy                     |
| ----------------- | ---------------- | ------------------------- | -------------------------- |
| `getenv`          | `rank`           | `request_gpus`            | `max_retries`              |
| `environment`     | `request_disk`   | `require_gpus`            | `allowed_execute_duration` |
| `input`           | `request_memory` | `gpus_minimum_capability` | `allowed_job_duration`     |
| `max_materialize` | `requirements`   | `gpus_minimum_memory`     | `retry_until`              |
| `max_idle`        |                  | `gpus_minimum_runtime`    |                            |
|                   |                  | `cuda_version`            |                            |
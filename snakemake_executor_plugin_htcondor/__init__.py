from dataclasses import dataclass, field
from typing import List, Generator, Optional
from snakemake_interface_executor_plugins.executors.base import SubmittedJobInfo
from snakemake_interface_executor_plugins.executors.remote import RemoteExecutor
from snakemake_interface_executor_plugins.settings import (
    ExecutorSettingsBase,
    CommonSettings,
)
from snakemake_interface_executor_plugins.jobs import (
    JobExecutorInterface,
)
from snakemake_interface_common.exceptions import WorkflowError  # noqa

import htcondor
from os.path import join
from os import makedirs


# Optional:
# Define additional settings for your executor.
# They will occur in the Snakemake CLI as --<executor-name>-<param-name>
# Omit this class if you don't need any.
# Make sure that all defined fields are Optional and specify a default value
# of None or anything else that makes sense in your case.
@dataclass
class ExecutorSettings(ExecutorSettingsBase):
    jobdir: Optional[str] = field(
        default=".snakemake/htcondor",
        metadata={
            "help": "Directory where the job will create a directory to store log, "
            "output and error files.",
            "required": True,
        },
    )


# Required:
# Specify common settings shared by various executors.
common_settings = CommonSettings(
    # define whether your executor plugin executes locally
    # or remotely. In virtually all cases, it will be remote execution
    # (cluster, cloud, etc.). Only Snakemake's standard execution
    # plugins (snakemake-executor-plugin-dryrun, snakemake-executor-plugin-local)
    # are expected to specify False here.
    non_local_exec=True,
    # Whether the executor implies to not have a shared file system
    implies_no_shared_fs=False,
    # whether to deploy workflow sources to default storage provider before execution
    job_deploy_sources=True,
    # whether arguments for setting the storage provider shall be passed to jobs
    pass_default_storage_provider_args=True,
    # whether arguments for setting default resources shall be passed to jobs
    pass_default_resources_args=True,
    # whether environment variables shall be passed to jobs (if False, use
    # self.envvars() to obtain a dict of environment variables and their values
    # and pass them e.g. as secrets to the execution backend)
    pass_envvar_declarations_to_cmd=True,
    # whether the default storage provider shall be deployed before the job is run on
    # the remote node. Usually set to True if the executor does not assume a shared fs
    auto_deploy_default_storage_provider=True,
    # specify initial amount of seconds to sleep before checking for job status
    init_seconds_before_status_checks=0,
)


# Required:
# Implementation of your executor
class Executor(RemoteExecutor):
    def __post_init__(self):
        # access workflow
        self.workflow
        # access executor specific settings
        self.workflow.executor_settings

    def run_job(self, job: JobExecutorInterface):
        # Submitting job to HTCondor

        # Creating directory to store log, output and error files
        jobDir = self.workflow.executor_settings.jobdir
        makedirs(jobDir, exist_ok=True)

        # Creating submit dictionary which is passed to htcondor.Submit
        submit_dict = {
            "executable": "/bin/bash",
            "arguments": self.format_job_exec(
                job
            ),  # using the method from RemoteExecutor
            "log": join(jobDir, "$(ClusterId).log"),
            "output": join(jobDir, "$(ClusterId).out"),
            "error": join(jobDir, "$(ClusterId).err"),
            "request_cpus": str(job.threads),
        }

        # Basic commands
        if job.resources.get("getenv"):
            submit_dict["getenv"] = job.resources.get("getenv")
        else:
            submit_dict["getenv"] = True

        for key in ["environment", "input", "max_materialize", "max_idle"]:
            if job.resources.get(key):
                submit_dict[key] = job.resources.get(key)

        # Commands for matchmaking
        for key in [
            "rank",
            "request_disk",
            "request_memory",
            "requirements",
        ]:
            if job.resources.get(key):
                submit_dict[key] = job.resources.get(key)

        # Commands for matchmaking (GPU)
        for key in [
            "request_gpus",
            "require_gpus",
            "gpus_minimum_capability",
            "gpus_minimum_memory ",
            "gpus_minimum_runtime",
            "cuda_version",
        ]:
            if job.resources.get(key):
                submit_dict[key] = job.resources.get(key)

        # Policy commands
        if job.resources.get("max_retries"):
            submit_dict["max_retries"] = job.resources.get("max_retries")
        else:
            submit_dict["max_retries"] = 5

        for key in ["allowed_execute_duration", "allowed_job_duration", "retry_until"]:
            if job.resources.get(key):
                submit_dict[key] = job.resources.get(key)

        # HTCondor submit description
        self.logger.debug(f"HTCondor submit subscription: {submit_dict}")
        submit_description = htcondor.Submit(submit_dict)

        # Client for HTCondor Schedduler
        schedd = htcondor.Schedd()

        # Submitting job to HTCondor
        try:
            submit_result = schedd.submit(submit_description)
        except Exception as e:
            raise WorkflowError(f"Failed to submit HTCondor job: {e}")

        self.report_job_submission(SubmittedJobInfo(job=job, external_jobid=submit_result.cluster()))

    async def check_active_jobs(
        self, active_jobs: List[SubmittedJobInfo]
    ) -> Generator[SubmittedJobInfo, None, None]:
        # Check the status of active jobs.

        for current_job in active_jobs:
            async with self.status_rate_limiter:
                # Get the status of the job
                try:
                    schedd = htcondor.Schedd()
                    job_status = schedd.query(
                        constraint=f"ClusterId == {current_job.external_jobid}",
                        projection=["JobStatus"],
                    )
                except Exception as e:
                    self.logger.warning(f"Failed to retrieve HTCondor job status: {e}")
                    # Assuming the job is still running and retry next time
                    yield current_job
                self.logger.debug(
                    f"HTCondor job {current_job.external_jobid} status: {job_status}"
                )

                # Overview of HTCondor job status:
                # 1: Idle
                # 2: Running
                # 3: Removed
                # 4: Completed
                # 5: Held
                # 6: Transferring Output
                # 7: Suspended

                # Running/idle jobs
                if job_status[0]["JobStatus"] in [1, 2, 6, 7]:
                    if job_status[0]["JobStatus"] in [7]:
                        self.logger.warning(
                            f"HTCondor job {current_job.external_jobid} is suspended."
                        )
                    yield current_job
                # Successful jobs
                elif job_status[0]["JobStatus"] in [4]:
                    self.report_job_success(current_job)
                # Errored jobs
                elif job_status[0]["JobStatus"] in [3, 5]:
                    self.report_job_error(current_job)
                else:
                    raise WorkflowError(
                        f"Unknown HTCondor job status: {job_status[0]['JobStatus']}"
                    )

    def cancel_jobs(self, active_jobs: List[SubmittedJobInfo]):
        # Cancel all active jobs.
        # This method is called when Snakemake is interrupted.

        if active_jobs:
            schedd = htcondor.Schedd()
            job_ids = [current_job.external_jobid for current_job in active_jobs]
            # For some reason HTCondor requires not the BATCH_NAME but the full JOB_IDS
            job_ids = [f"ClusterId == {x}.0" for x in job_ids]
            self.logger.debug(f"Cancelling HTCondor jobs: {job_ids}")
            try:
                schedd.act(htcondor.JobAction.Remove, job_ids)
            except Exception as e:
                self.logger.warning(f"Failed to cancel HTCondor jobs: {e}")

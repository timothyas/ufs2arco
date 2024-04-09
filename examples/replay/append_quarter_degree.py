"""We can't use a dask cluster, because it cannot serialize the tasks of opening multiple
datasets with an io buffered reader object, orsomething.

So, this is easy enough to just submit separate slurm jobs that work on their own job ID.
"""

import os
import subprocess

from ufs2arco import FV3Dataset, Timer
from replay_appender import ReplayAppenderQuarterDegree


def submit_slurm_appender(job_id, appender):

    the_code = \
        f"from replay_appender import ReplayAppenderQuarterDegree\n"+\
        f"appender = ReplayAppenderQuarterDegree(\n"+\
        f"    n_jobs={appender.n_jobs},\n"+\
        f"    config_filename='{appender.config_filename}',\n"+\
        f"    storage_options={appender.storage_options},\n"+\
        f"    main_cache_path='{appender.main_cache_path}',\n"+\
        f")\n"+\
        f"appender.run({job_id})"

    slurm_dir = "slurm/replay-append-0.25-degree"
    txt = "#!/bin/bash\n\n" +\
        f"#SBATCH -J rqd{job_id:03d}\n"+\
        f"#SBATCH -o {slurm_dir}/{job_id:03d}.%j.out\n"+\
        f"#SBATCH -e {slurm_dir}/{job_id:03d}.%j.err\n"+\
        f"#SBATCH --nodes=1\n"+\
        f"#SBATCH --ntasks=1\n"+\
        f"#SBATCH --cpus-per-task=30\n"+\
        f"#SBATCH --partition=compute\n"+\
        f"#SBATCH -t 120:00:00\n\n"+\
        f"source /contrib/Tim.Smith/miniconda3/etc/profile.d/conda.sh\n"+\
        f"conda activate ufs2arco\n"+\
        f'python -c "{the_code}"'

    script_dir = "job-scripts"
    fname = f"{script_dir}/submit_qappender{job_id:03d}.sh"

    for this_dir in [slurm_dir, script_dir]:
        if not os.path.isdir(this_dir):
            os.makedirs(this_dir)

    with open(fname, "w") as f:
        f.write(txt)

    subprocess.run(f"sbatch {fname}", shell=True)


if __name__ == "__main__":

    walltime = Timer()
    localtime = Timer()

    walltime.start("Initializing job")

    appender = ReplayAppenderQuarterDegree(
        n_jobs=15,
        config_filename="config-0.25-degree.yaml",
        storage_options={"token": "/contrib/Tim.Smith/.gcs/replay-service-account.json"},
        main_cache_path="/lustre/Tim.Smith/tmp-replay/0.25-degree",
    )

    localtime.start("Make and Store Container Dataset")
    appender.store_container()
    localtime.stop()

    localtime.start("Run slurm jobs")
    for job_id in range(appender.n_jobs):
        submit_slurm_appender(job_id, appender)
    localtime.stop()

    walltime.stop("Walltime Time")

"""
Use this to append a dataset in time

TODO:
    - verify that the start and end time is correct
"""

from os.path import join, isdir
from datetime import datetime, timedelta
from shutil import rmtree

import numpy as np
import pandas as pd
import xarray as xr
from zarr import NestedDirectoryStore

from ufs2arco import FV3Dataset, Timer
from replay_mover import ReplayMoverQuarterDegree


class ReplayAppenderQuarterDegree(ReplayMoverQuarterDegree):

    @property
    def new_xcycles(self):
        cycles = pd.date_range(start="2023-10-13T12:00:00", end="2023-12-31T06:00:00", freq="6h")
        return xr.DataArray(cycles, coords={"cycles": cycles}, dims="cycles")

    @property
    def new_xtime(self):
        time = pd.date_range(start="2023-10-13T12:00:00", end="2023-12-31T09:00:00", freq="3h")
        iau_time = time - timedelta(hours=6)
        return xr.DataArray(iau_time, coords={"time": iau_time}, dims="time", attrs={"long_name": "time", "axis": "T"})

    @property
    def splits(self):
        #need to use self.new_xcycles, that's it
        return [int(x) for x in np.linspace(0, len(self.new_xcycles), self.n_jobs+1)]


    def my_cycles(self, job_id):
        # again, use new_xcycles, that's it
        slices = [slice(st, ed) for st, ed in zip(self.splits[:-1], self.splits[1:])]
        xda = self.new_xcycles.isel(cycles=slices[job_id])
        cycles_datetime = self.npdate2datetime(xda)
        return cycles_datetime


    def store_container(self):

        localtime = Timer()

        replay = FV3Dataset(path_in=self.cached_path, config_filename=self.config_filename)
        dds = self.create_container(ufsdataset=replay, new_time=self.new_xtime)

        localtime.start("Storing to zarr")
        store = NestedDirectoryStore(path=replay.data_path) if replay.is_nested else replay.data_path
        dds.to_zarr(store, compute=False, storage_options=self.storage_options, append_dim="time")
        localtime.stop()

        del dds
        if isdir(self.cache_storage(0)):
            rmtree(self.cache_storage(0), ignore_errors=True)


    def move_single_dataset(self, job_id, cycle):

        replay = FV3Dataset(path_in=self.cached_path, config_filename=self.config_filename)
        xds = replay.open_dataset(cycle, **self.ods_kwargs(job_id))

        all_time = xr.concat([self.xtime, self.new_xtime], dim="time")
        index = list(all_time.values).index(xds.time.values[0])
        tslice = slice(index, index+2)

        region = {
            "time": tslice,
            "pfull": slice(None, None),
            "grid_yt": slice(None, None),
            "grid_xt": slice(None, None),
        }
        region = {k : v for k,v in region.items() if k in xds.dims}

        replay.store_dataset(
            xds,
            region=region,
            storage_options=self.storage_options,
        )

        # This is a hacky way to clear the cache, since we don't create a filesystem object
        del xds
        if isdir(self.cache_storage(job_id)):
            rmtree(self.cache_storage(job_id), ignore_errors=True)

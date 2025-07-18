import os
import yaml
import logging
from typing import Optional
import fsspec

import xarray as xr

logger = logging.getLogger("ufs2arco")

class NOAAGribForecastData:
    """
    Generic access patterns for forecast datasets stored somewhere in Grib

    Classes that inherit this need their own:
        * :attr:`available_level` attribute / property
        * :meth:`_build_path` method
        * :attr:`static_vars`
        * :attr:`sample_dims`
        * :attr:`horizontal_dims`
        * :attr:`file_suffixes`
    """

    # fill these out per subclass (unique to base source)
    file_suffixes = tuple()

    @property
    def _fsname(self) -> str:
        """hrrr, gefs, or gfs"""

        if "gefs" in self.name.lower():
            return "gefs"
        elif "gfs" in self.name.lower():
            return "gfs"
        elif "hrrr" in self.name.lower():
            return "hrrr"
        else:
            raise NotImplementedError(f"ufs2arco.sources.NOAAGribForecastData could not recognize forecast system with name = {self.name}")

    @property
    def available_variables(self) -> tuple:
        return tuple(self._varmeta.keys())

    def __init__(
        self,
        variables: Optional[list | tuple] = None,
        levels: Optional[list | tuple] = None,
        use_nearest_levels: Optional[bool] = False,
        slices: Optional[dict] = None,
        accum_hrs: Optional[dict] = None,
    ) -> None:
        path = os.path.join(
            os.path.dirname(__file__),
            f"reference.{self._fsname}.yaml",
        )
        with open(path, "r") as f:
            self._varmeta = yaml.safe_load(f)

        # for accumulated variables
        if accum_hrs is not None:
            if len(self.fhr) > 1:
                dfhr = int(self.fhr[1] - self.fhr[0])
                for key, val in accum_hrs.items():
                    if val > dfhr:
                        raise ValueError(f"{self.name}: Cannot request 'accum_hrs' value that is greater than the forecast hour step (fhr: 'step'). Found accum_hrs['{key}'] = {val} which is greater than fhr['step'] = {dfhr}")
            else:
                for key, val in accum_hrs.items():
                    if val > self.fhr[0]:
                        raise ValueError(f"{self.name}: Cannot request 'accum_hrs' value that is greater than the forecast hour when asking for a single valued fhr. Found accum_hrs['{key}'] = {val} which is greater than fhr['start'] = {self.fhr[0]}")

        self._accum_hrs = accum_hrs

        super().__init__(
            variables=variables,
            levels=levels,
            use_nearest_levels=use_nearest_levels,
            slices=slices,
        )

    def _open_static_vars(self, dims) -> bool:
        """Do this once per t0, ensemble member"""
        cond = True
        for key, val in dims.items():
            if key != "t0":
                cond = cond and val == getattr(self, key)[0]
        return cond

    def _open_local(self, dims, file_suffix, cache_dir):

        path = self._build_path(
            **dims,
            file_suffix=file_suffix,
        )
        kw = {"s3": {"anon": True}} if "s3://" in path else {}
        try:
            local_file = fsspec.open_local(
                path,
                filecache={"cache_storage": cache_dir},
                **kw,
            )
        except:
            local_file = None
            logger.warning(
                f"{self.name}: Trouble finding the file: {path}\n\t" +
                f"dims = {dims}, file_suffix = {file_suffix}"
            )
        return local_file

    def open_sample_dataset(
        self,
        dims: dict,
        open_static_vars: bool,
        cache_dir: Optional[str] = None,
    ) -> xr.Dataset:

        # 1. cache the grib files for this date, member, fhr
        cached_files = {}
        for suffix in self.file_suffixes:
            path = self._build_path(
                **dims,
                file_suffix=suffix,
            )
            if cache_dir is not None:
                cached_files[suffix] = self._open_local(dims, suffix, cache_dir)
            else:
                cached_files[suffix] = path

        # 2. read data arrays from those files
        dsdict = {}
        osv = open_static_vars or self._open_static_vars(dims)
        variables = self.variables if osv else self.dynamic_vars
        we_got_the_data = all(val is not None for val in cached_files.values())
        if we_got_the_data:
            for varname in variables:
                dslist = []
                # Note that when there are 2 file suffixes, we always try to read from both
                # because sometimes (e.g. GFS humidity), the variable is in one, sometimes
                # it's in the other. This is more straightforward, and not "too bad".
                for suffix in self._varmeta[varname]["file_suffixes"]:
                    try:
                        thisvar = self._open_single_variable(
                            dims=dims,
                            varname=varname,
                            file=cached_files[suffix],
                        )
                    except:
                        thisvar = None
                    dslist.append(thisvar)
                dslist = [xds for xds in dslist if xds is not None]
                if len(dslist) == 1:
                    dsdict[varname] = dslist[0]
                elif len(dslist) > 1:
                    dsdict[varname] = xr.merge(dslist)
                else:
                    logger.warning(
                        f"{self.name}: Could not find {varname}, will stop reading variables for this sample\n\t" +
                        f"dims = {dims}, file_suffixes = {self._varmeta[varname]['file_suffixes']}"
                    )
                    dsdict = {}
                    break

        # the dataset is either full or completely empty if we had trouble
        xds = xr.Dataset(dsdict)
        if len(xds) > 0:
            xds = self.apply_slices(xds)
        return xds


    def _open_single_variable(
        self,
        dims: dict,
        varname: str,
        file: fsspec.spec.AbstractFileSystem,
    ) -> xr.DataArray:
        """
        Open a single variable from a GRIB file.

        Args:
            file (fsspec.spec.AbstractFileSystem): The file to read.
            varname (str): The variable name to extract.

        Returns:
            xr.DataArray: The extracted variable as an xarray DataArray.
        """
        fbk = self._varmeta[varname]["filter_by_keys"].copy()
        if self._accum_hrs is not None and varname in self._accum_hrs and dims["fhr"]>0:
            ahr = int(self._accum_hrs[varname])
            end = int(dims["fhr"])
            start = end - ahr
            stepRange = f"{start}-{end}"
            fbk.update({"stepRange": stepRange})
        try:
            xds = xr.open_dataset(
                file,
                engine="cfgrib",
                filter_by_keys=fbk,
                decode_timedelta=True,
            )
        except:
            logger.warning(f"{self.name}._open_single_variable: unable to read varname = {varname} at dims = {dims}")
            return None

        if "original_name" in self._varmeta[varname]:
            og = self._varmeta[varname]["original_name"]
            xds = xds.rename({og: varname})
            xds[varname].attrs["original_name"] = og
        xda = xds[varname]

        if "isobaricInhPa" in xds.coords:
            if len(xda.dims) < 3:
                vv = xda["isobaricInhPa"].values
                xda = xda.expand_dims({"isobaricInhPa": [vv]})

        if fbk["typeOfLevel"] == "heightAboveGround":
            if "original_name" in self._varmeta[varname]:
                level = fbk["level"]
                xda.attrs["long_name"] = f"{level} metre " + xda.long_name

        elif fbk["typeOfLevel"] == "surface":
            if self._varmeta[varname].get("original_name", "") == "t":
                xda.attrs["long_name"] += " at surface"

            if xda.attrs["GRIB_stepType"] == "accum":
                long_name_suffix = " accumulated over forecast"
                if self._accum_hrs is not None and varname in self._accum_hrs:
                    xda.attrs["accumulation_hours"] = int(self._accum_hrs[varname])
                    long_name_suffix = f" accumulated during previous {int(self._accum_hrs[varname])} hours of the forecast"
                xda.attrs["long_name"] += long_name_suffix

            elif xda.attrs["GRIB_stepType"] == "avg":
                xda.attrs["long_name"] = "Time-mean " + xda.attrs["long_name"]

        elif fbk["typeOfLevel"] in ("lowCloudLayer", "middleCloudLayer", "highCloudLayer"):
            full = fbk["typeOfLevel"].replace("CloudLayer", "")
            new = f"{full[0]}cc"
            xda.attrs["long_name"] = xda.long_name.replace("Total", full.capitalize())

        for v in [fbk["typeOfLevel"], "number"]:
            if v in xda.coords and v not in xda.dims:
                xda = xda.drop_vars(v)

        xds = xda.to_dataset(name=varname)
        for key, val in self.rename.items():
            if key in xds:
                xds = xds.rename({key: val})

        # always delete valid_time, since it's easier to just add it at the very end
        if "valid_time" in xds:
            xds = xds.drop_vars("valid_time")

        if varname in self.static_vars:
            for key in ["lead_time"]:
                if key in xds:
                    xds = xds.drop_vars(key)

            xds = xds.expand_dims("t0")
        else:

            # handle vertical levels
            if "level" in xds and self.levels is not None:
                level_selection = [l for l in self.levels if l in xds.level.values]
                if len(level_selection) == 0:
                    # we don't select vertical levels available in this file
                    return None
                xds = xds.sel(level=level_selection, **self._level_sel_kwargs)

            # handle potential ensemble member dimension
            # note that we do this first so that the dims work out in order:
            # t0, fhr, member, level, **horizontal_dims
            if "member" in dims:
                # Note that the description is only known to be true for GEFS...
                # but I'll just leave it for now
                xds = xds.expand_dims("member")
                xds["member"] = xr.DataArray(
                    [dims["member"]],
                    coords={"member": [dims["member"]]},
                    dims=("member",),
                    attrs={
                        "description": "ID=0 comes from gecXX files, ID>0 comes from gepXX files",
                        "long_name": "ensemble member ID",
                    },
                )

            # handle lead_time/fhr coordinates
            xds = xds.expand_dims(["t0", "lead_time"])
            xds["fhr"] = xr.DataArray(
                [int(lt / 1e9 / 3600) for lt in xds["lead_time"].values],
                coords=xds["lead_time"].coords,
                attrs={
                    "long_name": "hours since initial time",
                    "units": "integer hours",
                },
            )
            xds = xds.swap_dims({"lead_time": "fhr"})

        return xds[varname]


    def open_grib(
        self,
        dims,
        file_suffix,
        cache_dir,
        **kwargs,
    ) -> xr.Dataset:
        """
        Open a single GRIB file.

        Args:
            dims (dict): e.g. {"t0": "2020-01-01T00", "fhr": 0}
            file_suffix (str): e.g. "a", "b", "prs", etc
            cache_dir (str): path to caching the grib file
            kwargs: passed to xarray.open_dataset

        Returns:
            xr.Dataset: with the contents of the grib file, after some minimal postprocessing
        """

        file = self._open_local(dims, file_suffix, cache_dir)
        if file is None:
            return None

        if "decode_timedelta" not in kwargs:
            kwargs["decode_timedelta"] = True
        xds = xr.open_dataset(
            file,
            engine="cfgrib",
            **kwargs,
        )
        if "isobaricInhPa" in xds.coords:
            if len(xds.dims) < 3:
                vv = xds["isobaricInhPa"].values
                xds = xds.expand_dims({"isobaricInhPa": [vv]})

        for key, val in self.rename.items():
            if key in xds:
                xds = xds.rename({key: val})

        # handle potential ensemble member dimension
        # note that we do this first so that the dims work out in order:
        # t0, fhr, member, level, **horizontal_dims
        if "member" in dims:
            # Note that the description is only known to be true for GEFS...
            # but I'll just leave it for now
            xds = xds.expand_dims("member")
            xds["member"] = xr.DataArray(
                [dims["member"]],
                coords={"member": [dims["member"]]},
                dims=("member",),
                attrs={
                    "description": "ID=0 comes from gecXX files, ID>0 comes from gepXX files",
                    "long_name": "ensemble member ID",
                },
            )

        # handle lead_time/fhr coordinates
        xds = xds.expand_dims(["t0", "lead_time"])
        xds["fhr"] = xr.DataArray(
            [int(lt / 1e9 / 3600) for lt in xds["lead_time"].values],
            coords=xds["lead_time"].coords,
            attrs={
                "long_name": "hours since initial time",
                "units": "integer hours",
            },
        )
        xds = xds.swap_dims({"lead_time": "fhr"})

        # recreate valid_time, since it's not always there
        valid_time = xds["t0"] + xds["lead_time"]
        if "valid_time" in xds:
            xds["valid_time"] = xds["valid_time"].expand_dims(["t0", "fhr"])
            assert valid_time.squeeze() == xds.valid_time.squeeze()
            xds = xds.drop_vars("valid_time")

        xds["valid_time"] = valid_time
        xds = xds.set_coords("valid_time")

        return xds

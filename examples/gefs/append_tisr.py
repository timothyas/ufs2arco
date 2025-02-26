"""Use graphcast/solar_radiation to compute and append toa_incident_solar_radiation to the dataset"""

import logging
import xarray as xr

from graphcast import solar_radiation

from graphufs.log import setup_simple_log


if __name__ == "__main__":

    setup_simple_log()
    zarr_path = "/pscratch/sd/t/timothys/gefs/one-degree/forecasts.zarr"
    ds = xr.open_zarr(zarr_path)
    ds = ds.drop_vars([x for x in ds.data_vars])


    rename = {
        "valid_time": "datetime",
        "t0": "time",
        "pressure": "level",
        "latitude": "lat",
        "longitude": "lon",
    }
    ds = ds.rename(rename)

    ds["datetime"].load()
    logging.info(f"Loaded dataset:\n{ds}\n")
    ds["toa_incident_solar_radiation"] = solar_radiation.get_toa_incident_solar_radiation_for_xarray(
        data_array_like=ds.sel(fhr=0, member=0, drop=True),
        integration_period="6h",
    )

    for key, val in rename.items():
        if val in ds:
            ds = ds.rename({val: key})

    ds["toa_incident_solar_radiation"] = ds["toa_incident_solar_radiation"].chunk(
        {
            "t0": 1,
            "latitude": -1,
            "longitude": -1,
        },
    )

    ds["toa_incident_solar_radiation"].attrs = {
        "description": "computed from graphcast.solar_radiation",
        "integration_period": "6h",
        "units": "J/m^2",
    }

    logging.info(f"Computed TISR:\n{ds}\n")


    ds = ds.to_zarr(zarr_path, mode="a")
    logging.info(f"Appended to path: {zarr_path}")

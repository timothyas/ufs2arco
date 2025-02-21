import subprocess
import re
import zarr

def extract_unique_dates(log_output):
    date_pattern = re.compile(r'\(t0, member, fhr, key\) = (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
    unique_dates = set()

    for line in log_output:
        match = date_pattern.search(line)
        if match:
            unique_dates.add(match.group(1))

    return sorted(unique_dates)

def get_log_output():
    grep_command = "grep -A1 WARNING /global/cfs/cdirs/m4718/timothys/gefs/one-degree/logs/* | grep -v WARNING"
    result = subprocess.run(grep_command, shell=True, capture_output=True, text=True)
    return result.stdout.splitlines()

if __name__ == "__main__":
    log_output = get_log_output()
    unique_dates = extract_unique_dates(log_output)
    unique_dates = tuple(sorted(unique_dates))

    ds = zarr.open("/pscratch/sd/t/timothys/gefs/one-degree/forecasts.zarr", mode="r+")
    ds.attrs["missing_dates"] = unique_dates
    zarr.consolidate_metadata("/pscratch/sd/t/timothys/gefs/one-degree/forecasts.zarr")

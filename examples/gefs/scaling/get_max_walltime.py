import os
import re

def get_last_line(filepath):
    """Efficiently fetches the last line of a file."""
    with open(filepath, 'rb') as f:
        try:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
        except OSError:  # Handle small files
            f.seek(0)
        return f.readline().decode().strip()

def extract_walltime(line):
    """Extracts the first number in brackets from the line."""
    match = re.search(r'\[(\d+) s\]', line)
    return int(match.group(1)) if match else None

def find_max_walltime(directory):
    """Scans all files in the directory and returns the max walltime."""
    max_walltime = 0
    for root, _, files in os.walk(directory):
        for file in files:
            filepath = os.path.join(root, file)
            last_line = get_last_line(filepath)
            walltime = extract_walltime(last_line)
            if walltime is not None:
                max_walltime = max(max_walltime, walltime)
    return max_walltime

# Example usage:
if __name__ == "__main__":


    for directory in [
        "logs-01",
        "logs-01-again",
        "logs-02",
        "logs-02-again",
        "logs-04",
        "logs-04-again",
        "logs-2017",
        "logs-2018",
        "logs",
    ]:
        max_time = find_max_walltime(directory)
        print("Directory = ", directory, " Maximum walltime:", max_time, "seconds")

"""
This returns, note that 2017 and 2018 are the 8 node examples, and the last one is 2017-sept2020

Directory =  logs-01  Maximum walltime: 1240 seconds
Directory =  logs-01-again  Maximum walltime: 1520 seconds
Directory =  logs-02  Maximum walltime: 705 seconds
Directory =  logs-02-again  Maximum walltime: 683 seconds
Directory =  logs-04  Maximum walltime: 434 seconds
Directory =  logs-04-again  Maximum walltime: 470 seconds
Directory =  logs-2017  Maximum walltime: 308 seconds
Directory =  logs-2018  Maximum walltime: 338 seconds
Directory =  logs  Maximum walltime: 1210 seconds
"""

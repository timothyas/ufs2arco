# GEFSDataset

## One Degree data, some issues


The full run completed as expected, except for rank 401. These logs are in
"logs"

I tried to patch it up a few times, but this rank got stuck on batch number 117.
The failed patch attempts are logs-failed-patch-(01 & 02).
This is:
    * t0 = 2018-12-11T06
    * member 10
    * fhr 6


Then I just skipped this index, and everything ran perfectly (except that it
didn't get the last time stamps couple of time stamps 2020-09-23. this is how I
learned that they switched resolution in the middle of the day).

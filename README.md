## Tget - A download parallelization utility

Creates simultaneous connections to the resource host to accelerate download speeds 

Targeted for use on large files, some sample results below comparing time to download a 1GB .iso 
<pre>
firefox - 214s ( 4.7MB/s)
   wget - 178s ( 5.7MB/s)
   tget - 102s (10.0MB/s)
</pre>

### Installation
Tested on linux with Python 3.11 \
Windows/Mac functionality untested

Insert this into ~/.bashrc and reload the session
```
alias tget='python /path/to/your/tget.py'
```

tget can now be called like any other command line tool

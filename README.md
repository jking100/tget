## tGet - A download parallelization utility

Creates simultaneous connections to the resource host to accelerate download speeds 

Targeted for use on large files \
Testing on a 1gb iso image: 
<pre>
firefox - 214s ( 4.7MB/s)
   wget - 178s ( 5.7MB/s)
   tGet - 102s (10.0MB/s)
</pre>

### TODO

Package for distribution on PyPI

### Ez "Install" (terminal alias)

Store your script in a dependable location \
\>\> ~/.bashrc:
```
...
alias tget='python /path/to/your/tget.py'
...
```
 and reload the session

 ### Install
 mv /path/to/your/tget.py ~/bin/tget
 chmod +x ~/bin/tget

 reload shell

 usage tget -h

tget can now be used like most command line tools
To get started:

tget -h

Tested on: Python (3.11) in a linux enivironment
Functionality on Windows and macOS has not been tested.

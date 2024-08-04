# tget: a wget inspired clone
#
#
#
# Joseph King, Aug 2024

import sys
import argparse
import requests
import time
import random
import threading
from math import ceil

TGET_VER = "00" + "." + "00" + "." + "01"

def draw_error(error: str) -> None:
    print(f"tget: {error}")
    print(f"Usage: tget [OPTION]... [URL]...")
    print(f"")
    print(f"Try tget --help for more options.")

"""
        GNU Wget 1.20.3, a non-interactive network retriever.
        Usage: wget [OPTION]... [URL]...

        Mandatory arguments to long options are mandatory for short options too.

        Startup:
          -V,  --version                   display the version of Wget and exit
"""

def draw_help() -> None:
    print(f"Tget {TGET_VER}, a cli web download tool")
    print(f"Usage: tget [OPTION]... [URL]...")
    print(f"")
    print(f"General:")
    print(f"  -v, print Tget version and exit")
    print(f"  -h, display this help screen")

    print(f"Threads:")
    print(f"  -t, set number of download threads")

def download(url: str, start: int, end: int) -> requests.request: #worker that takes url and start and end byte and downloads the content hten returns its data
    headers = {"Range": f"bytes={start}-{end}"}
    response = requests.get(url, headers=headers)
    
    if(response.status_code not in [200,206]):
        print(f"status code: {response.status_code}")
        return response

    return response

def main() -> None:
    #draw_error("missing URL")
    #draw_help()

    #USAGE: tget [URL]... [OPTION]...
    parser = argparse.ArgumentParser(
                                prog='tget',
                                description='Downloads file from URL, utilizing threaded downloading',
                                epilog='Joseph King, 2024'
                                )
    parser.add_argument("URL", type=str, help="URL of resource to get")
    parser.add_argument('-t', dest='threads', default=1, type=int, help="Set number of download threads")
    parser.add_argument('-o', dest='output', default=".", metavar='OUTPUT FILE', type=str, help="Set location of download")
    parser.add_argument('-s', '--stats', action='store_true', help="Toggle download statistic output")
    parser.add_argument('-p', '--python', action='store_true', help="Toggle python info output")
    parser.add_argument('--version', action='version', version=f"Tget version: {TGET_VER}")
    args = parser.parse_args()        

    print("-" * 80)
    if(args.python):
        print(f"Python env.: {sys.executable} ({sys.version.split()[0]})")
    print(str(args))
    print("-" * 80)

    if(not args.URL): # Double checking for valid url at minimum
        print(f"URL Error")
        return None
    
    if (args.stats):
        start_time = time.perf_counter()
    
    #md5sum of this: b3215c06647bc550406a9c8ccc378756
    args.URL = 'http://ipv4.download.thinkbroadband.com/5MB.zip'

    chunksize = 512 * 1000

    header = requests.head(args.URL)
    if(header.headers['content-length']):
        print(f"Length (Byte): {header.headers['content-length']}")
    count = int(header.headers['content-length']) / chunksize
    print(ceil(count))

    index_for_download = []
    start = 0
    for i in range(ceil(count)):
        if(i == 0):
            index_for_download.append([start,start+chunksize])
        else:
            index_for_download.append([start+1,start+chunksize])
        start += chunksize
    index_for_download[-1][1] = int(header.headers['content-length'])
    print(index_for_download)

    bits = b''

    for i in index_for_download:
        response = download(args.URL, i[0], i[1])
        bits += response.content
    
    with open("./testing/parts.dwnl", "wb") as f:
        f.write(bits)
    
    print("End")
    return None



#    if(response.headers['content-length'] and args.threads != 1):
#        chunksize = float(response.headers['content-length']) / args.threads
#    else:
#        chunksize = 512 * 1000 #512kb
#    headers = {"Range": f"bytes=0-{chunksize}"}
#    response = requests.get(args.URL, headers=headers)

    
    if (args.stats and start_time):
        elapsed_time = time.perf_counter() - start_time
        print(f"\tTime: {elapsed_time:.2f}s")

    return None

if __name__ == "__main__":
    main()
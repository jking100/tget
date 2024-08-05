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
import concurrent.futures
from math import ceil
import re

TGET_VER = "00" + "." + "00" + "." + "02"

def generate_download_byte_indexes(chunksize: int, totalsize: int) -> list:
    count = ceil(int(totalsize) / float(chunksize))
    index_for_download = []
    start = 0
    for i in range(count):
        if(i == 0):
            index_for_download.append((start,start+chunksize, i))
        else:
            index_for_download.append((start+1,start+chunksize, i))
        start += chunksize
    index_for_download[-1] = (index_for_download[-1][0], int(totalsize), count - 1)
    return index_for_download

def download(url: str, start: int, end: int, id: int) -> requests.request: #worker that takes url and start and end byte and downloads the content hten returns its data
    print(f"{id} starting")
    headers = {"Range": f"bytes={start}-{end}"}
    response = requests.get(url, headers=headers)
    
    if(response.status_code not in [200,206]):
        print(f"{id} status code: {response.status_code}")
        return response

    print(f"{id} status code: {response.status_code}")
    return response

def get_args():
    parser = argparse.ArgumentParser(
                                prog='tget',
                                description='Downloads file from URL, utilizing threaded downloading',
                                epilog='Joseph King, 2024'
                                )
    parser.add_argument("URL", type=str, help="URL of resource to get")
    parser.add_argument('-t', dest='threads', default=8, type=int, help="Set number of download threads (1-16) [default: 8]")
    parser.add_argument('-o', dest='output', default=".", metavar='OUTPUT FILE', type=str, help="Set location of download")
    parser.add_argument('-s', '--stats', action='store_true', help="Toggle download statistic output")
    parser.add_argument('-p', '--python', action='store_true', help="Toggle python info output")
    parser.add_argument('--version', action='version', version=f"Tget version: {TGET_VER}")
    
    return parser.parse_args()

def main() -> int:
    args = get_args()        

    if(args.stats or args.python):
        print("-" * 80)
        if(args.python):
            print(f"Python env.: {sys.executable} ({sys.version.split()[0]})")
        if(args.stats):
            print(str(args))
        print("-" * 80)
    
    if (args.stats):
        start_time1 = time.perf_counter()
    
    args.URL = 'http://ipv4.download.thinkbroadband.com/5MB.zip' # b3215c06647bc550406a9c8ccc378756
    args.URL = 'http://ipv4.download.thinkbroadband.com/50MB.zip' # 2699c63cb6699b2272f78989b09e88b1
    regex = '[^\/\\&\?]+\.\w{3,4}(?=([\?&].*$|$))'
    x = re.search(regex,args.URL)
    if(x):
        args.output = f'./{x.group(0)}'
    else:
        print("Failed to grab file name from url, defaulting to tget-XX.dwnl")
        args.output = f'./tget-{random.randint(0,9)}{random.randint(0,9)}.dwnl'

    #check if output location is valid
    try:
        with open(args.output, 'wb') as file:
            pass
    except IOError as e:
        print("Error with output file location.")
        print(f"Error: {e}")
        return -1
    
    print("File: ",args.output)
    header = requests.head(args.URL)
    if (header.status_code not in (200, 206)):
        print(f"Error: {header.status_code}\n \
              URL: {args.URL}")
        return -1
        
    if(header.headers['content-length'] and args.stats):
        print(f"Size (Byte): {header.headers['content-length']} B")
        print(f"Size (MByte): {int(int(header.headers['content-length'])/float(1024*1024))} MB")

    if(args.threads not in range(1,17)):
        print("Error: Threads must be a value between (1-16)")
        return -1
    
    chunksize = int(int(header.headers['content-length']) / float(args.threads))
    
    
    chunkcount = args.threads

    work_list = generate_download_byte_indexes(int(chunksize), header.headers['content-length'])

    bits = b''

    if(args.stats):
        for i in work_list:
            print(f"{i[1]-i[0]} - {i}")

    data = [b''] * chunkcount

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(args.threads, 16)) as executor:
        future_to_download = {
            executor.submit(download, args.URL, start, end, id): (start, end, id) for start, end, id in work_list
            }
        
        for future in concurrent.futures.as_completed(future_to_download):
            _, _, id = future_to_download[future]
            data[id] = (future.result().content)

    with open(f"./testing/{args.output}", "wb") as f:
        for i in range(chunkcount):
            f.write(data[i])
        print("File wrote")
    
    if (args.stats and start_time1):
        elapsed_time = time.perf_counter() - start_time1
        print(f"\t       Time: {elapsed_time:.2f}s")
        #print(f"\tDownloading: {download_time:.2f}s ({(download_time/count):.2f}s/chunk)")
        #print(f"\t    Writing: {filewrite_time:.2f}s")

    return 1   

if __name__ == "__main__":
    main()
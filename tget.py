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

TGET_VER = "00" + "." + "00" + "." + "02"

def generate_download_byte_indexes(chunksize: int, totalsize: int, count: int) -> list:
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
    print(f"In download {start}")
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
    parser.add_argument('-t', dest='threads', default=1, type=int, help="Set number of download threads")
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
    
    #md5sum of this: b3215c06647bc550406a9c8ccc378756
    args.URL = 'http://ipv4.download.thinkbroadband.com/5MB.zip'

    header = requests.head(args.URL)
    if (header.status_code != (200|206)):
        print(f"Error: {header.status_code}\n \
              URL: {args.URL}")
        return -1
        
    if(header.headers['content-length']):
        print(f"Length (Byte): {header.headers['content-length']}")
    
    chunksize = 512 * 1000
    #chunksize = int(header.headers['content-length'])/5
    
    count = ceil(int(header.headers['content-length']) / chunksize)

    index_for_download = generate_download_byte_indexes(int(chunksize), header.headers['content-length'], count)

    bits = b''

    if(False):
        map_list = []
        for i in range(len(index_for_download)):
            map_list.append([args.URL, index_for_download[i][0], index_for_download[i][1]])

    for i in index_for_download:
        print(f"{i[1]-i[0]} - {i}")

    data = [b''] * count

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(count, 24)) as executor:
        future_to_download = {
            executor.submit(download, args.URL, start, end, id): (start, end, id) for start, end, id in index_for_download
            }
        
        for future in concurrent.futures.as_completed(future_to_download):

            _, _, id = future_to_download[future]
            #print(start)
            print(id)

            data[id] = (future.result().content)
            #print(url)

    if(False):
        for i in range(count):
            t = executor.submit(download, args.URL, 
                         index_for_download[i][0], 
                         index_for_download[i][1])
            if t.result().status_code not in [200,206]:
                print(f"Bad download {args.URL} {index_for_download[i][0]} {index_for_download[i][1]}")
                return None
            data[i] = t.result().content

    with open("./testing/parts.dwnl", "wb") as f:
        for i in range(count):
            f.write(data[i])
        print("File wrote")
    
            

    if (args.stats and start_time1):
        elapsed_time = time.perf_counter() - start_time1
        print(f"\t       Time: {elapsed_time:.2f}s")
        #print(f"\tDownloading: {download_time:.2f}s ({(download_time/count):.2f}s/chunk)")
        #print(f"\t    Writing: {filewrite_time:.2f}s")

    return 1   

    download_time = 0
    filewrite_time = 0

    for i in index_for_download:
        start_time = time.perf_counter()
        response = download(args.URL, i[0], i[1])
        elapsed_time = time.perf_counter() - start_time
        download_time += elapsed_time
        #print(f"\tTime: {elapsed_time:.2f}s")
        start_time = time.perf_counter()
        bits += response.content
        elapsed_time = time.perf_counter() - start_time
        filewrite_time += elapsed_time
    
    with open("./testing/parts.dwnl", "wb") as f:
        start_time = time.perf_counter()
        f.write(bits)
        elapsed_time = time.perf_counter() - start_time
        filewrite_time += elapsed_time
        print("File wrote")

    if (args.stats and start_time):
        elapsed_time = time.perf_counter() - start_time1
        print(f"\t       Time: {elapsed_time:.2f}s")
        print(f"\tDownloading: {download_time:.2f}s ({(download_time/count):.2f}s/chunk)")
        print(f"\t    Writing: {filewrite_time:.2f}s")

    return None    

if __name__ == "__main__":
    main()
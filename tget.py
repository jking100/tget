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

TGET_VER = "00" + "." + "00" + "." + "03"

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
    parser.add_argument('-t', dest='threads', default=4, type=int, help="Set number of download threads (1-10) [default: 4]")
    parser.add_argument('-o', dest='output', default=".", metavar='OUTPUT FILE', type=str, help="Set location of download")
    parser.add_argument('--md5', dest='md5', default=None, type=str, help="Check download against source md5 checksum")
    parser.add_argument('--version', action='version', version=f"Tget version: {TGET_VER}")
    
    return parser.parse_args()

class thread_worker: #an object that knows only how to open http connection and then write those bytes into a given file object, intended to be called as a subthread
    
    def __init__(self, url: str, start: int, end: int, thread_id: int, thread_lock, file):
        self.url = url
        self.start = start
        self.end = end
        self.thread_id = thread_id
        self.thread_lock = thread_lock
        self.file = file
        self.content = b'' * (end-start)

    def execute(self) -> int:
        headers = {"Range": f"bytes={self.start}-{self.end}"}
        response = requests.get(self.url, headers=headers)

        if(response.status_code not in [200,206]):
            return response.status_code
                
        with self.thread_lock:
            self.file.seek(self.start)
            self.file.write(response.content)

        return response.status_code

    def get_content(self):
        return self.content

def execute_thread_workers(url, start, end, thread_id, thread_lock, file):
    #url, start, end, thread_id, thread_lock, file = zip(*worker_instructions)

    print("Starting: ", thread_id)
    worker = thread_worker(url, start, end, thread_id, thread_lock, file)
    return worker.execute()

def main() -> int:
    args = get_args()        
    
    start_time_main = time.perf_counter()
    
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
        
    if(header.headers['content-length']):
        print(f"Size (Byte): {header.headers['content-length']} B")
        print(f"Size (MByte): {int(int(header.headers['content-length'])/float(1024*1024))} MB")

    if(args.threads not in range(1,11)):
        print("Error: Threads must be a value between (1-10)")
        return -1
    
    chunksize = ceil(int(header.headers['content-length']) / float(args.threads))
    
    
    chunkcount = args.threads

    work_list = generate_download_byte_indexes(int(chunksize), header.headers['content-length'])

    bits = b''


    for i in work_list:
        print(f"{i} [{i[1]-i[0]}]B")

    data = [b''] * chunkcount

    with open(f"./testing/{args.output}", "wb") as file:
        #for file writing with mutliple threads targeting same file
        thread_lock = threading.Lock()

        worker_instructions = []
        for i in range(args.threads):
            #url, start, end, thread_id, thread_lock, file
            worker_instructions.append(
                                        (args.URL, 
                                        work_list[i][0], #start
                                        work_list[i][1], #end
                                        work_list[i][2], #id
                                        thread_lock,
                                        file)                        
            )
        #for i in worker_instructions:
        #    print(i)
        
    #init
    #open file object
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
            task_dict = { 
                executor.submit(
                    execute_thread_workers, 
                    args.URL, start, end, thread_id, thread_lock, file
                    ): (start, end, thread_id) 
                    for _, start, end, thread_id, _, _ in worker_instructions
            }            
            
            for task in concurrent.futures.as_completed(task_dict):
                _, _, id = task_dict[task]
                if task.done:
                    print(f"terminate: {id} - {task.result()}")
    
    elapsed_time_main = time.perf_counter() - start_time_main
    print(f"\tGlobal Time: {elapsed_time_main:.2f}s")
        #print(f"\tDownloading: {download_time:.2f}s ({(download_time/count):.2f}s/chunk)")
        #print(f"\t    Writing: {filewrite_time:.2f}s")

    return 1   

if __name__ == "__main__":
    main()
    import resource; print(f"Max Mem Usage (MB): {int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}")
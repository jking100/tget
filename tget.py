#
# Tget: a wget inspired clone
#
# todo: implement checksum verification option, code could use a few comments
# 
# flow: get and verify args, check global connection and retreive file info, 
#           create list of download byte ranges per thread, spool up worker 
#           threads and distribute work. Workers make partial http GET requests,
#           request is done in streaming mode in chunks, workers wait for file
#           lock to release before indexing into file at proper location and 
#           writing by chunks. File is written in any order depending on what 
#           workers have completed filling their stream. Main thread waits for 
#           all workers to return ok http responses, if a worker has an error
#           a stop signal is sent to all threads and file is deleted then exit.
#           Otherwise downlaod time and stats are displayed on exit
#           
# Joseph King, Aug 2024

import argparse
import requests
from time import perf_counter
from random import randint
import threading
import concurrent.futures
from math import ceil
from re import match
from pathlib import Path
import hashlib


TGET_VER = "01" + "." + "01"

def generate_thread_byte_indexes(threads: int, totalsize: int) -> list:
    byte_portion = ceil(totalsize / float(threads))
    count = ceil(totalsize / float(byte_portion))
    thread_byte_index = []
    start = 0
    for i in range(count):
        if(i == 0):
            thread_byte_index.append((i, start, start+byte_portion))
        else:
            thread_byte_index.append((i, start+1, start+byte_portion))
        start += byte_portion
    thread_byte_index[-1] = (count-1, thread_byte_index[-1][1], totalsize)
    #for i in thread_byte_index: print(i)
    return thread_byte_index

def get_args():
    parser = argparse.ArgumentParser(
                                prog='tget',
                                description='A parallel download acceleration utility',
                                )
    parser.add_argument("URL", type=str, help="URL of resource to get")
    parser.add_argument('-t', dest='threads', default=4, type=int, help="Set number of download threads (1-10) [default: 4]")
    parser.add_argument('-o', dest='output', default=None, metavar='OUTPUT FILE', type=str, help="Set location of download")
    parser.add_argument('--checksum', dest='sha', default=None, type=str, help="Check download against source sha256 checksum")
    parser.add_argument('--version', action='version', version=f"Tget v{TGET_VER} - A parallel download acceleration utility (Joseph King, 2024)")
    
    return parser.parse_args()

class thread_worker: #an object that knows only how to open http connection and then write those bytes into a given file object, intended to be called as a subthread
    
    def __init__(self, url: str, start: int, end: int, thread_id: int, thread_lock, file, stop_work):
        self.url = url
        self.start = start
        self.end = end
        self.thread_id = thread_id
        self.thread_lock = thread_lock
        self.file = file
        self.cursor_offset = 0
        self.stop_work = stop_work

    def execute(self) -> int:
        headers = {"Range": f"bytes={self.start}-{self.end}"}
        response = requests.get(self.url, headers=headers, stream=True)

        #if(self.thread_id == 2): response.status_code = 201
        
        if(response.status_code not in [200,206]):
            print(f"\tt{self.thread_id} {response.status_code} fail")
            return response.status_code
        print(f"    t{self.thread_id} {response.status_code} ok")
                
        #1mb seems to be pretty good comparing file ops/mem use. None=unlimit http repsonse size (MAX MEM usually)
        for i in response.iter_content(chunk_size=1024*1024, decode_unicode=False):
            if self.stop_work.is_set(): return -1
            with self.thread_lock:
                self.file.seek(self.start+self.cursor_offset)
                self.file.write(i)
                self.cursor_offset = self.file.tell()-self.start

        return response.status_code

def execute_thread_workers(url, start, end, thread_id, thread_lock, file, stop_work):
    worker = thread_worker(url, start, end, thread_id, thread_lock, file, stop_work)
    return worker.execute()

def check_sha256(file, checksum: str) -> bool:
    #2dce83fbc71ddffac53b37c484088fa2334f39641fa0d9ca6516fd0f656dac2a
    digest = hashlib.file_digest(file, "sha256")
    file_checksum = digest.hexdigest()

    return True if (file_checksum == checksum) else False

def main() -> int:
    args = get_args()        
    
    start_time_main = perf_counter()

    #These blocks should probably be functioned off since they are basically
    #   just input validation and checking the web for responses
    ##################################################################
    if(args.threads not in range(1,11)):
        print("Error: Threads must be a value between (1-10)")
        return -1
    ##################################################################
    url_parts = args.URL.split("/")
    name = url_parts[-1]
    regex = r"^([\w\.-]+)"
    x = match(regex,name)
    if(not x):
        print("Warn: Failed to parse filename, defaulting to tget-{0-9}.dwnl")
        args.output = f'./tget-{randint(0,9)}.dwnl'
    if args.output == None:
        args.output = name
    ##################################################################
    #check if output location is valid
    args.output = Path().resolve() / args.output
    try:
        with open(args.output, 'wb') as file:
            pass
    except IOError as e:
        print("Error: Output file location.")
        print(f"\t{e}")
        return -1
    
    ##################################################################
    
    print("Connecting to", args.URL)
    ##################################################################
    header = requests.head(args.URL)
    if (header.status_code not in (200, 206)):
        print(f"Error: {header.status_code}")
        return -1
    if (not header.headers['content-length'] or not header.headers['content-type']):
        print("Error with HTTP response: Failed to retreive file info")
        return -1
    ##################################################################
    
    print(f"Connection ok {header.status_code}")  
    print(f"Size: {int(header.headers['content-length'])/1024:.0f}KB ", end='')
    print(f"{int(header.headers['content-length'])/(1024*1024):.0f}MB ", end='')
    print(f"[{header.headers['content-type']}]")
    print(f"Saving to: '{args.output}'")

    ############################################################################

    try:
        with open(args.output, "wb") as file:
            #for file writing with mutliple threads targeting same file
            thread_lock = threading.Lock()
            stop_work = threading.Event()
            is_download_ok = True
            
            thread_byte_index = generate_thread_byte_indexes(args.threads, int(header.headers['content-length']))

            with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as executor:
                print(f"\nDownloading ({args.threads} threads)")
                task_dict = { 
                    executor.submit(
                        execute_thread_workers, 
                        args.URL, start, end, thread_id, thread_lock, file, stop_work
                        ): (thread_id, start, end) 
                        for thread_id, start, end in thread_byte_index
                }            

                for task in concurrent.futures.as_completed(task_dict):
                    id, _, _ = task_dict[task]
                    if task.result() not in (200, 206):
                        stop_work.set()
                        print(f"\nDownload Failed - `{args.output}` Connection error [{task.result()}]")
                        with thread_lock:
                            print("Deleting")
                            Path.unlink(args.output, missing_ok=True)
                        is_download_ok = False
                        break

            if not is_download_ok:
                return -1

            elapsed_time_main = perf_counter() - start_time_main
            print(f"\nDownload Complete - `{args.output}` in {elapsed_time_main:.1f}s @ {int(header.headers['content-length'])/float(1024*1024*elapsed_time_main):.1f}MB/s")

    except Exception as e:
        print(f"File Error: {e}")
        return -1
    
    if(args.sha):
        try:
            with open(args.output, "rb") as file:
                if(not check_sha256(file, args.sha)):
                    print(f"Checksum verification - fail")
                else:
                    print(f"Checksum verification - pass")

        except Exception as e:
            print("Checksum verify:")
            print(f"File Error: {e}")
            return -1
    
    return 0


if __name__ == "__main__":
    main()

    #used for testing memory usage varying the chunksize of the http request in streaming mode
    #seems that mem uses matches file size closely with chunsize=None or very large(>content-size/threads)
    #with 1mb chunks seems mem usage is 40-50mb regardless
    #with 1kb chunks seems mem usage is around 30 with slight decrease in speed
    #chunk size should be more or less directly proportional to the total number of times our threads will have to potentially switch file writing
    
    #import resource; print(f"Max Mem Usage (MB): {int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}")
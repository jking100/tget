#!/usr/bin/env python3

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

# current issues:
# fails to write gzip? content to the disk. seems to download it just fine

#todo
#make/rewrite existing worker manager function so it handles more of the logic automatically
#re work error handling

import argparse
import requests
import time
import random
import threading
import concurrent.futures
from math import ceil
from re import match
from pathlib import Path
import hashlib


TGET_VER = "01" + "." + "01"

def get_args():
    parser = argparse.ArgumentParser(
                                prog='tget',
                                description='A parallel download acceleration utility',
                                )
    parser.add_argument("URL", type=str, help="")
    parser.add_argument('-t', dest='threads', metavar='[1-8]', default=4, type=int, choices=range(1,9), help="Set number of download threads (default: 4)")
    parser.add_argument('-o', dest='output', default=None, metavar='FILE', type=str, help="write download to FILE")
    parser.add_argument('--sha256', dest='sha', metavar='', default=None, type=str, help="Check download against given sha256 checksum")
    parser.add_argument('--version', action='version', version=f"Tget v{TGET_VER} - A parallel download acceleration utility (Joseph King, 2024)")
    
    return parser.parse_args()

def validate_input(args): #checks all arguments for validity
    # return Tuple("Error String", Boolean(Abort_Main), HttpResponseheader)
    #check url, threads, output, and sha (64 char long)

    ##################################################################
    #Check URL
    print(f"Checking connection to `{args.URL}`")
    header = requests.head(args.URL)
    if (header.status_code not in (200, 206)):
        return (f"Connection Failure: {header.status_code}", True)
    if (not header.headers['content-length'] or not header.headers['content-type']):
        return (f"Resource Failure: Failed to retrieve necessary file info", True)
    print(" "*2 + f"Connection ok {header.status_code}")

    if (int(header.headers['content-length']) < (1024**2)):
        print(" "*2 + f"Size: {int(header.headers['content-length'])/1024:.0f}KB ", end='')
    elif (int(header.headers['content-length']) < (1024**3)):
        print(f"{int(header.headers['content-length'])/(1024**2):.0f}MB ", end='')
    else:
        print(f"{int(header.headers['content-length'])/(1024**3):.0f}GB ", end='')
    print(f"[{header.headers['content-type']}]")

    ##################################################################
    #threads are checked by argparse object in its definition

    ##################################################################
    #Check output file path if given, else default to basic from url

    final_file_path = None
    if (args.output): #user specified FILE path
        final_file_path = Path(args.output)
    else: #no user specification
        #regex the url to get the file name
        url_parts = args.URL.split("/")
        file_name = url_parts[-1]
        if(not match(r"^([\w\.-]+)", file_name)):
            print("Warning: Failed to retrieve filename, defaulting to tget-{date}.dwnl")
            date = header.headers["Date"].split()[2] + header.headers["Date"].split()[1]
            file_name = f'tget-{date}.dwnl'

        final_file_path = Path(Path().resolve(), Path(file_name)) #should be windows compatible
    
    #overwrite args.output with final_file_path so args.output is now String -> Path()
    args.output = final_file_path
    #print("-"*80 + f"\nDEBUG: {args.output}\n" + "-"*80)

    #check if file can be opened
    print(f"Testing file output to `{args.output}`")
    try:
        with open(args.output, 'wb') as file:
            pass
    except IOError as e:
        return (f"Error: {str(e)[10:]}", True)
    
    print(" "*2 + "File output okay")

    ##################################################################
    #Check SHA is 64 Chars
    if(args.sha):
        if (len(args.sha) != 64):
            args.sha = "INVALID"
            print("WARN: Invalid checksum, disabling verification")

    return (f"\nInitializing download | {args.threads} threads", False, header)

class stopwatch:
    def __init__(self):
        self.start_time = time.perf_counter()

    def time_elapsed(self):
        return time.perf_counter() - self.start_time
    
class thread_manager:
    def __init__(self, header, file_path, url, threads):
        self.workers: thread_worker = []
        self.file_path = file_path
        self.url = url
        self.threads = threads
        self.file_size = int(header.headers['content-length'])
        self.results = []

    def _generate_thread_byte_indexes(self, threads: int, totalsize: int) -> list:

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

    def _execute_thread_workers(self, url, start, end, thread_id, thread_lock, file, stop_work):
        worker = thread_worker(url, start, end, thread_id, thread_lock, file, stop_work)
        return worker.execute()
    
    def start_download(self):
        #init connection

        try:
            with open(self.file_path, "wb") as file:
                #for file writing with mutliple threads targeting same file
                thread_lock = threading.Lock()
                stop_work = threading.Event()
                is_download_ok = True
                
                thread_byte_index = self._generate_thread_byte_indexes(self.threads, self.file_size)

                with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
                    print(f"\nDownloading ({self.threads} threads)")
                    task_dict = { 
                        executor.submit(
                            self._execute_thread_workers, 
                            self.url, start, end, thread_id, thread_lock, file, stop_work
                            ): (thread_id, start, end) 
                            for thread_id, start, end in thread_byte_index
                    }            

                    for task in concurrent.futures.as_completed(task_dict):
                        id, _, _ = task_dict[task]
                        if task.result() not in (200, 206):
                            stop_work.set()
                            print(f"\nDownload Failed: Connection error [{task.result()}]")
                            with thread_lock:
                                print("Deleting")
                                Path.unlink(self.file_path, missing_ok=True)
                            is_download_ok = False
                            break

                if not is_download_ok:
                    return -1
                return 0
                
        except Exception as e:
            print(f"thread_manager::start_download(): {e}")
            return -1

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
            print(f"  t{self.thread_id} {response.status_code} fail")
            return response.status_code
        print(f"  t{self.thread_id} {response.status_code} ok")
                
        #1mb seems to be pretty good
        for i in response.iter_content(chunk_size=1024**2, decode_unicode=False):
            if self.stop_work.is_set(): return -1
            with self.thread_lock:
                self.file.seek(self.start+self.cursor_offset)
                self.file.write(i)
                self.cursor_offset = self.file.tell()-self.start

        return response.status_code

def main() -> int:
    args = get_args()  

    validation_msg, is_error, header = validate_input(args)
    print(validation_msg)
    if (is_error):
        return -1
    
    overall_timer = stopwatch()

    ############################################################################
    #input is good, call the manager to spool up the threads
    #manager will handle returning the info of the download
    manager = thread_manager(header, args.output, args.URL, args.threads)
    manager.start_download()


    total_time = overall_timer.time_elapsed()
    print(f"\nDownload Complete - `{args.output}` in {total_time:.1f}s @ {int(header.headers['content-length'])/float(1024*1024*total_time):.1f}MB/s")


    ########################
    if(args.sha != None):
            try:
                with open(args.output, "rb") as file:
                    file_checksum = hashlib.file_digest(file, "sha256").hexdigest()
                    print(f"Checksum `{args.output}`: {file_checksum}")
                    if(args.sha != "INVALID"):
                        if(file_checksum != args.sha):
                            print(f"Checksum Verification - fail")
                        else:
                            print(f"Checksum Verification - pass")

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
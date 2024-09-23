#!/usr/bin/env python3

# Tget: a wget inspired clone
#
# todo: implement checksum verification option, code could use a few comments
# 
# flow: get and verify args, check global connection and retrieve file info, 
#           create list of download byte ranges per thread, spool up worker 
#           threads and distribute work. Workers make partial http GET requests,
#           request is done in streaming mode in chunks, workers wait for file
#           lock to release before indexing into file at proper location and 
#           writing by chunks. File is written in any order depending on what 
#           workers have completed filling their stream. Main thread waits for 
#           all workers to return ok http responses, if a worker has an error
#           a stop signal is sent to all threads and file is deleted then exit.
#           Otherwise download time and stats are displayed on exit
#           
# Joseph King, Aug 2024

# current issues:
# fails to write gzip? content to the disk. seems to download it just fine

#todo
#
# Add progress bar for the download, bonus points if it differentiates threads


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


TGET_VER = "01" + "." + "04"

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
    try:
        header = requests.head(args.URL)
    except Exception as e:
        return (f"Connection Failure: {e}", True, None)
    if (header.status_code not in (200, 206)):
        return (f"Connection Failure: {header.status_code}", True, None)
    if (not header.headers['content-length'] or not header.headers['content-type']):
        return (f"Resource Failure: Failed to retrieve necessary file info", True, None)
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
        return (f"Error: {str(e)[10:]}", True, None)
    
    print(" "*2 + "File output okay")

    ##################################################################
    #Check SHA is 64 Chars
    if(args.sha):
        if (len(args.sha) != 64):
            args.sha = "INVALID"
            print("WARN: Invalid checksum, disabling verification")

    return (f"\nInitializing download | {args.threads} threads\n", False, header)
    
class thread_manager:
    def __init__(self, header, file_path, url, threads):
        self.workers: thread_worker = []
        self.url = url
        self.threads = threads
        self.file_size = int(header.headers['content-length'])
        self.file_path = file_path
        try:
            self.file = open(self.file_path, "wb")
        except Exception as e:
            print(f"Thread Manager init: {e}")

        self.total_time_download = 0
        self.file_prog = 0
        self.prog_time_log = [0]*5
        self.results = [0]
        self.worker_log = [0 for i in range(8)]
        self.start_time_download = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.file.close()
        #print(self.worker_log)

    def worker_make_report(self, worker_id, progress: float):
        self.worker_log[worker_id] = progress

    def _generate_thread_byte_indexes(self, threads: int, total_size: int) -> list:

        byte_portion = ceil(total_size / float(threads))
        thread_byte_index = []
        start = 0
        for i in range(threads):
            if(i == 0):
                thread_byte_index.append((i, start, start+byte_portion))
            else:
                thread_byte_index.append((i, start+1, start+byte_portion))
            start += byte_portion
        thread_byte_index[-1] = (threads-1, thread_byte_index[-1][1], total_size)
        return thread_byte_index

    def _progressbar(self, total, path):
        time.sleep(.1)
        #[### 7 ############|#################|##################|#################] 100%
        bar = "## # #############|#################|##################|#################"
        bar_len = len(bar)

        #size = Path(path).stat().st_size - (total-(total/self.threads))
        #prog = size/float(total/self.threads)

        indiv = ""
        if sum(self.worker_log) >= self.threads:
            for i in range(self.threads):  
                write_bar = f"[{bar[0:3]}{i}{bar[4:]}]"
                indiv += f"{write_bar} 100%" + ('\n' if i != self.threads-1 else '')
                #move_back = '\033[1F' * self.threads
                self.file_prog = 1
        else:
            for i in range(self.threads):   
                #print('\033[2F')
                prog = int(self.worker_log[i]*100)
                bar = bar[0:3] + str(i) + bar[4:]
                slice_stop = 1 + int(prog/float(100) * bar_len) 
                write_bar = f"[{bar[0:slice_stop]}{'-'*(bar_len-slice_stop)}]"
                indiv += f"{write_bar} {int(self.worker_log[i]*100)}%" + ('\n' if i != self.threads-1 else '')
                #move_back = '\033[1F' * self.threads
                self.file_prog = sum(self.worker_log)/float(self.threads)

        now = time.perf_counter() - self.start_time_download
        est_total = now / (self.file_prog + .01)
        t_remain = (est_total) - now

        curr_mbps = (self.file_prog*self.file_size)/float(1024**2)/now 
        avg_mbps = ((sum(self.prog_time_log) / float(len(self.prog_time_log))) * .2) + (curr_mbps * .8)
        self.prog_time_log.pop(0)
        self.prog_time_log.append(avg_mbps)

        #print(str(now - self.prog_time_log[-1][0]))
        # [### 0 ############|##################|##################|##########--------] 100%
        print('\033[1F' * (self.threads+1) + indiv + f"\n[{now:.0f}s elapsed] [{t_remain:.0f}s remain] [{avg_mbps:.1f} MB/s]{' '*10}", flush=True)

    def _execute_thread_workers(self, url, start, end, thread_id, thread_lock, file, stop_work, boss):
        worker = thread_worker(url, start, end, thread_id, thread_lock, file, stop_work, boss)
        return worker.execute()
    
    def start_download(self):
        self.start_time_download = time.perf_counter()

        #for file writing with multiple threads targeting same file
        thread_lock = threading.Lock()
        stop_work = threading.Event()
        boss = self
        abortFlag = False
        
        thread_byte_index = self._generate_thread_byte_indexes(self.threads, self.file_size)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.threads) as executor:
            futures = []
            for _, (thread_id, start, end) in enumerate(thread_byte_index):
                #print(thread_id, start, end)
                futures.append(
                    executor.submit(self._execute_thread_workers, 
                                self.url,
                                start,
                                end,
                                thread_id,
                                thread_lock,
                                self.file,
                                stop_work,
                                boss))
                
            processed = set()
            done = set()
            total_file_size = thread_byte_index[-1][2]

            while(len(done) < self.threads):
                done, not_done = concurrent.futures.wait(futures, 1)

                for i in done.difference(processed):
                    processed.add(i)
                    if i.result() not in (200, 206):
                        stop_work.set()
                        print(f"\nDownload Failed: Connection error [{i.result()}]")
                        abortFlag = True
                        self.threads = -1 #negate self.threads to exit while asap
                        break

                self._progressbar(total_file_size, self.file_path)

        if abortFlag: # ABORT
            return -1
        
        #COMPLETE
        self.total_time_download = time.perf_counter() - self.start_time_download

        return 0
    
class thread_worker: #an object that knows only how to open http connection and then write those bytes into a given file object, intended to be called as a subthread
    
    def __init__(self, url: str, start: int, end: int, thread_id: int, thread_lock, file, stop_work, boss):
        self.url = url
        self.start = start
        self.end = end
        self.thread_id = thread_id
        self.thread_lock = thread_lock
        self.file = file
        self.cursor_offset = 0
        self.stop_work = stop_work
        self.boss = boss

    def execute(self) -> int:
        headers = {"Range": f"bytes={self.start}-{self.end}"}
        response = requests.get(self.url, headers=headers, stream=True)
        
        if(response.status_code not in [200,206]):
            print(f"  t{self.thread_id} {response.status_code} fail")
            return response.status_code
        print(f"  t{self.thread_id} {response.status_code} ok")
                
        #1mb seems to be pretty good
        for i in response.iter_content(chunk_size=1024**2, decode_unicode=False):
            if self.stop_work.is_set(): return -1
            #time.sleep(.2) if self.thread_id != 0 else time.sleep(2)
            with self.thread_lock:
                self.file.seek(self.start+self.cursor_offset)
                self.file.write(i)
                self.cursor_offset = self.file.tell()-self.start
            ##sussyVV
            prog = self.cursor_offset/float(self.end - self.start)
            self.boss.worker_make_report(self.thread_id, prog)

        return response.status_code

def main() -> int:
    args = get_args()  

    validation_msg, is_error, header = validate_input(args)
    print(validation_msg)
    if (is_error):
        return -1
    
    ############################################################################
    #input is good, call the manager to spool up the threads
    #manager will handle returning the info of the download
    total_time_download = None

    with thread_manager(header, args.output, args.URL, args.threads) as boss:
        boss.start_download()
        total_time_download = boss.total_time_download

    print(f"\nDownload Complete - `{args.output}` in {total_time_download:.0f}s @ {int(header.headers['content-length'])/float(1024**2*total_time_download):.1f}MB/s")

    ########################
    if(args.sha != None):
        try:
            with open(args.output, "rb") as file:
                file_checksum = hashlib.file_digest(file, "sha256").hexdigest()
                print(f"Checksum `{args.output}`: {file_checksum}")
                if(args.sha != "INVALID"):
                    print("Checksum Verification -", "pass" if file_checksum == args.sha else "fail")

        except Exception as e:
            print("Error: Failed to generate file checksum")
            print(f"Error: {e}")

    return 0

if __name__ == "__main__":
    main()

    #used for testing memory usage varying the chunksize of the http request in streaming mode
    #seems that mem uses matches file size closely with chunksize=None or very large(>content-size/threads)
    #with 1mb chunks seems mem usage is 40-50mb regardless
    #with 1kb chunks seems mem usage is around 30 with slight decrease in speed
    #chunk size should be more or less directly proportional to the total number of times our threads will have to potentially switch file writing
    
    #import resource; print(f"Max Mem Usage (MB): {int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}")
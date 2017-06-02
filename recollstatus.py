#!/usr/bin/env python

from __future__  import print_function
import errno
import os
import shutil
import datetime
import collections
import argparse
import logging

def recollindex_running(pid_filepath):
    # Example PID file path: ~/.recoll/index.pid
    try:
        pid_file = open(pid_filepath)
    except IOError as e:
        if e.errno == 2:
            logging.error("Could not find 'index.pid' at {}\n".format(pid_filepath))
        else:
            logging.error("Could not open 'index.pid' at {}\n".format(pid_filepath))
        raise

    recoll_pid_string = pid_file.read()
    if recoll_pid_string == '':
        return False

    try:
        recoll_pid = int(recoll_pid_string)
    except ValueError:
        logging.error("Not a valid process ID: {}\n".format(recoll_pid_string))
        raise

    try:
        os.kill(recoll_pid, 0)
    except OSError as e:
        if e.errno == errno.ESRCH:
            logging.warning("{} has process ID {}, but no process with that ID is running.\n".format(pid_filepath, recoll_pid_string))
            return False
        else:
            raise

    return True

def latest_query(history_path):
    now = datetime.datetime.now()
    if os.path.isfile(history_path):
        history_timestamp = os.path.getmtime(history_path)
        date_last_query = datetime.datetime.fromtimestamp(history_timestamp)
    else:
        return None, now

    return date_last_query, now

def running_time(flintlock_path):
    if os.path.isfile(flintlock_path):
        flintflock_timestamp = os.path.getmtime(flintlock_path)
        now = datetime.datetime.now()
        date_recollindex_started = datetime.datetime.fromtimestamp(flintflock_timestamp)
    return date_recollindex_started, now

def since_last_run(idxstatus_path):
    if os.path.isfile(idxstatus_path):
        idxstatus_timestamp = os.path.getmtime(idxstatus_path)
        now = datetime.datetime.now()
        date_recollindex_last_started = datetime.datetime.fromtimestamp(idxstatus_timestamp)
    return date_recollindex_last_started, now

def write_tempfile(fp, prefix):
    import tempfile
    temp = tempfile.NamedTemporaryFile(prefix=prefix, delete=False)
    logging.info("Copying {} to {}\n".format(fp.name, temp.name))
    fp.seek(0)
    temp.file.write(fp.read())
    temp.close()

def parse_idxstatus(idxstatus_path, write_tempfiles=True):
    idxstatus = collections.OrderedDict()

    with open(idxstatus_path) as idxstatus_fp:
        text = idxstatus_fp.read()
    text_wrapped = text.replace('\\\n', '')
    for line in text_wrapped.splitlines():
        try:
            key, val = (x.strip() for x in line.split('=', 1))
        except ValueError:
            logging.error("Cannot parse line: {}\n".format(line))
            if write_tempfiles:
                # If the parsing the idxstatus file fails,
                # keep a copy of it for later debugging.
                write_tempfile(idxstatus_fp, prefix="idxstatus")
            raise

        idxstatus[key] = val

    if idxstatus['phase'] in [0, 4, 5]:
        # Don't have examples of these to test with yet.
        write_tempfile(idxstatus_fp, prefix="idxstatus")

    return idxstatus

def format_idxstatus(idxstatus):
    DbIxStatus = {
        '0' : "DBIXS_NONE",
        '1' : "DBIXS_FILES",
        '2' : "DBIXS_PURGE",
        '3' : "DBIXS_STEMDB",
        '4' : "DBIXS_CLOSING",
        '5' : "DBIXS_MONITOR",
        '6' : "DBIXS_DONE",
    }
    formatted = ['DbIxStatus is {}: {}'.format(idxstatus['phase'], DbIxStatus[idxstatus['phase']])]
    # https://bitbucket.org/medoc/recoll/src/dabc5bae1dd7f8b5049ef021c441ffb8050cd7eb/src/index/indexer.h?at=default&fileviewer=file-view-default#indexer.h-40
    descriptors = collections.OrderedDict()
    descriptors['docsdone'] = 'Documents updated:'
    descriptors['filesdone'] = 'Files tested:'
    descriptors['filerrors'] = 'Failed files:'
    descriptors['totfiles'] = 'Total files in index:'
    descriptors['dbtotdocs'] = 'Starting number of indexed documents:'
    for field, description in descriptors.items():
        if field in idxstatus:
            formatted.append('{} {}'.format(description, idxstatus[field]))
    if idxstatus['phase'] == '1':
        formatted.append('Indexing this file: {}'.format(idxstatus['fn']))
    else:
        formatted.append('Not indexing files now.')

    return '\n'.join(formatted)

def recollstatus(recoll_dir):
    status = []
    if recollindex_running(os.path.join(recoll_dir, "index.pid")):
        status.append("recollindex is running")
        recollindex_start, then = running_time(os.path.join(recoll_dir, "xapiandb", "flintlock"))
        recollindex_elapsed_time = then - recollindex_start
        status.append(" recollindex has been running for {}".format(recollindex_elapsed_time))
        status.append(format_idxstatus(parse_idxstatus(os.path.join(recoll_dir, "idxstatus.txt"))))
    else:
        status.append("recollindex is not running")
        recollindex_last_started, then = since_last_run(os.path.join(recoll_dir, "idxstatus.txt"))
        time_since_last_index = then - recollindex_last_started
        status.append(" recollindex was last started on {}".format(recollindex_last_started.ctime()))
        status.append(" time since recollindex last started: {}".format(time_since_last_index))

    date_of_last_query, date_now = latest_query(os.path.join(recoll_dir, "history"))
    if date_of_last_query:
        duration_since_last_query = date_now - date_of_last_query

        status.append("recoll database last queried on: {}".format(date_of_last_query.ctime()))
        status.append(" which was {} ago.".format(duration_since_last_query))

    return '\n'.join(status)

def readable_directory(path):
    if not os.path.isdir(path):
        raise argparse.ArgumentTypeError('not an existing directory: {}'.format(path))
    if not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError('not a readable directory: {}'.format(path))
    return path

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Display status of recollindex.')
    parser.add_argument(
        '-d',
        '--recoll-dir',
        type=readable_directory,
        default=os.path.expanduser("~/.recoll"),
        help='Recoll directory'
    )
    args = parser.parse_args()

    try:
        if shutil.which("recoll") is None:
            logging.warning("Could not find 'recoll' executable. Is recoll installed?\n")
    except AttributeError:
        # shutil.which() is only in python 3.3 and later.
        pass

    print(recollstatus(args.recoll_dir))

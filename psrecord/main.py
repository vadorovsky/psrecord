# Copyright (c) 2013, Thomas P. Robitaille
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import (unicode_literals, division, print_function,
                        absolute_import)

import time
import argparse

children = []


def get_percent(process=None):
    import psutil
    if process is not None:
        return process.cpu_percent()
    return psutil.cpu_percent()


def get_memory(process):
    return process.memory_info()


def get_virtual_memory():
    import psutil
    return psutil.virtual_memory()


def all_children(pr):

    global children

    try:
        children_of_pr = pr.children(recursive=True)
    except Exception:  # pragma: no cover
        return children

    for child in children_of_pr:
        if child not in children:
            children.append(child)

    return children


def main():

    parser = argparse.ArgumentParser(
        description='Record CPU and memory usage for a process')

    parser.add_argument('--process', type=str,
                        help='the process id or command')

    parser.add_argument('--log', type=str,
                        help='output the statistics to a file')

    parser.add_argument('--plot', type=str,
                        help='output the statistics to a plot')

    parser.add_argument('--duration', type=float,
                        help='how long to record for (in seconds). If not '
                             'specified, the recording is continuous until '
                             'the job exits.')

    parser.add_argument('--interval', type=float,
                        help='how long to wait between each sample (in '
                             'seconds). By default the process is sampled '
                             'as often as possible.')

    parser.add_argument('--include-children',
                        help='include sub-processes in statistics (results '
                             'in a slower maximum sampling rate).',
                        action='store_true')

    # TODO(vadorovsky): Make this prettier / more well thought.
    parser.add_argument('--virtual-memory',
                        help='use virtual memory in plot',
                        action='store_true')

    # TODO(vadorovsky): Make this prettier / more well thought.
    parser.add_argument('--only-cpu',
                        help='only plot cpu usage',
                        action='store_true')

    parser.add_argument('--bump-cpu', type=float,
                        help='bump cpu usage by specified value')

    parser.add_argument('--bump-memory', type=int,
                        help='bump memory usage by specified value')

    args = parser.parse_args()

    pid = None
    if args.process is not None:
        # Attach to process
        try:
            pid = int(args.process)
            print("Attaching to process {0}".format(pid))
            sprocess = None
        except Exception:
            import subprocess
            command = args.process
            print("Starting up command '{0}' and attaching to process"
                  .format(command))
            sprocess = subprocess.Popen(command, shell=True)
            pid = sprocess.pid

    interval = None
    if args.interval is not None:
        interval = args.interval
    else:
        # Set a default interval for system-wide profiling. Gathering
        # system-wide CPU usage without intervals provides weird results (almost
        # always either 0.0 or 100.0).
        if args.process is None:
            interval = 0.1

    monitor(pid, logfile=args.log, plot=args.plot, duration=args.duration,
            interval=interval, include_children=args.include_children,
            virtual_memory=args.virtual_memory, only_cpu=args.only_cpu,
            bump_cpu=args.bump_cpu, bump_memory=args.bump_memory)

    if args.process is not None and sprocess is not None:
        sprocess.kill()


def monitor(pid=None, logfile=None, plot=None, duration=None, interval=None,
            include_children=False, virtual_memory=False, only_cpu=False,
            bump_cpu=None, bump_memory=None):

    # We import psutil here so that the module can be imported even if psutil
    # is not present (for example if accessing the version)
    import psutil

    pr = psutil.Process(pid) if pid is not None else None

    # Record start time
    start_time = time.time()

    if logfile:
        f = open(logfile, 'w')
        f.write("# {0:12s} {1:12s} {2:12s} {3:12s}\n".format(
            'Elapsed time'.center(12),
            'CPU (%)'.center(12),
            'Real (MB)'.center(12),
            'Virtual (MB)'.center(12))
        )

    log = {}
    log['times'] = []
    log['cpu'] = []
    log['mem_real'] = []
    log['mem_virtual'] = []

    try:

        # Start main event loop
        while True:

            # Find current time
            current_time = time.time()

            if pr is not None:
                try:
                    pr_status = pr.status()
                except TypeError:  # psutil < 2.0
                    pr_status = pr.status
                except psutil.NoSuchProcess:  # pragma: no cover
                    break

                # Check if process status indicates we should exit
                if pr_status in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
                    print("Process finished ({0:.2f} seconds)"
                          .format(current_time - start_time))
                    break

            # Check if we have reached the maximum time
            if duration is not None and current_time - start_time > duration:
                break

            # Get current CPU and memory
            current_cpu = None
            current_mem_real = None
            current_mem_virtual = None
            if pr is not None:
                try:
                    current_cpu = get_percent(pr)
                    current_mem = get_memory(pr)
                except Exception:
                    break
                current_mem_real = current_mem.rss / 1024. ** 2
                current_mem_virtual = current_mem.vms / 1024. ** 2
            else:
                try:
                    current_cpu = get_percent()
                    current_mem = get_virtual_memory()
                except Exception:
                    break
                current_mem_real = current_mem.active / 1024. ** 2
                current_mem_virtual = current_mem.used / 1024. ** 2

            # Bump CPU usage
            if bump_cpu is not None:
                current_cpu += bump_cpu

            # Bump memory usage
            if bump_memory is not None:
                current_mem_real += bump_memory
                current_mem_virtual += bump_memory

            # Get information for children
            if pr is not None and include_children:
                for child in all_children(pr):
                    try:
                        current_cpu += get_percent(child)
                        current_mem = get_memory(child)
                    except Exception:
                        continue
                    current_mem_real += current_mem.rss / 1024. ** 2
                    current_mem_virtual += current_mem.vms / 1024. ** 2

            if logfile:
                f.write("{0:12.3f} {1:12.3f} {2:12.3f} {3:12.3f}\n".format(
                    current_time - start_time,
                    current_cpu,
                    current_mem_real,
                    current_mem_virtual))
                f.flush()

            if interval is not None:
                time.sleep(interval)

            # If plotting, record the values
            if plot:
                log['times'].append(current_time - start_time)
                log['cpu'].append(current_cpu)
                log['mem_real'].append(current_mem_real)
                log['mem_virtual'].append(current_mem_virtual)

    except KeyboardInterrupt:  # pragma: no cover
        pass

    if logfile:
        f.close()

    if plot:

        # Use non-interactive backend, to enable operation on headless machines
        import matplotlib.pyplot as plt
        with plt.rc_context({'backend': 'Agg'}):

            fig = plt.figure()
            ax = fig.add_subplot(1, 1, 1)

            ax.plot(log['times'], log['cpu'], '-', lw=1, color='r')

            ax.set_ylabel('CPU (%)', color='r')
            ax.set_xlabel('time (s)')
            ax.set_ylim(0., max(log['cpu']) * 1.2)

            if not only_cpu:
                ax2 = ax.twinx()

                # TODO(vadorovsky): So far virtual memory makes more sense for
                # system-wide profiling, but that needs more investigation.
                if virtual_memory:
                    ax2.plot(log['times'], log['mem_virtual'], '-', lw=1, color='b')
                    ax2.set_ylim(0., max(log['mem_virtual']) * 1.2)

                    ax2.set_ylabel('Virtual Memory (MB)', color='b')
                else:
                    ax2.plot(log['times'], log['mem_real'], '-', lw=1, color='b')
                    ax2.set_ylim(0., max(log['mem_real']) * 1.2)

                    ax2.set_ylabel('Real Memory (MB)', color='b')

            ax.grid()

            fig.savefig(plot)

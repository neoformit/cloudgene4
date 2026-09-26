"""Boot a long-lived E2E stack for exploratory probing (T07b).

    E2E_ARTIFACTS=<dir> venv/bin/python -m e2e.exploratory.serve

Prints BASE_URL / HOME and stays up until SIGINT/SIGTERM.
"""
import signal
import sys
import time

from e2e import stack as stack_mod


def main():
    s = stack_mod.start_stack('explore')
    print('BASE_URL=%s' % s.base_url, flush=True)
    print('HOME=%s' % s.home, flush=True)
    print('WORKER=%s' % s.worker_available, flush=True)
    stop = []
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    signal.signal(signal.SIGINT, lambda *a: stop.append(1))
    try:
        while not stop:
            time.sleep(0.5)
    finally:
        s.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())

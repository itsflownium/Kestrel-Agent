"""Launch the real CLI in a pseudo-terminal and resize it without restarting."""
import codecs
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time

import pyte


def test_real_cli_reflows_from_80_to_fullscreen_and_back(tmp_path):
    master, slave = pty.openpty()
    def size(columns, rows=54):
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, columns, 0, 0))
    size(80)
    env = {**os.environ, 'KESTREL_HOME': str(tmp_path/'data'), 'TERM': 'xterm-256color'}
    env.pop('COLUMNS', None)
    env.pop('LINES', None)
    process = subprocess.Popen([sys.executable, '-m', 'kestrel_agent.cli', '-C', str(tmp_path)],
        stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
    screen = pyte.Screen(80, 54)
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder('utf-8')('replace')
    def observe(predicate, timeout=12):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if select.select([master], [], [], .05)[0]:
                stream.feed(decoder.decode(os.read(master, 65536)))
            if predicate(screen.display):
                return
            if process.poll() is not None:
                break
        raise AssertionError('\n'.join(screen.display))
    try:
        observe(lambda rows: any('YOUR NEXT TASK' in row for row in rows) and any('SKILL SHELF' in row for row in rows))
        size(207)
        screen.resize(lines=54, columns=207)
        os.kill(process.pid, signal.SIGWINCH)
        observe(lambda rows: any('─'*190 in row for row in rows))
        assert any('SKILL SHELF' in row[90:] for row in screen.display)
        size(60, 24)
        screen.resize(lines=24, columns=60)
        os.kill(process.pid, signal.SIGWINCH)
        observe(lambda rows: any('COMMAND DESK' in row for row in rows) and any('YOUR NEXT TASK' in row for row in rows) and not any('SKILL SHELF' in row for row in rows))
        os.write(master, b'\x03')
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        os.close(master)
        os.close(slave)

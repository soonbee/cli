import os
import subprocess

EDITOR = os.environ.get('EDITOR', 'vim')


def edit(f, syntax=None):
    """Open editor

    :param f: file name
    """
    cmd = [EDITOR]
    if syntax and EDITOR == 'vim':
        cmd.append('-c "set syntax={}"'.format(syntax))
    cmd.append(f)
    cmd = ' '.join(cmd)
    subprocess.call(cmd, shell=True)

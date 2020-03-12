import os

from ltcli import color


necessary_env = []
export_example = {
    'FBPATH': 'export FBPATH=$HOME/.flashbase',
    'LANG': 'export LANG=en_US.utf-8',
}

if 'FBPATH' not in os.environ:
    necessary_env.append('FBPATH')
if 'LANG' not in os.environ:
    necessary_env.append('LANG')

if necessary_env:
    msg = [
        'To start using ltcli, you should set env {}'.format(
            ', '.join(necessary_env)
        ),
        'ex)',
    ]
    for env in necessary_env:
        msg.append(export_example[env])
    print(color.red('\n'.join(msg)))
    exit(1)

os.environ['LC_ALL'] = os.environ['LANG']

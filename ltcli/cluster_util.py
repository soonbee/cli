import os

from ltcli.log import logger
from ltcli import config, utils


def validate_id(cluster_id):
    if not isinstance(cluster_id, int):
        return False
    if cluster_id < 1:
        return False
    return True


def get_cluster_list():
    base_directory = config.get_base_directory()
    buf = os.listdir(base_directory)
    buf = filter(lambda x: x.startswith('cluster_'), buf)
    buf = filter(lambda x: utils.is_number(str(x[8:])), buf)
    buf = list(map(lambda x: int(x[8:]), buf))
    cluster_list = []
    for cluster_id in buf:
        cluster_dir = 'cluster_{}'.format(cluster_id)
        cluster_path = os.path.join(base_directory, cluster_dir)
        if not os.path.isfile(os.path.join(cluster_path, '.deploy.state')):
            cluster_list.append(int(cluster_id))
    cluster_list.sort()
    return cluster_list


def convert_list_2_seq(ports):
    logger.debug('ports: {}'.format(ports))
    ports.sort()
    logger.debug('sorted ports: {}'.format(ports))
    ret = []
    s = ports[0]
    pre = ports[0] - 1
    for port in ports:
        if pre != port - 1:
            if s != pre:
                ret.append('$(seq {} {})'.format(s, pre))
            else:
                ret.append(s)
            s = port
        pre = port
    if s != pre:
        ret.append('$(seq {} {})'.format(s, pre))
    else:
        ret.append(s)
    logger.debug('converted: {}'.format(ret))
    return ret

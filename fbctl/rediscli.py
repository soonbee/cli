from __future__ import print_function

from terminaltables import AsciiTable

from fbctl import config
from fbctl import utils
from fbctl.center import Center
from fbctl.rediscli_util import RedisCliUtil
from fbctl.utils import TableReport
from fbctl.log import logger


class RedisCliInfo(object):
    def __init__(self):
        pass

    def all(self, host=None, port=None):
        """Command: cli info all"""
        RedisCliUtil.command(sub_cmd='info', host=host, port=port)

    def memory(self, host=None, port=None):
        """Command: cli info memory"""
        RedisCliUtil.command(sub_cmd='info memory', host=host, port=port)

    def eviction(self, host=None, port=None):
        """Command: cli info eviction"""
        RedisCliUtil.command(sub_cmd='info eviction', host=host, port=port)

    def keyspace(self, host=None, port=None):
        """Command: cli info keyspace"""
        RedisCliUtil.command(sub_cmd='info keyspace', host=host, port=port)

    def tablespace(self, host=None, port=None):
        """Command: cli info tablespace"""
        RedisCliUtil.command(sub_cmd='info tablespace', host=host, port=port)

    def replication(self, host=None, port=None):
        """Command: cli info replication"""
        RedisCliUtil.command('info replication', host=host, port=port)


class RedisCliCluster(object):
    def __init__(self):
        pass

    def info(self):
        """Command: cli cluster info"""
        RedisCliUtil.command('cluster info')

    def nodes(self):
        """Command: cli cluster nodes"""
        RedisCliUtil.command('cluster nodes')

    def slots(self):
        """Command: cli cluster slots"""
        def formatter(outs):
            lines = outs.splitlines()
            replicas = config.get_replicas()
            column_count = 2 + 2 * (replicas + 1)
            row_count = len(lines) / column_count
            header = [['start', 'end', 'm_ip', 'm_port']]
            remain = column_count - 4
            data = []
            for i in range(0, remain / 2):
                header[0].append('s_ip_%d' % i)
                header[0].append('s_port_%d' % i)
            for i in range(0, row_count):
                data.append(lines[i * column_count: column_count * (i + 1)])
            data.sort(key=lambda x: int(x[0]))
            table = AsciiTable(header + data)
            print(table.table)

        RedisCliUtil.command('cluster slots', formatter=formatter)


class RedisCliConfig(object):
    def __init__(self):
        pass

    def get(self, key, all=False, host=None, port=None):
        """Command: cli config get [key]

        :param key: redis config keyword
        :param all: If True, command to all nodes
        :param host: host
        :param port: port
        """
        if not isinstance(all, bool):
            logger.error("option '--all' can use only 'True' or 'False'")
            return
        sub_cmd = 'config get "{key}"'.format(key=key)
        if all:
            RedisCliUtil.command_all(
                sub_cmd=sub_cmd,
                formatter=utils.print_table)
        else:
            RedisCliUtil.command(
                sub_cmd=sub_cmd,
                host=host,
                port=port)

    def set(self, key, value, all=False, save=False, host=None, port=None):
        """Command: cli config set [key] [value]

        :param key: redis config keyword
        :param value: value
        :param save: If True, save value to config file
        :param all: If True, command to all nodes
        :param host: host
        :param port: port
        """
        if not isinstance(all, bool):
            logger.error("option '--all' can use only 'True' or 'False'")
            return
        if not isinstance(save, bool):
            logger.error("option '--save' can use only 'True' or 'False'")
            return
        tr = TableReport(['step', 'result'])
        sub_cmd = 'config set {key} {value}'.format(key=key, value=value)
        if all:
            RedisCliUtil.command_all(
                sub_cmd=sub_cmd, formatter=utils.print_table)
        else:
            RedisCliUtil.command(
                sub_cmd=sub_cmd,
                host=host,
                port=port)
        if save:
            RedisCliUtil.save_redis_template_config(key, value)
            center = Center()
            center.update_ip_port()
            success = center.check_hosts_connection()
            if not success:
                return
            center.configure_redis()
            center.sync_conf()
